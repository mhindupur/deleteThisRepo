"""Intent → operation. Clarification comes from the catalog, not HITL."""

from __future__ import annotations

import re

from accusec.memory.catalog.catalog import get_operation
from accusec.shared.domain.models import (
    Clarification,
    Entity,
    OperationalRequest,
    Plan,
    Principal,
    Scope,
)

TENANT = "tenant-1"
WORKSPACE = "aws-prod"
ACCOUNT = "123456789012"

# Deterministic list-filter synonyms. Not embeddings / LLM.
_LIFECYCLE_PATTERNS = (
    ("stopping", r"\bstopping\b|\bshutting[- ]down\b"),
    ("terminated", r"\bterminated\b"),
    ("pending", r"\bpending\b"),
    ("running", r"\b(?:running|started|online)\b"),
    ("stopped", r"\bstopped\b|\bshutdown\b|\bhalted\b|\bpowered[- ]off\b|\bin\s+stop(?:ped)?\s+state\b|\bstop\s+state\b"),
)


class Planner:
    def __init__(
        self,
        *,
        tenant_id: str = TENANT,
        workspace_id: str = WORKSPACE,
        account_id: str | None = ACCOUNT,
    ) -> None:
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.account_id = account_id

    def parse(self, intent: str, principal: Principal) -> OperationalRequest:
        text = intent.lower()
        region = _region(text)
        scopes: list[Scope] = []
        if self.account_id:
            scopes.append(Scope(scope_type="account", scope_id=self.account_id))
        if region:
            scopes.append(Scope(scope_type="region", scope_id=region))
        conditions: dict = {}
        type_match = re.search(r"(t2\.\w+|t3\.\w+|m5\.\w+|t3a\.\w+)", text)
        if type_match:
            conditions["instance_type"] = type_match.group(1)
        id_match = re.search(r"i-[a-z0-9]+", text)
        if id_match:
            conditions["instance_id"] = id_match.group(0)

        wants_list = bool(re.search(r"\b(list|show|find)\b", text))
        wants_stop = bool(re.search(r"\bstop\b", text)) and not wants_list
        lifecycle = _lifecycle_state(text, list_intent=wants_list or "t2." in text or "t3." in text)
        if lifecycle:
            conditions["lifecycle_state"] = lifecycle

        if wants_stop:
            operation_id = "compute.instance.stop"
            conditions.pop("lifecycle_state", None)
        elif wants_list or "t2." in text or "t3." in text:
            operation_id = "compute.instance.list"
        else:
            operation_id = "compute.instance.read"

        return OperationalRequest(
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            principal=principal,
            intent=intent,
            operation_id=operation_id,
            target_entity_type=get_operation(operation_id).entity_type,
            scopes=scopes,
            conditions=conditions,
            requested_outcome=intent,
        )

    def missing_slots(self, request: OperationalRequest) -> list[str]:
        op = get_operation(request.operation_id)
        missing = []
        for slot in op.required_slots:
            if slot == "region" and not any(s.scope_type == "region" for s in request.scopes):
                missing.append(slot)
            elif slot == "instance_id" and not request.conditions.get("instance_id") and not request.target_entity_ids:
                missing.append(slot)
        return missing

    def clarify(self, request: OperationalRequest, candidates: list[Entity]) -> Clarification:
        missing = self.missing_slots(request)
        questions = []
        if "instance_id" in missing:
            questions.append("Which instance_id should be stopped? Provide instance_id, name, type, or VPC.")
        if "region" in missing:
            questions.append("Which region/account scope should this run in?")
        return Clarification(missing_slots=missing, questions=questions, candidates=candidates)

    def plan(self, request: OperationalRequest, entity_ids: list[str], context_id: str, approval_required: bool) -> Plan:
        op = get_operation(request.operation_id)
        return Plan(
            operation_id=request.operation_id,
            target_entity_ids=entity_ids,
            context_id=context_id,
            risk_level=op.risk_level,
            approval_required=approval_required or op.approval_default,
            steps=[{"tool": tool} for tool in op.required_tools],
            expected_postconditions=op.expected_postconditions,
        )


def _lifecycle_state(text: str, *, list_intent: bool) -> str | None:
    for state, pattern in _LIFECYCLE_PATTERNS:
        if re.search(pattern, text):
            return state
    if list_intent and re.search(r"\bstop\b", text):
        return "stopped"
    return None


def _region(text: str) -> str | None:
    match = re.search(r"us[- ][a-z]+-\d", text.lower())
    if not match:
        match = re.search(r"(ap|eu|sa|ca|af|me)[- ][a-z]+-\d", text.lower())
    if not match:
        return None
    return match.group(0).replace(" ", "-")
