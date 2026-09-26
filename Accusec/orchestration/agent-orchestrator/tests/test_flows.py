from datetime import timedelta

from accusec.orchestration.orchestrator.runtime import ADMIN, AGENT, ALICE, VIEWER, build_runtime
from accusec.shared.domain.models import Entity, TaskState, utcnow


def test_list_t2_small_us_east_1_from_memory():
    runtime = build_runtime()
    task = runtime.submit("list out all t2.small in US-east-1", ALICE)
    assert task.state == TaskState.SUCCEEDED
    assert task.used_llm is False
    ids = {row["instance_id"] for row in task.result["instances"]}
    assert ids == {"i-aaa111", "i-bbb222"}
    assert all(row["instance_type"] == "t2.small" for row in task.result["instances"])
    assert all(row["region"] == "us-east-1" for row in task.result["instances"])


def test_list_does_not_leak_other_region():
    runtime = build_runtime()
    task = runtime.submit("list out all t2.small in US-east-1", ALICE)
    ids = {row["instance_id"] for row in task.result["instances"]}
    assert "i-ddd444" not in ids


def test_stop_in_region_asks_clarification_not_hitl():
    runtime = build_runtime()
    task = runtime.submit("Stop Instance in US-EAST-1", ALICE)
    assert task.state == TaskState.AWAITING_CONTEXT
    assert task.clarification is not None
    assert "instance_id" in task.clarification.missing_slots
    assert task.result["candidates"]["count"] >= 2
    assert "approval_id" not in task.result


def test_stop_after_clarify_refreshes_aws_then_hitl_then_postcondition():
    runtime = build_runtime()
    task = runtime.submit("Stop Instance in US-EAST-1", ALICE)
    task = runtime.apply_clarification(task.task_id, "i-bbb222")
    assert task.state == TaskState.AWAITING_APPROVAL
    approval_id = task.result["approval_id"]
    task = runtime.approve(task.task_id, approval_id, ALICE, approved=True)
    assert task.state == TaskState.SUCCEEDED
    assert task.result["lifecycle_state"] in {"stopping", "stopped"}
    assert task.result["verified_from"] == "aws.api"


def test_start_stopped_instance_requires_hitl_then_updates_memory():
    runtime = build_runtime()
    stopped = runtime.submit("stop instance i-bbb222", ALICE)
    stopped = runtime.approve(stopped.task_id, stopped.result["approval_id"], ALICE, approved=True)
    assert stopped.result["lifecycle_state"] in {"stopping", "stopped"}

    task = runtime.submit("start ec2 instanceid i-bbb222", ALICE)
    assert task.request.operation_id == "compute.instance.start"
    assert task.state == TaskState.AWAITING_APPROVAL
    assert task.result["action"] == "start_instance"
    task = runtime.approve(task.task_id, task.result["approval_id"], ALICE, approved=True)
    assert task.state == TaskState.SUCCEEDED
    assert task.result["lifecycle_state"] in {"pending", "running"}
    remembered = runtime.entities.query(
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        provider_entity_id="i-bbb222",
    )
    assert remembered[0].lifecycle_state in {"pending", "running"}


def test_list_stopped_t3_from_memory_not_classified_as_stop():
    runtime = build_runtime()
    stopped = Entity(
        entity_id=Entity.make_id("aws", "aws.ec2.instance", "tenant-1", "123456789012", "us-east-1", "i-stop1"),
        provider_entity_id="i-stop1",
        entity_type="aws.ec2.instance",
        provider="aws",
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        display_name="stopped-box",
        account_id="123456789012",
        region="us-east-1",
        lifecycle_state="stopped",
        configuration={"instance_type": "t3.medium", "vpc_id": "vpc-east"},
        source="memory",
        last_observed_at=utcnow(),
    )
    running = Entity(
        entity_id=Entity.make_id("aws", "aws.ec2.instance", "tenant-1", "123456789012", "us-east-1", "i-run1"),
        provider_entity_id="i-run1",
        entity_type="aws.ec2.instance",
        provider="aws",
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        display_name="running-box",
        account_id="123456789012",
        region="us-east-1",
        lifecycle_state="running",
        configuration={"instance_type": "t3.medium", "vpc_id": "vpc-east"},
        source="memory",
        last_observed_at=utcnow(),
    )
    runtime.entities.upsert(stopped)
    runtime.entities.upsert(running)
    task = runtime.submit("list out all t3.medium in US-east-1 stopped state", ALICE)
    assert task.request.operation_id == "compute.instance.list"
    assert task.state == TaskState.SUCCEEDED
    ids = {row["instance_id"] for row in task.result["instances"]}
    assert "i-stop1" in ids
    assert "i-run1" not in ids
    assert all(row["state"] == "stopped" for row in task.result["instances"])

    same = runtime.submit("list out all t3.medium in US-east-1 which are in stop state", ALICE)
    assert same.request.conditions["lifecycle_state"] == "stopped"
    assert {row["instance_id"] for row in same.result["instances"]} == ids


