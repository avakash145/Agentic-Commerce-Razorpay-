from sqlalchemy import text

from app.db.database import engine


def build_product_documents():
    """Build text and visual evidence for every product without join fan-out."""

    query = text(
        """
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
            p.price_selection_required,
            p.description,
            p.breadcrumbs,
            p.condition,
            p.delivery,
            p.return_policy,
            p.stars,
            p.reviews_count,
            p.in_stock,
            p.raw_data,
            ps.ram_gb,
            ps.storage_gb,
            ps.gpu,
            ps.cpu,
            ps.screen_size_inches,

            COALESCE((
                SELECT json_agg(
                    json_build_object(
                        'name', attributes.attribute_name,
                        'value', attributes.attribute_value
                    )
                )
                FROM (
                    SELECT DISTINCT attribute_name, attribute_value
                    FROM product_attributes
                    WHERE product_id = p.product_id
                    ORDER BY attribute_name, attribute_value
                ) AS attributes
            ), '[]'::json) AS attributes,

            COALESCE((
                SELECT json_agg(
                    json_build_object(
                        'rating', reviews.rating,
                        'title', reviews.title,
                        'review', reviews.review_text
                    )
                    ORDER BY reviews.review_date DESC NULLS LAST
                )
                FROM reviews
                WHERE reviews.product_id = p.product_id
            ), '[]'::json) AS reviews,

            COALESCE((
                SELECT json_agg(
                    json_build_object(
                        'media_type', media.media_type,
                        'url', media.url,
                        'metadata', media.metadata
                    )
                    ORDER BY CASE media.media_type
                        WHEN 'product_thumbnail' THEN 1
                        WHEN 'image' THEN 2
                        WHEN 'product_gallery' THEN 3
                        WHEN 'product_high_resolution' THEN 4
                        WHEN 'video_preview' THEN 5
                        WHEN 'product_video' THEN 6
                        ELSE 7
                    END, media.media_id
                )
                FROM media
                WHERE media.product_id = p.product_id
                  AND media.review_id IS NULL
                  AND media.url IS NOT NULL
            ), '[]'::json) AS media

        FROM products p

        LEFT JOIN product_specs ps
            ON p.product_id = ps.product_id

        ORDER BY p.product_id
        """
    )

    documents = []

    with engine.connect() as connection:
        rows = connection.execute(query)

        for row in rows:
            raw_data = row.raw_data or {}
            source_data = (
                raw_data.get("canonical", raw_data)
                if isinstance(raw_data, dict)
                else {}
            )
            content_data = (
                source_data.get("content", {})
                if isinstance(source_data, dict)
                and isinstance(source_data.get("content"), dict)
                else {}
            )
            features = source_data.get("features") or content_data.get("features") or []
            features = [str(item) for item in features if item]
            review_intelligence = (
                source_data.get("review_intelligence", {})
                if isinstance(source_data, dict)
                else {}
            )
            review_summary = (
                review_intelligence.get("text")
                if isinstance(review_intelligence, dict)
                else None
            )
            price_resolution = (
                source_data.get("price_resolution", {})
                if isinstance(source_data, dict)
                else {}
            )

            specs = {
                "RAM": row.ram_gb,
                "Storage": row.storage_gb,
                "GPU": row.gpu,
                "CPU": row.cpu,
                "Screen size": row.screen_size_inches,
            }
            spec_parts = [
                f"{name}: {value}"
                for name, value in specs.items()
                if value is not None
            ]

            parts = [f"Product: {row.title}"]
            if row.brand:
                parts.append(f"Brand: {row.brand}")
            if row.price is not None:
                parts.append(f"Price: {row.price} {row.currency or ''}")
            if row.price_min is not None and row.price_max is not None:
                if row.price_max > row.price_min:
                    parts.append(
                        f"Price range: {row.price_min} to {row.price_max} "
                        f"{row.currency or ''}"
                    )
                if row.price_selection_required:
                    parts.append("Price requires variant or seller selection")
            if row.price_source and row.price_source not in {"product", "unavailable"}:
                parts.append(f"Price source: {row.price_source}")
            if row.description:
                parts.append(f"Description: {row.description}")
            if row.breadcrumbs:
                parts.append(f"Category: {row.breadcrumbs}")
            if spec_parts:
                parts.append("Specifications: " + "; ".join(spec_parts))
            if row.condition:
                parts.append(f"Condition: {row.condition}")
            if row.delivery:
                parts.append(f"Delivery: {row.delivery}")
            if row.return_policy:
                parts.append(f"Return policy: {row.return_policy}")
            if row.stars is not None:
                parts.append(f"Rating: {row.stars}/5")
            parts.append(f"Review count: {row.reviews_count or 0}")
            parts.append(f"In stock: {row.in_stock}")

            for attribute in row.attributes:
                if attribute.get("name") and attribute.get("value"):
                    parts.append(
                        f"{attribute['name']}: {attribute['value']}"
                    )

            for review in row.reviews:
                if review.get("review"):
                    parts.append(
                        f"Customer review ({review.get('rating')}/5): "
                        f"{review.get('title') or ''} {review['review']}"
                    )

            if review_summary:
                parts.append(f"Review summary: {review_summary}")
            for candidate in price_resolution.get("candidates", []):
                if not isinstance(candidate, dict) or candidate.get("value") is None:
                    continue
                label = (
                    candidate.get("variant_name")
                    or candidate.get("provider")
                    or candidate.get("source")
                )
                parts.append(
                    f"Price option ({label}): {candidate['value']} "
                    f"{candidate.get('currency') or row.currency or ''}"
                )

            media_items = [
                item for item in row.media if isinstance(item, dict)
            ]
            image_urls = [
                item.get("url")
                for item in media_items
                if item.get("url")
                and item.get("media_type") in {
                    "image",
                    "product_thumbnail",
                    "product_gallery",
                    "product_high_resolution",
                    "product_aplus",
                }
            ]
            video_urls = [
                item.get("url")
                for item in media_items
                if item.get("url")
                and item.get("media_type") == "product_video"
            ]
            video_preview_urls = [
                item.get("url")
                for item in media_items
                if item.get("url")
                and item.get("media_type") == "video_preview"
            ]

            if image_urls:
                parts.append(f"Image evidence: {len(image_urls)} images")
            if video_urls or video_preview_urls:
                parts.append(
                    "Video evidence: "
                    f"{len(video_urls)} videos, "
                    f"{len(video_preview_urls)} preview frames"
                )

            embedding_parts = [
                f"Product: {row.title}",
                f"Brand: {row.brand}" if row.brand else "",
                f"Category: {row.breadcrumbs}" if row.breadcrumbs else "",
                (
                    f"Price: {row.price} {row.currency or ''}"
                    if row.price is not None else ""
                ),
                (
                    f"Price range: {row.price_min} to {row.price_max} "
                    f"{row.currency or ''}"
                    if row.price_min is not None
                    and row.price_max is not None
                    and row.price_max > row.price_min
                    else ""
                ),
                "Specifications: " + "; ".join(spec_parts) if spec_parts else "",
                "Features: " + "; ".join(features[:8]) if features else "",
                f"Description: {row.description}" if row.description else "",
                f"Review summary: {review_summary}" if review_summary else "",
            ]

            documents.append(
                {
                    "product_id": row.product_id,
                    "asin": row.asin,
                    "content": "\n".join(parts),
                    "embedding_text": "\n".join(
                        part for part in embedding_parts if part
                    ),
                    "image_urls": image_urls,
                    "video_urls": video_urls,
                    "video_preview_urls": video_preview_urls,
                }
            )

    return documents
