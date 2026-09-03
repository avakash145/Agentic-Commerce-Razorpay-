from typing import Optional, List

from pydantic import BaseModel, Field


class CommerceIntent(BaseModel):
    """
    Structured representation of a user's
    shopping request.

    This object is produced by the LLM.

    It is NOT an authorization object.
    It cannot directly execute commerce actions.
    """

    # SEMANTIC SEARCH

    search_query: str = Field(
        default="",
        description=(
            "Semantic product search query. "
            "Example: AI laptop"
        )
    )

    category: Optional[str] = Field(
        default=None,
        description=(
            "Product category explicitly requested "
            "by the user."
        )
    )

    search_terms: List[str] = Field(
        default_factory=list,
        description=(
            "Important semantic terms from the "
            "user's request."
        )
    )

    # PRICE

    max_price_inr: Optional[float] = Field(
        default=None,
        description=(
            "Maximum budget in INR."
        )
    )

    min_price_inr: Optional[float] = Field(
        default=None,
        description=(
            "Minimum price in INR."
        )
    )

    # PRODUCT SPECIFICATIONS

    min_ram_gb: Optional[int] = Field(
        default=None,
        description=(
            "Minimum RAM requirement in GB."
        )
    )

    min_storage_gb: Optional[int] = Field(
        default=None,
        description=(
            "Minimum storage requirement in GB."
        )
    )

    gpu: Optional[str] = Field(
        default=None,
        description=(
            "Required GPU family or model."
        )
    )

    cpu: Optional[str] = Field(
        default=None,
        description=(
            "Required CPU family or model."
        )
    )
    # QUALITY / AVAILABILITY

    min_rating: Optional[float] = Field(
        default=None,
        description=(
            "Minimum product rating."
        )
    )

    stock_required: Optional[bool] = Field(
        default=True,
        description=(
            "Whether the product must be "
            "in stock."
        )
    )