from accusec.orchestration.orchestrator.runtime import ALICE
from accusec.orchestration.planner.planner import Planner


def test_list_stopped_is_list_not_stop():
    req = Planner().parse("list out all t3.medium in US-east-1 stopped state", ALICE)
    assert req.operation_id == "compute.instance.list"
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
