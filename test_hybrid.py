from app.catalog.search_service import (
    CatalogSearchService
)


search = CatalogSearchService()


results = search.hybrid_search(
    "laptop for AI development with powerful GPU",
    limit=5
)


for i, product in enumerate(
    results,
    start=1
):

    print()
    print(
        f"========== RESULT {i} =========="
    )

    print(
        "ASIN:",
        product["asin"]
    )

    print(
        "Title:",
        product["title"]
    )

    print(
        "Price:",
        product["price"],
        product["currency"]
    )

    print(
        "Rating:",
        product["stars"]
    )

    print(
        "Lexical rank:",
        product["lexical_rank"]
    )

    print(
        "Semantic rank:",
        product["semantic_rank"]
    )

    print(
        "Similarity:",
        product["similarity"]
    )

    print(
        "Hybrid score:",
        product["hybrid_score"]
    )