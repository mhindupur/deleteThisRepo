"""HTTP API + desktop web console. Chat is a client — tasks stay in the orchestrator."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from accusec.orchestration.orchestrator.runtime import (
    ALICE,
    PRINCIPALS,
    allow_connection_regions,
    build_runtime,
    connect_aws,
    resolve_principal,
)
from accusec.shared.domain.models import OperationalRequest, Scope, SecretSpec, Task

CONSOLE_DIR = Path(__file__).resolve().parents[2] / "web-console" / "src"
IAM_ROLE_ARN = re.compile(r"^arn:aws[-a-z]*:iam::(\d{12}):role/.+", re.IGNORECASE)
NO_STORE = {"Cache-Control": "no-store"}


class ConsoleStatic(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def account_id_from_role_arn(role_arn: str) -> str:
    match = IAM_ROLE_ARN.match(role_arn.strip())
    if not match:
        raise ValueError("IAM role ARN must look like arn:aws:iam::123456789012:role/RoleName")
    return match.group(1)


class ConnectBody(BaseModel):
    role_arn: str
    regions: str
    account_id: str | None = None
    profile: str = "default"
    external_id: str = "accusec-local"
    secret_name: str = "aws/operator"


class AskBody(BaseModel):
    intent: str
    principal_id: str | None = None
    endpoint_identity_id: str | None = None


class ApproveBody(BaseModel):
    approval_id: str
    approved: bool = True
    principal_id: str | None = None


class ClarifyBody(BaseModel):
    instance_id: str


class SyncBody(BaseModel):
    region: str
    connection_id: str | None = None


def _principal(principal_id: str | None):
    try:
        return resolve_principal(principal_id)
    except KeyError as exc:
        raise HTTPException(400, f"unknown principal {principal_id}") from exc


def _task_payload(task: Task) -> dict:
    return {
        "task_id": task.task_id,
        "state": task.state.value,
        "operation": task.request.operation_id,
        "intent": task.request.intent,
        "used_llm": task.used_llm,
        "context_id": task.context_id,
        "agent_id": task.request.agent_id,
        "project_id": task.request.project_id,
        "datacenter_id": task.request.datacenter_id,
        "endpoint_identity_id": task.request.endpoint_identity_id,
        "result": task.result,
    }


def _instance_row(entity) -> dict:
    return {
        "instance_id": entity.provider_entity_id,
        "name": entity.display_name,
        "instance_type": entity.configuration.get("instance_type"),
        "region": entity.region,
        "vpc_id": entity.configuration.get("vpc_id"),
        "state": entity.lifecycle_state,
        "source": entity.source,
        "last_observed_at": entity.last_observed_at,
    }


def create_app(runtime=None) -> FastAPI:
    app = FastAPI(title="AccuSec Web Console", version="0.1.0")
    app.state.runtime = runtime

    def rt():
        if app.state.runtime is None:
            app.state.runtime = build_runtime()
        return app.state.runtime

    @app.get("/api/health")
    def health():
        runtime = rt()
        conn = runtime.control.active_aws()
        org = runtime.control.org_snapshot()
        identities = runtime.control.list_identities(tenant_id=org["tenant_id"])
        return {
            "ok": True,
            "edition": "desktop",
            "tenant_id": org["tenant_id"],
            "project_id": org["project_id"],
            "datacenter_id": org["datacenter_id"],
            "workspace_id": org["workspace_id"],
            "agent_id": "agent-aws-pack",
            "principal_id": ALICE.principal_id,
            "principal_name": ALICE.display_name,
            "roles": list(ALICE.roles),
            "principals": [
                {
                    "principal_id": item.principal_id,
                    "display_name": item.display_name,
                    "roles": list(item.roles),
                    "principal_type": item.principal_type,
                }
                for item in PRINCIPALS.values()
            ],
            "identities": [
                {
                    "endpoint_identity_id": item.endpoint_identity_id,
                    "identity_type": item.identity_type,
                    "display_name": item.display_name,
                    "status": item.status,
                    "endpoint_id": item.endpoint_id,
                    "secret_ref": item.secret_ref,
                }
                for item in identities
            ],
            "org": org,
            "connected": bool(conn and conn.status == "active"),
        }

    @app.get("/api/connection")
    def connection():
        runtime = rt()
        conn = runtime.control.active_aws()
        if not conn:
            return {"status": "disconnected"}
        spec = runtime.secrets.resolve(conn.secret_ref)
        return {
            "connection_id": conn.connection_id,
            "provider": conn.provider,
            "account_id": conn.account_id,
            "regions": conn.regions,
            "secret_ref": conn.secret_ref,
            "status": conn.status,
            "last_sync_at": conn.last_sync_at,
            "last_error": conn.last_error,
            "endpoint_id": conn.endpoint_id,
            "project_id": conn.project_id,
            "datacenter_id": conn.datacenter_id,
            "auth": spec.public_view(),
            "coverage": runtime.control.coverage_for(conn.connection_id),
        }

    @app.post("/api/connection")
    def connect(body: ConnectBody):
        runtime = rt()
        regions = [item.strip() for item in body.regions.split(",") if item.strip()]
        if not regions:
            raise HTTPException(400, "at least one region is required")
        try:
            account_id = account_id_from_role_arn(body.role_arn)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if body.account_id and body.account_id != account_id:
            raise HTTPException(400, f"account {body.account_id} does not match role ARN account {account_id}")
        runtime.secrets.put(
            body.secret_name,
            SecretSpec(
                auth_mode="assume_role",
                role_arn=body.role_arn,
                profile=body.profile,
                external_id=body.external_id.strip() or None,
            ),
        )
        try:
            conn = connect_aws(
                runtime,
                account_id=account_id,
                regions=regions,
                secret_ref=body.secret_name,
                principal=ALICE,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc
        runtime.bind_connection(conn)
        return {
            "connection_id": conn.connection_id,
            "status": conn.status,
            "account_id": conn.account_id,
            "regions": conn.regions,
            "secret_ref": conn.secret_ref,
            "caller_arn": conn.caller_arn,
        }

    @app.post("/api/sync")
    def sync(body: SyncBody):
        runtime = rt()
        conn = (
            runtime.control.get_connection(body.connection_id)
            if body.connection_id
            else runtime.control.active_aws()
        )
        if conn is None:
            raise HTTPException(400, "No AWS connection. Register an IAM role first.")
        try:
            if body.region.lower() not in {region.lower() for region in conn.regions}:
                conn = allow_connection_regions(
                    runtime,
                    regions=[body.region],
                    principal=ALICE,
                    connection_id=conn.connection_id,
                )
            runtime.bind_connection(conn)
            run = runtime.collector.sync(conn, region=body.region, principal=ALICE)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc
        return {
            "sync_id": run.sync_id,
            "status": run.status,
            "region": run.region,
            "upserted": run.upserted,
            "missing": run.missing,
            "enumerated_types": run.enumerated_types,
            "skipped": run.skipped,
        }

    @app.get("/api/entities")
    def entities(region: str | None = None, instance_type: str | None = None, state: str | None = None):
        runtime = rt()
        conn = runtime.control.active_aws()
        tenant = conn.tenant_id if conn else "tenant-1"
        workspace = conn.workspace_id if conn else "aws-prod"
        account = conn.account_id if conn else None
        rows = runtime.entities.query(
            tenant_id=tenant,
            workspace_id=workspace,
            entity_type="aws.ec2.instance",
            region=region,
            account_id=account,
            instance_type=instance_type,
            lifecycle_state=state,
        )
        scopes: list[Scope] = []
        if account:
            scopes.append(Scope(scope_type="account", scope_id=account))
        if region:
            scopes.append(Scope(scope_type="region", scope_id=region))
        request = OperationalRequest(
            tenant_id=tenant,
            workspace_id=workspace,
            project_id=conn.project_id if conn else "project-0",
            datacenter_id=conn.datacenter_id if conn else "dc-aws",
            principal=ALICE,
            intent="list",
            operation_id="compute.instance.list",
            scopes=scopes,
            agent_id="agent-aws-pack",
        )
        allowed, decision = runtime.authz.context_access(request, rows)
        return {
            "source": "organizational_memory",
            "count": len(allowed),
            "policy": decision.effect.value,
            "instances": [_instance_row(entity) for entity in allowed],
        }

    @app.get("/api/org")
    def org():
        runtime = rt()
        snapshot = runtime.control.org_snapshot()
        snapshot["agent_id"] = "agent-aws-pack"
        snapshot["principals"] = [
            {
                "principal_id": item.principal_id,
                "display_name": item.display_name,
                "roles": list(item.roles),
                "principal_type": item.principal_type,
            }
            for item in PRINCIPALS.values()
        ]
        snapshot["identities"] = [
            {
                "endpoint_identity_id": item.endpoint_identity_id,
                "identity_type": item.identity_type,
                "display_name": item.display_name,
                "status": item.status,
                "endpoint_id": item.endpoint_id,
                "secret_ref": item.secret_ref,
            }
            for item in runtime.control.list_identities(tenant_id=snapshot["tenant_id"])
        ]
        return snapshot

    @app.get("/api/identities")
    def identities():
        runtime = rt()
        return {
            "identities": [
                {
                    "endpoint_identity_id": item.endpoint_identity_id,
                    "identity_type": item.identity_type,
                    "display_name": item.display_name,
                    "status": item.status,
                    "endpoint_id": item.endpoint_id,
                    "secret_ref": item.secret_ref,
                }
                for item in runtime.control.list_identities(tenant_id="tenant-1")
            ]
        }

    @app.post("/api/ask")
    def ask(body: AskBody):
        runtime = rt()
        principal = _principal(body.principal_id)
        return _task_payload(
            runtime.submit(body.intent, principal, endpoint_identity_id=body.endpoint_identity_id)
        )

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        runtime = rt()
        task = runtime.get_task(task_id)
        if task is None:
            raise HTTPException(404, "unknown task")
        return _task_payload(task)

    @app.post("/api/tasks/{task_id}/clarify")
    def clarify(task_id: str, body: ClarifyBody):
        runtime = rt()
        if runtime.get_task(task_id) is None:
            raise HTTPException(404, "unknown task")
        return _task_payload(runtime.apply_clarification(task_id, body.instance_id))

    @app.post("/api/tasks/{task_id}/approve")
    def approve(task_id: str, body: ApproveBody):
        runtime = rt()
        if runtime.get_task(task_id) is None:
            raise HTTPException(404, "unknown task")
        try:
            task = runtime.approve(
                task_id,
                body.approval_id,
                _principal(body.principal_id),
                approved=body.approved,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc
        return _task_payload(task)

    @app.get("/")
    def index():
        page = CONSOLE_DIR / "index.html"
        if not page.exists():
            raise HTTPException(500, f"web console missing at {page}")
        return FileResponse(page, headers=NO_STORE)

    if CONSOLE_DIR.exists():
        app.mount("/static", ConsoleStatic(directory=CONSOLE_DIR), name="static")
    return app


def main(argv: list[str] | None = None) -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="AccuSec desktop web console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8477)
    args = parser.parse_args(argv)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
