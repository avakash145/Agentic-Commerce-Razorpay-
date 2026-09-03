from pydantic import BaseModel, Field
from typing import List


class PurchaseIntent(BaseModel):

    query: str

    max_budget: int = Field(gt=0)

    currency: str = "INR"

    quantity: int = Field(default=1, ge=1)

    allowed_categories: List[str] = []

    requires_confirmation_above: int | None = None