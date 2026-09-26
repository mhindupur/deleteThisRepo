"""Durable task orchestrator — chat is not the system of record."""

from __future__ import annotations

from accusec.agents.aws_pack.pack import attached_instance_ids, summarize_list, summarize_volumes
from accusec.memory.catalog.catalog import get_operation
from accusec.shared.domain.models import (
    AuditEvent,
    AuthzKind,
    PolicyEffect,
    Principal,
    Task,
    TaskState,
    TopologyEdge,
)


from accusec.security.identities import resolve_identity


class AgentOrchestrator:
    def __init__(
        self,
        *,
        planner,
        context,
        authz,
        harness,
        hitl,
        workflow,
        audit,
        gateway,
        entities,
        control=None,
    ) -> None:
        self.planner = planner
        self.context = context
        self.authz = authz
        self.harness = harness
        self.hitl = hitl
        self.workflow = workflow
        self.audit = audit
        self.gateway = gateway
        self.entities = entities
        self.control = control
        self.tasks: dict[str, Task] = {}

    def submit(self, intent: str, principal: Principal, endpoint_identity_id: str | None = None) -> Task:
        request = self.planner.parse(intent, principal)
        request.human_initiator_id = principal.principal_id
        request.agent_id = request.agent_id or getattr(self.planner, "agent_id", "agent-aws-pack")
        task = Task(request=request)
        self.tasks[task.task_id] = task
        try:
            self._bind_identity(request, endpoint_identity_id)
        except (PermissionError, ValueError) as exc:
            task.result = {"status": "denied", "reason": str(exc)}
            self.workflow.transition(task, TaskState.FAILED)
            self._persist(task)
            return task
        self.audit.record(
            AuditEvent(
                event_type="task.admitted",
                tenant_id=request.tenant_id,
                principal_id=principal.principal_id,
                operation_id=request.operation_id,
                task_id=task.task_id,
                correlation_id=request.correlation_id,
                project_id=request.project_id,
                datacenter_id=request.datacenter_id,
                agent_id=request.agent_id,
                endpoint_identity_id=request.endpoint_identity_id,
                payload={"intent": intent},
            )
        )
        task = self._advance(task)
        self._persist(task)
        return task

    def _advance(self, task: Task) -> Task:
        request = task.request
        missing = self.planner.missing_slots(request)
        if missing:
            self.workflow.transition(task, TaskState.AWAITING_CONTEXT)
            if request.operation_id in {"storage.volume.read", "storage.volume.expand"}:
                entity_type = (
                    "aws.ec2.volume" if "volume_id" in missing else "aws.ec2.instance"
                )
                candidates = self.entities.query(
                    tenant_id=request.tenant_id,
                    workspace_id=request.workspace_id,
                    entity_type=entity_type,
                )
                task.clarification = self.planner.clarify(request, candidates)
                task.result = {
                    "status": "needs_clarification",
                    "questions": task.clarification.questions,
                    "candidates": summarize_list(candidates),
                }
                return task
            package = self.context.assemble(request)
            task.context_id = package.context_id
            task.clarification = self.planner.clarify(request, package.entities)
            task.result = {
                "status": "needs_clarification",
                "questions": task.clarification.questions,
                "candidates": summarize_list(package.entities),
            }
            return task

        if request.operation_id == "storage.volume.read":
            return self._advance_volume_read(task)
        if request.operation_id == "storage.volume.expand":
            return self._advance_volume_expand(task)

        write = get_operation(request.operation_id).read_or_write == "write"
        self.workflow.transition(task, TaskState.PLANNING)

        if not write:
            try:
                package = self.context.assemble(request, force_refresh=False)
            except PermissionError as exc:
                task.result = {"status": "denied", "reason": str(exc)}
                self.workflow.transition(task, TaskState.FAILED)
                return task
            task.context_id = package.context_id
            task.used_llm = False
            self.gateway.complete(context_id=package.context_id, prompt="")
            task.result = {
                **summarize_list(package.entities),
                "status": "succeeded",
                "source": "organizational_memory",
                "freshness": package.freshness,
            }
            self.workflow.transition(task, TaskState.SUCCEEDED)
            return task

        exec_decision = self.authz.engine.evaluate(
            request.principal,
            request.operation_id,
            AuthzKind.EXECUTION,
            scopes=request.scopes,
            entity_type=request.target_entity_type,
        )
        if exec_decision.effect == PolicyEffect.DENY:
            task.result = {"status": "denied", "reason": exec_decision.reason}
            self.workflow.transition(task, TaskState.FAILED)
            return task

        instance_id = request.conditions.get("instance_id")
        remembered = self.entities.query(
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            provider_entity_id=instance_id,
            entity_type=request.target_entity_type,
        )
        if not remembered:
            task.result = {
                "status": "not_found",
                "reason": "instance is not in Organizational Memory. Sync the region before a change operation.",
            }
            self.workflow.transition(task, TaskState.FAILED)
            return task

        entity = remembered[0]
        entity_decision = self.authz.execution(
            request.principal, request.operation_id, entity, request.scopes
        )
        if entity_decision.effect == PolicyEffect.DENY:
            task.result = {"status": "denied", "reason": entity_decision.reason}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        exec_decision = entity_decision

        try:
            live = self.context.assemble(request, force_refresh=True)
        except PermissionError as exc:
            task.result = {"status": "denied", "reason": str(exc)}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        if live.entities:
            entity = live.entities[0]
            task.context_id = live.context_id
        else:
            task.context_id = live.context_id
        aws_state = entity.lifecycle_state
        if request.operation_id == "compute.instance.start" and aws_state in {"running", "pending"}:
            task.result = {
                "status": "succeeded",
                "source": "aws.api",
                "instance_id": instance_id,
                "lifecycle_state": aws_state,
                "reason": f"{instance_id} is already {aws_state}.",
                "verified_from": "aws.api",
            }
            self.workflow.transition(task, TaskState.SUCCEEDED)
            return task
        start = request.operation_id == "compute.instance.start"
        plan = self.planner.plan(
            request, [entity.entity_id], task.context_id, True
        )
        task.plan = plan
        approval_id = self.hitl.request_approval(plan, request.principal, task_id=task.task_id)
        self.workflow.transition(task, TaskState.AWAITING_APPROVAL)
        task.result = {
            "status": "awaiting_approval",
            "approval_id": approval_id,
            "plan_id": plan.plan_id,
            "plan_version": plan.version,
            "action": "start_instance" if start else "stop_instance",
            "target": summarize_list([entity]),
            "aws_state": aws_state,
            "memory_hit": True,
            "policy_decision_id": exec_decision.policy_decision_id,
            "freshness": live.freshness,
            "reason": (
                f"Start {instance_id} ({entity.display_name}) on AWS. Current state is {aws_state}."
                if start
                else f"Stop {instance_id} ({entity.display_name}) on AWS. Current state is {aws_state}."
            ),
            **self._governance(request, exec_decision),
        }
        return task

    def _instance_from_memory(self, request) -> list:
        return self.entities.query(
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            provider_entity_id=request.conditions.get("instance_id"),
            entity_type="aws.ec2.instance",
        )

    def _volumes_from_memory(self, request, instance_id: str) -> list:
        volumes = self.entities.query(
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            entity_type="aws.ec2.volume",
        )
        return [
            volume
            for volume in volumes
            if instance_id in attached_instance_ids(volume) and volume.configuration.get("size") is not None
        ]

    def _advance_volume_read(self, task: Task) -> Task:
        request = task.request
        self.workflow.transition(task, TaskState.PLANNING)
        access = self.authz.engine.evaluate(
            request.principal,
            request.operation_id,
            AuthzKind.CONTEXT_ACCESS,
            scopes=request.scopes,
            entity_type="aws.ec2.volume",
        )
        if access.effect == PolicyEffect.DENY:
            task.result = {"status": "denied", "reason": access.reason}
            self.workflow.transition(task, TaskState.FAILED)
            return task

        instance_id = request.conditions["instance_id"]
        remembered = self._instance_from_memory(request)
        if not remembered:
            task.result = {
                "status": "not_found",
                "reason": f"{instance_id} is not in Organizational Memory. Sync the region, then retry volume details.",
            }
            self.workflow.transition(task, TaskState.FAILED)
            return task
        instance = remembered[0]
        volumes = self._volumes_from_memory(request, instance_id)
        if volumes:
            task.used_llm = False
            task.result = {
                **summarize_volumes(volumes, instance_id=instance_id),
                "status": "succeeded",
                "source": "organizational_memory",
                "instance_name": instance.display_name,
            }
            self.workflow.transition(task, TaskState.SUCCEEDED)
            return task

        exec_decision = self.authz.engine.evaluate(
            request.principal,
            request.operation_id,
            AuthzKind.EXECUTION,
            entity=instance,
            scopes=request.scopes,
            entity_type="aws.ec2.volume",
        )
        if exec_decision.effect == PolicyEffect.DENY:
            task.result = {"status": "denied", "reason": exec_decision.reason}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        plan = self.planner.plan(request, [instance.entity_id], task.context_id or "", True)
        task.plan = plan
        approval_id = self.hitl.request_approval(plan, request.principal, task_id=task.task_id)
        self.workflow.transition(task, TaskState.AWAITING_APPROVAL)
        task.result = {
            "status": "awaiting_approval",
            "approval_id": approval_id,
            "plan_id": plan.plan_id,
            "plan_version": plan.version,
            "action": "hydrate_volumes",
            "memory_hit": False,
            "instance_id": instance_id,
            "instance_name": instance.display_name,
            "region": instance.region,
            "policy_decision_id": exec_decision.policy_decision_id,
            "reason": (
                f"No attached volume size for {instance_id} ({instance.display_name}) in Organizational Memory. "
                "Approve a DescribeVolumes call to AWS; AccuSec will display the result and upsert memory."
            ),
            **self._governance(request, exec_decision),
        }
        return task

    def _volume_from_memory(self, request):
        volume_id = request.conditions.get("volume_id")
        rows = self.entities.query(
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            provider_entity_id=volume_id,
            entity_type="aws.ec2.volume",
        )
        return rows

    def _advance_volume_expand(self, task: Task) -> Task:
        request = task.request
        self.workflow.transition(task, TaskState.PLANNING)
        volume_id = request.conditions["volume_id"]
        size_gb = int(request.conditions["size_gb"])
        remembered = self._volume_from_memory(request)
        if not remembered:
            task.result = {
                "status": "not_found",
                "reason": f"{volume_id} is not in Organizational Memory. Read/sync the volume first, then expand.",
            }
            self.workflow.transition(task, TaskState.FAILED)
            return task
        volume = remembered[0]
        instance_id = request.conditions.get("instance_id")
        attached = attached_instance_ids(volume)
        if instance_id and attached and instance_id not in attached:
            task.result = {
                "status": "failed",
                "reason": f"{volume_id} is not attached to {instance_id} in Organizational Memory.",
            }
            self.workflow.transition(task, TaskState.FAILED)
            return task
        exec_decision = self.authz.engine.evaluate(
            request.principal,
            request.operation_id,
            AuthzKind.EXECUTION,
            entity=volume,
            scopes=request.scopes,
            entity_type="aws.ec2.volume",
        )
        if exec_decision.effect == PolicyEffect.DENY:
            task.result = {"status": "denied", "reason": exec_decision.reason}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        region = volume.region
        live_size = volume.configuration.get("size")
        if region:
            try:
                observed = self.harness.invoke(
                    "aws.ec2.describe_volumes",
                    {"region": region, "volume_ids": [volume_id]},
                )
                if observed:
                    volume = observed[0]
                    self.entities.upsert(volume)
                    live_size = volume.configuration.get("size")
            except Exception as exc:  # noqa: BLE001
                task.result = {
                    "status": "failed",
                    "reason": f"could not refresh volume from AWS: {exc.__class__.__name__}",
                }
                self.workflow.transition(task, TaskState.FAILED)
                return task
        current = int(live_size or 0)
        if size_gb < current:
            task.result = {
                "status": "failed",
                "reason": f"EBS volumes cannot be shrunk. Current {current} GiB, requested {size_gb} GiB.",
            }
            self.workflow.transition(task, TaskState.FAILED)
            return task
        if size_gb == current:
            task.result = {
                **summarize_volumes([volume], instance_id=instance_id),
                "status": "succeeded",
                "source": "aws.api",
                "reason": f"{volume_id} is already {current} GiB.",
            }
            self.workflow.transition(task, TaskState.SUCCEEDED)
            return task
        plan = self.planner.plan(request, [volume.entity_id], task.context_id or "", True)
        task.plan = plan
        approval_id = self.hitl.request_approval(plan, request.principal, task_id=task.task_id)
        self.workflow.transition(task, TaskState.AWAITING_APPROVAL)
        task.result = {
            "status": "awaiting_approval",
            "approval_id": approval_id,
            "plan_id": plan.plan_id,
            "plan_version": plan.version,
            "action": "expand_volume",
            "memory_hit": True,
            "volume_id": volume_id,
            "instance_id": instance_id,
            "current_size_gb": current,
            "requested_size_gb": size_gb,
            "region": region,
            "policy_decision_id": exec_decision.policy_decision_id,
            "volumes": summarize_volumes([volume], instance_id=instance_id)["volumes"],
            "reason": (
                f"Expand {volume_id} from {current} GiB to {size_gb} GiB on AWS. "
                "This cannot be reversed by shrinking. Confirm to run ModifyVolume, then AccuSec will verify and update memory."
            ),
            **self._governance(request, exec_decision),
        }
        return task

    def _execute_expand(self, task: Task) -> Task:
        request = task.request
        volume_id = request.conditions["volume_id"]
        size_gb = int(request.conditions["size_gb"])
        remembered = self._volume_from_memory(request)
        if not remembered:
            task.result = {"status": "not_found", "reason": "volume left Organizational Memory before expand"}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        volume = remembered[0]
        region = volume.region
        if not region:
            task.result = {"status": "failed", "reason": "region is required to modify a volume"}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        self.workflow.transition(task, TaskState.RUNNING)
        key = f"{task.task_id}:{volume_id}:expand:{size_gb}"
        try:
            self.harness.invoke(
                "aws.ec2.modify_volume",
                {"volume_id": volume_id, "size_gb": size_gb, "region": region},
                idempotency_key=key,
            )
        except Exception as exc:  # noqa: BLE001
            task.result = {"status": "failed", "reason": str(exc)}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        self.workflow.transition(task, TaskState.VALIDATING)
        observed = self.harness.invoke(
            "aws.ec2.describe_volumes",
            {"region": region, "volume_ids": [volume_id]},
        )
        entity = observed[0]
        entity.last_sync_id = remembered[0].last_sync_id if remembered else entity.last_sync_id
        self.entities.upsert(entity)
        new_size = int(entity.configuration.get("size") or 0)
        ok = new_size >= size_gb
        task.result = {
            **summarize_volumes([entity], instance_id=request.conditions.get("instance_id")),
            "status": "succeeded" if ok else "postcondition_failed",
            "source": "aws.api",
            "verified_from": "aws.api",
            "volume_id": volume_id,
            "requested_size_gb": size_gb,
            "size_gb": new_size,
        }
        self.workflow.transition(task, TaskState.SUCCEEDED if ok else TaskState.FAILED)
        self.audit.record(
            AuditEvent(
                event_type="task.completed",
                tenant_id=request.tenant_id,
                principal_id=request.principal.principal_id,
                operation_id=request.operation_id,
                task_id=task.task_id,
                correlation_id=request.correlation_id,
                payload={"volume_id": volume_id, "size_gb": new_size},
            )
        )
        return task

    def apply_clarification(self, task_id: str, instance_id: str) -> Task:
        task = self.require_task(task_id)
        task.request.conditions["instance_id"] = instance_id
        task.clarification = None
        self._bind_identity(task.request, task.request.endpoint_identity_id)
        task = self._advance(task)
        self._persist(task)
        return task

    def approve(self, task_id: str, approval_id: str, approver: Principal, approved: bool = True) -> Task:
        task = self.require_task(task_id)
        if not task.plan:
            raise ValueError("no plan")
        self._bind_identity(task.request, task.request.endpoint_identity_id)
        self.hitl.decide(approval_id, approved, approver, task.plan)
        if not approved:
            self.workflow.transition(task, TaskState.CANCELLED)
            task.result = {"status": "rejected"}
            self._persist(task)
            return task
        if task.request.operation_id == "storage.volume.read":
            task = self._hydrate_volumes(task)
        elif task.request.operation_id == "storage.volume.expand":
            task = self._execute_expand(task)
        else:
            instance_id = task.request.conditions["instance_id"]
            task = self._execute_power(task, instance_id)
        self._persist(task)
        return task

    def _hydrate_volumes(self, task: Task) -> Task:
        request = task.request
        instance_id = request.conditions["instance_id"]
        remembered = self._instance_from_memory(request)
        if not remembered:
            task.result = {"status": "not_found", "reason": "instance left Organizational Memory before hydrate"}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        instance = remembered[0]
        region = instance.region or next(
            (scope.scope_id for scope in request.scopes if scope.scope_type == "region"), None
        )
        if not region:
            task.result = {"status": "failed", "reason": "region is required to describe volumes"}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        self.workflow.transition(task, TaskState.RUNNING)
        observed = self.harness.invoke(
            "aws.ec2.describe_volumes",
            {"region": region, "instance_ids": [instance_id]},
        )
        self.workflow.transition(task, TaskState.VALIDATING)
        for entity in observed:
            self.entities.upsert(entity)
            self.context.topology.add(
                TopologyEdge(
                    source_entity_id=entity.entity_id,
                    relationship_type="ATTACHED_TO",
                    target_entity_id=instance.entity_id,
                    tenant_id=entity.tenant_id,
                    workspace_id=entity.workspace_id,
                )
            )
        task.result = {
            **summarize_volumes(list(observed), instance_id=instance_id),
            "status": "succeeded",
            "source": "aws.api",
            "verified_from": "aws.api",
            "instance_name": instance.display_name,
        }
        self.workflow.transition(task, TaskState.SUCCEEDED)
        self.audit.record(
            AuditEvent(
                event_type="task.completed",
                tenant_id=request.tenant_id,
                principal_id=request.principal.principal_id,
                operation_id=request.operation_id,
                task_id=task.task_id,
                correlation_id=request.correlation_id,
                payload={"instance_id": instance_id, "volume_count": len(observed)},
            )
        )
        return task

    def _execute_power(self, task: Task, instance_id: str) -> Task:
        start = task.request.operation_id == "compute.instance.start"
        verb = "start" if start else "stop"
        tool = "aws.ec2.start_instances" if start else "aws.ec2.stop_instances"
        ok_states = {"running", "pending"} if start else {"stopped", "stopping"}
        region = next((s.scope_id for s in task.request.scopes if s.scope_type == "region"), None)
        remembered = self.entities.query(
            tenant_id=task.request.tenant_id,
            workspace_id=task.request.workspace_id,
            provider_entity_id=instance_id,
        )
        if remembered:
            region = region or remembered[0].region
        if not region:
            task.result = {"status": "failed", "reason": f"region is required to {verb} an instance"}
            self.workflow.transition(task, TaskState.FAILED)
            return task
        self.workflow.transition(task, TaskState.RUNNING)
        key = f"{task.task_id}:{instance_id}:{verb}"
        self.harness.invoke(
            tool,
            {"instance_id": instance_id, "region": region, "idempotency_key": key},
            idempotency_key=key,
        )
        self.workflow.transition(task, TaskState.VALIDATING)
        observed = self.harness.invoke(
            "aws.ec2.describe_instances",
            {"region": region, "instance_ids": [instance_id]},
        )
        entity = observed[0]
        entity.last_sync_id = remembered[0].last_sync_id if remembered else entity.last_sync_id
        self.entities.upsert(entity)
        ok = entity.lifecycle_state in ok_states
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

    def _execute_stop(self, task: Task, instance_id: str) -> Task:
        return self._execute_power(task, instance_id)

    def get_task(self, task_id: str) -> Task | None:
        task = self.tasks.get(task_id)
        if task:
            return task
        if self.control:
            task = self.control.get_task(task_id)
            if task:
                self.tasks[task_id] = task
        return task

    def require_task(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def _persist(self, task: Task) -> None:
        self.tasks[task.task_id] = task
        if self.control:
            self.control.save_task(task)

    def _governance(self, request, decision) -> dict:
        return {
            "agent_id": request.agent_id,
            "project_id": request.project_id,
            "datacenter_id": request.datacenter_id,
            "endpoint_identity_id": request.endpoint_identity_id,
            "obligations": list(decision.obligations),
        }

    def _bind_identity(self, request, requested_id: str | None = None) -> None:
        if requested_id:
            request.endpoint_identity_id = requested_id
        if not self.control:
            self._apply_execution_context(request)
            return
        identities = self.control.list_identities(tenant_id=request.tenant_id)
        if not identities:
            self._apply_execution_context(request)
            return
        chosen = resolve_identity(
            identities,
            request.operation_id,
            request.endpoint_identity_id,
            endpoint_id=request.endpoint_id or getattr(self.planner, "endpoint_id", None),
        )
        if chosen is None:
            if request.operation_id in {"compute.instance.stop", "compute.instance.start", "storage.volume.expand"}:
                raise PermissionError("no Endpoint Access Identity is entitled for this operation")
            self._apply_execution_context(request)
            return
        request.endpoint_identity_id = chosen.endpoint_identity_id
        request.endpoint_id = chosen.endpoint_id
        self._apply_execution_context(request, identity_type=chosen.identity_type)

    def _apply_execution_context(self, request, identity_type: str | None = None) -> None:
        if identity_type is None and self.control and request.endpoint_identity_id:
            identity = self.control.get_identity(request.endpoint_identity_id)
            identity_type = identity.identity_type if identity else None
        if self.harness is not None:
            self.harness.execution_context = {
                "identity_type": identity_type or "OPERATOR",
                "endpoint_identity_id": request.endpoint_identity_id,
                "agent_id": request.agent_id,
                "human_initiator_id": request.human_initiator_id,
                "tenant_id": request.tenant_id,
                "project_id": request.project_id,
                "datacenter_id": request.datacenter_id,
            }
