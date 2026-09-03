from sqlalchemy import text

from app.db.database import engine

from app.catalog.embeddings import (
    get_embedding_model
)


def main():

    query_text = (
        "laptop for AI development "
        "with powerful GPU"
    )

    model = get_embedding_model()

    query_embedding = (
        model.embed_query(
            query_text
        )
    )

    sql = text(
        """
        SELECT
            pd.product_id,
            pd.asin,
            p.title,
            p.price,
            p.currency,
            p.stars,

            1 - (
                pd.embedding
                <=> CAST(
                    :embedding AS vector
                )
            ) AS similarity

        FROM product_documents pd

        JOIN products p
            ON p.product_id =
               pd.product_id

        ORDER BY
            pd.embedding
            <=> CAST(
                :embedding AS vector
            )

        LIMIT 5;
        """
    )

    with engine.connect() as conn:

        rows = conn.execute(
            sql,
            {
                "embedding":
                    str(query_embedding)
            }
        )

        for index, row in enumerate(
            rows,
            start=1
        ):

            print()
            print(
                f"========== {index} =========="
            )

            print(
                "ASIN:",
                row.asin
            )

            print(
                "Title:",
                row.title
            )

            print(
                "Price:",
                row.price,
                row.currency
            )

            print(
                "Rating:",
                row.stars
            )

            print(
                "Similarity:",
                round(
                    float(row.similarity),
                    4
                )
            )


if __name__ == "__main__":
    main()