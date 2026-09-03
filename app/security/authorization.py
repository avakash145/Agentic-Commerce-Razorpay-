from enum import Enum

from app.security.mandate import PaymentMandate


class AuthorizationStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"


class AuthorizationResult:

    def __init__(
        self,
        status: AuthorizationStatus,
        reason: str
    ):
        self.status = status
        self.reason = reason

    @property
    def allowed(self) -> bool:
        return self.status == AuthorizationStatus.AUTHORIZED