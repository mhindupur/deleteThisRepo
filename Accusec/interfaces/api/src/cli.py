"""Local task API / CLI. Chat is a client of this — not the system of record."""

from __future__ import annotations

import argparse
import json
import sys

from accusec.orchestration.orchestrator.runtime import ALICE, allow_connection_regions, build_runtime, connect_aws
from accusec.shared.domain.models import SecretSpec, Task


def _dump(task: Task) -> str:
    return json.dumps(
        {
            "task_id": task.task_id,
            "state": task.state.value,
            "operation": task.request.operation_id,
            "used_llm": task.used_llm,
            "context_id": task.context_id,
            "result": task.result,
        },
        indent=2,
        default=str,
    )


def _print(payload) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _secrets_cli(argv: list[str], db: str | None) -> None:
    parser = argparse.ArgumentParser(
        prog="accusec secrets",
        description="Register how AccuSec authenticates to a provider. Values stay in ~/.accusec/secrets.json, never in MySQL or prompts.",
    )
    sub = parser.add_subparsers(dest="action", required=True)
    put = sub.add_parser("put", help="Store a named secret reference (role ARN, profile, or lab keys)")
    put.add_argument("name", help="Name, e.g. aws/operator")
    put.add_argument(
        "--auth-mode",
        required=True,
        choices=["assume-role", "profile", "access-key"],
        help="assume-role is the developer default: AccuSecInventoryReader + your AWS CLI profile",
    )
    put.add_argument("--role-arn", help="arn:aws:iam::ACCOUNT:role/AccuSecInventoryReader")
    put.add_argument("--external-id", default="accusec-local")
    put.add_argument("--profile", help="AWS CLI profile allowed to assume the role (or used directly)")
    put.add_argument("--access-key-id")
    put.add_argument("--secret-access-key")
    sub.add_parser("list", help="List secret names and public fields (no key material)")
    args = parser.parse_args(argv)
    runtime = build_runtime(db)
    if args.action == "list":
        _print(runtime.secrets.list_public())
        return
    mode = {"assume-role": "assume_role", "profile": "profile", "access-key": "access_key"}[args.auth_mode]
    spec = SecretSpec(
        auth_mode=mode,
        profile=args.profile,
        role_arn=args.role_arn,
        external_id=args.external_id if mode == "assume_role" else None,
        access_key_id=args.access_key_id,
        secret_access_key=args.secret_access_key,
    )
    ref = runtime.secrets.put(args.name, spec)
    _print({"secret_ref": ref, **spec.public_view()})


