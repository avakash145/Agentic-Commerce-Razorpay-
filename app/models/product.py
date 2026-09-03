from pydantic import BaseModel, Field
from typing import List


class Product(BaseModel):
    product_id: str
    name: str

    price: int = Field(gt=0)
    currency: str = "INR"

    category: str
    description: str

    stock: int = Field(ge=0)

    tags: List[str] = []