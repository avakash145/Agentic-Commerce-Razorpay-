from app.agent.intent_parser import (
    IntentParser
)


parser = IntentParser()


queries = [

    "Find me an AI laptop under ₹80000",

    "I need a gaming laptop with at least "
    "16GB RAM and an RTX GPU",

    "Find me a laptop under 80000 with "
    "512GB storage and at least 4 star rating"
]


for query in queries:

    print()
    print(
        "================================"
    )

    print(
        "USER:",
        query
    )

    print()

    intent = parser.parse(
        query
    )

    print(
        intent.model_dump_json(
            indent=2
        )
    )