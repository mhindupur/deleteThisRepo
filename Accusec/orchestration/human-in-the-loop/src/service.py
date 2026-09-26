from accusec.shared.domain.models import Plan, Principal, new_id


class HitlService:
    """Approve/reject a specific plan version — not slot-filling. Durable when a store is bound."""

    def __init__(self, store=None) -> None:
        self._store = store
        self._approvals: dict[str, dict] = {}

    def _load(self, approval_id: str) -> dict | None:
        record = self._approvals.get(approval_id)
        if record:
            return record
        if self._store:
            record = self._store.get_approval(approval_id)
            if record:
                self._approvals[approval_id] = record
        return record

    def _persist(self, approval_id: str, record: dict) -> None:
        self._approvals[approval_id] = record
        if self._store:
            self._store.save_approval(approval_id, record)

    def request_approval(self, plan: Plan, principal: Principal, task_id: str | None = None) -> str:
        approval_id = new_id("appr")
        record = {
            "plan_id": plan.plan_id,
            "version": plan.version,
            "status": "pending",
            "requester": principal.principal_id,
            "task_id": task_id,
        }
        self._persist(approval_id, record)
        return approval_id

    def decide(self, approval_id: str, approved: bool, approver: Principal, plan: Plan) -> dict:
        record = self._load(approval_id)
        if not record:
            raise ValueError("unknown approval")
        if record["plan_id"] != plan.plan_id or record["version"] != plan.version:
            raise ValueError("approval is bound to a different plan version")
        record["status"] = "approved" if approved else "rejected"
        record["approver"] = approver.principal_id
        self._persist(approval_id, record)
        return record

    def is_approved(self, approval_id: str, plan: Plan) -> bool:
        record = self._load(approval_id)
        if not record:
            return False
        return (
            record["status"] == "approved"
            and record["plan_id"] == plan.plan_id
            and record["version"] == plan.version
        )
