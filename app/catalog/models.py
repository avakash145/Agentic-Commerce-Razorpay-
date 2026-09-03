from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class CatalogProduct:

    product_id: int

    asin: str

    title: str

    brand: Optional[str]

    price: Decimal

    currency: str

    in_stock: bool

    rating: Optional[Decimal]

    reviews_count: int

    description: Optional[str]