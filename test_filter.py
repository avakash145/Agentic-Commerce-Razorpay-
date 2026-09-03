from app.catalog.search_service import CatalogSearchService
from app.catalog.filter_service import ProductFilterService


search_service = CatalogSearchService()
filter_service = ProductFilterService()


print("\nSearching...\n")

candidates = search_service.hybrid_search(
    query="laptop for AI development with powerful GPU",
    limit=20
)

print(
    f"Candidates found: {len(candidates)}"
)

# 1. SHOW RETRIEVED PRODUCTS

print("\n========== CANDIDATES ==========\n")

for product in candidates:

    print(
        product["product_id"],
        "|",
        product["asin"],
        "|",
        product["title"]
    )

# 2. PRICE ONLY

print("\n========== PRICE ==========\n")

price_results = filter_service.filter_products(
    candidates,
    max_price_inr=80000
)

print(
    "After price:",
    len(price_results)
)

# 3. PRICE + STOCK

print("\n========== STOCK ==========\n")

stock_results = filter_service.filter_products(
    candidates,
    max_price_inr=80000,
    in_stock=True
)

print(
    "After stock:",
    len(stock_results)
)


# 4. PRICE + STOCK + RATING

print("\n========== RATING ==========\n")

rating_results = filter_service.filter_products(
    candidates,
    max_price_inr=80000,
    in_stock=True,
    min_rating=4.0
)

print(
    "After rating:",
    len(rating_results)
)


for product in rating_results:

    print(
        product["asin"],
        "|",
        product["stars"],
        "|",
        product["price_inr"]
    )


# 5. PRICE + STOCK + RATING + RAM

print("\n========== RAM ==========\n")

ram_results = filter_service.filter_products(
    candidates,
    max_price_inr=80000,
    in_stock=True,
    min_rating=4.0,
    min_ram_gb=16
)

print(
    "After RAM:",
    len(ram_results)
)

for product in ram_results:

    print(
        product["asin"],
        "|",
        product["title"],
        "| RAM:",
        product["specs"]["ram_gb"]
    )


# 6. RTX

print("\n========== RTX ==========\n")

gpu_results = filter_service.filter_products(
    candidates,
    max_price_inr=80000,
    in_stock=True,
    min_rating=4.0,
    min_ram_gb=16,
    required_gpu="RTX"
)

print(
    "After GPU:",
    len(gpu_results)
)

for product in gpu_results:

    print()
    print(
        product["asin"],
        "|",
        product["title"]
    )

    print(
        "Price INR:",
        product["price_inr"]
    )

    print(
        "RAM:",
        product["specs"]["ram_gb"]
    )

    print(
        "GPU:",
        product["specs"]["gpu"]
    )

    print(
        "Rating:",
        product["stars"]
    )