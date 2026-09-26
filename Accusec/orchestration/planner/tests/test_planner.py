from accusec.orchestration.orchestrator.runtime import ALICE
from accusec.orchestration.planner.planner import Planner


def test_list_stopped_is_list_not_stop():
    req = Planner().parse("list out all t3.medium in US-east-1 stopped state", ALICE)
    assert req.operation_id == "compute.instance.list"
    assert req.project_id == "project-0"
    assert req.datacenter_id == "dc-aws"
    assert req.agent_id == "agent-aws-pack"
    assert req.human_initiator_id == ALICE.principal_id
    assert any(s.scope_type == "project" and s.scope_id == "project-0" for s in req.scopes)
    assert any(s.scope_type == "datacenter" and s.scope_id == "dc-aws" for s in req.scopes)
    assert req.conditions["instance_type"] == "t3.medium"
    assert req.conditions["lifecycle_state"] == "stopped"
    assert any(s.scope_type == "region" and s.scope_id == "us-east-1" for s in req.scopes)


def test_list_without_region_is_still_list():
    req = Planner().parse("list out t3.large instances, which are in stopped state", ALICE)
    assert req.operation_id == "compute.instance.list"
    assert req.conditions["instance_type"] == "t3.large"
    assert req.conditions["lifecycle_state"] == "stopped"
    assert not any(s.scope_type == "region" for s in req.scopes)


def test_stop_instance_still_maps_to_stop():
    req = Planner().parse("Stop Instance in US-EAST-1", ALICE)
    assert req.operation_id == "compute.instance.stop"
    assert "lifecycle_state" not in req.conditions


def test_start_instance_maps_to_start_not_read():
    req = Planner().parse("start ec2 instanceid : i-0964bd4075cf9a5fd", ALICE)
    assert req.operation_id == "compute.instance.start"
    assert req.conditions["instance_id"] == "i-0964bd4075cf9a5fd"
    assert "lifecycle_state" not in req.conditions


def test_stop_and_stopped_mean_the_same_on_list():
    planner = Planner()
    stopped = planner.parse("list out t3.large instances, which are in stopped state", ALICE)
    stop = planner.parse("list out t3.large instances, which are in stop state", ALICE)
    assert stopped.operation_id == "compute.instance.list"
    assert stop.operation_id == "compute.instance.list"
    assert stopped.conditions["lifecycle_state"] == "stopped"
    assert stop.conditions["lifecycle_state"] == "stopped"


def test_planner_uses_connected_account():
    req = Planner(account_id="442042550517").parse("list out all t3.medium in US-east-1", ALICE)
    assert any(s.scope_type == "account" and s.scope_id == "442042550517" for s in req.scopes)


def test_volume_expand_maps_to_storage_volume_expand():
    req = Planner().parse(
        "update volume id : vol-078edd8e2e220553d of instanceid :i-0bf952d162c939337 , update storage size 20GB to 30GB",
        ALICE,
    )
    assert req.operation_id == "storage.volume.expand"
    assert req.conditions["volume_id"] == "vol-078edd8e2e220553d"
    assert req.conditions["instance_id"] == "i-0bf952d162c939337"
    assert req.conditions["size_gb"] == 30


def test_volume_attached_maps_to_storage_volume_read():
    req = Planner().parse(
        "provide volume attached to instanceid :i-0bf952d162c939337 and what is the storage size?",
        ALICE,
    )
    assert req.operation_id == "storage.volume.read"
    assert req.conditions["instance_id"] == "i-0bf952d162c939337"
