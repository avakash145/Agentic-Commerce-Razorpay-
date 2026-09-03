from decimal import Decimal, ROUND_HALF_UP


CURRENCY_DECIMALS = {
    "JPY": 0,
    "KRW": 0,

    "KWD": 3,
    "BHD": 3,
    "OMR": 3,
}


CURRENCY_ALIASES = {
    "$": "USD",
    "US$": "USD",
    "USD": "USD",

    "€": "EUR",
    "EUR": "EUR",

    "£": "GBP",
    "GBP": "GBP",

    "₹": "INR",
    "INR": "INR",

    "¥": "JPY",
    "JPY": "JPY",

    "CNY": "CNY",
    "RMB": "CNY",

    "CAD": "CAD",
    "AUD": "AUD",
    "SGD": "SGD",
}


def normalize_currency(
    currency: str
) -> str:

    if not currency:
        raise ValueError(
            "Currency is required"
        )

    normalized = (
        currency
        .strip()
        .upper()
    )

    try:
        return CURRENCY_ALIASES[
            normalized
        ]

    except KeyError:

        raise ValueError(
            f"Unsupported currency: "
            f"{currency}"
        )


def to_subunits(
    amount: Decimal,
    currency: str
) -> int:

    currency = normalize_currency(
        currency
    )

    decimals = (
        CURRENCY_DECIMALS.get(
            currency,
            2
        )
    )

    multiplier = Decimal(
        10 ** decimals
    )

    return int(
        (
            amount * multiplier
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP
        )
    )