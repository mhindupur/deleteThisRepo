from accusec.orchestration.orchestrator.runtime import ALICE, build_runtime
from accusec.shared.domain.models import TaskState


def test_context_package_has_provenance():
    runtime = build_runtime()
    task = runtime.submit("list out all t2.small in US-east-1", ALICE)
    assert task.context_id
    assert task.state == TaskState.SUCCEEDED
