from decimal import Decimal

import pytest

from app.models.transaction import TransactionStatus
from app.payments.transaction_service import TransactionService
from app.security.keys import KeyManager


def test_ed25519_key_manager_verifies_only_original_payload():
    manager = KeyManager()
    payload = b"authorized checkout mandate"
    signature = manager.sign(payload)

    assert manager.verify(signature, payload)
    assert not manager.verify(signature, b"tampered checkout mandate")


class FakeTransaction:
    amount = Decimal("70000.00")
    currency = "INR"
    status = TransactionStatus.CREATED.value
    transaction_id = "txn_test"


class FakeRepository:
    def __init__(self, transaction=None):
        self.transaction = transaction

    def get_by_order_id(self, order_id):
        return self.transaction

    def set_payment_id(self, transaction, payment_id):
        transaction.razorpay_payment_id = payment_id
        return transaction

    def update_status(self, transaction, status):
        transaction.status = status.value
        return transaction


def test_capture_rejects_unknown_order_before_dereferencing_it():
    service = TransactionService(FakeRepository())

    with pytest.raises(ValueError, match="Unknown Razorpay order"):
        service.handle_payment_captured(
            order_id="order_unknown",
            payment_id="pay_test",
            amount=7000000,
            currency="INR",
        )


def test_capture_rejects_amount_tampering():
    transaction = FakeTransaction()
    service = TransactionService(FakeRepository(transaction))

    with pytest.raises(ValueError, match="amount does not match"):
        service.handle_payment_captured(
            order_id="order_test",
            payment_id="pay_test",
            amount=8000000,
            currency="INR",
        )