def test_list_without_region_returns_stale_memory_and_does_not_crash():
    runtime = build_runtime()
    stopped = Entity(
        entity_id=Entity.make_id("aws", "aws.ec2.instance", "tenant-1", "123456789012", "us-east-1", "i-large1"),
        provider_entity_id="i-large1",
        entity_type="aws.ec2.instance",
        provider="aws",
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        display_name="k8s-master",
        account_id="123456789012",
        region="us-east-1",
        lifecycle_state="stopped",
        configuration={"instance_type": "t3.large", "vpc_id": "vpc-east"},
        source="aws.api",
        last_observed_at=utcnow() - timedelta(hours=3),
    )
    runtime.entities.upsert(stopped)

    class BoomHarness:
        def invoke(self, *args, **kwargs):
            raise ValueError("region is required for live DescribeInstances")

    runtime.orchestrator.context.harness = BoomHarness()
    task = runtime.submit("list out t3.large instances, which are in stopped state", ALICE)
    assert task.request.operation_id == "compute.instance.list"
    assert task.state == TaskState.SUCCEEDED
    ids = {row["instance_id"] for row in task.result["instances"]}
    assert "i-large1" in ids
    assert all(row["state"] == "stopped" for row in task.result["instances"])


def test_stop_unknown_instance_does_not_invent_from_aws():
    runtime = build_runtime()
    task = runtime.submit("stop instance i-notpresent999", ALICE)
    assert task.state == TaskState.FAILED
    assert task.result["status"] == "not_found"


def test_viewer_is_denied_before_hitl():
    runtime = build_runtime()
    task = runtime.submit("stop instance i-bbb222", VIEWER)
    assert task.state == TaskState.FAILED
    assert task.result["status"] == "denied"
    assert "approval_id" not in task.result


def test_volume_question_uses_memory_then_hitl_hydrate():
    from accusec.agents.aws_pack.pack import attached_instance_ids

    runtime = build_runtime()
    for volume in runtime.entities.query(
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        entity_type="aws.ec2.volume",
        exclude_missing=False,
    ):
        if "i-bbb222" in attached_instance_ids(volume):
            volume.lifecycle_state = "missing"
            runtime.entities.upsert(volume)
    intent = "provide volume attached to instanceid i-bbb222 and what is the storage size?"
    task = runtime.submit(intent, ALICE)
    assert task.request.operation_id == "storage.volume.read"
    assert task.state == TaskState.AWAITING_APPROVAL
    assert task.result["action"] == "hydrate_volumes"
    task = runtime.approve(task.task_id, task.result["approval_id"], ALICE, approved=True)
    assert task.state == TaskState.SUCCEEDED
    assert task.result["source"] == "aws.api"
    assert task.result["total_size_gb"] == 20
    assert task.result["volumes"][0]["volume_id"] == "vol-bbb222"
    remembered = runtime.entities.query(
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        entity_type="aws.ec2.volume",
        provider_entity_id="vol-bbb222",
    )
    assert remembered
    assert remembered[0].configuration["size"] == 20

    again = runtime.submit(intent, ALICE)
    assert again.state == TaskState.SUCCEEDED
    assert again.result["source"] == "organizational_memory"
    assert again.result["total_size_gb"] == 20


def test_expand_volume_requires_hitl_then_updates_memory():
    from accusec.integration.aws_connector.connector import fixture_volumes

    runtime = build_runtime()
    volume = fixture_volumes()[1]
    volume.source = "memory"
    runtime.entities.upsert(volume)
    intent = "update volume id vol-bbb222 of instanceid i-bbb222, update storage size 20GB to 30GB"
    task = runtime.submit(intent, ALICE)
    assert task.request.operation_id == "storage.volume.expand"
    assert task.state == TaskState.AWAITING_APPROVAL
    assert task.result["action"] == "expand_volume"
    assert task.result["current_size_gb"] == 20
    assert task.result["requested_size_gb"] == 30
    task = runtime.approve(task.task_id, task.result["approval_id"], ALICE, approved=True)
    assert task.state == TaskState.SUCCEEDED
    assert task.result["size_gb"] == 30
    remembered = runtime.entities.query(
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        entity_type="aws.ec2.volume",
        provider_entity_id="vol-bbb222",
    )
    assert remembered[0].configuration["size"] == 30


def test_audit_has_no_raw_secrets():
    runtime = build_runtime()
    runtime.submit("list out all t2.small in US-east-1", ALICE)
    for event in runtime.audit.events:
        dumped = str(event.payload)
        assert "password" not in dumped.lower()
        assert "AKIA" not in dumped


def test_desktop_admin_is_denied_cloud_stop():
    runtime = build_runtime()
    task = runtime.submit("stop instance i-bbb222", ADMIN)
    assert task.state == TaskState.FAILED
    assert task.result["status"] == "denied"
    assert "approval_id" not in task.result


def test_agent_principal_can_list_from_memory():
    runtime = build_runtime()
    task = runtime.submit("list out all t2.small in US-east-1", AGENT)
    assert task.state == TaskState.SUCCEEDED
    assert task.request.agent_id == "agent-aws-pack"
    assert task.request.project_id == "project-0"
    assert task.request.datacenter_id == "dc-aws"


def test_stop_hitl_is_durable_across_runtime_restart():
    first = build_runtime()
    task = first.submit("stop instance i-bbb222", ALICE)
    assert task.state == TaskState.AWAITING_APPROVAL
    assert "REQUIRE_APPROVAL" in task.result["obligations"]
    assert task.request.endpoint_identity_id
    task_id = task.task_id
    approval_id = task.result["approval_id"]

    second = build_runtime()
    restored = second.get_task(task_id)
    assert restored is not None
    assert restored.state == TaskState.AWAITING_APPROVAL
    finished = second.approve(task_id, approval_id, ALICE, approved=True)
    assert finished.state == TaskState.SUCCEEDED
    assert finished.result["lifecycle_state"] in {"stopping", "stopped"}
