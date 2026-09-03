from pydantic import BaseModel, Field


class CreateOrderRequest(BaseModel):
    mandate_id: str
    amount: int = Field(gt=0)
    currency: str = "INR"
    receipt: str = Field(min_length=1, max_length=40)