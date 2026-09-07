"""Canonical AccuSec domain types (Canon 3 semantic model)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ALLOW_WITH_APPROVAL = "allow_with_approval"


class AuthzKind(str, Enum):
    CONTEXT_ACCESS = "context_access"
    EXECUTION = "execution"


class TaskState(str, Enum):
    CREATED = "created"
    AWAITING_CONTEXT = "awaiting_context"
    PLANNING = "planning"
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    AWAITING_APPROVAL = "awaiting_approval"
    READY = "ready"
    RUNNING = "running"
    VALIDATING = "validating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    READ = "read"
    LOW = "low"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


class Principal(BaseModel):
    principal_id: str
    display_name: str
    roles: list[str] = Field(default_factory=list)


class Scope(BaseModel):
    """Authorization and retrieval boundary (not the same as Entity)."""

    scope_type: str
    scope_id: str
    attributes: dict[str, str] = Field(default_factory=dict)

    def matches_entity(self, entity: Entity) -> bool:
        attrs = entity.configuration | {
            "account_id": entity.account_id or "",
            "region": entity.region or "",
            "vpc_id": entity.configuration.get("vpc_id", ""),
        }
        if self.scope_type == "region":
            return attrs.get("region", "").lower() == self.scope_id.lower()
        if self.scope_type == "account":
            return attrs.get("account_id") == self.scope_id
        if self.scope_type == "vpc":
            return attrs.get("vpc_id") == self.scope_id
        if self.scope_type == "workspace":
            return entity.workspace_id == self.scope_id
        if self.scope_type == "tenant":
            return entity.tenant_id == self.scope_id
        return self.scope_id in {entity.entity_id, entity.provider_entity_id}


class Entity(BaseModel):
    entity_id: str
    provider_entity_id: str
    entity_type: str
    provider: str
    tenant_id: str
    workspace_id: str
    display_name: str
    account_id: str | None = None
    region: str | None = None
    lifecycle_state: str = "unknown"
    configuration: dict[str, Any] = Field(default_factory=dict)
    last_observed_at: datetime = Field(default_factory=utcnow)
    source: str = "memory"
    freshness_status: str = "fresh"
    last_sync_id: str | None = None

    @staticmethod
    def make_id(provider: str, entity_type: str, tenant: str, account: str, region: str, native_id: str) -> str:
        short_type = entity_type.split(".")[-1]
        return f"accusec:{provider}:{short_type}:{tenant}:{account}:{region}:{native_id}"


class TopologyEdge(BaseModel):
    relationship_id: str = Field(default_factory=lambda: new_id("rel"))
    source_entity_id: str
    relationship_type: str
    target_entity_id: str
    tenant_id: str
    workspace_id: str


class Operation(BaseModel):
    operation_id: str
    entity_type: str
    read_or_write: str
    risk_level: RiskLevel
    destructive: bool = False
    idempotent: bool = True
    approval_default: bool = False
    required_slots: list[str] = Field(default_factory=list)
    required_context_types: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    expected_postconditions: list[str] = Field(default_factory=list)


class OperationalRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: new_id("req"))
    tenant_id: str
    workspace_id: str
    principal: Principal
    intent: str
    operation_id: str
    target_entity_ids: list[str] = Field(default_factory=list)
    target_entity_type: str | None = None
    scopes: list[Scope] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    requested_outcome: str | None = None
    correlation_id: str = Field(default_factory=lambda: new_id("corr"))


class PolicyDecision(BaseModel):
    policy_decision_id: str = Field(default_factory=lambda: new_id("decision"))
    kind: AuthzKind
    effect: PolicyEffect
    principal_id: str
    operation_id: str
    entity_type: str | None = None
    scope_ids: list[str] = Field(default_factory=list)
    reason: str
    decided_at: datetime = Field(default_factory=utcnow)


class ContextPackage(BaseModel):
    context_id: str = Field(default_factory=lambda: new_id("ctx"))
    tenant_id: str
    workspace_id: str
    principal: Principal
    request: OperationalRequest
    authorization: dict[str, Any] = Field(default_factory=dict)
    entities: list[Entity] = Field(default_factory=list)
    topology: list[TopologyEdge] = Field(default_factory=list)
    ownership: list[dict[str, Any]] = Field(default_factory=list)
    applicable_policies: list[str] = Field(default_factory=list)
    learned_memory: list[dict[str, Any]] = Field(default_factory=list)
    freshness: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    redactions: list[str] = Field(default_factory=list)
    truncated: bool = False
    generated_at: datetime = Field(default_factory=utcnow)


class Clarification(BaseModel):
    missing_slots: list[str]
    questions: list[str]
    candidates: list[Entity] = Field(default_factory=list)


class Plan(BaseModel):
    plan_id: str = Field(default_factory=lambda: new_id("plan"))
    version: int = 1
    operation_id: str
    target_entity_ids: list[str] = Field(default_factory=list)
    context_id: str | None = None
    risk_level: RiskLevel = RiskLevel.READ
    approval_required: bool = False
    steps: list[dict[str, Any]] = Field(default_factory=list)
    expected_postconditions: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    event_type: str
    tenant_id: str
    principal_id: str
    operation_id: str | None = None
    task_id: str | None = None
    correlation_id: str | None = None
    policy_decision_id: str | None = None
    context_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utcnow)


class SecretSpec(BaseModel):
    """Credential handle for a connector. Never put values in prompts or audit."""

    auth_mode: str
    profile: str | None = None
    role_arn: str | None = None
    external_id: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None

    def public_view(self) -> dict[str, Any]:
        return {
            "auth_mode": self.auth_mode,
            "profile": self.profile,
            "role_arn": self.role_arn,
            "external_id": self.external_id,
            "has_access_key": bool(self.access_key_id),
        }


class ProviderConnection(BaseModel):
    connection_id: str = Field(default_factory=lambda: new_id("conn"))
    provider: str
    tenant_id: str
    workspace_id: str
    account_id: str
    regions: list[str] = Field(default_factory=list)
    secret_ref: str
    status: str = "pending_verify"
    last_sync_at: datetime | None = None
    last_error: str | None = None
    created_by: str
    caller_arn: str | None = None


class SyncRun(BaseModel):
    sync_id: str = Field(default_factory=lambda: new_id("sync"))
    connection_id: str
    provider: str
    account_id: str
    region: str
    mode: str = "full"
    status: str = "running"
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    upserted: int = 0
    missing: int = 0
    enumerated_types: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    error: str | None = None


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: new_id("task"))
    state: TaskState = TaskState.CREATED
    request: OperationalRequest
    context_id: str | None = None
    plan: Plan | None = None
    clarification: Clarification | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    used_llm: bool = False
