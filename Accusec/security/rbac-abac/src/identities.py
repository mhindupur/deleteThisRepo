"""Deterministic Endpoint Access Identity selection. Never pick the most privileged silently."""

from __future__ import annotations

from accusec.shared.domain.models import EndpointAccessIdentity

WRITE_OPERATIONS = frozenset(
    {
        "compute.instance.stop",
        "compute.instance.start",
        "storage.volume.expand",
    }
)


def required_identity_type(operation_id: str) -> str:
    if operation_id in WRITE_OPERATIONS:
        return "OPERATOR"
    return "READ_ONLY"


def resolve_identity(
    identities: list[EndpointAccessIdentity],
    operation_id: str,
    requested_id: str | None = None,
    endpoint_id: str | None = None,
) -> EndpointAccessIdentity | None:
    active = [item for item in identities if item.status == "active"]
    if endpoint_id:
        scoped = [item for item in active if item.endpoint_id == endpoint_id]
        if scoped:
            active = scoped
    if requested_id:
        for item in active:
            if item.endpoint_identity_id == requested_id:
                needed = required_identity_type(operation_id)
                if needed == "OPERATOR" and item.identity_type == "READ_ONLY":
                    raise PermissionError("READ_ONLY identity cannot execute this operation")
                return item
        raise ValueError(f"unknown endpoint identity {requested_id}")
    needed = required_identity_type(operation_id)
    matching = [item for item in active if item.identity_type == needed]
    if needed == "READ_ONLY" and not matching:
        matching = [item for item in active if item.identity_type in {"OPERATOR", "AGENT_WORKLOAD"}]
    if needed == "OPERATOR" and not matching:
        matching = [item for item in active if item.identity_type == "AGENT_WORKLOAD"]
    if len(matching) == 1:
        return matching[0]
    if not matching:
        return None
    raise ValueError("multiple Endpoint Access Identities match; select one explicitly")
