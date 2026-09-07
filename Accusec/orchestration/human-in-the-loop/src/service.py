from accusec.shared.domain.models import Plan, Principal, new_id


class HitlService:
    """Approve/reject a specific plan version — not slot-filling."""

    def __init__(self) -> None:
        self._approvals: dict[str, dict] = {}

    def request_approval(self, plan: Plan, principal: Principal) -> str:
        approval_id = new_id("appr")
        self._approvals[approval_id] = {
            "plan_id": plan.plan_id,
            "version": plan.version,
            "status": "pending",
            "requester": principal.principal_id,
        }
        return approval_id

    def decide(self, approval_id: str, approved: bool, approver: Principal, plan: Plan) -> dict:
        record = self._approvals[approval_id]
        if record["plan_id"] != plan.plan_id or record["version"] != plan.version:
            raise ValueError("approval is bound to a different plan version")
        record["status"] = "approved" if approved else "rejected"
        record["approver"] = approver.principal_id
        return record

    def is_approved(self, approval_id: str, plan: Plan) -> bool:
        record = self._approvals.get(approval_id)
        if not record:
            return False
        return (
            record["status"] == "approved"
            and record["plan_id"] == plan.plan_id
            and record["version"] == plan.version
        )
