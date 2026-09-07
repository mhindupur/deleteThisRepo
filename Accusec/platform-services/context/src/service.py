"""12-step Context Service: authz at query time, memory first, optional AWS refresh, rank/reduce."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from accusec.memory.catalog.catalog import get_operation
from accusec.memory.entity.store import EntityStore
from accusec.memory.topology.store import TopologyStore
from accusec.platform_services.authorization.service import AuthorizationService
from accusec.shared.domain.models import (
    AuditEvent,
    ContextPackage,
    Entity,
    OperationalRequest,
    PolicyEffect,
    utcnow,
)

TOKEN_CAP = 10
LIST_MAX_AGE = timedelta(minutes=5)


class ContextService:
    def __init__(
        self,
        entities: EntityStore,
        topology: TopologyStore,
        authz: AuthorizationService,
        audit,
        harness=None,
    ) -> None:
        self.entities = entities
        self.topology = topology
        self.authz = authz
        self.audit = audit
        self.harness = harness

    def assemble(self, request: OperationalRequest, *, force_refresh: bool = False) -> ContextPackage:
        op = get_operation(request.operation_id)
        region = next((s.scope_id for s in request.scopes if s.scope_type == "region"), None)
        account = next((s.scope_id for s in request.scopes if s.scope_type == "account"), None)
        instance_type = request.conditions.get("instance_type")
        instance_id = request.conditions.get("instance_id")
        vpc_id = request.conditions.get("vpc_id")
        lifecycle_state = request.conditions.get("lifecycle_state")
        query = dict(
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            entity_type=op.entity_type if op.entity_type != "*" else "aws.ec2.instance",
            region=region,
            account_id=account,
            instance_type=instance_type,
            vpc_id=vpc_id,
            provider_entity_id=instance_id,
            lifecycle_state=lifecycle_state,
        )

        rows = self.entities.query(**query)
        stale = self._stale(rows)
        refreshed_from_aws = False
        refresh_error = None
        wants_refresh = bool(self.harness) and (force_refresh or stale or not rows)
        # Live DescribeInstances requires a region. List without a region reads memory as-is.
        if wants_refresh and not region and not force_refresh:
            wants_refresh = False
        if wants_refresh:
            try:
                aws_rows = self.harness.invoke(
                    "aws.ec2.describe_instances",
                    {
                        "region": region,
                        "instance_type": instance_type,
                        "instance_ids": [instance_id] if instance_id else None,
                    },
                )
                for entity in aws_rows:
                    self.entities.upsert(entity)
                rows = self.entities.query(**query)
                refreshed_from_aws = True
            except Exception as exc:  # noqa: BLE001 — reads must still return memory observations
                refresh_error = exc.__class__.__name__
                if not rows:
                    rows = self.entities.query(**query)

        allowed, decision = self.authz.context_access(request, rows)
        if decision.effect == PolicyEffect.DENY and not allowed:
            raise PermissionError(decision.reason)

        truncated = False
        if len(allowed) > TOKEN_CAP:
            allowed = allowed[:TOKEN_CAP]
            truncated = True

        ids = {e.entity_id for e in allowed}
        package = ContextPackage(
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            principal=request.principal,
            request=request,
            authorization={
                "context_access": decision.effect.value,
                "policy_decision_id": decision.policy_decision_id,
            },
            entities=allowed,
            topology=self.topology.for_entities(ids),
            freshness={
                "max_age_seconds": LIST_MAX_AGE.total_seconds(),
                "refreshed_from_aws": refreshed_from_aws,
                "entity_count": len(allowed),
                "stale": stale,
                "refresh_error": refresh_error,
            },
            provenance={
                "memory": "entity-sql",
                "sources": sorted({e.source for e in allowed}),
            },
            truncated=truncated,
        )
        self.audit.record(
            AuditEvent(
                event_type="context.assembled",
                tenant_id=request.tenant_id,
                principal_id=request.principal.principal_id,
                operation_id=request.operation_id,
                correlation_id=request.correlation_id,
                policy_decision_id=decision.policy_decision_id,
                context_id=package.context_id,
                payload={
                    "entity_count": len(allowed),
                    "truncated": truncated,
                    "refresh_error": refresh_error,
                },
            )
        )
        return package

    def _stale(self, rows: list[Entity]) -> bool:
        if not rows:
            return True
        now = utcnow()
        return any(now - self._observed_at(e) > LIST_MAX_AGE for e in rows)

    def _observed_at(self, entity: Entity) -> datetime:
        value = entity.last_observed_at
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
