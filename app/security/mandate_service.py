from datetime import datetime, timedelta, timezone

from app.models.product import Product
from app.models.purchase_intent import PurchaseIntent
from app.security.mandate import PaymentMandate
from app.security.policy_engine import evaluate_purchase


def create_payment_mandate(
    agent_id: str,
    user_id: str,
    merchant_id: str,
    intent: PurchaseIntent,
    product: Product
) -> PaymentMandate:

    decision = evaluate_purchase(intent, product)

    if not decision.allowed:
        raise PermissionError(
            f"Cannot create mandate: {decision.reason}"
        )

    total = product.price * intent.quantity

    now = datetime.now(timezone.utc)

    expires_at = now + timedelta(minutes=10)

    requires_confirmation = (
        intent.requires_confirmation_above is not None
        and total > intent.requires_confirmation_above
    )

    return PaymentMandate(
        agent_id=agent_id,
        user_id=user_id,
        merchant_id=merchant_id,
        product_id=product.product_id,
        amount=total,
        currency=product.currency,
        quantity=intent.quantity,
        purpose=f"Purchase of {product.name}",
        created_at=now,
        expires_at=expires_at,
        requires_confirmation=requires_confirmation
    )