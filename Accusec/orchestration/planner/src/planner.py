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
        project_id: str = "project-0",
        datacenter_id: str = "dc-aws",
        agent_id: str = "agent-aws-pack",
        endpoint_id: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.account_id = account_id
        self.project_id = project_id
        self.datacenter_id = datacenter_id
        self.agent_id = agent_id
        self.endpoint_id = endpoint_id

    def parse(self, intent: str, principal: Principal) -> OperationalRequest:
        text = intent.lower()
        region = _region(text)
        scopes: list[Scope] = []
        if self.account_id:
            scopes.append(Scope(scope_type="account", scope_id=self.account_id))
        scopes.append(Scope(scope_type="project", scope_id=self.project_id))
        scopes.append(Scope(scope_type="datacenter", scope_id=self.datacenter_id))
        if region:
            scopes.append(Scope(scope_type="region", scope_id=region))
        conditions: dict = {}
        type_match = re.search(r"(t2\.\w+|t3\.\w+|m5\.\w+|t3a\.\w+)", text)
        if type_match:
            conditions["instance_type"] = type_match.group(1)
        id_match = re.search(r"i-[a-z0-9]+", text)
        if id_match:
            conditions["instance_id"] = id_match.group(0)
        vol_match = re.search(r"vol-[a-z0-9]+", text)
        if vol_match:
            conditions["volume_id"] = vol_match.group(0)
        size_match = re.search(r"(?:to|into)\s+(\d+)\s*(?:gi?b)?", text)
        if size_match:
            conditions["size_gb"] = int(size_match.group(1))

        wants_list = bool(re.search(r"\b(list|show|find)\b", text))
        wants_stop = bool(re.search(r"\bstop\b", text)) and not wants_list
        wants_start = bool(re.search(r"\bstart\b", text)) and not wants_list and not wants_stop
        wants_expand = bool(
            re.search(r"\b(update|expand|resize|increase|modify|grow)\b", text)
        ) and ("size_gb" in conditions or bool(re.search(r"\b(volume|storage|ebs|disk)\b", text)))
        wants_volume = bool(
            re.search(r"\b(volume|volumes|ebs|storage|disk|disks)\b", text)
        ) and not wants_stop and not wants_expand
        lifecycle = _lifecycle_state(text, list_intent=wants_list or "t2." in text or "t3." in text)
        if lifecycle:
            conditions["lifecycle_state"] = lifecycle

        if wants_stop:
            operation_id = "compute.instance.stop"
            conditions.pop("lifecycle_state", None)
        elif wants_start:
            operation_id = "compute.instance.start"
            conditions.pop("lifecycle_state", None)
        elif wants_expand:
            operation_id = "storage.volume.expand"
            conditions.pop("lifecycle_state", None)
        elif wants_volume:
            operation_id = "storage.volume.read"
            conditions.pop("lifecycle_state", None)
        elif wants_list or "t2." in text or "t3." in text:
            operation_id = "compute.instance.list"
        else:
            operation_id = "compute.instance.read"

        return OperationalRequest(
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            datacenter_id=self.datacenter_id,
            principal=principal,
            intent=intent,
            operation_id=operation_id,
            target_entity_type=get_operation(operation_id).entity_type,
            scopes=scopes,
            conditions=conditions,
            requested_outcome=intent,
            endpoint_id=self.endpoint_id,
            agent_id=self.agent_id,
            human_initiator_id=principal.principal_id,
        )

    def missing_slots(self, request: OperationalRequest) -> list[str]:
        op = get_operation(request.operation_id)
        missing = []
        for slot in op.required_slots:
            if slot == "region" and not any(s.scope_type == "region" for s in request.scopes):
                missing.append(slot)
            elif slot == "instance_id" and not request.conditions.get("instance_id") and not request.target_entity_ids:
                missing.append(slot)
            elif slot == "volume_id" and not request.conditions.get("volume_id"):
                missing.append(slot)
            elif slot == "size_gb" and not request.conditions.get("size_gb"):
                missing.append(slot)
        return missing

    def clarify(self, request: OperationalRequest, candidates: list[Entity]) -> Clarification:
        missing = self.missing_slots(request)
        questions = []
        if "instance_id" in missing:
            if request.operation_id == "storage.volume.read":
                questions.append("Which instance_id should volume details be read for?")
            elif request.operation_id == "compute.instance.start":
                questions.append("Which instance_id should be started? Provide instance_id, name, type, or VPC.")
            else:
                questions.append("Which instance_id should be stopped? Provide instance_id, name, type, or VPC.")
        if "volume_id" in missing:
            questions.append("Which volume_id should be expanded?")
        if "size_gb" in missing:
            questions.append("What target size in GiB should the volume be expanded to?")
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
