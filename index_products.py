import json

from sqlalchemy import text

from app.db.database import engine

from app.catalog.document_builder import (
    build_product_documents
)

from app.catalog.embeddings import (
    MODEL_NAME,
    get_embedding_model,
)


BATCH_SIZE = 32


def insert_batch(
    conn,
    documents,
    embeddings,
    legacy_embeddings,
):

    query = text(
        """
        INSERT INTO product_documents (
            product_id,
            asin,
            content,
            metadata,
            embedding,
            embedding_multimodal,
            embedding_model
        )
        VALUES (
            :product_id,
            :asin,
            :content,
            CAST(:metadata AS jsonb),
            CAST(:legacy_embedding AS vector),
            CAST(:multimodal_embedding AS vector),
            :embedding_model
        )
        """
    )

    rows = []

    for document, embedding, legacy_embedding in zip(
        documents,
        embeddings,
        legacy_embeddings,
    ):

        rows.append(
            {
                "product_id":
                    document["product_id"],

                "asin":
                    document["asin"],

                "content":
                    document["content"],

                "metadata": json.dumps({
                    "source": "amazon",
                    "type": "product",
                    "modalities": document.get(
                        "embedding_modalities",
                        {"text": True, "images": 0, "video_frames": 0},
                    ),
                }),

                "legacy_embedding":
                    str(legacy_embedding),

                "multimodal_embedding":
                    str(embedding),

                "embedding_model": MODEL_NAME,
            }
        )

    conn.execute(
        query,
        rows
    )


def main():

    print(
        "\nBuilding product documents..."
    )

    documents = (
        build_product_documents()
    )

    print(
        f"Documents found: "
        f"{len(documents)}"
    )

    if not documents:
        print(
            "No products found."
        )
        return

    print(
        "\nLoading embedding model..."
    )

    embedding_model = (
        get_embedding_model()
    )

    # Preserve the existing text vectors when possible. They are a fallback
    # index, so there is no reason to run a second full model inference pass
    # every time product metadata or media is refreshed. New ASINs are
    # computed lazily below.
    with engine.connect() as conn:
        existing_legacy_embeddings = {
            row.asin: row.embedding
            for row in conn.execute(text(
                """
                SELECT asin, CAST(embedding AS text) AS embedding
                FROM product_documents
                WHERE embedding IS NOT NULL
                """
            ))
        }
    legacy_embedding_model = None

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE product_documents "
            "ADD COLUMN IF NOT EXISTS embedding_multimodal vector(512)"
        ))

    print(
        "Embedding model loaded."
    )

    total = len(documents)

    # Compute embeddings before replacing the derived index. If model loading
    # or embedding fails, the previous working index remains intact.
    all_embeddings = []
    all_legacy_embeddings = []
    batches = []
    for start in range(
        0,
        total,
        BATCH_SIZE
    ):

        batch = documents[
            start:start + BATCH_SIZE
        ]

        print(
            f"Embedding "
            f"{start + 1}-{min(start + BATCH_SIZE, total)}"
            f"/{total}"
        )

        embeddings = embedding_model.embed_documents(batch)
        legacy_embeddings = [
            existing_legacy_embeddings.get(document["asin"])
            for document in batch
        ]
        missing_indexes = [
            index for index, embedding in enumerate(legacy_embeddings)
            if embedding is None
        ]
        if missing_indexes:
            if legacy_embedding_model is None:
                from app.catalog.embeddings import get_legacy_embedding_model

                legacy_embedding_model = get_legacy_embedding_model()
            missing_documents = [batch[index] for index in missing_indexes]
            missing_embeddings = legacy_embedding_model.embed_documents([
                document["content"] for document in missing_documents
            ])
            for index, embedding in zip(missing_indexes, missing_embeddings):
                legacy_embeddings[index] = embedding
        batches.append(batch)
        all_embeddings.extend(embeddings)
        all_legacy_embeddings.extend(legacy_embeddings)

    # product_documents is a derived index and has no unique constraint on
    # product_id in the existing schema. Rebuilding it makes this command
    # safe after a catalog ingestion and prevents stale duplicate embeddings.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM product_documents"))
        offset = 0
        for batch in batches:
            batch_embeddings = all_embeddings[offset:offset + len(batch)]
            batch_legacy_embeddings = all_legacy_embeddings[
                offset:offset + len(batch)
            ]
            insert_batch(
                conn,
                batch,
                batch_embeddings,
                batch_legacy_embeddings,
            )
            offset += len(batch)

    print(
        "\nIndexing completed."
    )


if __name__ == "__main__":
    main()
