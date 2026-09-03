"""Normalize Apify Amazon exports and load one canonical catalog.

The crawler exports two representations of the same product: a flat raw
record and a processed nested record.  This pipeline intentionally treats
ASIN as the identity, merges non-empty values from both representations,
deduplicates child records, and keeps incomplete products browseable while
marking them as not checkout-ready.

Usage:

    python catalog_pipeline.py --dry-run
    python catalog_pipeline.py

The default command writes a canonical snapshot and quality report under
``processed/`` and upserts the relational catalog in PostgreSQL.
"""

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.catalog.spec_extractor import ProductSpecExtractor
from app.db.database import engine


DEFAULT_RAW_DIR = Path("raw")
DEFAULT_PROCESSED_FILE = Path("processed/products.json")
DEFAULT_CANONICAL_FILE = Path("processed/catalog_canonical.json")
DEFAULT_REPORT_FILE = Path("processed/catalog_quality_report.json")

ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)
MONEY_PATTERN = re.compile(
    r"(?P<currency>USD|INR|EUR|GBP|JPY|CNY|CAD|AUD|SGD|AED|SAR|"
    r"\$|₹|€|£|¥)?\s*(?P<amount>\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
EMPTY = (None, "", [], {})


def _value(record: dict, *paths: tuple[str, ...] | str) -> Any:
    """Return the first non-empty value from dotted or tuple paths."""

    for path in paths:
        parts = path.split(".") if isinstance(path, str) else path
        current: Any = record
        for part in parts:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current not in EMPTY:
            return current
    return None


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return []


def _clean_text(value: Any) -> str | None:
    if value in EMPTY:
        return None
    result = " ".join(str(value).split())
    return result or None


def _number(value: Any) -> float | None:
    if value in EMPTY:
        return None
    if isinstance(value, dict):
        value = value.get("value") or value.get("amount")
    try:
        return float(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in EMPTY:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "in stock", "available"}:
            return True
        if lowered in {"false", "no", "out of stock", "unavailable"}:
            return False
    return bool(value)


def _currency(value: Any) -> str | None:
    value = _clean_text(value)
    return value.upper() if value and len(value) <= 10 else value


def _dedupe(values: list[Any], key=None) -> list[Any]:
    result = []
    seen = set()
    key = key or (lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    for value in values:
        if value in EMPTY:
            continue
        marker = key(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def _merge_value(existing: Any, incoming: Any) -> Any:
    if existing in EMPTY:
        return incoming
    if incoming in EMPTY:
        return existing
    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = dict(existing)
        for key, value in incoming.items():
            merged[key] = _merge_value(merged.get(key), value)
        return merged
    if isinstance(existing, list) and isinstance(incoming, list):
        return _dedupe(existing + incoming)
    return existing


def _parse_money_text(value: Any) -> tuple[float | None, str | None]:
    if not isinstance(value, str):
        return None, None
    match = MONEY_PATTERN.search(value)
    if not match:
        return None, None
    try:
        amount = float(Decimal(match.group("amount").replace(",", "")))
    except (InvalidOperation, TypeError, ValueError):
        return None, None
    return amount, _currency(match.group("currency"))


def _price(value: Any) -> tuple[float | None, str | None]:
    if isinstance(value, dict):
        numeric = (
            value.get("value")
            or value.get("amount")
            or value.get("price")
            or value.get("currentPrice")
        )
        amount, parsed_currency = _price(numeric)
        currency = _currency(
            value.get("currency")
            or value.get("currencyCode")
            or value.get("symbol")
        ) or parsed_currency
        return amount, currency
    amount, currency = _parse_money_text(value)
    if amount is not None:
        return amount, currency
    return _number(value), None


def _items(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _entity_text(value: Any) -> str | None:
    if isinstance(value, dict):
        return _clean_text(
            value.get("name")
            or value.get("title")
            or value.get("label")
            or value.get("displayName")
        )
    return _clean_text(value)


def _price_candidate(
    value: Any,
    source: str,
    fallback_currency: str | None = None,
    **metadata: Any,
) -> dict | None:
    amount, currency = _price(value)
    if amount is None or amount <= 0:
        return None
    return {
        "value": amount,
        "currency": currency or fallback_currency,
        "source": source,
        **{
            key: value
            for key, value in metadata.items()
            if value not in EMPTY
        },
    }


def _offer_rows(record: dict) -> list[dict]:
    raw_offers = _value(
        record,
        "offers",
        "commerce.offers",
        "sellerOffers",
        "buyingOptions",
        "buy_box_offers",
    )
    fallback_currency = _currency(
        _value(record, "currency", "commerce.currency")
    )
    rows = []
    for offer in _items(raw_offers):
        price_value = _value(
            offer,
            "price",
            "currentPrice",
            "salePrice",
            "buyingPrice",
            "amount",
        )
        price, price_currency = _price(price_value)
        seller_value = _value(
            offer,
            "seller",
            "merchant",
            "provider",
            "retailer",
            "soldBy",
            "sold_by",
        )
        seller_name = _entity_text(seller_value) or _clean_text(
            _value(offer, "sellerName", "merchantName", "providerName")
        )
        seller_id = _clean_text(
            _value(offer, "sellerId", "merchantId", "providerId")
        )
        row = {
            "provider": _clean_text(
                _value(offer, "provider", "retailer", "marketplace")
            ) or seller_name,
            "seller_name": seller_name,
            "seller_id": seller_id,
            "url": _clean_text(
                _value(offer, "url", "offerUrl", "offer_url", "buyUrl")
            ),
            "price": price,
            "currency": price_currency or fallback_currency,
            "shipping_price": _number(
                _value(offer, "shippingPrice", "shipping_price", "shipping")
            ),
            "in_stock": _bool(
                _value(offer, "inStock", "in_stock", "availability")
            ),
            "condition": _clean_text(
                _value(offer, "condition", "itemCondition")
            ),
            "raw_data": offer,
        }
        if any(row[key] not in EMPTY for key in ("price", "seller_name", "provider", "url")):
            rows.append(row)
    return _dedupe(
        rows,
        key=lambda item: (
            item.get("seller_id"),
            item.get("provider"),
            item.get("price"),
            item.get("currency"),
            item.get("url"),
        ),
    )


def _price_candidates(record: dict) -> list[dict]:
    fallback_currency = _currency(
        _value(record, "currency", "commerce.currency")
    )
    candidates = []

    direct = _price_candidate(
        _value(record, "price", "commerce.price"),
        "product",
        fallback_currency,
    )
    if direct:
        candidates.append(direct)

    for offer in _offer_rows(record):
        if offer.get("price") is None:
            continue
        candidates.append({
            "value": offer["price"],
            "currency": offer.get("currency") or fallback_currency,
            "source": "offer",
            "provider": offer.get("provider"),
            "seller_name": offer.get("seller_name"),
            "seller_id": offer.get("seller_id"),
            "url": offer.get("url"),
        })

    variants = _value(
        record,
        "variantDetails",
        "variants.variant_details",
        "variants.details",
        "variants.items",
    )
    for variant in _items(variants):
        variant_price = _value(
            variant,
            "price",
            "currentPrice",
            "salePrice",
            "buyingPrice",
        )
        candidate = _price_candidate(
            variant_price,
            "variant",
            fallback_currency,
            variant_asin=_clean_text(variant.get("asin") or variant.get("ASIN")),
            variant_name=_clean_text(
                variant.get("name")
                or variant.get("title")
                or variant.get("label")
            ),
        )
        if candidate:
            candidates.append(candidate)

    price_range = _value(record, "priceRange", "commerce.price_range")
    if isinstance(price_range, dict):
        minimum = _price_candidate(
            price_range.get("min") or price_range.get("minimum"),
            "price_range_min",
            fallback_currency,
        )
        maximum = _price_candidate(
            price_range.get("max") or price_range.get("maximum"),
            "price_range_max",
            fallback_currency,
        )
        if minimum:
            candidates.append(minimum)
        if maximum:
            candidates.append(maximum)
    elif isinstance(price_range, str):
        range_values = [
            _price_candidate(match.group(0), "price_range_min", fallback_currency)
            for match in MONEY_PATTERN.finditer(price_range)
        ]
        range_values = [candidate for candidate in range_values if candidate]
        if range_values:
            candidates.append(range_values[0])
            if len(range_values) > 1:
                range_values[-1]["source"] = "price_range_max"
                candidates.append(range_values[-1])

    return _dedupe(
        candidates,
        key=lambda item: (
            item.get("source"),
            item.get("value"),
            item.get("currency"),
            item.get("variant_asin"),
            item.get("provider"),
        ),
    )


def _currency_key(value: str | None) -> str | None:
    aliases = {
        "$": "USD",
        "US$": "USD",
        "₹": "INR",
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",
    }
    normalized = _currency(value)
    return aliases.get(normalized, normalized)


def _resolve_price_candidates(
    candidates: list[dict],
    preferred_currency: str | None = None,
    product_asin: str | None = None,
) -> dict:
    priority = {
        "product": 0,
        "offer": 1,
        "variant": 2,
        "variant_product": 3,
        "price_range_min": 4,
        "price_range_max": 4,
    }
    valid = [
        candidate for candidate in candidates
        if candidate.get("value") is not None
        and candidate.get("value") > 0
    ]
    if not valid:
        return {
            "price": None,
            "currency": preferred_currency,
            "price_min": None,
            "price_max": None,
            "source": "unavailable",
            "price_is_exact": False,
            "price_selection_required": False,
            "price_options_count": 0,
            "candidates": [],
        }

    groups = defaultdict(list)
    for candidate in valid:
        groups[_currency_key(candidate.get("currency"))].append(candidate)
    preferred_key = _currency_key(preferred_currency)
    if preferred_key in groups:
        selected_group = groups[preferred_key]
    else:
        selected_group = min(
            groups.values(),
            key=lambda group: (
                min(priority.get(item.get("source"), 99) for item in group),
                -len(group),
            ),
        )

    best_priority = min(
        priority.get(item.get("source"), 99)
        for item in selected_group
    )
    active = [
        item for item in selected_group
        if priority.get(item.get("source"), 99) == best_priority
    ]
    chosen = min(active, key=lambda item: item["value"])
    source = chosen.get("source")
    if source == "price_range_min":
        source_label = "price_range"
    elif source == "variant_product":
        source_label = "linked_variant"
    elif len(active) > 1 and source == "offer":
        source_label = "lowest_offer"
    elif len(active) > 1 and source == "variant":
        source_label = "lowest_variant"
    else:
        source_label = source

    selection_required = source in {
        "price_range_min",
        "variant",
        "variant_product",
    }
    if source == "variant" and len(active) == 1:
        selection_required = chosen.get("variant_asin") not in {
            None,
            product_asin,
        }
    if source == "offer" and len(active) > 1:
        selection_required = True

    return {
        "price": chosen["value"],
        "currency": chosen.get("currency") or preferred_currency,
        "price_min": min(item["value"] for item in active),
        "price_max": max(item["value"] for item in active),
        "source": source_label,
        "price_is_exact": not selection_required and source not in {
            "price_range_min",
            "price_range_max",
        },
        "price_selection_required": selection_required,
        "price_options_count": len(active),
        "candidates": [
            {
                key: value
                for key, value in item.items()
                if key in {
                    "value", "currency", "source", "provider", "seller_name",
                    "seller_id", "url", "variant_asin", "variant_name",
                }
            }
            for item in active
        ],
    }


def _flatten_attributes(*groups: Any) -> list[dict[str, str]]:
    attributes = []
    for group in groups:
        for item in _as_list(group):
            if not isinstance(item, dict):
                continue
            name = _clean_text(
                item.get("key") or item.get("name") or item.get("attribute_name")
            )
            value = _clean_text(
                item.get("value") or item.get("attribute_value")
            )
            if name and value:
                attributes.append({"name": name, "value": value})
    return _dedupe(attributes, key=lambda item: (item["name"].lower(), item["value"].lower()))


def _flatten_reviews(*groups: Any) -> list[dict]:
    reviews = []
    for group in groups:
        for item in _as_list(group):
            if not isinstance(item, dict):
                continue
            review = {
                "review_id": _clean_text(
                    item.get("reviewId") or item.get("review_id") or item.get("id")
                ),
                "username": _clean_text(
                    item.get("username") or item.get("userName") or item.get("user")
                ),
                "rating": _number(
                    item.get("ratingScore") or item.get("rating") or item.get("stars")
                ),
                "title": _clean_text(
                    item.get("reviewTitle") or item.get("title")
                ),
                "review_text": _clean_text(
                    item.get("reviewDescription")
                    or item.get("reviewText")
                    or item.get("review")
                    or item.get("text")
                ),
                "review_date": _clean_text(
                    item.get("date") or item.get("reviewDate") or item.get("review_date")
                ),
                "review_url": _clean_text(
                    item.get("reviewUrl") or item.get("review_url")
                ),
                "reaction": _clean_text(
                    item.get("reviewReaction") or item.get("reaction")
                ),
                "is_verified": _bool(
                    item.get("isVerified")
                    if item.get("isVerified") is not None
                    else item.get("is_verified")
                ),
                "is_amazon_vine": _bool(
                    item.get("isAmazonVine")
                    if item.get("isAmazonVine") is not None
                    else item.get("is_amazon_vine")
                ),
                "variant": _clean_text(item.get("variant")),
                "raw_data": item,
                "media": [
                    image.get("url") if isinstance(image, dict) else image
                    for image in _as_list(
                        item.get("reviewImages") or item.get("review_images")
                    )
                ],
            }
            if review["review_text"] or review["title"] or review["rating"] is not None:
                reviews.append(review)

    unique = {}
    for review in reviews:
        marker = review["review_id"] or hashlib.sha1(
            json.dumps(
                [review.get("username"), review.get("title"), review.get("review_text")],
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        if marker not in unique:
            review["review_id"] = marker if review["review_id"] is None else marker
            unique[marker] = review
    return list(unique.values())


def _media(record: dict) -> list[dict[str, str]]:
    media = []
    nested = record.get("media") if isinstance(record.get("media"), dict) else {}
    sources = (
        ("product_thumbnail", _value(record, "thumbnailImage", "media.thumbnail")),
        ("product_gallery", _value(record, "galleryThumbnails", "media.gallery")),
        ("product_high_resolution", _value(record, "highResolutionImages", "media.high_resolution")),
    )
    # Include A+ images as secondary product media when available.
    aplus = _value(record, "aPlusContent", "content.a_plus_content")
    if isinstance(aplus, dict):
        sources += (("product_aplus", [item for item in aplus.get("rawImages", []) if isinstance(item, dict)]),)

    video_sources = []
    if isinstance(aplus, dict):
        video_sources.extend(_as_list(aplus.get("rawVideos")))
    video_sources.extend(
        _as_list(
            _value(
                record,
                "videos",
                "videoUrls",
                "video_sources",
                "content.videos",
            )
        )
    )

    seen = set()
    for media_type, value in sources:
        values = value if isinstance(value, list) else [value]
        for item in values:
            url = item.get("url") if isinstance(item, dict) else item
            url = _clean_text(url)
            if not url or not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            media.append({"media_type": media_type, "url": url})

    for item in video_sources:
        if not isinstance(item, dict):
            continue
        video_url = _clean_text(
            item.get("url") or item.get("videoUrl") or item.get("video_url")
        )
        preview_url = _clean_text(
            item.get("previewImageUrl")
            or item.get("preview_image_url")
            or item.get("thumbnail")
        )
        if video_url and video_url.startswith(("http://", "https://")):
            media.append({
                "media_type": "product_video",
                "url": video_url,
                "metadata": {"preview_image_url": preview_url} if preview_url else {},
            })
        if preview_url and preview_url.startswith(("http://", "https://")):
            if preview_url not in seen:
                seen.add(preview_url)
                media.append({
                    "media_type": "video_preview",
                    "url": preview_url,
                    "metadata": {"video_url": video_url} if video_url else {},
                })
    return media


def _category_kind(breadcrumbs: str | None, title: str | None) -> str:
    text_value = f"{breadcrumbs or ''} {title or ''}".lower()
    rules = (
        ("laptop", ("laptop", "notebook")),
        ("desktop", ("desktop", "tower pc", "all-in-one")),
        ("monitor", ("monitor", "display")),
        ("keyboard", ("keyboard",)),
        ("mouse", ("mouse", "mice")),
        ("mobile", ("smartphone", "cell phone", "mobile phone", "phone")),
        ("tablet", ("tablet", "ipad")),
        ("headphone", ("headphone", "headset", "earbud")),
        ("camera", ("camera", "webcam")),
        ("storage", ("ssd", "hard drive", "flash drive", "memory card")),
        ("networking", ("router", "network", "wi-fi", "wifi")),
        ("accessory", ("computer", "electronics", "accessor")),
    )
    for kind, terms in rules:
        if any(term in text_value for term in terms):
            return kind
    return "other"


def _canonicalize(record: dict, source_file: str) -> dict | None:
    identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
    commerce = record.get("commerce") if isinstance(record.get("commerce"), dict) else {}
    classification = record.get("classification") if isinstance(record.get("classification"), dict) else {}
    content = record.get("content") if isinstance(record.get("content"), dict) else {}
    ratings = record.get("ratings") if isinstance(record.get("ratings"), dict) else {}
    popularity = record.get("popularity") if isinstance(record.get("popularity"), dict) else {}
    variants = record.get("variants") if isinstance(record.get("variants"), dict) else {}

    asin = _clean_text(_value(record, "asin", "identity.asin"))
    if not asin or not ASIN_PATTERN.match(asin):
        return None
    asin = asin.upper()

    price_candidates = _price_candidates(record)
    currency = _currency(
        _value(record, "currency", "commerce.currency", "commerce.price.currency")
    )
    price_resolution = _resolve_price_candidates(
        price_candidates,
        preferred_currency=currency,
        product_asin=asin,
    )
    price = price_resolution["price"]
    currency = price_resolution["currency"] or currency
    breadcrumbs = _clean_text(
        _value(record, "breadCrumbs", "breadcrumbs", "classification.breadcrumbs")
    )
    title = _clean_text(_value(record, "title", "identity.title"))
    description = _clean_text(_value(record, "description", "content.description", "bookDescription"))
    features = _as_list(_value(record, "features", "content.features"))
    product_overview = _as_list(
        _value(record, "productOverview", "classification.product_overview")
    )
    attributes = _flatten_attributes(
        _value(record, "attributes", "classification.attributes"),
        _value(record, "productOverview", "classification.product_overview"),
        _value(record, "variantAttributes", "classification.variant_attributes"),
    )
    reviews = _flatten_reviews(
        _value(record, "productPageReviews", "reviews"),
    )
    media = _media(record)

    canonical = {
        "asin": asin,
        "original_asin": _clean_text(_value(record, "originalAsin", "identity.original_asin")) or asin,
        "title": title,
        "brand": _clean_text(_value(record, "brand", "identity.brand")),
        "url": _clean_text(_value(record, "url", "identity.url", "unNormalizedProductUrl")),
        "price": price,
        "currency": currency,
        "list_price": _number(_value(record, "listPrice", "commerce.list_price")),
        "shipping_price": _number(_value(record, "shippingPrice", "commerce.shipping_price")),
        "in_stock": _bool(_value(record, "inStock", "commerce.in_stock")),
        "in_stock_text": _clean_text(_value(record, "inStockText", "commerce.in_stock_text")),
        "stars": _number(_value(record, "stars", "ratings.stars")),
        "stars_breakdown": _value(record, "starsBreakdown", "ratings.stars_breakdown") or {},
        "reviews_count": int(_number(_value(record, "reviewsCount", "ratings.reviews_count")) or 0),
        "answered_questions": int(_number(_value(record, "answeredQuestions", "ratings.answered_questions")) or 0),
        "breadcrumbs": breadcrumbs,
        "description": description,
        "delivery": _clean_text(_value(record, "delivery", "commerce.delivery")),
        "fastest_delivery": _clean_text(_value(record, "fastestDelivery", "commerce.fastest_delivery")),
        "return_policy": _clean_text(_value(record, "returnPolicy", "commerce.return_policy")),
        "condition": _clean_text(_value(record, "condition", "commerce.condition")),
        "is_amazon_choice": _bool(_value(record, "isAmazonChoice", "popularity.is_amazon_choice")),
        "amazon_choice_text": _clean_text(_value(record, "amazonChoiceText", "popularity.amazon_choice_text")),
        "video_count": int(_number(_value(record, "videosCount", "media.video_count")) or 0),
        "review_intelligence": _value(record, "aiReviewsSummary", "review_intelligence") or {},
        "seller": _value(record, "seller", "commerce.seller") or {},
        "offers": _offer_rows(record),
        "attributes": attributes,
        "reviews": reviews,
        "media": media,
        "features": [_clean_text(item) for item in features if _clean_text(item)],
        "product_overview": product_overview,
        "variants": {
            "variant_asins": _as_list(_value(record, "variantAsins", "variants.variant_asins")),
            "variant_details": _items(_value(record, "variantDetails", "variants.variant_details")),
        },
        "price_candidates": price_candidates,
        "price_resolution": price_resolution,
        "source_file": source_file,
    }
    canonical["category_kind"] = _category_kind(breadcrumbs, title)
    canonical["quality"] = quality_for(canonical)
    return canonical


def quality_for(product: dict) -> dict:
    issues = []
    score = 0
    if product.get("asin"):
        score += 15
    else:
        issues.append("missing_asin")
    if product.get("title"):
        score += 20
    else:
        issues.append("missing_title")
    if product.get("price") is not None and product.get("currency"):
        score += 25
    else:
        issues.append("missing_price_or_currency")
    if product.get("in_stock") is not None:
        score += 10
    else:
        issues.append("missing_stock_state")
    if product.get("breadcrumbs"):
        score += 10
    else:
        issues.append("missing_category")
    if product.get("media"):
        score += 10
    else:
        issues.append("missing_images")
    if product.get("attributes") or product.get("features"):
        score += 5
    else:
        issues.append("missing_attributes")
    if product.get("reviews") or product.get("reviews_count"):
        score += 5
    else:
        issues.append("missing_reviews")
    required_for_ready = {
        "missing_asin",
        "missing_title",
        "missing_price_or_currency",
        "missing_stock_state",
        "missing_category",
        "missing_images",
    }
    status = "ready" if not required_for_ready.intersection(issues) else "partial"
    return {"score": score, "status": status, "issues": issues}


def load_source_records(raw_dir: Path, processed_file: Path) -> tuple[list[dict], dict[str, list[str]]]:
    records = []
    source_files = defaultdict(list)
    for path in sorted(raw_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("products", data.get("items", []))
        for row in rows:
            if not isinstance(row, dict):
                continue
            records.append((row, path.name))

    if processed_file.exists():
        data = json.loads(processed_file.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("products", data.get("items", []))
        for index, row in enumerate(rows):
            if isinstance(row, dict):
                records.append((row, f"{processed_file.name}#{index + 1}"))

    return records, source_files


def _apply_price_resolution(product: dict) -> None:
    resolution = product.get("price_resolution") or {}
    product["price"] = resolution.get("price")
    product["currency"] = resolution.get("currency") or product.get("currency")
    product["price_min"] = resolution.get("price_min")
    product["price_max"] = resolution.get("price_max")
    product["price_source"] = resolution.get("source", "unavailable")
    product["price_is_exact"] = bool(resolution.get("price_is_exact"))
    product["price_selection_required"] = bool(
        resolution.get("price_selection_required")
    )
    product["price_options_count"] = int(
        resolution.get("price_options_count") or 0
    )


def _variant_rows(product: dict) -> list[dict]:
    variants = product.get("variants") or {}
    details = variants.get("variant_details") or []
    linked_prices = {
        str(item.get("variant_asin")).upper(): item
        for item in product.get("price_candidates", [])
        if item.get("source") == "variant_product" and item.get("variant_asin")
    }
    rows = []
    seen = set()
    for detail in details:
        if not isinstance(detail, dict):
            continue
        asin = _clean_text(detail.get("asin") or detail.get("ASIN"))
        if asin:
            asin = asin.upper()
            if not ASIN_PATTERN.match(asin):
                asin = None
        direct_price, direct_currency = _price(
            _value(detail, "price", "currentPrice", "salePrice", "buyingPrice")
        )
        linked = linked_prices.get(asin or "")
        price = direct_price if direct_price is not None else (
            linked.get("value") if linked else None
        )
        currency = direct_currency or (
            linked.get("currency") if linked else product.get("currency")
        )
        marker = asin or json.dumps(detail, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        rows.append({
            "asin": asin,
            "name": _clean_text(
                detail.get("name") or detail.get("title") or detail.get("label")
            ),
            "price": price,
            "currency": currency,
            "thumbnail_url": _clean_text(
                detail.get("thumbnail") or detail.get("thumbnailUrl")
            ),
            "in_stock": _bool(
                _value(detail, "inStock", "in_stock", "availability")
            ),
            "raw_data": detail,
        })

    for variant_asin in variants.get("variant_asins") or []:
        asin = _clean_text(variant_asin)
        if not asin:
            continue
        asin = asin.upper()
        if not ASIN_PATTERN.match(asin) or asin in seen:
            continue
        seen.add(asin)
        linked = linked_prices.get(asin)
        rows.append({
            "asin": asin,
            "name": None,
            "price": linked.get("value") if linked else None,
            "currency": linked.get("currency") if linked else product.get("currency"),
            "thumbnail_url": None,
            "in_stock": None,
            "raw_data": {"asin": asin},
        })
    return rows


def _ensure_price_schema() -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        for statement in (
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_min NUMERIC",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_max NUMERIC",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_source TEXT",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_is_exact BOOLEAN",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_selection_required BOOLEAN",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_options_count INTEGER",
            "CREATE TABLE IF NOT EXISTS product_variants ("
            "variant_id BIGSERIAL PRIMARY KEY,"
            "product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,"
            "asin TEXT, name TEXT, price NUMERIC, currency TEXT,"
            "thumbnail_url TEXT, in_stock BOOLEAN, raw_data JSONB)" ,
            "ALTER TABLE product_variants ADD COLUMN IF NOT EXISTS currency TEXT",
            "ALTER TABLE product_variants ADD COLUMN IF NOT EXISTS in_stock BOOLEAN",
            "CREATE TABLE IF NOT EXISTS product_offers ("
            "offer_id BIGSERIAL PRIMARY KEY,"
            "product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,"
            "provider TEXT, seller_name TEXT, seller_id TEXT, url TEXT,"
            "price NUMERIC, currency TEXT, shipping_price NUMERIC,"
            "in_stock BOOLEAN, condition TEXT, raw_data JSONB)" ,
            "CREATE INDEX IF NOT EXISTS product_offers_product_id_idx "
            "ON product_offers(product_id)",
        ):
            connection.execute(text(statement))


def build_catalog(
    raw_dir: Path = DEFAULT_RAW_DIR,
    processed_file: Path = DEFAULT_PROCESSED_FILE,
    allowed_kinds: set[str] | None = None,
) -> tuple[list[dict], dict]:
    records, _ = load_source_records(raw_dir, processed_file)
    grouped: dict[str, list[dict]] = defaultdict(list)
    invalid = 0
    for record, source_file in records:
        canonical = _canonicalize(record, source_file)
        if canonical is None:
            invalid += 1
            continue
        grouped[canonical["asin"]].append(canonical)

    catalog = []
    for asin, candidates in sorted(grouped.items()):
        # Higher quality first; merge the remaining records so one incomplete
        # crawl page cannot erase a complete value from another page.
        candidates.sort(key=lambda item: item["quality"]["score"], reverse=True)
        merged = dict(candidates[0])
        for candidate in candidates[1:]:
            for key in (
                "original_asin", "title", "brand", "url", "price", "currency",
                "list_price", "shipping_price", "in_stock", "in_stock_text", "stars",
                "reviews_count", "answered_questions", "breadcrumbs", "description",
                "delivery", "fastest_delivery", "return_policy", "condition",
                "is_amazon_choice", "amazon_choice_text", "video_count", "stars_breakdown",
                "review_intelligence", "seller", "offers",
            ):
                merged[key] = _merge_value(merged.get(key), candidate.get(key))
            merged["attributes"] = _dedupe(
                merged.get("attributes", []) + candidate.get("attributes", []),
                key=lambda item: (item["name"].lower(), item["value"].lower()),
            )
            merged["reviews"] = _dedupe(
                merged.get("reviews", []) + candidate.get("reviews", []),
                key=lambda item: item.get("review_id"),
            )
            merged["media"] = _dedupe(
                merged.get("media", []) + candidate.get("media", []),
                key=lambda item: item.get("url"),
            )
            merged["features"] = _dedupe(merged.get("features", []) + candidate.get("features", []))
            merged["price_candidates"] = _dedupe(
                merged.get("price_candidates", [])
                + candidate.get("price_candidates", []),
                key=lambda item: (
                    item.get("source"), item.get("value"), item.get("currency"),
                    item.get("variant_asin"), item.get("provider"),
                ),
            )
            merged["variants"] = {
                "variant_asins": _dedupe(
                    (merged.get("variants") or {}).get("variant_asins", [])
                    + (candidate.get("variants") or {}).get("variant_asins", [])
                ),
                "variant_details": _dedupe(
                    (merged.get("variants") or {}).get("variant_details", [])
                    + (candidate.get("variants") or {}).get("variant_details", []),
                    key=lambda item: (
                        item.get("asin"), item.get("name")
                    ) if isinstance(item, dict) else str(item),
                ),
            }
            merged["source_file"] = f"{merged.get('source_file')};{candidate.get('source_file')}"
        merged["price_resolution"] = _resolve_price_candidates(
            merged.get("price_candidates", []),
            preferred_currency=merged.get("currency"),
            product_asin=asin,
        )
        _apply_price_resolution(merged)
        merged["duplicate_source_count"] = len(candidates)
        catalog.append(merged)

    # A parent ASIN often has no price while one of its variant ASINs also
    # appears elsewhere in the crawl with a real price. Link that observed
    # price back to the parent for browse/filtering, but mark it as requiring
    # a variant choice so checkout never silently charges the cheapest child.
    by_asin = {product["asin"]: product for product in catalog}
    for product in catalog:
        existing_sources = {
            item.get("source") for item in product.get("price_candidates", [])
        }
        if existing_sources.intersection({"product", "offer", "variant"}):
            continue
        variants = product.get("variants") or {}
        references = list(variants.get("variant_asins") or [])
        references.extend(
            item.get("asin")
            for item in variants.get("variant_details") or []
            if isinstance(item, dict) and item.get("asin")
        )
        inherited = []
        for variant_asin in _dedupe(references):
            variant = by_asin.get(str(variant_asin).upper())
            if not variant or variant.get("price") is None:
                continue
            variant_resolution = variant.get("price_resolution") or {}
            if variant_resolution.get("source") in {"unavailable", "linked_variant"}:
                continue
            detail = next(
                (
                    item for item in variants.get("variant_details") or []
                    if isinstance(item, dict)
                    and str(item.get("asin", "")).upper() == str(variant_asin).upper()
                ),
                {},
            )
            inherited.append({
                "value": variant["price"],
                "currency": variant.get("currency"),
                "source": "variant_product",
                "variant_asin": variant["asin"],
                "variant_name": detail.get("name") if isinstance(detail, dict) else None,
            })
        if inherited:
            product["price_candidates"] = _dedupe(
                product.get("price_candidates", []) + inherited,
                key=lambda item: (
                    item.get("source"), item.get("value"), item.get("currency"),
                    item.get("variant_asin"), item.get("provider"),
                ),
            )
            product["price_resolution"] = _resolve_price_candidates(
                product["price_candidates"],
                preferred_currency=product.get("currency"),
                product_asin=product.get("asin"),
            )
            _apply_price_resolution(product)
        product["quality"] = quality_for(product)

    excluded = 0
    if allowed_kinds:
        before = len(catalog)
        catalog = [
            product
            for product in catalog
            if product["category_kind"] in allowed_kinds
        ]
        excluded = before - len(catalog)

    report = build_quality_report(records, catalog, invalid)
    report["excluded_by_category_kind"] = excluded
    report["allowed_category_kinds"] = sorted(allowed_kinds) if allowed_kinds else None
    return catalog, report


def build_quality_report(records: list, catalog: list[dict], invalid: int) -> dict:
    reasons = Counter()
    categories = Counter()
    price_sources = Counter()
    for product in catalog:
        reasons.update(product["quality"]["issues"])
        categories[product["category_kind"]] += 1
        price_sources[(product.get("price_resolution") or {}).get("source", "unavailable")] += 1
    return {
        "source_records": len(records),
        "invalid_records": invalid,
        "unique_asins": len(catalog),
        "duplicate_records_collapsed": len(records) - invalid - len(catalog),
        "ready_products": sum(product["quality"]["status"] == "ready" for product in catalog),
        "partial_products": sum(product["quality"]["status"] == "partial" for product in catalog),
        "quality_issue_counts": dict(reasons),
        "price_source_counts": dict(price_sources),
        "category_counts": dict(categories),
        "ready_definition": "ASIN, title, price, currency, stock, category, and at least one image",
    }


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    value = str(value).strip()
    for parser in (
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")).date(),
        lambda item: datetime.strptime(item, "%B %d, %Y").date(),
        lambda item: datetime.strptime(item, "%b %d, %Y").date(),
    ):
        try:
            return parser(value)
        except ValueError:
            continue
    return None


def _specs(product: dict) -> dict:
    attribute_text = " ".join(
        f"{item.get('name')}: {item.get('value')}"
        for item in product.get("attributes", [])
    )
    text_value = " ".join(
        [
            product.get("title") or "",
            product.get("description") or "",
            product.get("breadcrumbs") or "",
            " ".join(product.get("features", [])),
            attribute_text,
        ]
    )
    return {
        "ram_gb": ProductSpecExtractor.extract_ram(text_value),
        "storage_gb": ProductSpecExtractor.extract_storage(text_value),
        "gpu": ProductSpecExtractor.extract_gpu(text_value),
        "cpu": ProductSpecExtractor.extract_cpu(text_value),
        "screen_size_inches": ProductSpecExtractor.extract_screen_size(text_value),
    }


def _review_id(review: dict) -> str:
    return str(review["review_id"])


def upsert_catalog(catalog: list[dict], source: str = "apify") -> dict:
    _ensure_price_schema()
    product_sql = text(
        """
        INSERT INTO products (
            asin, original_asin, title, brand, url, price, currency,
            price_min, price_max, price_source, price_is_exact,
            price_selection_required, price_options_count,
            list_price, shipping_price, in_stock, in_stock_text, stars,
            reviews_count, answered_questions, breadcrumbs, description,
            delivery, fastest_delivery, return_policy, condition,
            is_amazon_choice, amazon_choice_text, video_count, raw_data,
            updated_at
        ) VALUES (
            :asin, :original_asin, :title, :brand, :url, :price, :currency,
            :price_min, :price_max, :price_source, :price_is_exact,
            :price_selection_required, :price_options_count,
            :list_price, :shipping_price, :in_stock, :in_stock_text, :stars,
            :reviews_count, :answered_questions, :breadcrumbs, :description,
            :delivery, :fastest_delivery, :return_policy, :condition,
            :is_amazon_choice, :amazon_choice_text, :video_count,
            CAST(:raw_data AS jsonb), CURRENT_TIMESTAMP
        )
        ON CONFLICT (asin) DO UPDATE SET
            original_asin = EXCLUDED.original_asin,
            title = EXCLUDED.title,
            brand = EXCLUDED.brand,
            url = EXCLUDED.url,
            price = EXCLUDED.price,
            currency = EXCLUDED.currency,
            price_min = EXCLUDED.price_min,
            price_max = EXCLUDED.price_max,
            price_source = EXCLUDED.price_source,
            price_is_exact = EXCLUDED.price_is_exact,
            price_selection_required = EXCLUDED.price_selection_required,
            price_options_count = EXCLUDED.price_options_count,
            list_price = EXCLUDED.list_price,
            shipping_price = EXCLUDED.shipping_price,
            in_stock = EXCLUDED.in_stock,
            in_stock_text = EXCLUDED.in_stock_text,
            stars = EXCLUDED.stars,
            reviews_count = EXCLUDED.reviews_count,
            answered_questions = EXCLUDED.answered_questions,
            breadcrumbs = EXCLUDED.breadcrumbs,
            description = EXCLUDED.description,
            delivery = EXCLUDED.delivery,
            fastest_delivery = EXCLUDED.fastest_delivery,
            return_policy = EXCLUDED.return_policy,
            condition = EXCLUDED.condition,
            is_amazon_choice = EXCLUDED.is_amazon_choice,
            amazon_choice_text = EXCLUDED.amazon_choice_text,
            video_count = EXCLUDED.video_count,
            raw_data = EXCLUDED.raw_data,
            updated_at = CURRENT_TIMESTAMP
        RETURNING product_id
        """
    )
    specs_sql = text(
        """
        INSERT INTO product_specs (
            product_id, ram_gb, storage_gb, gpu, cpu, screen_size_inches, updated_at
        ) VALUES (
            :product_id, :ram_gb, :storage_gb, :gpu, :cpu, :screen_size_inches, CURRENT_TIMESTAMP
        )
        ON CONFLICT (product_id) DO UPDATE SET
            ram_gb = EXCLUDED.ram_gb, storage_gb = EXCLUDED.storage_gb,
            gpu = EXCLUDED.gpu, cpu = EXCLUDED.cpu,
            screen_size_inches = EXCLUDED.screen_size_inches,
            updated_at = CURRENT_TIMESTAMP
        """
    )
    attribute_sql = text(
        """
        INSERT INTO product_attributes (product_id, attribute_name, attribute_value)
        VALUES (:product_id, :name, :value)
        """
    )
    review_sql = text(
        """
        INSERT INTO reviews (
            review_id, product_id, username, rating, title, review_text,
            review_date, review_url, reaction, is_verified, is_amazon_vine,
            variant, raw_data
        ) VALUES (
            :review_id, :product_id, :username, :rating, :title, :review_text,
            :review_date, :review_url, :reaction, :is_verified, :is_amazon_vine,
            :variant, CAST(:raw_data AS jsonb)
        ) ON CONFLICT (review_id) DO UPDATE SET
            product_id = EXCLUDED.product_id, username = EXCLUDED.username,
            rating = EXCLUDED.rating, title = EXCLUDED.title,
            review_text = EXCLUDED.review_text, review_date = EXCLUDED.review_date,
            review_url = EXCLUDED.review_url, reaction = EXCLUDED.reaction,
            is_verified = EXCLUDED.is_verified, is_amazon_vine = EXCLUDED.is_amazon_vine,
            variant = EXCLUDED.variant, raw_data = EXCLUDED.raw_data
        """
    )
    media_sql = text(
        """
        INSERT INTO media (product_id, review_id, media_type, url, source, metadata)
        VALUES (:product_id, :review_id, :media_type, :url, :source, CAST(:metadata AS jsonb))
        ON CONFLICT (product_id, review_id, media_type, url) DO NOTHING
        """
    )
    variant_sql = text(
        """
        INSERT INTO product_variants (
            product_id, asin, name, price, currency, thumbnail_url,
            in_stock, raw_data
        ) VALUES (
            :product_id, :asin, :name, :price, :currency, :thumbnail_url,
            :in_stock, CAST(:raw_data AS jsonb)
        )
        """
    )
    offer_sql = text(
        """
        INSERT INTO product_offers (
            product_id, provider, seller_name, seller_id, url, price,
            currency, shipping_price, in_stock, condition, raw_data
        ) VALUES (
            :product_id, :provider, :seller_name, :seller_id, :url, :price,
            :currency, :shipping_price, :in_stock, :condition,
            CAST(:raw_data AS jsonb)
        )
        """
    )

    with engine.begin() as connection:
        inserted = 0
        for product in catalog:
            raw_data = dict(product)
            raw_data["pipeline"] = {
                "version": 3,
                "quality": product["quality"],
                "source_file": product.get("source_file"),
                "duplicate_source_count": product.get("duplicate_source_count", 1),
            }
            product_row = {
                key: product.get(key)
                for key in (
                    "asin", "original_asin", "title", "brand", "url", "price", "currency",
                    "price_min", "price_max", "price_source", "price_is_exact",
                    "price_selection_required", "price_options_count",
                    "list_price", "shipping_price", "in_stock", "in_stock_text", "stars",
                    "reviews_count", "answered_questions", "breadcrumbs", "description",
                    "delivery", "fastest_delivery", "return_policy", "condition",
                    "is_amazon_choice", "amazon_choice_text", "video_count",
                )
            }
            product_row["raw_data"] = json.dumps(raw_data, ensure_ascii=False, default=str)
            product_id = connection.execute(product_sql, product_row).scalar_one()

            # Rebuild child rows for this ASIN. This prevents stale media,
            # reviews, and attributes when a later crawl changes the record.
            connection.execute(text("DELETE FROM media WHERE product_id = :product_id"), {"product_id": product_id})
            connection.execute(text("DELETE FROM reviews WHERE product_id = :product_id"), {"product_id": product_id})
            connection.execute(text("DELETE FROM product_attributes WHERE product_id = :product_id"), {"product_id": product_id})
            connection.execute(text("DELETE FROM product_variants WHERE product_id = :product_id"), {"product_id": product_id})
            connection.execute(text("DELETE FROM product_offers WHERE product_id = :product_id"), {"product_id": product_id})

            for attribute in product.get("attributes", []):
                connection.execute(attribute_sql, {"product_id": product_id, **attribute})

            review_ids = set()
            for review in product.get("reviews", []):
                review_id = _review_id(review)
                review_ids.add(review_id)
                connection.execute(
                    review_sql,
                    {
                        "review_id": review_id,
                        "product_id": product_id,
                        "username": review.get("username"),
                        "rating": review.get("rating"),
                        "title": review.get("title"),
                        "review_text": review.get("review_text"),
                        "review_date": _parse_date(review.get("review_date")),
                        "review_url": review.get("review_url"),
                        "reaction": review.get("reaction"),
                        "is_verified": review.get("is_verified"),
                        "is_amazon_vine": review.get("is_amazon_vine"),
                        "variant": review.get("variant"),
                        "raw_data": json.dumps(review.get("raw_data") or {}, ensure_ascii=False, default=str),
                    },
                )
                for image_url in _dedupe(review.get("media", [])):
                    if image_url:
                        connection.execute(
                            media_sql,
                            {
                                "product_id": product_id,
                                "review_id": review_id,
                                "media_type": "review_image",
                                "url": image_url,
                                "source": source,
                                "metadata": json.dumps({"review_id": review_id}),
                            },
                        )

            for image in product.get("media", []):
                connection.execute(
                    media_sql,
                    {
                        "product_id": product_id,
                        "review_id": None,
                        "media_type": image["media_type"],
                        "url": image["url"],
                        "source": source,
                        "metadata": json.dumps(
                            {
                                "source_file": product.get("source_file"),
                                **(image.get("metadata") or {}),
                            }
                        ),
                    },
                )

            for variant in _variant_rows(product):
                connection.execute(
                    variant_sql,
                    {
                        "product_id": product_id,
                        "asin": variant.get("asin"),
                        "name": variant.get("name"),
                        "price": variant.get("price"),
                        "currency": variant.get("currency"),
                        "thumbnail_url": variant.get("thumbnail_url"),
                        "in_stock": variant.get("in_stock"),
                        "raw_data": json.dumps(
                            variant.get("raw_data") or {},
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                )

            for offer in product.get("offers", []):
                connection.execute(
                    offer_sql,
                    {
                        "product_id": product_id,
                        "provider": offer.get("provider"),
                        "seller_name": offer.get("seller_name"),
                        "seller_id": offer.get("seller_id"),
                        "url": offer.get("url"),
                        "price": offer.get("price"),
                        "currency": offer.get("currency"),
                        "shipping_price": offer.get("shipping_price"),
                        "in_stock": offer.get("in_stock"),
                        "condition": offer.get("condition"),
                        "raw_data": json.dumps(
                            offer.get("raw_data") or {},
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                )

            connection.execute(specs_sql, {"product_id": product_id, **_specs(product)})
            inserted += 1

    return {"products_upserted": inserted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--processed-file", type=Path, default=DEFAULT_PROCESSED_FILE)
    parser.add_argument("--canonical-file", type=Path, default=DEFAULT_CANONICAL_FILE)
    parser.add_argument("--report-file", type=Path, default=DEFAULT_REPORT_FILE)
    parser.add_argument(
        "--kinds",
        default="",
        help="Optional comma-separated category kinds to keep",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build files/report without writing PostgreSQL")
    args = parser.parse_args()

    allowed_kinds = {
        item.strip()
        for item in args.kinds.split(",")
        if item.strip()
    } or None
    catalog, report = build_catalog(
        args.raw_dir,
        args.processed_file,
        allowed_kinds,
    )
    args.canonical_file.parent.mkdir(parents=True, exist_ok=True)
    args.canonical_file.write_text(json.dumps(catalog, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    if not args.dry_run:
        print(json.dumps(upsert_catalog(catalog), indent=2))


if __name__ == "__main__":
    main()
