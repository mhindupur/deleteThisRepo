"""Inventory collector — no vendor SDKs. Calls MCP tools, upserts observations."""

from __future__ import annotations

from collections import Counter

from accusec.shared.domain.models import (
    AuditEvent,
    AuthzKind,
    PolicyEffect,
    Principal,
    ProviderConnection,
    Scope,
    SyncRun,
    TopologyEdge,
    utcnow,
)


class InventoryCollector:
    def __init__(self, *, harness, entities, topology, control_plane, authz, audit) -> None:
        self.harness = harness
        self.entities = entities
        self.topology = topology
        self.control_plane = control_plane
        self.authz = authz
        self.audit = audit

    def sync(
        self,
        connection: ProviderConnection,
        *,
        region: str,
        principal: Principal,
        mode: str = "full",
    ) -> SyncRun:
        if region.lower() not in {r.lower() for r in connection.regions}:
            allowed = ", ".join(connection.regions) or "(none)"
            raise ValueError(
                f"region {region} is not allowlisted on connection {connection.connection_id} "
                f"(allowed: {allowed}). Add it with: accusec provider allow-region --region {region}"
            )
        scopes = [
            Scope(scope_type="account", scope_id=connection.account_id),
            Scope(scope_type="region", scope_id=region),
        ]
        decision = self.authz.engine.evaluate(
            principal,
            "inventory.sync",
            AuthzKind.CONTEXT_ACCESS,
            scopes=scopes,
            entity_type="*",
        )
        if decision.effect == PolicyEffect.DENY:
            raise PermissionError(decision.reason)

        run = SyncRun(
            connection_id=connection.connection_id,
            provider=connection.provider,
            account_id=connection.account_id,
            region=region,
            mode=mode,
        )
        self.control_plane.save_sync(run)
        self.audit.record(
            AuditEvent(
                event_type="inventory.sync.started",
                tenant_id=connection.tenant_id,
                principal_id=principal.principal_id,
                operation_id="inventory.sync",
                payload={
                    "connection_id": connection.connection_id,
                    "region": region,
                    "secret_ref": connection.secret_ref,
                },
            )
        )
        try:
            self._run(connection, region, run)
            run.status = "succeeded" if not run.skipped else "partial"
        except Exception as exc:  # noqa: BLE001 — record vendor/collector failure on the run
            run.status = "failed"
            run.error = exc.__class__.__name__
            raise
        finally:
            run.finished_at = utcnow()
            self.control_plane.save_sync(run)
            connection.last_sync_at = run.finished_at
            if run.status == "failed":
                connection.last_error = run.error
            else:
                connection.last_error = None
            self.control_plane.upsert_connection(connection)
            self.audit.record(
                AuditEvent(
                    event_type="inventory.sync.finished",
                    tenant_id=connection.tenant_id,
                    principal_id=principal.principal_id,
                    operation_id="inventory.sync",
                    payload={
                        "sync_id": run.sync_id,
                        "status": run.status,
                        "upserted": run.upserted,
                        "missing": run.missing,
                    },
                )
            )
        return run

    def _run(self, connection: ProviderConnection, region: str, run: SyncRun) -> None:
        raw = self.harness.invoke(
            "aws.resourceexplorer.search",
            {"region": region, "query": "*"},
        )
        hits = raw["entities"] if isinstance(raw, dict) else raw
        skipped = list(raw.get("skipped") or []) if isinstance(raw, dict) else []
        hydrated = self.harness.invoke("aws.ec2.describe_instances", {"region": region})
        by_id = {}
        for entity in hits:
            entity.tenant_id = connection.tenant_id
            entity.workspace_id = connection.workspace_id
            entity.account_id = entity.account_id or connection.account_id
            entity.last_sync_id = run.sync_id
            by_id[entity.entity_id] = entity
        for entity in hydrated:
            entity.tenant_id = connection.tenant_id
            entity.workspace_id = connection.workspace_id
            entity.account_id = connection.account_id
            entity.last_sync_id = run.sync_id
            entity.source = "aws.api"
            by_id[entity.entity_id] = entity
            vpc_id = entity.configuration.get("vpc_id")
            if vpc_id:
                self.topology.add(
                    TopologyEdge(
                        source_entity_id=entity.entity_id,
                        relationship_type="IN_VPC",
                        target_entity_id=vpc_id,
                        tenant_id=entity.tenant_id,
                        workspace_id=entity.workspace_id,
                    )
                )
        for entity in by_id.values():
            self.entities.upsert(entity)
        counts = Counter(e.entity_type for e in by_id.values())
        depths = {e.entity_type: e.source for e in by_id.values()}
        for entity_type, count in sorted(counts.items()):
            depth = "hydrated" if depths.get(entity_type) == "aws.api" else "enumerated"
            sample = next(e for e in by_id.values() if e.entity_type == entity_type)
            provider_type = sample.configuration.get("provider_type") or entity_type
            self.control_plane.record_coverage(
                connection_id=connection.connection_id,
                entity_type=entity_type,
                provider_type=provider_type,
                region=region,
                depth=depth,
                resource_count=count,
            )
        missing = self.entities.mark_missing(
            provider="aws",
            account_id=connection.account_id,
            region=region,
            sync_id=run.sync_id,
            tenant_id=connection.tenant_id,
            workspace_id=connection.workspace_id,
        )
        run.upserted = len(by_id)
        run.missing = missing
        run.enumerated_types = sorted(counts)
        hydrated_types = set(counts)
        run.skipped = [
            item
            for item in skipped
            if item.split(":", 1)[0].strip() not in hydrated_types
        ]
