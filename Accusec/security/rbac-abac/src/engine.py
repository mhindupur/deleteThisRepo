"""Deterministic RBAC/ABAC over Principal + Operation + Entity type + Scope + Conditions."""

from __future__ import annotations

from dataclasses import dataclass

from accusec.shared.domain.models import (
    AuthzKind,
    Entity,
    OperationalRequest,
    OBLIGATION_APPROVAL,
    PolicyDecision,
    PolicyEffect,
    Principal,
    Scope,
)


@dataclass(frozen=True)
class PolicyRule:
    roles: tuple[str, ...]
    operations: tuple[str, ...]
    entity_types: tuple[str, ...]
    effect: PolicyEffect
    kind: AuthzKind
    region: str | None = None
    account_id: str | None = None


DEFAULT_RULES = (
    PolicyRule(
        roles=("cloud-operator", "cloud-viewer"),
        operations=("compute.instance.list", "compute.instance.read", "resource.read", "storage.volume.read"),
        entity_types=("aws.ec2.instance", "aws.ec2.volume", "*"),
        effect=PolicyEffect.ALLOW,
        kind=AuthzKind.CONTEXT_ACCESS,
        region="us-east-1",
        account_id="123456789012",
    ),
    PolicyRule(
        roles=("desktop-administrator", "cloud-operator"),
        operations=("provider.connect", "provider.read", "inventory.sync"),
        entity_types=("*",),
        effect=PolicyEffect.ALLOW,
        kind=AuthzKind.CONTEXT_ACCESS,
    ),
    PolicyRule(
        roles=("cloud-operator",),
        operations=("compute.instance.list", "compute.instance.read", "resource.read", "inventory.sync", "storage.volume.read", "storage.volume.expand"),
        entity_types=("aws.ec2.instance", "aws.ec2.volume", "*"),
        effect=PolicyEffect.ALLOW,
        kind=AuthzKind.CONTEXT_ACCESS,
    ),
    PolicyRule(
        roles=("cloud-operator",),
        operations=("compute.instance.stop", "compute.instance.start"),
        entity_types=("aws.ec2.instance",),
        effect=PolicyEffect.ALLOW_WITH_APPROVAL,
        kind=AuthzKind.EXECUTION,
        region="us-east-1",
        account_id="123456789012",
    ),
    PolicyRule(
        roles=("cloud-operator",),
        operations=("compute.instance.stop", "compute.instance.start"),
        entity_types=("aws.ec2.instance",),
        effect=PolicyEffect.ALLOW_WITH_APPROVAL,
        kind=AuthzKind.EXECUTION,
    ),
    PolicyRule(
        roles=("cloud-operator",),
        operations=("compute.instance.stop", "compute.instance.start"),
        entity_types=("aws.ec2.instance",),
        effect=PolicyEffect.ALLOW_WITH_APPROVAL,
        kind=AuthzKind.CONTEXT_ACCESS,
        region="us-east-1",
        account_id="123456789012",
    ),
    PolicyRule(
        roles=("cloud-operator",),
        operations=("compute.instance.stop", "compute.instance.start"),
        entity_types=("aws.ec2.instance",),
        effect=PolicyEffect.ALLOW_WITH_APPROVAL,
        kind=AuthzKind.CONTEXT_ACCESS,
    ),
    PolicyRule(
        roles=("cloud-operator",),
        operations=("storage.volume.read", "storage.volume.expand"),
        entity_types=("aws.ec2.volume", "aws.ec2.instance", "*"),
        effect=PolicyEffect.ALLOW_WITH_APPROVAL,
        kind=AuthzKind.EXECUTION,
    ),
    PolicyRule(
        roles=("ai-engineer",),
        operations=("compute.instance.list", "compute.instance.read", "resource.read", "storage.volume.read"),
        entity_types=("aws.ec2.instance", "aws.ec2.volume", "*"),
        effect=PolicyEffect.ALLOW,
        kind=AuthzKind.CONTEXT_ACCESS,
    ),
    PolicyRule(
        roles=("ai-engineer",),
        operations=("compute.instance.stop", "compute.instance.start", "storage.volume.read", "storage.volume.expand"),
        entity_types=("aws.ec2.instance", "aws.ec2.volume", "*"),
        effect=PolicyEffect.ALLOW_WITH_APPROVAL,
        kind=AuthzKind.EXECUTION,
    ),
    PolicyRule(
        roles=("ai-engineer",),
        operations=("compute.instance.stop", "compute.instance.start"),
        entity_types=("aws.ec2.instance",),
        effect=PolicyEffect.ALLOW_WITH_APPROVAL,
        kind=AuthzKind.CONTEXT_ACCESS,
    ),
)


class PolicyEngine:
    def __init__(self, rules: tuple[PolicyRule, ...] = DEFAULT_RULES) -> None:
        self.rules = rules

    def evaluate(
        self,
        principal: Principal,
        operation_id: str,
        kind: AuthzKind,
        entity: Entity | None = None,
        scopes: list[Scope] | None = None,
        entity_type: str | None = None,
    ) -> PolicyDecision:
        scopes = scopes or []
        region = None
        account = None
        etype = entity_type
        if entity:
            region = entity.region
            account = entity.account_id
            etype = entity.entity_type
        for scope in scopes:
            if scope.scope_type == "region":
                region = scope.scope_id
            if scope.scope_type == "account":
                account = scope.scope_id
        for rule in self.rules:
            if kind != rule.kind:
                continue
            if not set(principal.roles) & set(rule.roles):
                continue
            if operation_id not in rule.operations:
                continue
            if etype and etype not in rule.entity_types and "*" not in rule.entity_types:
                continue
            if rule.region and region and rule.region.lower() != region.lower():
                continue
            if rule.account_id and account and rule.account_id != account:
                continue
            return PolicyDecision(
                kind=kind,
                effect=rule.effect,
                principal_id=principal.principal_id,
                operation_id=operation_id,
                entity_type=etype,
                scope_ids=[s.scope_id for s in scopes],
                obligations=[OBLIGATION_APPROVAL] if rule.effect == PolicyEffect.ALLOW_WITH_APPROVAL else [],
                reason=f"matched {rule.effect.value} for roles={principal.roles}",
            )
        return PolicyDecision(
            kind=kind,
            effect=PolicyEffect.DENY,
            principal_id=principal.principal_id,
            operation_id=operation_id,
            entity_type=etype,
            scope_ids=[s.scope_id for s in scopes],
            reason="no matching policy rule",
        )

    def filter_entities(
        self,
        principal: Principal,
        operation_id: str,
        entities: list[Entity],
        scopes: list[Scope],
        kind: AuthzKind = AuthzKind.CONTEXT_ACCESS,
    ) -> tuple[list[Entity], PolicyDecision]:
        allowed: list[Entity] = []
        last = self.evaluate(
            principal, operation_id, kind, scopes=scopes, entity_type="aws.ec2.instance"
        )
        for entity in entities:
            decision = self.evaluate(principal, operation_id, kind, entity=entity, scopes=scopes)
            last = decision
            if decision.effect != PolicyEffect.DENY:
                allowed.append(entity)
        if allowed and last.effect == PolicyEffect.DENY:
            last = PolicyDecision(
                kind=kind,
                effect=PolicyEffect.ALLOW,
                principal_id=principal.principal_id,
                operation_id=operation_id,
                reason="subset of entities authorized",
            )
        return allowed, last
