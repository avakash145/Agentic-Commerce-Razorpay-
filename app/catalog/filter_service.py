from decimal import Decimal

from sqlalchemy import (
    text,
    bindparam
)

from app.db.database import engine

from app.payments.fx_service import FXService
from app.payments.currency import normalize_currency


class ProductFilterService:

    @staticmethod
    def _normalized_text(value):
        """Normalize punctuation such as RTX™ for reliable text matching."""

        if not value:
            return ""

        normalized = str(value).lower()
        normalized = normalized.replace("™", " ")
        normalized = normalized.replace("®", " ")
        return " ".join(
            "".join(
                character if character.isalnum() else " "
                for character in normalized
            ).split()
        )

    @classmethod
    def _matches_category(cls, product, category):
        if not category:
            return True

        category = cls._normalized_text(category)

        aliases = {
            "laptop": ("laptop", "notebook"),
            "laptops": ("laptop", "notebook"),
            "notebook": ("laptop", "notebook"),
            "notebooks": ("laptop", "notebook"),
            "phone": ("phone", "smartphone", "cell phone"),
            "smartphone": ("phone", "smartphone", "cell phone"),
            "headphone": ("headphone", "headset"),
            "headphones": ("headphone", "headset"),
            "earbuds": ("earbuds", "earbud"),
            "mouse": ("mouse", "mice"),
            "desktop": ("desktop", "computer"),
            "computer": ("computer", "desktop"),
            "webcam": ("webcam", "camera"),
            "printer": ("printer",),
            "router": ("router", "network"),
            "ssd": ("ssd", "storage"),
            "storage": ("ssd", "storage", "hard drive"),
        }

        # Breadcrumbs are the catalog's authoritative category. Use the
        # title only for older rows that do not have breadcrumbs; otherwise
        # a keyboard title mentioning "laptop" can be misclassified.
        category_source = (
            product.get("breadcrumbs")
            or product.get("title")
        )
        category_text = cls._normalized_text(category_source)
        return any(
            cls._normalized_text(alias) in category_text
            for alias in aliases.get(category, (category,))
        )

    @classmethod
    def _matches_gpu(cls, product, specs, required_gpu):
        if not required_gpu:
            return True

        required = cls._normalized_text(required_gpu)
        extracted = cls._normalized_text(specs.get("gpu"))
        product_text = cls._normalized_text(
            " ".join(
                str(product.get(field) or "")
                for field in ("title", "description", "breadcrumbs")
            )
        )

        # Prefer the structured value, but fall back to the source catalog
        # text when spec extraction missed symbols such as RTX™ 5070.
        if required == "gpu":
            return bool(extracted) or " gpu " in f" {product_text} "

        return required in extracted or required in product_text

    def __init__(self):
        self.fx_service = FXService()

    # LOAD PRODUCT SPECS

    def _load_specs(self, product_ids):

        if not product_ids:
            return {}

        query = text(
            """
            SELECT
                product_id,
                ram_gb,
                storage_gb,
                gpu,
                cpu,
                screen_size_inches

            FROM product_specs

            WHERE product_id IN :product_ids
            """
        ).bindparams(
            bindparam(
                "product_ids",
                expanding=True
            )
        )

        specs = {}

        with engine.connect() as conn:

            rows = conn.execute(
                query,
                {
                    "product_ids": list(
                        product_ids
                    )
                }
            )

            for row in rows:

                specs[
                    row.product_id
                ] = {
                    "ram_gb":
                        row.ram_gb,

                    "storage_gb":
                        row.storage_gb,

                    "gpu":
                        row.gpu,

                    "cpu":
                        row.cpu,

                    "screen_size_inches":
                        row.screen_size_inches
                }

        return specs

    # FILTER PRODUCTS

    def filter_products(
        self,
        products,
        max_price_inr=None,
        min_price_inr=None,
        in_stock=None,
        min_rating=None,
        required_terms=None,
        min_ram_gb=None,
        min_storage_gb=None,
        required_category=None,
        required_gpu=None,
        required_cpu=None
    ):

        filtered = []

        # NORMALIZE LIMITS


        if max_price_inr is not None:

            max_price_inr = Decimal(
                str(max_price_inr)
            )

        if min_price_inr is not None:

            min_price_inr = Decimal(
                str(min_price_inr)
            )

        # LOAD SPECS

        product_ids = [
            product["product_id"]
            for product in products
            if product.get("product_id") is not None
        ]

        specs_map = self._load_specs(
            product_ids
        )
        # FX CACHE

        fx_cache = {}

        # PRODUCT LOOP

        price_required = (
            max_price_inr is not None
            or min_price_inr is not None
        )

        for product in products:

            product_id = product.get(
                "product_id"
            )
            # PRICE
            price = product.get(
                "price"
            )

            currency = product.get(
                "currency"
            )

            if price is None or not currency:
                # Keep incomplete scraped products available for browsing and
                # detail pages. They are excluded whenever a price constraint
                # is present and checkout still validates price server-side.
                if price_required:
                    continue
                normalized_currency = (
                    normalize_currency(currency)
                    if currency
                    else None
                )
                rate = None
                price_inr = None

            else:
                try:

                    price = Decimal(
                        str(price)
                    )

                    normalized_currency = (
                        normalize_currency(
                            currency
                        )
                    )

                    # CACHE FX RATE

                    if (
                        normalized_currency
                        not in fx_cache
                    ):

                        fx_cache[
                            normalized_currency
                        ] = (
                            self.fx_service
                            .get_rate(
                                normalized_currency,
                                "INR"
                            )
                        )

                    rate = fx_cache[
                        normalized_currency
                    ]

                    price_inr = (
                        price * rate
                    ).quantize(
                        Decimal("0.01")
                    )

                except Exception as exc:

                    print(
                        f"[FX ERROR] "
                        f"{product.get('asin')}: "
                        f"{exc}"
                    )

                    # Fail closed for malformed priced products.
                    continue

            # FINANCIAL METADATA

            product["price_inr"] = price_inr

            price_min = product.get("price_min")
            price_max = product.get("price_max")
            product["price_min_inr"] = (
                Decimal(str(price_min)) * rate
                if price_min is not None and rate is not None
                else price_inr
            )
            product["price_max_inr"] = (
                Decimal(str(price_max)) * rate
                if price_max is not None and rate is not None
                else price_inr
            )

            product["fx_rate"] = rate

            product[
                "fx_source_currency"
            ] = normalized_currency

            # MAX PRICE

            if (
                max_price_inr is not None
                and price_inr > max_price_inr
            ):
                continue
            # MIN PRICE

            if (
                min_price_inr is not None
                and price_inr < min_price_inr
            ):
                continue

            # STOCK

            if in_stock is True:

                if (
                    product.get("in_stock")
                    is not True
                ):
                    continue
            # RATING

            if min_rating is not None:

                rating = product.get(
                    "stars"
                )

                if rating is None:
                    continue

                try:

                    rating = Decimal(
                        str(rating)
                    )

                except Exception:

                    continue

                if rating < Decimal(
                    str(min_rating)
                ):
                    continue
            # TITLE / BRAND TERMS


            # PRODUCT SPECS

            if not self._matches_category(
                product,
                required_category
            ):
                continue

            # Specifications are optional metadata.  A product should not
            # disappear from a plain search just because extraction has not
            # been run; only an explicit spec constraint requires a value.
            specs = specs_map.get(product_id, {})
            product["specs"] = specs
            # RAM


            if min_ram_gb is not None:

                ram = specs.get(
                    "ram_gb"
                )

                if ram is None:
                    continue

                if float(ram) < float(
                    min_ram_gb
                ):
                    continue

            # STORAGE

            if min_storage_gb is not None:

                storage = specs.get(
                    "storage_gb"
                )

                if storage is None:
                    continue

                if float(storage) < float(
                    min_storage_gb
                ):
                    continue

            # GPU

            if required_gpu:

                gpu = specs.get(
                    "gpu"
                )

                if not self._matches_gpu(
                    product,
                    specs,
                    required_gpu
                ):
                    continue

            # CPU

            if required_cpu:

                cpu = specs.get(
                    "cpu"
                )

                if not cpu:
                    continue

                if (
                    str(required_cpu).lower()
                    not in str(cpu).lower()
                ):
                    continue

            # PASSED

            filtered.append(
                product
            )

        return filtered
