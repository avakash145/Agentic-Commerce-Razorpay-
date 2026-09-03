from datetime import datetime, timezone

from app.db.models import TransactionDB
from app.models.transaction import TransactionStatus


class TransactionRepository:

    def __init__(self, db):
        self.db = db

    def create(
        self,
        transaction_id: str,
        mandate_id: str,
        razorpay_order_id: str,
        amount,
        currency: str,
        source_amount=None,
        source_currency=None,
        fx_rate=None,
        fx_timestamp=None
    ):

        transaction = TransactionDB(
            transaction_id=transaction_id,
            mandate_id=mandate_id,

            razorpay_order_id=razorpay_order_id,

            amount=amount,
            currency=currency,

            source_amount=source_amount,
            source_currency=source_currency,
            fx_rate=fx_rate,
            fx_timestamp=fx_timestamp,

            status=TransactionStatus.CREATED.value
        )

        self.db.add(transaction)

        self.db.commit()

        self.db.refresh(transaction)

        return transaction

    def get_by_order_id(
        self,
        razorpay_order_id: str
    ):

        return (
            self.db.query(TransactionDB)
            .filter(
                TransactionDB.razorpay_order_id
                == razorpay_order_id
            )
            .first()
        )

    def update_status(
        self,
        transaction,
        status: TransactionStatus
    ):

        transaction.status = status.value
        transaction.updated_at = (
            datetime.now(timezone.utc)
        )

        self.db.commit()
        self.db.refresh(transaction)

        return transaction

    def set_payment_id(
        self,
        transaction,
        payment_id: str
    ):

        transaction.razorpay_payment_id = payment_id
        transaction.updated_at = (
            datetime.now(timezone.utc)
        )

        self.db.commit()
        self.db.refresh(transaction)

        return transaction