from app.models.transaction import (
    Transaction,
    TransactionStatus
)


ALLOWED_TRANSITIONS = {

    TransactionStatus.CREATED: {
        TransactionStatus.AUTHORIZED
    },

    TransactionStatus.AUTHORIZED: {
        TransactionStatus.EXECUTING
    },

    TransactionStatus.EXECUTING: {
        TransactionStatus.COMPLETED,
        TransactionStatus.FAILED
    },

    TransactionStatus.COMPLETED: {
        TransactionStatus.REFUNDED
    },

    TransactionStatus.FAILED: set(),

    TransactionStatus.REFUNDED: set()
}


def transition(
    transaction: Transaction,
    new_status: TransactionStatus
):

    current = transaction.status

    allowed = ALLOWED_TRANSITIONS.get(
        current,
        set()
    )

    if new_status not in allowed:

        raise ValueError(
            f"Invalid transition: "
            f"{current} -> {new_status}"
        )

    transaction.status = new_status

    return transaction