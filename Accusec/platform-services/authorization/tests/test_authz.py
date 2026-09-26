from accusec.orchestration.orchestrator.runtime import ADMIN, ALICE, VIEWER
from accusec.security.engine import PolicyEngine
from accusec.security.identities import resolve_identity
from accusec.shared.domain.models import (
    AuthzKind,
    EndpointAccessIdentity,
    Entity,
    OBLIGATION_APPROVAL,
    PolicyEffect,
)


def test_viewer_cannot_stop():
    engine = PolicyEngine()
    entity = Entity(
        entity_id="e",
        provider_entity_id="i-aaa111",
        entity_type="aws.ec2.instance",
        provider="aws",
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        display_name="web",
        account_id="123456789012",
        region="us-east-1",
    )
    decision = engine.evaluate(VIEWER, "compute.instance.stop", AuthzKind.EXECUTION, entity=entity)
    assert decision.effect == PolicyEffect.DENY


def test_desktop_admin_cannot_stop():
    engine = PolicyEngine()
    entity = Entity(
        entity_id="e",
        provider_entity_id="i-aaa111",
        entity_type="aws.ec2.instance",
        provider="aws",
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        display_name="web",
        account_id="123456789012",
        region="us-east-1",
    )
    decision = engine.evaluate(ADMIN, "compute.instance.stop", AuthzKind.EXECUTION, entity=entity)
    assert decision.effect == PolicyEffect.DENY


def test_operator_stop_carries_approval_obligation():
    engine = PolicyEngine()
    entity = Entity(
        entity_id="e",
        provider_entity_id="i-aaa111",
        entity_type="aws.ec2.instance",
        provider="aws",
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        display_name="web",
        account_id="123456789012",
        region="us-east-1",
    )
    decision = engine.evaluate(ALICE, "compute.instance.stop", AuthzKind.EXECUTION, entity=entity)
    assert decision.effect == PolicyEffect.ALLOW_WITH_APPROVAL
    assert OBLIGATION_APPROVAL in decision.obligations


def test_readonly_identity_cannot_be_selected_for_stop():
    identity = EndpointAccessIdentity(
        tenant_id="tenant-1",
        endpoint_id="ep-aws",
        identity_type="READ_ONLY",
        secret_ref="secret-ref:aws/reader",
        display_name="reader",
    )
    try:
        resolve_identity([identity], "compute.instance.stop", requested_id=identity.endpoint_identity_id)
        raise AssertionError("READ_ONLY stop should fail")
    except PermissionError:
        pass


def test_operator_identity_is_used_when_readonly_missing():
    identity = EndpointAccessIdentity(
        tenant_id="tenant-1",
        endpoint_id="ep-aws",
        identity_type="OPERATOR",
        secret_ref="secret-ref:aws/operator",
        display_name="operator",
    )
    chosen = resolve_identity([identity], "compute.instance.list")
    assert chosen is not None
    assert chosen.identity_type == "OPERATOR"
