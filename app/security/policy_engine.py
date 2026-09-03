from app.models.product import Product
from app.models.purchase_intent import PurchaseIntent


class PolicyDecision:

    def __init__(self, allowed: bool, reason: str):
        self.allowed = allowed
        self.reason = reason


def evaluate_purchase(
    intent: PurchaseIntent,
    product: Product
) -> PolicyDecision:

    total = product.price * intent.quantity

    if product.stock < intent.quantity:
        return PolicyDecision(
            False,
            "Insufficient stock"
        )

    if total > intent.max_budget:
        return PolicyDecision(
            False,
            "Purchase exceeds authorized budget"
        )

    if (
        intent.allowed_categories
        and product.category not in intent.allowed_categories
    ):
        return PolicyDecision(
            False,
            "Product category is not authorized"
        )

    if (
        intent.requires_confirmation_above is not None
        and total > intent.requires_confirmation_above
    ):
        return PolicyDecision(
            False,
            "Human confirmation required"
        )

    return PolicyDecision(
        True,
        "Purchase satisfies current policy"
    )
