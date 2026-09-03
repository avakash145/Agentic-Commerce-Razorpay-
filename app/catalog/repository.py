from sqlalchemy import text

from app.db.database import engine

from app.catalog.models import CatalogProduct


class ProductRepository:

    def search_products(
        self,
        query: str,
        limit: int = 10
    ):

        sql = text(
            """
            SELECT
                product_id,
                asin,
                title,
                brand,
                price,
                currency,
                in_stock,
                stars,
                reviews_count,
                description

            FROM products

            WHERE
                title ILIKE :query
                OR description ILIKE :query
                OR brand ILIKE :query

            ORDER BY
                stars DESC NULLS LAST,
                reviews_count DESC NULLS LAST

            LIMIT :limit
            """
        )

        with engine.connect() as conn:

            rows = conn.execute(
                sql,
                {
                    "query": f"%{query}%",
                    "limit": limit
                }
            )

            products = []

            for row in rows:

                products.append(
                    CatalogProduct(
                        product_id=row.product_id,
                        asin=row.asin,
                        title=row.title,
                        brand=row.brand,
                        price=row.price,
                        currency=row.currency,
                        in_stock=row.in_stock,
                        rating=row.stars,
                        reviews_count=row.reviews_count,
                        description=row.description
                    )
                )

        return products
