from __future__ import annotations

import os

from accusec.agents.harness.harness import SkillHarness
from accusec.ai.gateway.gateway import AiGateway
from accusec.data.operational_db.control_plane import ControlPlaneStore
from accusec.integration.aws_connector.connector import AccountMismatchError, AwsConnector, fixture_inventory
from accusec.integration.aws_mcp.server import AwsMcpServer
from accusec.integration.collectors.inventory_sync import InventoryCollector
from accusec.memory.entity.store import EntityStore
from accusec.memory.topology.store import TopologyStore
from accusec.orchestration.hitl.service import HitlService
from accusec.orchestration.orchestrator.orchestrator import AgentOrchestrator
from accusec.orchestration.planner.planner import Planner
from accusec.orchestration.workflow.engine import WorkflowEngine
from accusec.platform_services.audit.log import AuditLog
from accusec.platform_services.authorization.service import AuthorizationService
from accusec.platform_services.context.service import ContextService
from accusec.platform_services.secrets.store import SecretsManager
from accusec.shared.domain.models import (
    AuditEvent,
    AuthzKind,
    PolicyEffect,
    Principal,
    ProviderConnection,
    Scope,
    TopologyEdge,
)


def merge_regions(*groups: list[str]) -> list[str]:
    seen: list[str] = []
    found: set[str] = set()
    for group in groups:
        for region in group:
            key = region.strip().lower()
            if not key or key in found:
                continue
            found.add(key)
            seen.append(region.strip())
    return seen


def default_mysql_database() -> str:
    from accusec.memory.entity.store import mysql_config

    return mysql_config()["database"]


