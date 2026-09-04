from app.agent.intent_parser import IntentParser

from app.catalog.search_service import (
    CatalogSearchService
)

from app.catalog.filter_service import (
    ProductFilterService
)


class CommerceSearchService:

    def __init__(self, search_service=None, filter_service=None):

        self.intent_parser = (IntentParser())
        self.search_service = search_service or CatalogSearchService()
        self.filter_service = filter_service or ProductFilterService()

    # SEARCH

    def search(
        self,
        user_query: str,
        retrieval_limit: int = 20
    ):

        # PARSE USER INTENT

        intent = (
            self.intent_parser.parse(
                user_query
            )
        )
        # BUILD SEARCH QUERY

        search_query = (
            intent.search_query
        )

        if not search_query:

            search_query = user_query
        # HYBRID RETRIEVAL

        # Retrieve a wider pool before applying hard constraints.  A narrow
        # top-20 semantic result can otherwise hide an exact GPU/category
        # match behind highly rated but irrelevant products.
        candidate_limit = max(
            retrieval_limit * 4,
            80
        )

        candidates = (
            self.search_service
            .hybrid_search(
                query=search_query,
                limit=candidate_limit,
                candidate_limit=candidate_limit
            )
        )

        # DETERMINISTIC FILTERING
        products = (
            self.filter_service
            .filter_products(

                products=candidates,

                max_price_inr=(
                    intent.max_price_inr
                ),

                min_price_inr=(
                    intent.min_price_inr
                ),

                in_stock=(
                    intent.stock_required
                ),

                min_rating=(
                    intent.min_rating
                ),

                min_ram_gb=(
                    intent.min_ram_gb
                ),

                min_storage_gb=(
                    intent.min_storage_gb
                ),

                required_category=(
                    intent.category
                ),

                required_gpu=(
                    intent.gpu
                ),

                required_cpu=(
                    intent.cpu
                )
            )
        )

        # RETURN BOTH INTENT AND PRODUCTS
        return {
            "intent": intent,
            "products": products[:retrieval_limit],
            "candidate_count": len(
                candidates
            ),
            "result_count": len(
                products[:retrieval_limit]
            )
        }
