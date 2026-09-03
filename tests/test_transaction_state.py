import pytest

from app.models.transaction import (
    Transaction,
    TransactionStatus
)

from app.payments.transaction_state import (
    transition
)


def test_valid_transaction_flow():

    transaction = Transaction(
        transaction_id="txn_test_001",
        mandate_id="mandate_test_001",
        amount=70000,
        currency="INR"
    )

    transition(
        transaction,
        TransactionStatus.AUTHORIZED
    )

    assert transaction.status == (
        TransactionStatus.AUTHORIZED
    )

    transition(
        transaction,
        TransactionStatus.EXECUTING
    )

    assert transaction.status == (
        TransactionStatus.EXECUTING
    )

    transition(
        transaction,
        TransactionStatus.COMPLETED
    )

    assert transaction.status == (
        TransactionStatus.COMPLETED
    )


def test_invalid_transaction_flow():

    transaction = Transaction(
        transaction_id="txn_test_002",
        mandate_id="mandate_test_002",
        amount=70000,
        currency="INR"
    )

    with pytest.raises(ValueError):

        transition(
            transaction,
            TransactionStatus.COMPLETED
        )