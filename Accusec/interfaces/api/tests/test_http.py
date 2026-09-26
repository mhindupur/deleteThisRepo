from fastapi.testclient import TestClient

from accusec.interfaces.api.http import account_id_from_role_arn, create_app
from accusec.orchestration.orchestrator.runtime import ALICE, build_runtime
from accusec.shared.domain.models import TaskState


def test_console_list_then_stop_requires_hitl():
    runtime = build_runtime()
    client = TestClient(create_app(runtime))
    listed = client.post("/api/ask", json={"intent": "list out all t2.small in US-east-1"})
    assert listed.status_code == 200
    body = listed.json()
    assert body["state"] == TaskState.SUCCEEDED.value
    assert body["result"]["source"] == "organizational_memory"
    ids = {row["instance_id"] for row in body["result"]["instances"]}
    assert ids == {"i-aaa111", "i-bbb222"}

    stop = client.post("/api/ask", json={"intent": "stop instance i-bbb222"})
    assert stop.status_code == 200
    waiting = stop.json()
    assert waiting["state"] == TaskState.AWAITING_APPROVAL.value
    assert waiting["result"]["memory_hit"] is True
    approval_id = waiting["result"]["approval_id"]

    done = client.post(
        f"/api/tasks/{waiting['task_id']}/approve",
        json={"approval_id": approval_id, "approved": True},
    )
    assert done.status_code == 200
    finished = done.json()
    assert finished["state"] == TaskState.SUCCEEDED.value
    assert finished["result"]["lifecycle_state"] in {"stopping", "stopped"}
    remembered = runtime.entities.query(
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        provider_entity_id="i-bbb222",
    )
    assert remembered
    assert remembered[0].lifecycle_state in {"stopping", "stopped"}
    assert ALICE.principal_id == "alice"
    assert "cloud-operator" in ALICE.roles
    assert "desktop-administrator" in ALICE.roles


def test_health_and_index():
    client = TestClient(create_app(build_runtime()))
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["edition"] == "desktop"
    assert body["project_id"] == "project-0"
    assert body["datacenter_id"] == "dc-aws"
    assert body["agent_id"] == "agent-aws-pack"
    assert {row["principal_id"] for row in body["principals"]} >= {"alice", "admin", "bob", "agent-aws-pack"}
    page = client.get("/")
    assert page.status_code == 200
    assert "AccuSec Console" in page.text
    assert "Ask AccuSec" in page.text or "textarea" in page.text
    assert "Change workflow" in page.text
    assert "Entitlements" in page.text
    assert "Create Project" in page.text


def test_account_id_is_parsed_from_role_arn():
    assert account_id_from_role_arn("arn:aws:iam::442042550517:role/ACCUSEC_EC2_ROLE") == "442042550517"


def test_admin_principal_cannot_stop_via_console():
    client = TestClient(create_app(build_runtime()))
    denied = client.post(
        "/api/ask",
        json={"intent": "stop instance i-bbb222", "principal_id": "admin"},
    )
    assert denied.status_code == 200
    body = denied.json()
    assert body["state"] == TaskState.FAILED.value
    assert body["result"]["status"] == "denied"