def _use_fixtures(control: ControlPlaneStore, explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    env = os.environ.get("ACCUSEC_USE_FIXTURES")
    if env == "1":
        return True
    if env == "0":
        return False
    return control.active_aws() is None


class AccuSecRuntime:
    def __init__(self, orchestrator: AgentOrchestrator, **extras) -> None:
        self.orchestrator = orchestrator
        for key, value in extras.items():
            setattr(self, key, value)

    def __getattr__(self, name: str):
        return getattr(self.orchestrator, name)

    def bind_connection(self, conn: ProviderConnection) -> None:
        spec = self.secrets.resolve(conn.secret_ref)
        connector = AwsConnector(
            conn.secret_ref,
            secrets=self.secrets,
            fixture_mode=spec.auth_mode == "fixture",
            tenant_id=conn.tenant_id,
            workspace_id=conn.workspace_id,
            account_id=conn.account_id,
        )
        harness = SkillHarness(AwsMcpServer(connector))
        self.connector = connector
        self.orchestrator.harness = harness
        self.orchestrator.context.harness = harness
        self.collector = InventoryCollector(
            harness=harness,
            entities=self.entities,
            topology=self.orchestrator.context.topology,
            control_plane=self.control,
            authz=self.authz,
            audit=self.audit,
        )


def build_runtime(database: str | None = None, *, fixture_mode: bool | None = None) -> AccuSecRuntime:
    secrets = SecretsManager()
    control = ControlPlaneStore(database)
    entities = EntityStore(database)
    topology = TopologyStore()
    use_fixtures = _use_fixtures(control, fixture_mode)
    if use_fixtures:
        for entity in fixture_inventory():
            entity.source = "memory"
            entities.upsert(entity)
            vpc_id = entity.configuration.get("vpc_id")
            if vpc_id:
                topology.add(
                    TopologyEdge(
                        source_entity_id=entity.entity_id,
                        relationship_type="IN_VPC",
                        target_entity_id=vpc_id,
                        tenant_id=entity.tenant_id,
                        workspace_id=entity.workspace_id,
                    )
                )
    active = None if use_fixtures else control.active_aws()
    secret_ref = (
        active.secret_ref if active else secrets.reference("aws/local-fixture")
    )
    connector = AwsConnector(
        secret_ref,
        secrets=secrets,
        fixture_mode=use_fixtures or secret_ref.endswith("local-fixture"),
        tenant_id=active.tenant_id if active else "tenant-1",
        workspace_id=active.workspace_id if active else "aws-prod",
        account_id=active.account_id if active else None,
    )
    mcp = AwsMcpServer(connector)
    harness = SkillHarness(mcp)
    authz = AuthorizationService()
    audit = AuditLog()
    context = ContextService(entities, topology, authz, audit, harness=harness)
    planner = Planner(
        tenant_id=active.tenant_id if active else "tenant-1",
        workspace_id=active.workspace_id if active else "aws-prod",
        account_id=active.account_id if active else "123456789012",
    )
    orchestrator = AgentOrchestrator(
        planner=planner,
        context=context,
        authz=authz,
        harness=harness,
        hitl=HitlService(),
        workflow=WorkflowEngine(),
        audit=audit,
        gateway=AiGateway(),
        entities=entities,
    )
    collector = InventoryCollector(
        harness=harness,
        entities=entities,
        topology=topology,
        control_plane=control,
        authz=authz,
        audit=audit,
    )
    return AccuSecRuntime(
        orchestrator,
        secrets=secrets,
        control=control,
        collector=collector,
        connector=connector,
        fixture_mode=use_fixtures,
        entities=entities,
        audit=audit,
        authz=authz,
    )


def connect_aws(
    runtime: AccuSecRuntime,
    *,
    account_id: str,
    regions: list[str],
    secret_ref: str,
    principal: Principal,
    tenant_id: str = "tenant-1",
    workspace_id: str = "aws-prod",
) -> ProviderConnection:
    scopes = [Scope(scope_type="account", scope_id=account_id)]
    decision = runtime.authz.engine.evaluate(
        principal,
        "provider.connect",
        AuthzKind.CONTEXT_ACCESS,
        scopes=scopes,
        entity_type="*",
    )
    if decision.effect == PolicyEffect.DENY:
        raise PermissionError(decision.reason)
    name = secret_ref.removeprefix("secret-ref:")
    ref = runtime.secrets.reference(name)
    spec = runtime.secrets.resolve(ref)
    existing = runtime.control.find_connection(
        provider="aws", account_id=account_id, workspace_id=workspace_id
    )
    conn = existing or ProviderConnection(
        provider="aws",
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        account_id=account_id,
        regions=regions,
        secret_ref=ref,
        status="pending_verify",
        created_by=principal.principal_id,
    )
    conn.regions = merge_regions(conn.regions if existing else [], regions)
    conn.secret_ref = ref
    conn.status = "pending_verify"
    conn.last_error = None
    runtime.control.upsert_connection(conn)
    connector = AwsConnector(
        ref,
        secrets=runtime.secrets,
        fixture_mode=spec.auth_mode == "fixture",
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        account_id=account_id,
    )
    try:
        ident = connector.verify_account(account_id)
    except AccountMismatchError as exc:
        conn.status = "error"
        conn.last_error = str(exc)
        runtime.control.upsert_connection(conn)
        raise
    except Exception as exc:
        conn.status = "error"
        conn.last_error = exc.__class__.__name__
        runtime.control.upsert_connection(conn)
        raise
    conn.status = "active"
    conn.caller_arn = ident.get("Arn")
    runtime.control.upsert_connection(conn)
    runtime.audit.record(
        AuditEvent(
            event_type="provider.connected",
            tenant_id=tenant_id,
            principal_id=principal.principal_id,
            operation_id="provider.connect",
            payload={
                "connection_id": conn.connection_id,
                "provider": "aws",
                "account_id": account_id,
                "regions": conn.regions,
                "secret_ref": ref,
                "auth_mode": spec.public_view()["auth_mode"],
                "caller_arn": conn.caller_arn,
            },
        )
    )
    return conn


def allow_connection_regions(
    runtime: AccuSecRuntime,
    *,
    regions: list[str],
    principal: Principal,
    connection_id: str | None = None,
) -> ProviderConnection:
    conn = (
        runtime.control.get_connection(connection_id)
        if connection_id
        else runtime.control.active_aws()
    )
    if conn is None:
        raise ValueError("No AWS connection. Run: accusec provider connect aws ...")
    decision = runtime.authz.engine.evaluate(
        principal,
        "provider.connect",
        AuthzKind.CONTEXT_ACCESS,
        scopes=[Scope(scope_type="account", scope_id=conn.account_id)],
        entity_type="*",
    )
    if decision.effect == PolicyEffect.DENY:
        raise PermissionError(decision.reason)
    conn.regions = merge_regions(conn.regions, regions)
    runtime.control.upsert_connection(conn)
    runtime.audit.record(
        AuditEvent(
            event_type="provider.regions.updated",
            tenant_id=conn.tenant_id,
            principal_id=principal.principal_id,
            operation_id="provider.connect",
            payload={
                "connection_id": conn.connection_id,
                "regions": conn.regions,
            },
        )
    )
    return conn


ALICE = Principal(principal_id="alice", display_name="Alice", roles=["cloud-operator"])
VIEWER = Principal(principal_id="bob", display_name="Bob", roles=["cloud-viewer"])
