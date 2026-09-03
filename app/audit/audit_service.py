from app.db.models import AuditEventDB


class AuditService:

    def __init__(self, db):
        self.db = db

    def record(
        self,
        event_id: str,
        actor: str,
        action: str,
        status: str,
        reason: str | None = None
    ):

        event = AuditEventDB(
            event_id=event_id,
            actor=actor,
            action=action,
            status=status,
            reason=reason
        )

        self.db.add(event)

        return event