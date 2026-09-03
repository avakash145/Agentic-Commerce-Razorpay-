from enum import Enum
from decimal import Decimal

from pydantic import BaseModel


class TransactionStatus(str, Enum):

    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"

    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class Transaction(BaseModel):

    transaction_id: str

    mandate_id: str

    razorpay_order_id: str | None = None

    razorpay_payment_id: str | None = None

    amount: Decimal

    currency: str

    status: TransactionStatus = (
        TransactionStatus.CREATED
    )
