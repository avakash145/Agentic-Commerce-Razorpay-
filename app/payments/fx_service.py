from decimal import (
    Decimal,
    ROUND_HALF_UP
)

from datetime import (
    datetime,
    timezone
)

import requests


class FXService:

    BASE_URL = "https://api.frankfurter.app"

    # NORMALIZE CURRENCY

    def normalize_currency(
        self,
        currency: str
    ) -> str:

        if not currency:
            raise ValueError(
                "Currency is missing"
            )

        value = str(
            currency
        ).strip().upper()

        mapping = {

            "$": "USD",

            "US$": "USD",

            "USD": "USD",

            "₹": "INR",

            "RS": "INR",

            "RS.": "INR",

            "INR": "INR",

            "€": "EUR",

            "EUR": "EUR",

            "£": "GBP",

            "GBP": "GBP",

            "¥": "JPY",

            "JPY": "JPY"
        }

        return mapping.get(
            value,
            value
        )

    # GET FX RATE

    def get_rate(
        self,
        from_currency: str,
        to_currency: str = "INR"
    ) -> Decimal:

        from_currency = (
            self.normalize_currency(
                from_currency
            )
        )

        to_currency = (
            self.normalize_currency(
                to_currency
            )
        )


        if from_currency == to_currency:

            return Decimal("1")


        url = (
            f"{self.BASE_URL}/latest"
            f"?from={from_currency}"
            f"&to={to_currency}"
        )


        response = requests.get(

            url,

            timeout=15
        )


        response.raise_for_status()


        data = response.json()


        try:

            rate = Decimal(
                str(
                    data[
                        "rates"
                    ][
                        to_currency
                    ]
                )
            )

        except KeyError:

            raise ValueError(

                f"No FX rate available for "
                f"{from_currency} -> "
                f"{to_currency}"
            )


        return rate


    # CONVERT TO INR

    def convert_to_inr(
        self,
        amount: Decimal,
        currency: str
    ):

        currency = (
            self.normalize_currency(
                currency
            )
        )


        amount = Decimal(
            str(amount)
        )


        # ALREADY INR
        if currency == "INR":

            return {

                "source_amount":
                    amount,

                "source_currency":
                    "INR",

                "target_amount":
                    amount.quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP
                    ),

                "target_currency":
                    "INR",

                "rate":
                    Decimal("1"),

                "timestamp":
                    datetime.now(
                        timezone.utc
                    )
            }


        # FX

        rate = self.get_rate(

            currency,

            "INR"
        )


        converted = (

            amount * rate

        ).quantize(

            Decimal("0.01"),

            rounding=ROUND_HALF_UP
        )


        return {

            "source_amount":
                amount,

            "source_currency":
                currency,

            "target_amount":
                converted,

            "target_currency":
                "INR",

            "rate":
                rate,

            "timestamp":
                datetime.now(
                    timezone.utc
                )
        }