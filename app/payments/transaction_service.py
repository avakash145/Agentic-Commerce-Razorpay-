from decimal import Decimal

from app.models.transaction import TransactionStatus


class TransactionService:

    def __init__(self, repository):
        self.repository = repository

    # Helpers

    @staticmethod
    def _normalise_currency(
        currency: str
    ) -> str:

        if not currency:
            raise ValueError(
                "Currency is missing"
            )

        return currency.upper()

    @staticmethod
    def _amount_matches(
        transaction_amount: Decimal,
        razorpay_amount: int,
        currency: str
    ) -> bool:

        currency = currency.upper()

        # Razorpay uses currency subunits.
        #
        # Two decimal currencies:
        #     ₹100 -> 10000
        #
        # Zero decimal:
        #     ¥100 -> 100
        #
        # Three decimal:
        #     KWD 100 -> 100000

        zero_decimal = {
            "JPY",
            "KRW"
        }

        three_decimal = {
            "KWD",
            "BHD",
            "OMR"
        }

        if currency in zero_decimal:
            multiplier = Decimal("1")

        elif currency in three_decimal:
            multiplier = Decimal("1000")

        else:
            multiplier = Decimal("100")

        expected = (
            transaction_amount
            * multiplier
        )

        return int(expected) == int(
            razorpay_amount
        )

    # PAYMENT AUTHORIZED

    def handle_payment_authorized(
        self,
        order_id: str,
        payment_id: str,
        amount: int,
        currency: str
    ):

        transaction = (
            self.repository.get_by_order_id(
                order_id
            )
        )

        if not transaction:
            raise ValueError(
                f"Unknown Razorpay order: {order_id}"
            )

        currency = self._normalise_currency(
            currency
        )

        if transaction.currency.upper() != currency:
            raise ValueError(
                "Payment currency does not "
                "match transaction currency"
            )

        if not self._amount_matches(
            Decimal(str(transaction.amount)),
            amount,
            currency
        ):
            raise ValueError(
                "Payment amount does not "
                "match transaction amount"
            )

        self.repository.set_payment_id(
            transaction,
            payment_id
        )

        current = transaction.status

        # Already authorized or beyond.
        if current in {
            TransactionStatus.AUTHORIZED.value,
            TransactionStatus.EXECUTING.value,
            TransactionStatus.COMPLETED.value
        }:
            return transaction

        if current == TransactionStatus.CREATED.value:

            self.repository.update_status(
                transaction,
                TransactionStatus.AUTHORIZED
            )

            return transaction

        raise ValueError(
            f"Cannot authorize transaction "
            f"from state: {current}"
        )

    # PAYMENT CAPTURED

    def handle_payment_captured(
        self,
        order_id: str,
        payment_id: str,
        amount: int,
        currency: str
    ):
        

        transaction = (
            self.repository.get_by_order_id(
                order_id
            )
        )
        if not transaction:
            raise ValueError(
                f"Unknown Razorpay order: {order_id}"
            )

        currency = self._normalise_currency(
            currency
        )

        # Currency binding

        if transaction.currency.upper() != currency:
            raise ValueError(
                "Payment currency does not "
                "match transaction currency"
            )

        # Amount binding

        if not self._amount_matches(
            Decimal(str(transaction.amount)),
            amount,
            currency
        ):
            raise ValueError(
                "Payment amount does not "
                "match transaction amount"
            )
        # Bind Razorpay payment

        self.repository.set_payment_id(
            transaction,
            payment_id
        )

        current = transaction.status

        # Idempotency

        if current == (
            TransactionStatus.COMPLETED.value
        ):
            return transaction

        # Valid states for capture

        valid_states = {
            TransactionStatus.CREATED.value,
            TransactionStatus.AUTHORIZED.value,
            TransactionStatus.EXECUTING.value
        }

        if current not in valid_states:
            raise ValueError(
                f"Cannot complete transaction "
                f"from state: {current}"
            )

        # Complete transaction

        self.repository.update_status(
            transaction,
            TransactionStatus.COMPLETED
        )

        return transaction

    # PAYMENT FAILED

    def handle_payment_failed(
        self,
        order_id: str,
        payment_id: str | None,
        amount: int | None,
        currency: str | None
    ):

        transaction = (
            self.repository.get_by_order_id(
                order_id
            )
        )

        if not transaction:
            raise ValueError(
                f"Unknown Razorpay order: {order_id}"
            )

        # Don't turn a completed payment into FAILED

        if transaction.status == (
            TransactionStatus.COMPLETED.value
        ):
            return transaction

        if payment_id:

            self.repository.set_payment_id(
                transaction,
                payment_id
            )

        # Validate currency if supplied

        if currency:

            currency = self._normalise_currency(
                currency
            )

            if (
                transaction.currency.upper()
                != currency
            ):
                raise ValueError(
                    "Failed payment currency "
                    "does not match transaction"
                )

        # Validate amount if supplied

        if amount is not None:

            if not self._amount_matches(
                Decimal(str(transaction.amount)),
                amount,
                transaction.currency
            ):
                raise ValueError(
                    "Failed payment amount "
                    "does not match transaction"
                )

        # Update state

        self.repository.update_status(
            transaction,
            TransactionStatus.FAILED
        )

        return transaction
