from app.catalog.repository import (
    ProductRepository
)


repository = ProductRepository()


products = repository.search_products(
    "laptop",
    limit=5
)


for product in products:

    print()
    print("-----------------------------")

    print(
        "Product:",
        product.title
    )

    print(
        "ASIN:",
        product.asin
    )

    print(
        "Price:",
        product.price,
        product.currency
    )

    print(
        "Rating:",
        product.rating
    )

    print(
        "Reviews:",
        product.reviews_count
    )

    print(
        "In stock:",
        product.in_stock
    )