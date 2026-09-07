from accusec.security.engine import PolicyEngine
from accusec.shared.domain.models import AuthzKind, Entity, OperationalRequest, PolicyDecision, Principal, Scope


class AuthorizationService:
    def __init__(self, engine: PolicyEngine | None = None) -> None:
        self.engine = engine or PolicyEngine()

    def context_access(self, request: OperationalRequest, entities: list[Entity]) -> tuple[list[Entity], PolicyDecision]:
        return self.engine.filter_entities(
            request.principal,
            request.operation_id,
            entities,
            request.scopes,
            AuthzKind.CONTEXT_ACCESS,
        )

    def execution(self, principal: Principal, operation_id: str, entity: Entity, scopes: list[Scope]) -> PolicyDecision:
        return self.engine.evaluate(
            principal,
            operation_id,
            AuthzKind.EXECUTION,
            entity=entity,
            scopes=scopes,
        )
