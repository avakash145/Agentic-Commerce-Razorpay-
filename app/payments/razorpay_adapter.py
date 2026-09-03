import os

from decimal import Decimal, ROUND_HALF_UP

import razorpay

from dotenv import load_dotenv


load_dotenv()


class RazorpayAdapter:

    # Razorpay currency decimal rules

    ZERO_DECIMAL_CURRENCIES = {
        "JPY",
        "KRW",
    }

    THREE_DECIMAL_CURRENCIES = {
        "KWD",
        "BHD",
        "OMR",
    }

    # Initialization

    def __init__(self):

        key_id = os.getenv(
            "RAZORPAY_KEY_ID"
        )

        key_secret = os.getenv(
            "RAZORPAY_KEY_SECRET"
        )

        if not key_id:

            raise RuntimeError(
                "RAZORPAY_KEY_ID is missing"
            )

        if not key_secret:

            raise RuntimeError(
                "RAZORPAY_KEY_SECRET is missing"
            )

        # Safety: Test Mode only

        if not key_id.startswith(
            "rzp_test_"
        ):

            raise RuntimeError(
                "Only Razorpay Test Mode keys "
                "are allowed"
            )

        self.client = razorpay.Client(
            auth=(
                key_id,
                key_secret
            )
        )
    # CURRENCY → SUBUNIT CONVERSION

    @classmethod
    def to_subunits(
        cls,
        amount,
        currency: str
    ) -> int:

        currency = currency.upper()

        amount = Decimal(
            str(amount)
        )

        if amount < 0:

            raise ValueError(
                "Amount cannot be negative"
            )
        # Determine decimal precision
        if currency in cls.ZERO_DECIMAL_CURRENCIES:

            decimals = 0

        elif currency in cls.THREE_DECIMAL_CURRENCIES:

            decimals = 3

        else:

            # Most currencies including INR/USD/EUR
            # use two decimal places.
            decimals = 2

        multiplier = Decimal(
            10 ** decimals
        )
        # Convert to smallest currency unit

        subunits = (
            amount * multiplier
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP
        )

        return int(subunits)

    # CREATE RAZORPAY ORDER

    def create_order(
        self,
        amount,
        currency: str,
        receipt: str
    ):

        currency = currency.upper()

        # Validate amount

        if amount <= 0:

            raise ValueError(
                "Order amount must be greater than zero"
            )
        # Convert to Razorpay subunits

        amount_subunits = (
            self.to_subunits(
                amount,
                currency
            )
        )

        # Create Razorpay payload

        data = {
            "amount": amount_subunits,
            "currency": currency,
            "receipt": receipt
        }

        # Razorpay API

        return self.client.order.create(
            data=data
        )