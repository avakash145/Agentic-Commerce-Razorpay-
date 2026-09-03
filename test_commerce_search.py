from app.agent.commerce_search import (
    CommerceSearchService
)


service = (
    CommerceSearchService()
)


queries = [

    "Find me an AI laptop under ₹80000",

    (
        "Find me a gaming laptop "
        "under ₹1 lakh with at least "
        "16GB RAM and an RTX GPU"
    ),

    (
        "I need a laptop with "
        "at least 16GB RAM and "
        "512GB storage"
    )
]


for query in queries:

    print()
    print(
        "======================================"
    )

    print(
        "USER:",
        query
    )

    print(
        "======================================"
    )

    try:

        result = service.search(
            query
        )

        intent = result[
            "intent"
        ]

        products = result[
            "products"
        ]

        print()
        print(
            "STRUCTURED INTENT:"
        )

        print(
            intent.model_dump_json(
                indent=2
            )
        )

        print()
        print(
            "Candidates:",
            result[
                "candidate_count"
            ]
        )

        print(
            "Eligible:",
            result[
                "result_count"
            ]
        )

        print()

        for index, product in enumerate(
            products,
            start=1
        ):

            print(
                f"========== "
                f"PRODUCT {index} "
                f"=========="
            )

            print(
                "ASIN:",
                product.get(
                    "asin"
                )
            )

            print(
                "Title:",
                product.get(
                    "title"
                )
            )

            print(
                "Original price:",
                product.get(
                    "price"
                ),
                product.get(
                    "currency"
                )
            )

            print(
                "INR price:",
                product.get(
                    "price_inr"
                )
            )

            print(
                "Rating:",
                product.get(
                    "stars"
                )
            )

            specs = product.get(
                "specs",
                {}
            )

            print(
                "RAM:",
                specs.get(
                    "ram_gb"
                )
            )

            print(
                "Storage:",
                specs.get(
                    "storage_gb"
                )
            )

            print(
                "GPU:",
                specs.get(
                    "gpu"
                )
            )

            print(
                "CPU:",
                specs.get(
                    "cpu"
                )
            )

            print()

    except Exception as exc:

        print(
            "\nPIPELINE ERROR:"
        )

        print(
            type(exc).__name__,
            str(exc)
        )