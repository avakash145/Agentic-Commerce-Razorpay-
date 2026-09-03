import re

from sqlalchemy import text

from app.db.database import engine
from app.catalog.embeddings import (
    get_embedding_model,
    get_legacy_embedding_model,
)


class CatalogSearchService:

    @staticmethod
    def _lexical_conditions(query):
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", query.lower())
            if len(token) > 1
            and token not in {
                "find", "me", "an", "a", "the", "for", "with",
                "and", "under", "below",
            }
        ]

        if not tokens:
            tokens = [query.strip()]

        conditions = []
        params = {}
        fields = ("title", "description", "brand", "breadcrumbs")
        for index, token in enumerate(tokens):
            parameter = f"token_{index}"
            conditions.append(
                "(" + " OR ".join(
                    f"p.{field} ILIKE :{parameter}"
                    for field in fields
                ) + ")"
            )
            params[parameter] = f"%{token}%"

        return " AND ".join(conditions), params

    def __init__(self):
        self.embedding_model = None
        self.legacy_embedding_model = None

    # LEXICAL SEARCH

    def lexical_search(
        self,
        query: str,
        limit: int = 20
    ):

        where_clause, token_params = self._lexical_conditions(query)
        sql = text(
            f"""
            SELECT
                p.product_id,
                p.asin,
                p.title,
                p.brand,
                p.price,
                p.currency,
                p.price_min,
                p.price_max,
                p.price_source,
                p.price_is_exact,
                p.price_selection_required,
                p.price_options_count,
                p.breadcrumbs,
                p.description,
                p.stars,
                p.reviews_count,
                p.in_stock,

                (
                    SELECT m.url
                    FROM media m
                    WHERE
                        m.product_id = p.product_id
                        AND m.url IS NOT NULL
                        AND (
                            m.media_type IN (
                                'image',
                                'product_thumbnail',
                                'product_gallery',
                                'product_high_resolution'
                            )
                            OR m.media_type ILIKE '%image%'
                            OR m.media_type ILIKE '%thumbnail%'
                            OR m.media_type ILIKE '%gallery%'
                            OR m.media_type ILIKE '%high_resolution%'
                        )
                    ORDER BY
                        CASE m.media_type
                            WHEN 'product_thumbnail' THEN 1
                            WHEN 'image' THEN 2
                            WHEN 'product_gallery' THEN 3
                            WHEN 'product_high_resolution' THEN 4
                            ELSE 5
                        END,
                        m.media_id
                    LIMIT 1
                ) AS image

            FROM products p

            WHERE
                {where_clause}

            ORDER BY
                p.stars DESC NULLS LAST,
                p.reviews_count DESC NULLS LAST

            LIMIT :limit
            """
        )

        with engine.connect() as conn:

            rows = conn.execute(
                sql,
                {
                    **token_params,
                    "limit": limit
                }
            )

            return [
                dict(row._mapping)
                for row in rows
            ]

    # VECTOR SEARCH

    def _vector_search(self, embedding, limit, column):
        sql = text(
            f"""
            SELECT
                p.product_id,
                p.asin,
                p.title,
                p.brand,
                p.price,
                p.currency,
                p.price_min,
                p.price_max,
                p.price_source,
                p.price_is_exact,
                p.price_selection_required,
                p.price_options_count,
                p.breadcrumbs,
                p.description,
                p.stars,
                p.reviews_count,
                p.in_stock,

                (
                    SELECT m.url
                    FROM media m
                    WHERE
                        m.product_id = p.product_id
                        AND m.url IS NOT NULL
                        AND (
                            m.media_type IN (
                                'image',
                                'product_thumbnail',
                                'product_gallery',
                                'product_high_resolution'
                            )
                            OR m.media_type ILIKE '%image%'
                            OR m.media_type ILIKE '%thumbnail%'
                            OR m.media_type ILIKE '%gallery%'
                            OR m.media_type ILIKE '%high_resolution%'
                        )
                    ORDER BY
                        CASE m.media_type
                            WHEN 'product_thumbnail' THEN 1
                            WHEN 'image' THEN 2
                            WHEN 'product_gallery' THEN 3
                            WHEN 'product_high_resolution' THEN 4
                            ELSE 5
                        END,
                        m.media_id
                    LIMIT 1
                ) AS image,

                1 - (
                    pd.{column}
                    <=>
                    CAST(
                        :embedding AS vector
                    )
                ) AS similarity

            FROM product_documents pd

            JOIN products p
                ON p.product_id = pd.product_id

            WHERE
                pd.{column} IS NOT NULL

            ORDER BY
                pd.{column}
                <=>
                CAST(
                    :embedding AS vector
                )

            LIMIT :limit
            """
        )

        with engine.connect() as conn:
            rows = conn.execute(
                sql,
                {"embedding": str(embedding), "limit": limit}
            )
            return [dict(row._mapping) for row in rows]

    def vector_search(
        self,
        query: str,
        limit: int = 20
    ):
        """Prefer multimodal vectors and fall back to the old text index."""

        # Do not download/load CLIP on application startup or on every query
        # while the multimodal index is empty. The ingestion/index command is
        # responsible for creating these rows; until then the existing
        # MiniLM index remains the fast, compatible fallback.
        try:
            with engine.connect() as conn:
                multimodal_indexed = conn.execute(text(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM product_documents
                        WHERE embedding_multimodal IS NOT NULL
                    )
                    """
                )).scalar()
        except Exception as exc:
            print(f"[MULTIMODAL INDEX CHECK FAILED] {exc}")
            multimodal_indexed = False

        if multimodal_indexed:
            try:
                if self.embedding_model is None:
                    self.embedding_model = get_embedding_model()
                embedding = self.embedding_model.embed_query(query)
                results = self._vector_search(
                    embedding,
                    limit,
                    "embedding_multimodal",
                )
                if results:
                    return results
            except Exception as exc:
                print(f"[MULTIMODAL SEARCH FALLBACK] {exc}")

        if self.legacy_embedding_model is None:
            self.legacy_embedding_model = get_legacy_embedding_model()
        legacy_embedding = self.legacy_embedding_model.embed_query(query)
        return self._vector_search(
            legacy_embedding,
            limit,
            "embedding",
        )
    # HYBRID SEARCH

    def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        candidate_limit: int = 20
    ):

        lexical_results = self.lexical_search(
            query=query,
            limit=candidate_limit
        )

        try:
            vector_results = self.vector_search(
                query=query,
                limit=candidate_limit
            )
        except Exception as exc:
            # Lexical search is still useful when pgvector has not been
            # indexed yet or the embedding service is temporarily down.
            print(f"[VECTOR SEARCH FALLBACK] {exc}")
            vector_results = []

        products = {}
        # LEXICAL RESULTS

        for rank, product in enumerate(
            lexical_results,
            start=1
        ):

            product_id = product["product_id"]

            products[product_id] = {
                **product,
                "lexical_rank": rank,
                "semantic_rank": None,
                "similarity": None
            }
        # VECTOR RESULTS

        for rank, product in enumerate(
            vector_results,
            start=1
        ):

            product_id = product["product_id"]

            if product_id not in products:

                products[product_id] = {
                    **product,
                    "lexical_rank": None,
                    "semantic_rank": rank,
                    "similarity": product.get(
                        "similarity"
                    )
                }

            else:

                products[
                    product_id
                ]["semantic_rank"] = rank

                products[
                    product_id
                ]["similarity"] = product.get(
                    "similarity"
                )
                # IMAGE

                if not products[
                    product_id
                ].get("image"):

                    products[
                        product_id
                    ]["image"] = product.get(
                        "image"
                    )
        # RECIPROCAL RANK FUSION

        k = 60

        for product in products.values():

            score = 0.0

            lexical_rank = product.get(
                "lexical_rank"
            )

            semantic_rank = product.get(
                "semantic_rank"
            )

            if lexical_rank is not None:

                score += (
                    1.0
                    /
                    (k + lexical_rank)
                )

            if semantic_rank is not None:

                score += (
                    1.0
                    /
                    (k + semantic_rank)
                )

            product[
                "hybrid_score"
            ] = score

        # SORT

        ranked_products = sorted(
            products.values(),
            key=lambda product:
                product["hybrid_score"],
            reverse=True
        )

        return ranked_products[:limit]
