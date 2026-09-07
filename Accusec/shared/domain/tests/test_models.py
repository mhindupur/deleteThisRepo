from accusec.shared.domain.models import Entity, Scope


def test_entity_id_does_not_use_display_name():
    eid = Entity.make_id("aws", "aws.ec2.instance", "t1", "123", "us-east-1", "i-abc")
    assert "web" not in eid
    assert eid.startswith("accusec:aws:instance:")


def test_region_scope_matches():
    entity = Entity(
        entity_id="e1",
        provider_entity_id="i-1",
        entity_type="aws.ec2.instance",
        provider="aws",
        tenant_id="t",
        workspace_id="w",
        display_name="n",
        region="us-east-1",
    )
    assert Scope(scope_type="region", scope_id="us-east-1").matches_entity(entity)
    assert not Scope(scope_type="region", scope_id="us-west-2").matches_entity(entity)
