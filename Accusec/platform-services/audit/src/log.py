from accusec.shared.domain.models import AuditEvent


class AuditLog:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        payload = dict(event.payload)
        for key in list(payload):
            lowered = key.lower()
            if lowered in {
                "password",
                "secret_access_key",
                "access_key_id",
                "credential",
                "credentials",
                "session_token",
                "secret",
            } or lowered.endswith("_secret"):
                payload[key] = "[redacted]"
        event.payload = payload
        self.events.append(event)

    def for_correlation(self, correlation_id: str) -> list[AuditEvent]:
        return [e for e in self.events if e.correlation_id == correlation_id]
