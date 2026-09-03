from pydantic import BaseModel, Field
from datetime import datetime, timezone
from uuid import uuid4

class PaymentMandate(BaseModel):

    mandate_id: str = Field(
        default_factory=lambda: f"mandate_{uuid4().hex}"
    )

    nonce: str = Field(
        default_factory=lambda: uuid4().hex
    )

    idempotency_key: str = Field(
        default_factory=lambda: f"payment_{uuid4().hex}"
    )

    agent_id: str

    user_id: str

    merchant_id: str

    product_id: str

    amount: int

    currency: str = "INR"

    quantity: int = Field(default=1, ge=1)

    purpose: str

    created_at: datetime

    expires_at: datetime

    status: str = "PENDING"

    requires_confirmation: bool = False