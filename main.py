from app.models.product import Product
from app.models.purchase_intent import PurchaseIntent

from app.security.mandate_service import (
    create_payment_mandate
)

from app.security.keys import KeyManager
from app.security.mandate_signer import MandateSigner

from app.security.authorization_gateway import (
    AuthorizationGateway
)

from app.security.action_gateway import (
    SecureActionGateway
)

from app.security.idempotency import (
    IdempotencyStore
)

from app.security.action_models import (
    CreateOrderRequest
)

from app.payments.razorpay_adapter import (
    RazorpayAdapter
)

from app.db.database import SessionLocal

from app.payments.transaction_repository import (
    TransactionRepository
)


def main():
    # 1. USER INTENT

    intent = PurchaseIntent(
        query="AI laptop",
        max_budget=80000,
        allowed_categories=[
            "electronics"
        ],
        requires_confirmation_above=75000
    )

    # 2. PRODUCT

    product = Product(
        product_id="prod_001",
        name="RTX AI Laptop",
        price=70000,
        category="electronics",
        description=(
            "Laptop suitable for AI development"
        ),
        stock=5
    )


    # 3. CREATE PAYMENT MANDATE

    mandate = create_payment_mandate(
        agent_id="agent_001",
        user_id="user_001",
        merchant_id="merchant_001",
        intent=intent,
        product=product
    )

    print("\nPayment Mandate")
    print("----------------------")
    print("Mandate ID:", mandate.mandate_id)
    print("Amount:", mandate.amount)
    print("Currency:", mandate.currency)


    # 4. SIGN MANDATE

    key_manager = KeyManager()

    signer = MandateSigner(
        key_manager
    )

    signature = signer.sign(
        mandate
    )


    # 5. AUTHORIZATION GATEWAY

    authorization_gateway = (
        AuthorizationGateway(
            signer
        )
    )

    # 6. IDEMPOTENCY

    idempotency_store = (
        IdempotencyStore()
    )

    # 7. DATABASE

    db = SessionLocal()

    try:

        transaction_repository = (
            TransactionRepository(db)
        )

        # 8. SECURE ACTION GATEWAY

        action_gateway = SecureActionGateway(
            authorization_gateway=(
                authorization_gateway
            ),

            idempotency_store=(
                idempotency_store
            ),

            transaction_repository=(
                transaction_repository
            )
        )


        # 9. RAZORPAY

        razorpay_adapter = RazorpayAdapter()


        # 10. ACTION REQUEST

        request = CreateOrderRequest(
            mandate_id=mandate.mandate_id,
            amount=mandate.amount,
            currency=mandate.currency,
            receipt=mandate.mandate_id
        )


        # 11. EXECUTE SECURE ACTION

        result = action_gateway.create_order(
            mandate=mandate,
            signature=signature,
            intent=intent,
            product=product,
            request=request,
            razorpay_adapter=razorpay_adapter
        )

        # 12. RESULT

        print("\nRazorpay Order Created")
        print("----------------------")

        print(
            "Order ID:",
            result["id"]
        )

        print(
            "Amount:",
            result["amount"]
        )

        print(
            "Currency:",
            result["currency"]
        )

        print(
            "Status:",
            result["status"]
        )

        # 13. DATABASE TRANSACTION

        transaction = (
            transaction_repository.get_by_order_id(
                result["id"]
            )
        )

        if transaction:

            print("\nLocal Transaction")
            print("----------------------")

            print(
                "Transaction ID:",
                transaction.transaction_id
            )

            print(
                "Mandate ID:",
                transaction.mandate_id
            )

            print(
                "Razorpay Order ID:",
                transaction.razorpay_order_id
            )

            print(
                "Amount:",
                transaction.amount
            )

            print(
                "Currency:",
                transaction.currency
            )

            print(
                "Status:",
                transaction.status
            )

        else:

            print(
                "\nWARNING: "
                "Transaction was not found."
            )


    finally:

        db.close()

# APPLICATION ENTRY POINT

if __name__ == "__main__":
    main()