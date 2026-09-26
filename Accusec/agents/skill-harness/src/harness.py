from accusec.agents.aws_pack.pack import ALLOWED_TOOLS

WRITE_TOOLS = frozenset({"aws.ec2.stop_instances", "aws.ec2.start_instances", "aws.ec2.modify_volume"})


class SkillHarness:
    def __init__(self, mcp, allowlist: frozenset[str] | set[str] | tuple[str, ...] = ALLOWED_TOOLS) -> None:
        self.mcp = mcp
        self.allowlist = set(allowlist)
        self._idempotency: dict[str, object] = {}
        self.execution_context: dict[str, str | None] = {}

    def invoke(self, tool: str, arguments: dict, idempotency_key: str | None = None):
        if tool not in self.allowlist:
            raise PermissionError(f"tool not entitled: {tool}")
        identity_type = (self.execution_context or {}).get("identity_type")
        if tool in WRITE_TOOLS and identity_type == "READ_ONLY":
            raise PermissionError("READ_ONLY identity cannot invoke write tools")
        if idempotency_key and idempotency_key in self._idempotency:
            return self._idempotency[idempotency_key]
        result = self.mcp.call(tool, arguments)
        if idempotency_key:
            self._idempotency[idempotency_key] = result
        return result
