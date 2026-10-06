import json
from decimal import Decimal
from django.http import (
    JsonResponse,
    HttpResponse,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from sqlalchemy.exc import IntegrityError

from app.audit.audit_service import AuditService
from app.db.database import SessionLocal
from app.db.models import WebhookEventDB
from app.payments.webhook_verifier import WebhookVerifier
from app.payments.transaction_repository import TransactionRepository
from app.payments.transaction_service import TransactionService

# WEBHOOK VERIFIER
verifier = WebhookVerifier()


# RAZORPAY WEBHOOK
@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Django view for Razorpay Webhook events.
    Verifies HMAC signature, claims webhook idempotently in PostgreSQL,
    and updates transaction state.
    """
    # 1. READ RAW REQUEST BODY
    body = request.body

    # 2. READ SECURITY HEADERS
    signature = (
        request.headers.get("X-Razorpay-Signature")
        or request.META.get("HTTP_X_RAZORPAY_SIGNATURE")
    )
    event_id = (
        request.headers.get("x-razorpay-event-id")
        or request.headers.get("X-Razorpay-Event-Id")
        or request.META.get("HTTP_X_RAZORPAY_EVENT_ID")
    )

    # 3. VALIDATE REQUIRED HEADERS
    if not signature:
        return JsonResponse(
            {"detail": "Missing Razorpay signature"},
            status=400
        )

    if not event_id:
        return JsonResponse(
            {"detail": "Missing Razorpay event ID"},
            status=400
        )

    # 4. VERIFY RAZORPAY SIGNATURE
    is_valid = verifier.verify(
        payload=body,
        signature=signature
    )
    if not is_valid:
        return JsonResponse(
            {"detail": "Invalid webhook signature"},
            status=400
        )

    # 5. PARSE JSON
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return JsonResponse(
            {"detail": "Invalid JSON payload"},
            status=400
        )

    # 6. GET EVENT TYPE
    event_type = payload.get("event")
    print(f"[WEBHOOK] event_id={event_id} event={event_type}")

    if not event_type:
        return JsonResponse(
            {"detail": "Missing event type"},
            status=400
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
            # PostgreSQL UNIQUE(event_id) ensures concurrent duplicates are rejected
            db.flush()
        except IntegrityError:
            db.rollback()
            return JsonResponse({
                "status": "already_processed",
                "event_id": event_id
            })

        # 9. INITIALIZE SERVICES
        transaction_repository = TransactionRepository(db)
        transaction_service = TransactionService(transaction_repository)
        audit_service = AuditService(db)

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
                raise ValueError("Missing payment entity")

            order_id = payment_entity.get("order_id")
            payment_id = payment_entity.get("id")
            amount = payment_entity.get("amount")
            currency = payment_entity.get("currency")

            if not order_id:
                raise ValueError("Missing Razorpay order_id")
            if not payment_id:
                raise ValueError("Missing Razorpay payment id")
            if amount is None:
                raise ValueError("Missing payment amount")
            if not currency:
                raise ValueError("Missing payment currency")

            transaction = transaction_service.handle_payment_authorized(
                order_id=order_id,
                payment_id=payment_id,
                amount=amount,
                currency=currency
            )

            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action="payment.authorized",
                status="SUCCESS",
                reason=f"Transaction {transaction.transaction_id} authorized"
            )

        # 12. PAYMENT.CAPTURED
        elif event_type == "payment.captured":
            if not payment_entity:
                raise ValueError("Missing payment entity")

            order_id = payment_entity.get("order_id")
            payment_id = payment_entity.get("id")
            amount = payment_entity.get("amount")
            currency = payment_entity.get("currency")

            if not order_id:
                raise ValueError("Missing Razorpay order_id")
            if not payment_id:
                raise ValueError("Missing Razorpay payment id")
            if amount is None:
                raise ValueError("Missing payment amount")
            if not currency:
                raise ValueError("Missing payment currency")

            transaction = transaction_service.handle_payment_captured(
                order_id=order_id,
                payment_id=payment_id,
                amount=amount,
                currency=currency
            )

            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action="payment.captured",
                status="SUCCESS",
                reason=f"Transaction {transaction.transaction_id} completed"
            )

        # 13. PAYMENT.FAILED
        elif event_type == "payment.failed":
            if not payment_entity:
                raise ValueError("Missing payment entity")

            order_id = payment_entity.get("order_id")
            payment_id = payment_entity.get("id")
            amount = payment_entity.get("amount")
            currency = payment_entity.get("currency")

            if not order_id:
                raise ValueError("Missing Razorpay order_id")

            transaction = transaction_service.handle_payment_failed(
                order_id=order_id,
                payment_id=payment_id,
                amount=amount,
                currency=currency
            )

            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action="payment.failed",
                status="FAILED",
                reason=f"Transaction {transaction.transaction_id} payment failed"
            )

        # 14. ORDER.PAID
        elif event_type == "order.paid":
            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action="order.paid",
                status="RECEIVED",
                reason="Razorpay reported order as paid"
            )

        # 15. UNKNOWN EVENT
        else:
            audit_service.record(
                event_id=event_id,
                actor="razorpay",
                action=event_type,
                status="IGNORED",
                reason="Event type is not currently handled"
            )

        # 16. COMMIT
        print(
            f"[WEBHOOK SUCCESS] "
            f"event_id={event_id} "
            f"transaction={getattr(transaction, 'transaction_id', 'n/a')} "
            f"status={getattr(transaction, 'status', 'recorded')}"
        )
        db.commit()

        # 17. RESPONSE
        return JsonResponse({
            "status": "accepted",
            "event_id": event_id,
            "event": event_type
        })

    except ValueError as exc:
        db.rollback()
        print(f"[WEBHOOK VALIDATION ERROR] {event_id}: {exc}")
        return JsonResponse(
            {"detail": f"Webhook validation failed: {exc}"},
            status=400
        )

    except Exception as exc:
        db.rollback()
        print(f"[WEBHOOK INTERNAL ERROR] {event_id}: {exc}")
        return JsonResponse(
            {"detail": "Webhook processing failed"},
            status=500
        )

    finally:
        db.close()
