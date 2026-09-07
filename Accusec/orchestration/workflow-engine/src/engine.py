from accusec.shared.domain.models import Task, TaskState


class WorkflowEngine:
    def transition(self, task: Task, state: TaskState) -> Task:
        task.state = state
        return task
