from datetime import datetime, timezone

from app.models.product import Product
from app.models.purchase_intent import PurchaseIntent

from app.security.mandate import PaymentMandate
from app.security.mandate_signer import MandateSigner
from app.security.authorization import (
    AuthorizationResult,
    AuthorizationStatus
)


class AuthorizationGateway:

    def __init__(self, signer):
        self.signer = signer

    def authorize(
        self,
        mandate: PaymentMandate,
        signature: bytes,
        intent: PurchaseIntent,
        product: Product
    ) -> AuthorizationResult:

        # 1. Verify cryptographic signature
        if not self.signer.verify(
            mandate,
            signature
        ):
            return AuthorizationResult(
                AuthorizationStatus.REJECTED,
                "Invalid mandate signature"
            )

        # 2. Verify expiry
        now = datetime.now(timezone.utc)

        if now >= mandate.expires_at:
            return AuthorizationResult(
                AuthorizationStatus.REJECTED,
                "Mandate has expired"
            )

        # 3. Verify product binding
        if mandate.product_id != product.product_id:
            return AuthorizationResult(
                AuthorizationStatus.REJECTED,
                "Product does not match mandate"
            )

        # 4. Verify merchant binding
        if not mandate.merchant_id:
            return AuthorizationResult(
                AuthorizationStatus.REJECTED,
                "Merchant is missing"
            )

        # 5. Verify amount
        expected_amount = (
            product.price * mandate.quantity
        )

        if mandate.amount != expected_amount:
            return AuthorizationResult(
                AuthorizationStatus.REJECTED,
                "Mandate amount does not match product price"
            )

        # 6. Verify user budget
        if mandate.amount > intent.max_budget:
            return AuthorizationResult(
                AuthorizationStatus.REJECTED,
                "Transaction exceeds user budget"
            )

        # 7. Verify confirmation requirement
        if mandate.requires_confirmation:
            return AuthorizationResult(
                AuthorizationStatus.CONFIRMATION_REQUIRED,
                "Human confirmation is required"
            )

        # 8. Everything passed
        return AuthorizationResult(
            AuthorizationStatus.AUTHORIZED,
            "Transaction authorized"
        )