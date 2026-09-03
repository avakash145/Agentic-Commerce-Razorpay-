from app.security.action_models import CreateOrderRequest
from app.security.tool_registry import (
    AllowedTool,
    ALLOWED_TOOLS
)


class SecureActionGateway:

    def __init__(
        self,
        authorization_gateway,
        idempotency_store,
        transaction_repository
    ):

        self.authorization_gateway = (
            authorization_gateway
        )

        self.idempotency_store = (
            idempotency_store
        )

        self.transaction_repository = (
            transaction_repository
        )
    # CREATE ORDER

    def create_order(
        self,
        mandate,
        signature,
        intent,
        product,
        request: CreateOrderRequest,
        razorpay_adapter
    ):
        # 1. TOOL AUTHORIZATION

        if (
            AllowedTool.CREATE_ORDER
            not in ALLOWED_TOOLS
        ):

            raise PermissionError(
                "CREATE_ORDER tool is not authorized"
            )

        # 2. MANDATE ID BINDING

        if (
            request.mandate_id
            != mandate.mandate_id
        ):

            raise PermissionError(
                "Mandate mismatch"
            )
        # 3. CURRENCY BINDING

        if (
            request.currency.upper()
            != mandate.currency.upper()
        ):

            raise PermissionError(
                "Currency does not match mandate"
            )
        # 4. AMOUNT BINDING

        if request.amount != mandate.amount:

            raise PermissionError(
                "Amount does not match mandate"
            )

        # 5. AUTHORIZATION

        authorization = (
            self.authorization_gateway.authorize(
                mandate=mandate,
                signature=signature,
                intent=intent,
                product=product
            )
        )

        if not authorization.allowed:

            raise PermissionError(
                authorization.reason
            )

        # 6. IDEMPOTENCY

        idempotency_key = (
            mandate.idempotency_key
        )

        existing_result = (
            self.idempotency_store.get(
                idempotency_key
            )
        )

        if existing_result is not None:

            return existing_result

        # 7. CREATE RAZORPAY ORDER

        result = razorpay_adapter.create_order(
            amount=mandate.amount,
            currency=mandate.currency,
            receipt=mandate.mandate_id
        )

        # 8. VERIFY RAZORPAY RESPONSE

        if not result.get("id"):

            raise RuntimeError(
                "Razorpay did not return an order ID"
            )

        razorpay_amount = result.get(
            "amount"
        )

        razorpay_currency = result.get(
            "currency"
        )

        # IMPORTANT:
        # Razorpay amount is in subunits.
        # The adapter should already have converted
        # the mandate amount to subunits.

        expected_amount = (
            razorpay_adapter.to_subunits(
                mandate.amount,
                mandate.currency
            )
        )

        if razorpay_amount != expected_amount:

            raise RuntimeError(
                "Razorpay amount does not "
                "match authorized amount"
            )

        if (
            razorpay_currency.upper()
            != mandate.currency.upper()
        ):

            raise RuntimeError(
                "Razorpay currency does not "
                "match authorized currency"
            )
        # 9. CREATE LOCAL TRANSACTION

        transaction_id = (
            f"txn_{mandate.mandate_id}"
        )

        transaction = (
            self.transaction_repository.create(
                transaction_id=transaction_id,

                mandate_id=mandate.mandate_id,

                razorpay_order_id=result["id"],

                amount=mandate.amount,

                currency=mandate.currency,

                source_amount=getattr(
                    mandate,
                    "source_amount",
                    None
                ),

                source_currency=getattr(
                    mandate,
                    "source_currency",
                    None
                ),

                fx_rate=getattr(
                    mandate,
                    "fx_rate",
                    None
                ),

                fx_timestamp=getattr(
                    mandate,
                    "fx_timestamp",
                    None
                )
            )
        )

        # 10. SAVE IDEMPOTENCY RESULT

        self.idempotency_store.save(
            idempotency_key,
            result
        )

        return result