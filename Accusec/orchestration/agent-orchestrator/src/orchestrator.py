"""Durable task orchestrator — chat is not the system of record."""

from __future__ import annotations

from accusec.agents.aws_pack.pack import summarize_list
from accusec.memory.catalog.catalog import get_operation
from accusec.shared.domain.models import (
    AuditEvent,
    PolicyEffect,
    Principal,
    Task,
    TaskState,
)


class AgentOrchestrator:
    def __init__(self, *, planner, context, authz, harness, hitl, workflow, audit, gateway, entities) -> None:
        self.planner = planner
        self.context = context
        self.authz = authz
        self.harness = harness
        self.hitl = hitl
        self.workflow = workflow
        self.audit = audit
        self.gateway = gateway
        self.entities = entities
        self.tasks: dict[str, Task] = {}

    def submit(self, intent: str, principal: Principal) -> Task:
        request = self.planner.parse(intent, principal)
        task = Task(request=request)
        self.tasks[task.task_id] = task
        self.audit.record(
            AuditEvent(
                event_type="task.admitted",
                tenant_id=request.tenant_id,
                principal_id=principal.principal_id,
                operation_id=request.operation_id,
                task_id=task.task_id,
                correlation_id=request.correlation_id,
                payload={"intent": intent},
            )
        )
        return self._advance(task)

    def _advance(self, task: Task) -> Task:
        request = task.request
        missing = self.planner.missing_slots(request)
        if missing:
            self.workflow.transition(task, TaskState.AWAITING_CONTEXT)
            package = self.context.assemble(request)
            task.context_id = package.context_id
            task.clarification = self.planner.clarify(request, package.entities)
            task.result = {
                "status": "needs_clarification",
                "questions": task.clarification.questions,
                "candidates": summarize_list(package.entities),
            }
            return task

        write = get_operation(request.operation_id).read_or_write == "write"
        package = self.context.assemble(request, force_refresh=write)
        task.context_id = package.context_id
        self.workflow.transition(task, TaskState.PLANNING)

        if not write:
            task.used_llm = False
            self.gateway.complete(context_id=package.context_id, prompt="")
            task.result = summarize_list(package.entities)
            self.workflow.transition(task, TaskState.SUCCEEDED)
            return task

        if not package.entities:
            task.result = {"status": "not_found"}
            self.workflow.transition(task, TaskState.FAILED)
            return task

        entity = package.entities[0]
        exec_decision = self.authz.execution(
            request.principal, request.operation_id, entity, request.scopes
        )
        approval_needed = exec_decision.effect == PolicyEffect.ALLOW_WITH_APPROVAL
        if exec_decision.effect == PolicyEffect.DENY:
            task.result = {"status": "denied", "reason": exec_decision.reason}
            self.workflow.transition(task, TaskState.FAILED)
            return task

        plan = self.planner.plan(
            request, [entity.entity_id], package.context_id, approval_needed
        )
        task.plan = plan
        if approval_needed:
            approval_id = self.hitl.request_approval(plan, request.principal)
            self.workflow.transition(task, TaskState.AWAITING_APPROVAL)
            task.result = {
                "status": "awaiting_approval",
                "approval_id": approval_id,
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "target": summarize_list([entity]),
                "policy_decision_id": exec_decision.policy_decision_id,
            }
            return task
        return self._execute_stop(task, entity.provider_entity_id)

    def apply_clarification(self, task_id: str, instance_id: str) -> Task:
        task = self.tasks[task_id]
        task.request.conditions["instance_id"] = instance_id
        task.clarification = None
        return self._advance(task)

    def approve(self, task_id: str, approval_id: str, approver: Principal, approved: bool = True) -> Task:
        task = self.tasks[task_id]
        if not task.plan:
            raise ValueError("no plan")
        self.hitl.decide(approval_id, approved, approver, task.plan)
        if not approved:
            self.workflow.transition(task, TaskState.CANCELLED)
            task.result = {"status": "rejected"}
            return task
        instance_id = task.request.conditions["instance_id"]
        return self._execute_stop(task, instance_id)

    def _execute_stop(self, task: Task, instance_id: str) -> Task:
        self.workflow.transition(task, TaskState.RUNNING)
        key = f"{task.task_id}:{instance_id}:stop"
        self.harness.invoke(
            "aws.ec2.stop_instances",
            {"instance_id": instance_id, "idempotency_key": key},
            idempotency_key=key,
        )
        self.workflow.transition(task, TaskState.VALIDATING)
        observed = self.harness.invoke(
            "aws.ec2.describe_instances",
            {"instance_ids": [instance_id]},
        )
        entity = observed[0]
        self.entities.upsert(entity)
        ok = entity.lifecycle_state in {"stopped", "stopping"}
        task.result = {
            "status": "succeeded" if ok else "postcondition_failed",
            "instance_id": instance_id,
            "lifecycle_state": entity.lifecycle_state,
            "verified_from": "aws.api",
        }
        self.workflow.transition(task, TaskState.SUCCEEDED if ok else TaskState.FAILED)
        self.audit.record(
            AuditEvent(
                event_type="task.completed",
                tenant_id=task.request.tenant_id,
                principal_id=task.request.principal.principal_id,
                operation_id=task.request.operation_id,
                task_id=task.task_id,
                correlation_id=task.request.correlation_id,
                context_id=task.context_id,
                payload={"instance_id": instance_id, "state": entity.lifecycle_state},
            )
        )
        return task
