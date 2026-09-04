from fastapi import (
    APIRouter,
    Request,
    HTTPException)
from sqlalchemy.exc import IntegrityError
from app.audit.audit_service import (AuditService)
from app.db.database import (SessionLocal)
from app.db.models import (WebhookEventDB)
from app.payments.webhook_verifier import (WebhookVerifier)
from app.payments.transaction_repository import ( TransactionRepository)
from app.payments.transaction_service import (TransactionService)
# ROUTER

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"]
)


# WEBHOOK VERIFIER

verifier = WebhookVerifier()

# RAZORPAY WEBHOOK

@router.post("/razorpay")
async def razorpay_webhook(request: Request):
    # 1. READ RAW REQUEST BODY
    # IMPORTANT:
    # Razorpay signature verification must use the exact
    # raw request body.
    body = await request.body()

    # 2. READ SECURITY HEADERS

    signature = request.headers.get(
        "X-Razorpay-Signature"
    )

    event_id = request.headers.get(
        "x-razorpay-event-id"
    )
    # 3. VALIDATE REQUIRED HEADERS

    if not signature:

        raise HTTPException(
            status_code=400,
            detail="Missing Razorpay signature"
        )


    if not event_id:

        raise HTTPException(
            status_code=400,
            detail="Missing Razorpay event ID"
        )
    # 4. VERIFY RAZORPAY SIGNATURE
    is_valid = verifier.verify(
        payload=body,
        signature=signature
    )
    if not is_valid:

        # NEVER process an unauthenticated webhook.

        raise HTTPException(
            status_code=400,
            detail="Invalid webhook signature"
        )

    # 5. PARSE JSON

    try:

        payload = await request.json()

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload"
        )

    # 6. GET EVENT TYPE

    event_type = payload.get(
        "event"
    )
    print(
    f"[WEBHOOK] "
    f"event_id={event_id} "
    f"event={event_type}"
    )


    if not event_type:

        raise HTTPException(
            status_code=400,
            detail="Missing event type"
        )

    # 7. OPEN DATABASE SESSION

    db = SessionLocal()
    transaction = None


    try:
        # 8. CLAIM WEBHOOK EVENT

        webhook_event = WebhookEventDB(
            event_id=event_id,
            event_type=event_type
        )

        db.add(webhook_event)


        try:

            # PostgreSQL has:
            # UNIQUE(event_id)
            # Therefore concurrent duplicate events
            # cannot both claim the same event.
            db.flush()


        except IntegrityError:

            db.rollback()

            return {
                "status": "already_processed",
                "event_id": event_id
            }
        # 9. INITIALIZE SERVICES

        transaction_repository = (
            TransactionRepository(db)
        )

        transaction_service = (
            TransactionService(
                transaction_repository
            )
        )

        audit_service = (
            AuditService(db)
        )

        # 10. EXTRACT PAYMENT ENTITY

        payment_entity = (
            payload
            .get("payload", {})
            .get("payment", {})
            .get("entity")
        )

        # 11. PAYMENT.AUTHORIZED

        if event_type == "payment.authorized":

            if not payment_entity:

                raise ValueError(
                    "Missing payment entity"
                )


            order_id = payment_entity.get(
                "order_id"
            )

            payment_id = payment_entity.get(
                "id"
            )

            amount = payment_entity.get(
                "amount"
            )

            currency = payment_entity.get(
                "currency"
            )


            # Validate payload

            if not order_id:

                raise ValueError(
                    "Missing Razorpay order_id"
                )


            if not payment_id:

                raise ValueError(
                    "Missing Razorpay payment id"
                )


            if amount is None:

                raise ValueError(
                    "Missing payment amount"
                )


            if not currency:

                raise ValueError(
                    "Missing payment currency"
                )


            # Process transaction

            transaction = (
                transaction_service
                .handle_payment_authorized(
                    order_id=order_id,
                    payment_id=payment_id,
                    amount=amount,
                    currency=currency
                )
            )


            # Audit

            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action="payment.authorized",
                status="SUCCESS",
                reason=(
                    f"Transaction "
                    f"{transaction.transaction_id} "
                    f"authorized"
                )
            )


        # 12. PAYMENT.CAPTURED

        elif event_type == "payment.captured":

            if not payment_entity:

                raise ValueError(
                    "Missing payment entity"
                )


            order_id = payment_entity.get(
                "order_id"
            )

            payment_id = payment_entity.get(
                "id"
            )

            amount = payment_entity.get(
                "amount"
            )

            currency = payment_entity.get(
                "currency"
            )

            # Validate payload

            if not order_id:

                raise ValueError(
                    "Missing Razorpay order_id"
                )


            if not payment_id:

                raise ValueError(
                    "Missing Razorpay payment id"
                )


            if amount is None:

                raise ValueError(
                    "Missing payment amount"
                )


            if not currency:

                raise ValueError(
                    "Missing payment currency"
                )


            # Process transaction

            transaction = (
                transaction_service
                .handle_payment_captured(
                    order_id=order_id,
                    payment_id=payment_id,
                    amount=amount,
                    currency=currency
                )
            )


            # Audit

            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action="payment.captured",
                status="SUCCESS",
                reason=(
                    f"Transaction "
                    f"{transaction.transaction_id} "
                    f"completed"
                )
            )

        # 13. PAYMENT.FAILED

        elif event_type == "payment.failed":

            if not payment_entity:

                raise ValueError(
                    "Missing payment entity"
                )


            order_id = payment_entity.get(
                "order_id"
            )

            payment_id = payment_entity.get(
                "id"
            )

            amount = payment_entity.get(
                "amount"
            )

            currency = payment_entity.get(
                "currency"
            )


            if not order_id:

                raise ValueError(
                    "Missing Razorpay order_id"
                )

            # Process transaction

            transaction = (
                transaction_service
                .handle_payment_failed(
                    order_id=order_id,
                    payment_id=payment_id,
                    amount=amount,
                    currency=currency
                )
            )


            # Audit

            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action="payment.failed",
                status="FAILED",
                reason=(
                    f"Transaction "
                    f"{transaction.transaction_id} "
                    f"payment failed"
                )
            )


        # 14. ORDER.PAID

        elif event_type == "order.paid":

            # We don't independently complete the transaction
            # from order.paid.
            #
            # payment.captured is responsible for the actual
            # transaction state transition.

            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action="order.paid",
                status="RECEIVED",
                reason=(
                    "Razorpay reported order as paid"
                )
            )


        # 15. UNKNOWN EVENT

        else:

            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action=event_type,
                status="IGNORED",
                reason=(
                    "Event type is not currently handled"
                )
            )

        # 16. COMMIT

        # Webhook event
        # +
        # Transaction update
        # +
        # Audit event
        #
        # are committed together.
        print(
            f"[WEBHOOK SUCCESS] "
            f"event_id={event_id} "
            f"transaction={getattr(transaction, 'transaction_id', 'n/a')} "
            f"status={getattr(transaction, 'status', 'recorded')}"
        )
        db.commit()

        # 17. RESPONSE

        return {
            "status": "accepted",
            "event_id": event_id,
            "event": event_type
        }

    # 18. PROCESSING FAILURE
    except ValueError as exc:

        db.rollback()

        print(
            f"[WEBHOOK VALIDATION ERROR] "
            f"{event_id}: {exc}"
        )

        raise HTTPException(
            status_code=400,
            detail="Webhook validation failed"
        )

    except Exception as exc:

        db.rollback()

        print(
            f"[WEBHOOK INTERNAL ERROR] "
            f"{event_id}: {exc}"
        )

        raise HTTPException(
            status_code=500,
            detail="Webhook processing failed"
        )

    # 19. CLOSE DATABASEz

    finally:

        db.close()
