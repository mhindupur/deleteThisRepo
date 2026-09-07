from accusec.agents.aws_pack.pack import ALLOWED_TOOLS


class SkillHarness:
    def __init__(self, mcp, allowlist: frozenset[str] | set[str] | tuple[str, ...] = ALLOWED_TOOLS) -> None:
        self.mcp = mcp
        self.allowlist = set(allowlist)
        self._idempotency: dict[str, object] = {}

    def invoke(self, tool: str, arguments: dict, idempotency_key: str | None = None):
        if tool not in self.allowlist:
            raise PermissionError(f"tool not entitled: {tool}")
        if idempotency_key and idempotency_key in self._idempotency:
            return self._idempotency[idempotency_key]
        result = self.mcp.call(tool, arguments)
        if idempotency_key:
            self._idempotency[idempotency_key] = result
        return result