def _provider_cli(argv: list[str], db: str | None) -> None:
    parser = argparse.ArgumentParser(
        prog="accusec provider",
        description="Connect a cloud account and sync inventory observations into MySQL.",
    )
    sub = parser.add_subparsers(dest="action", required=True)
    connect = sub.add_parser(
        "connect",
        help="Register AWS account + secret-ref, then STS-verify GetCallerIdentity",
    )
    connect.add_argument("provider", choices=["aws"])
    connect.add_argument("--account", required=True, help="12-digit AWS account id (must match STS)")
    connect.add_argument("--regions", required=True, help="Comma-separated allowlist, e.g. us-east-1,us-west-2")
    connect.add_argument("--secret-ref", required=True, help="Name from `accusec secrets put`, e.g. aws/operator")
    connect.add_argument("--tenant", default="tenant-1")
    connect.add_argument("--workspace", default="aws-prod")
    sync = sub.add_parser("sync", help="Pull entities for a region into the entities table")
    sync.add_argument("--connection", help="connection_id from connect; default: active AWS connection")
    sync.add_argument("--region", required=True)
    allow = sub.add_parser(
        "allow-region",
        help="Add a region to the connection allowlist without reconnecting",
    )
    allow.add_argument("--region", required=True)
    allow.add_argument("--connection", help="connection_id; default: active AWS connection")
    sub.add_parser("status", help="Show connections, last sync, and entity-type coverage")
    args = parser.parse_args(argv)
    runtime = build_runtime(db)
    if args.action == "connect":
        regions = [r.strip() for r in args.regions.split(",") if r.strip()]
        conn = connect_aws(
            runtime,
            account_id=args.account,
            regions=regions,
            secret_ref=args.secret_ref,
            principal=ALICE,
            tenant_id=args.tenant,
            workspace_id=args.workspace,
        )
        _print(
            {
                "connection_id": conn.connection_id,
                "provider": conn.provider,
                "account_id": conn.account_id,
                "regions": conn.regions,
                "secret_ref": conn.secret_ref,
                "status": conn.status,
                "caller_arn": conn.caller_arn,
                "role": "AccuSecInventoryReader (observe-only). See integration/connectors/hybrid-cloud/aws/iam/README.md",
            }
        )
        return
    if args.action == "status":
        rows = []
        for conn in runtime.control.list_connections():
            rows.append(
                {
                    "connection_id": conn.connection_id,
                    "provider": conn.provider,
                    "account_id": conn.account_id,
                    "regions": conn.regions,
                    "secret_ref": conn.secret_ref,
                    "status": conn.status,
                    "last_sync_at": conn.last_sync_at,
                    "last_error": conn.last_error,
                    "coverage": runtime.control.coverage_for(conn.connection_id),
                    "recent_syncs": [
                        {
                            "sync_id": s.sync_id,
                            "region": s.region,
                            "status": s.status,
                            "upserted": s.upserted,
                            "missing": s.missing,
                            "enumerated_types": s.enumerated_types,
                            "skipped": s.skipped,
                        }
                        for s in runtime.control.recent_syncs(conn.connection_id, 5)
                    ],
                }
            )
        _print(rows)
        return
    if args.action == "allow-region":
        try:
            conn = allow_connection_regions(
                runtime,
                regions=[args.region],
                principal=ALICE,
                connection_id=args.connection,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        _print(
            {
                "connection_id": conn.connection_id,
                "account_id": conn.account_id,
                "regions": conn.regions,
                "status": conn.status,
            }
        )
        return
    conn = (
        runtime.control.get_connection(args.connection)
        if args.connection
        else runtime.control.active_aws()
    )
    if conn is None:
        raise SystemExit(
            "No AWS connection. Run: accusec provider connect aws --account ... --regions ... --secret-ref ..."
        )
    runtime.bind_connection(conn)
    runtime.connector.verify_account(conn.account_id)
    try:
        run = runtime.collector.sync(conn, region=args.region, principal=ALICE)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _print(
        {
            "sync_id": run.sync_id,
            "status": run.status,
            "region": run.region,
            "upserted": run.upserted,
            "missing": run.missing,
            "enumerated_types": run.enumerated_types,
            "skipped": run.skipped,
            "error": run.error,
        }
    )


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    db = None
    if "--db" in argv:
        idx = argv.index("--db")
        db = argv[idx + 1]
        del argv[idx : idx + 2]
    if argv and argv[0] == "secrets":
        _secrets_cli(argv[1:], db)
        return
    if argv and argv[0] == "provider":
        _provider_cli(argv[1:], db)
        return
    parser = argparse.ArgumentParser(description="AccuSec local Hybrid Cloud / AWS slice")
    parser.add_argument("intent", nargs="*", help="natural language intent")
    parser.add_argument("--inspect-db", action="store_true", help="Print entity rows and exit")
    parser.add_argument("--approve", metavar="TASK_ID:APPROVAL_ID")
    parser.add_argument("--clarify", metavar="TASK_ID:INSTANCE_ID")
    args = parser.parse_args(argv)
    runtime = build_runtime(db)
    if args.inspect_db:
        print(f"database: mysql://127.0.0.1/{runtime.entities.database}")
        print(json.dumps(runtime.entities.inspect_rows(), indent=2, default=str))
        return
    if args.approve:
        print("HITL approval requires an in-process runtime; use pytest for the stop flow.")
        return
    if args.clarify:
        print("Clarification is demonstrated in tests; pass instance_id in the intent for CLI.")
        return
    intent = " ".join(args.intent) or "list out all t2.small in US-east-1"
    task = runtime.submit(intent, ALICE)
    print(_dump(task))


if __name__ == "__main__":
    main()
