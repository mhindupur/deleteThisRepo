from accusec.orchestration.orchestrator.runtime import VIEWER
from accusec.security.engine import PolicyEngine
from accusec.shared.domain.models import AuthzKind, Entity, PolicyEffect


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
