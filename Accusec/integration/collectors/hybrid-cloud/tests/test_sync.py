from accusec.orchestration.orchestrator.runtime import ALICE, build_runtime
from accusec.shared.domain.models import Entity, utcnow


def test_sync_upserts_and_tombstones_missing():
    runtime = build_runtime(fixture_mode=True)
    from accusec.orchestration.orchestrator.runtime import connect_aws

    conn = connect_aws(
        runtime,
        account_id="123456789012",
        regions=["us-east-1"],
        secret_ref="aws/local-fixture",
        principal=ALICE,
    )
    runtime.bind_connection(conn)
    run = runtime.collector.sync(conn, region="us-east-1", principal=ALICE)
    assert run.status in {"succeeded", "partial"}
    assert run.upserted >= 3
    rows = runtime.entities.query(
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        entity_type="aws.ec2.instance",
        region="us-east-1",
        account_id="123456789012",
    )
    assert {r.provider_entity_id for r in rows} >= {"i-aaa111", "i-bbb222", "i-ccc333"}

    ghost = Entity(
        entity_id=Entity.make_id("aws", "aws.ec2.instance", "tenant-1", "123456789012", "us-east-1", "i-gone"),
        provider_entity_id="i-gone",
        entity_type="aws.ec2.instance",
        provider="aws",
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        display_name="gone",
        account_id="123456789012",
        region="us-east-1",
        lifecycle_state="running",
        configuration={"instance_type": "t2.small", "vpc_id": "vpc-east"},
        source="aws.api",
        last_observed_at=utcnow(),
        last_sync_id="sync-old",
    )
    runtime.entities.upsert(ghost)
    run2 = runtime.collector.sync(conn, region="us-east-1", principal=ALICE)
    assert run2.missing >= 1
    missing = runtime.entities.get(ghost.entity_id)
    assert missing is not None
    assert missing.lifecycle_state == "missing"
    assert missing.freshness_status == "stale"


def test_connect_audit_has_secret_ref_not_keys():
    runtime = build_runtime(fixture_mode=True)
    from accusec.orchestration.orchestrator.runtime import connect_aws
    from accusec.shared.domain.models import SecretSpec

    runtime.secrets.put(
        "aws/lab-test",
        SecretSpec(auth_mode="fixture", role_arn="arn:aws:iam::123456789012:role/AccuSecInventoryReader"),
    )
    connect_aws(
        runtime,
        account_id="123456789012",
        regions=["us-east-1"],
        secret_ref="aws/lab-test",
        principal=ALICE,
        workspace_id="aws-prod-audit",
    )
    dumped = " ".join(str(e.payload) for e in runtime.audit.events)
    assert "AKIA" not in dumped
    assert "secret_access_key" not in dumped.lower()
    assert any(e.event_type == "provider.connected" for e in runtime.audit.events)


def test_allow_region_merges_allowlist():
    runtime = build_runtime(fixture_mode=True)
    from accusec.orchestration.orchestrator.runtime import allow_connection_regions, connect_aws

    conn = connect_aws(
        runtime,
        account_id="123456789012",
        regions=["us-east-1"],
        secret_ref="aws/local-fixture",
        principal=ALICE,
        workspace_id="aws-prod-regions",
    )
    conn = allow_connection_regions(runtime, regions=["ap-south-1"], principal=ALICE, connection_id=conn.connection_id)
    assert "us-east-1" in conn.regions
    assert "ap-south-1" in conn.regions
    runtime.bind_connection(conn)
    run = runtime.collector.sync(conn, region="ap-south-1", principal=ALICE)
    assert run.status in {"succeeded", "partial"}
