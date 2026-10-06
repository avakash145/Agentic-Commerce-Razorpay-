from pathlib import Path
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from collections import defaultdict
import json
import os
import uuid
import hmac
import hashlib
import requests

from django.http import (
    JsonResponse,
    FileResponse,
    HttpResponse,
)

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from django.conf import settings
from config import settings as config_settings

from app.catalog.search_service import (
    CatalogSearchService
)

from app.agent.commerce_search import (
    CommerceSearchService
)

from app.db.database import (
    engine,
    SessionLocal
)

from app.payments.transaction_repository import (
    TransactionRepository
)

from app.payments.transaction_service import (
    TransactionService
)

from app.payments.fx_service import (
    FXService
)

from app.payments.currency import (
    to_subunits,
    normalize_currency
)

from sqlalchemy import text
from app.api.webhook import razorpay_webhook
from app.commerce.user_commerce_service import get_user_commerce_service

# PATHS

BASE_DIR = Path(
    config_settings.BASE_DIR
)


STATIC_DIR = (
    BASE_DIR
    / "app"
    / "static"
)

# SERVICES

catalog_service = None
commerce_search_service = None

fx_service = (
    FXService()
)


def get_catalog_search_service():
    global catalog_service

    if catalog_service is None:
        catalog_service = CatalogSearchService()

    return catalog_service


def get_commerce_search_service():
    global commerce_search_service

    if commerce_search_service is None:
        commerce_search_service = CommerceSearchService(
            search_service=get_catalog_search_service()
        )

    return commerce_search_service


from app.agent.langchain_copilot import LangChainCommerceCopilot

langchain_copilot = None


def get_langchain_copilot():
    global langchain_copilot

    if langchain_copilot is None:
        langchain_copilot = LangChainCommerceCopilot()

    return langchain_copilot


# JSON SAFE

def make_json_safe(
    value: Any
):

    if value is None:

        return None


    if isinstance(
        value,
        Decimal
    ):

        return float(value)


    if isinstance(
        value,
        dict
    ):

        return {

            str(key):
                make_json_safe(item)

            for key, item
            in value.items()

        }


    if isinstance(
        value,
        list
    ):

        return [
            make_json_safe(item)

            for item in value
        ]


    if hasattr(
        value,
        "isoformat"
    ):

        return value.isoformat()


    return value


# HEALTH


@require_GET
def health(
    request
):

    return JsonResponse({

        "status":
            "ok",

        "service":
            "agentic-commerce",

        "framework":
            "django"

    })


# STORE & CHAT PAGES

@require_GET
def store_page(
    request
):
    file_path = (
        STATIC_DIR
        / "ecommerce.html"
    )

    if not file_path.exists():
        file_path = (
            STATIC_DIR
            / "chatbot.html"
        )

    if not file_path.exists():
        return HttpResponse(
            "Storefront not found",
            status=500
        )

    return FileResponse(
        open(
            file_path,
            "rb"
        ),
        content_type="text/html"
    )


@require_GET
def chat_page(
    request
):
    file_path = (
        STATIC_DIR
        / "ecommerce.html"
    )

    if not file_path.exists():
        file_path = (
            STATIC_DIR
            / "chatbot.html"
        )

    if not file_path.exists():
        return HttpResponse(
            "Storefront not found",
            status=500
        )

    return FileResponse(
        open(
            file_path,
            "rb"
        ),
        content_type="text/html"
    )


@require_GET
def legacy_chat_page(
    request
):
    file_path = (
        STATIC_DIR
        / "chatbot.html"
    )

    if not file_path.exists():
        return HttpResponse(
            "chatbot.html not found",
            status=500
        )

    return FileResponse(
        open(
            file_path,
            "rb"
        ),
        content_type="text/html"
    )


# CHECKOUT PAGE

@require_GET
def checkout_page(
    request
):

    file_path = (
        STATIC_DIR
        / "checkout.html"
    )


    if not file_path.exists():

        return HttpResponse(
            "checkout.html not found",
            status=500
        )


    return FileResponse(
        open(
            file_path,
            "rb"
        ),

        content_type="text/html"
    )


# IMAGE PROXY


ALLOWED_IMAGE_HOSTS = {

    "m.media-amazon.com",

    "images-na.ssl-images-amazon.com",

    "images.amazon.com",

    "images-eu.ssl-images-amazon.com",

    "images-fe.ssl-images-amazon.com",

    "images.amazon.in",
    "m.media-amazon.com"
}


@require_GET
def image_proxy(
    request
):

    url = (
        request.GET.get(
            "url",
            ""
        )
        .strip()
    )


    if not url:

        return JsonResponse(
            {
                "error":
                    "Missing image URL"
            },

            status=400
        )


    # PARSE

    try:

        parsed = urlparse(
            url
        )

    except Exception:

        return JsonResponse(
            {
                "error":
                    "Invalid image URL"
            },

            status=400
        )


    # SCHEME

    if parsed.scheme not in {

        "http",

        "https"

    }:

        return JsonResponse(
            {
                "error":
                    "Only HTTP/HTTPS images are allowed"
            },

            status=400
        )


    # HOST

    hostname = (
        parsed.hostname
        or ""
    ).lower()


    if hostname not in ALLOWED_IMAGE_HOSTS:

        return JsonResponse(
            {
                "error":
                    "Image domain is not allowed"
            },

            status=403
        )


    # REQUEST IMAGE

    try:

        response = requests.get(

            url,

            headers={

                "User-Agent":
                    (
                        "Mozilla/5.0 "
                        "(X11; Linux x86_64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/140 Safari/537.36"
                    ),

                "Accept":
                    (
                        "image/avif,"
                        "image/webp,"
                        "image/apng,"
                        "image/svg+xml,"
                        "image/*,"
                        "*/*;q=0.8"
                    ),

                "Referer":
                    "https://www.amazon.com/",

            },

            timeout=15

        )

        response.raise_for_status()


    except requests.RequestException as exc:

        return JsonResponse(
            {
                "error":
                    (
                        "Unable to load image: "
                        + str(exc)
                    )
            },

            status=502
        )

    # CONTENT TYPE
    content_type = (

        response.headers
        .get(
            "content-type",
            ""
        )

    )


    if not content_type.startswith(
        "image/"
    ):

        return JsonResponse(
            {
                "error":
                    "Remote resource is not an image"
            },

            status=415
        )


    # RETURN

    return HttpResponse(

        response.content,

        content_type=content_type,

        headers={

            "Cache-Control":
                "public, max-age=86400"

        }

    )


def _price_inr(price, currency):
    if price is None or not currency:
        return None
    try:
        normalized_currency = normalize_currency(currency)
        rate = fx_service.get_rate(normalized_currency, "INR")
        return Decimal(str(price)) * Decimal(str(rate))
    except Exception:
        return None


def _product_summary(row, specs=None):
    item = dict(row)
    item["image_url"] = item.get("image")
    item["price_inr"] = _price_inr(item.get("price"), item.get("currency"))
    item["price_min_inr"] = _price_inr(item.get("price_min"), item.get("currency"))
    item["price_max_inr"] = _price_inr(item.get("price_max"), item.get("currency"))
    item["specs"] = specs or {}
    item.pop("image", None)
    return make_json_safe(item)


# PRODUCT DETAIL

@require_GET
def product_detail(
    request,
    asin: str,
    reviews_limit: int = 12
):
    """Return the complete browseable product view for one catalog ASIN."""

    product_sql = text(
        """
        SELECT
            p.product_id, p.asin, p.original_asin, p.title, p.brand, p.url,
            p.price, p.currency, p.price_min, p.price_max, p.price_source,
            p.price_is_exact, p.price_selection_required, p.price_options_count,
            p.list_price, p.shipping_price, p.in_stock,
            p.in_stock_text, p.stars, p.reviews_count, p.answered_questions,
            p.breadcrumbs, p.description, p.delivery, p.fastest_delivery,
            p.return_policy, p.condition, p.is_amazon_choice,
            p.amazon_choice_text, p.video_count, p.raw_data
        FROM products p
        WHERE p.asin = :asin
        """
    )
    media_sql = text(
        """
        SELECT media_id, media_type, url, metadata
        FROM media
        WHERE product_id = :product_id
          AND review_id IS NULL
          AND url IS NOT NULL
          AND media_type IN (
              'image', 'product_thumbnail', 'product_gallery',
              'product_high_resolution', 'product_aplus', 'video_preview'
          )
        ORDER BY
            CASE media_type
                WHEN 'product_thumbnail' THEN 1
                WHEN 'product_high_resolution' THEN 2
                WHEN 'product_gallery' THEN 3
                WHEN 'product_aplus' THEN 4
                ELSE 5
            END,
            media_id
        """
    )
    attributes_sql = text(
        """
        SELECT attribute_name, attribute_value
        FROM product_attributes
        WHERE product_id = :product_id
        ORDER BY attribute_id
        """
    )
    specs_sql = text(
        """
        SELECT ram_gb, storage_gb, gpu, cpu, screen_size_inches
        FROM product_specs
        WHERE product_id = :product_id
        """
    )
    reviews_sql = text(
        """
        SELECT review_id, username, rating, title, review_text, review_date,
               review_url, reaction, is_verified, is_amazon_vine, variant
        FROM reviews
        WHERE product_id = :product_id
        ORDER BY review_date DESC NULLS LAST, review_id
        LIMIT :reviews_limit
        """
    )
    review_media_sql = text(
        """
        SELECT review_id, url
        FROM media
        WHERE product_id = :product_id
          AND review_id IS NOT NULL
          AND url IS NOT NULL
        ORDER BY media_id
        """
    )
    videos_sql = text(
        """
        SELECT media_id, url, metadata
        FROM media
        WHERE product_id = :product_id
          AND review_id IS NULL
          AND media_type = 'product_video'
          AND url IS NOT NULL
        ORDER BY media_id
        """
    )
    variants_sql = text(
        """
        SELECT variant_id, asin, name, price, currency, thumbnail_url,
               in_stock
        FROM product_variants
        WHERE product_id = :product_id
        ORDER BY variant_id
        """
    )
    offers_sql = text(
        """
        SELECT offer_id, provider, seller_name, seller_id, url, price,
               currency, shipping_price, in_stock, condition
        FROM product_offers
        WHERE product_id = :product_id
        ORDER BY price ASC NULLS LAST, offer_id
        """
    )

    with engine.connect() as connection:
        row = connection.execute(product_sql, {"asin": asin.strip()}).mappings().first()
        if row is None:
            return JsonResponse({"detail": "Product not found"}, status=404)

        product = dict(row)
        product_id = product["product_id"]
        raw_data = product.pop("raw_data", {}) or {}
        if not isinstance(raw_data, dict):
            raw_data = {}

        media = [dict(item) for item in connection.execute(media_sql, {"product_id": product_id}).mappings()]
        videos = [dict(item) for item in connection.execute(videos_sql, {"product_id": product_id}).mappings()]
        variant_rows = [dict(item) for item in connection.execute(variants_sql, {"product_id": product_id}).mappings()]
        offer_rows = [dict(item) for item in connection.execute(offers_sql, {"product_id": product_id}).mappings()]
        attributes = [dict(item) for item in connection.execute(attributes_sql, {"product_id": product_id}).mappings()]
        specs_row = connection.execute(specs_sql, {"product_id": product_id}).mappings().first()
        specs = dict(specs_row) if specs_row else {}
        reviews = [dict(item) for item in connection.execute(reviews_sql, {"product_id": product_id, "reviews_limit": reviews_limit}).mappings()]
        review_media = defaultdict(list)
        for item in connection.execute(review_media_sql, {"product_id": product_id}).mappings():
            review_media[item["review_id"]].append(item["url"])

        for review in reviews:
            review["images"] = review_media.get(review["review_id"], [])

        breadcrumb_leaf = (product.get("breadcrumbs") or "").split(">")[-1].strip()
        category_pattern = f"%{breadcrumb_leaf}%" if breadcrumb_leaf else "%__no_category__%"
        brand = product.get("brand") or ""
        similar_sql = text(
            """
            SELECT
                p.product_id, p.asin, p.title, p.brand, p.price, p.currency,
                p.stars, p.reviews_count, p.in_stock,
                (
                    SELECT m.url
                    FROM media m
                    WHERE m.product_id = p.product_id
                      AND m.review_id IS NULL
                      AND m.url IS NOT NULL
                    ORDER BY CASE m.media_type
                        WHEN 'product_thumbnail' THEN 1
                        WHEN 'product_gallery' THEN 2
                        WHEN 'product_high_resolution' THEN 3
                        ELSE 4 END,
                        m.media_id
                    LIMIT 1
                ) AS image
            FROM products p
            WHERE p.product_id <> :product_id
              AND (
                    p.breadcrumbs ILIKE :category_pattern
                    OR (:brand <> '' AND lower(p.brand) = lower(:brand))
              )
            ORDER BY
                CASE WHEN p.breadcrumbs ILIKE :category_pattern THEN 0 ELSE 1 END,
                p.stars DESC NULLS LAST,
                p.reviews_count DESC NULLS LAST
            LIMIT 6
            """
        )
        similar_rows = [dict(item) for item in connection.execute(
            similar_sql,
            {
                "product_id": product_id,
                "category_pattern": category_pattern,
                "brand": brand,
            },
        ).mappings()]
        similar_specs = {}
        for similar in similar_rows:
            similar_spec = connection.execute(
                    specs_sql,
                    {"product_id": similar["product_id"]},
            ).mappings().first()
            similar_specs[similar["product_id"]] = dict(similar_spec) if similar_spec else {}

    source = raw_data.get("canonical", raw_data)
    if not isinstance(source, dict):
        source = {}
    content = source.get("content", {}) if isinstance(source.get("content"), dict) else {}
    classification = source.get("classification", {})
    if not isinstance(classification, dict):
        classification = {}
    ratings = source.get("ratings", {}) if isinstance(source.get("ratings"), dict) else {}
    review_intelligence = source.get("review_intelligence", {})
    if not isinstance(review_intelligence, dict):
        review_intelligence = {}
    seller_source = source.get("seller") or {}
    if not isinstance(seller_source, dict):
        seller_source = {}
    seller = {
        key: seller_source.get(key)
        for key in ("name", "id", "url")
        if seller_source.get(key)
    }

    product["price_inr"] = _price_inr(product.get("price"), product.get("currency"))
    product["price_min_inr"] = _price_inr(product.get("price_min"), product.get("currency"))
    product["price_max_inr"] = _price_inr(product.get("price_max"), product.get("currency"))
    product["checkout_ready"] = bool(
        product.get("price") is not None
        and product.get("currency")
        and product.get("in_stock") is True
        and product.get("price_selection_required") is not True
    )

    raw_variants = source.get("variants") or {}
    if not isinstance(raw_variants, dict):
        raw_variants = {}
    variants = {
        "variant_asins": raw_variants.get("variant_asins") or [],
        "variant_details": variant_rows,
    }

    response = {
        "product": product,
        "images": media,
        "videos": videos,
        "attributes": attributes,
        "specs": specs,
        "features": source.get("features") or content.get("features") or [],
        "product_overview": source.get("product_overview") or classification.get("product_overview", []),
        "rating_breakdown": source.get("stars_breakdown") or ratings.get("stars_breakdown") or {},
        "review_intelligence": review_intelligence,
        "seller": seller,
        "offers": offer_rows or source.get("offers") or [],
        "variants": variants,
        "reviews": reviews,
        "similar_products": [
            _product_summary(similar, similar_specs.get(similar["product_id"]))
            for similar in similar_rows
        ],
    }
    return JsonResponse(make_json_safe(response))


# CHAT API

@csrf_exempt
@require_POST
def chat(
    request
):

    # JSON

    try:

        body = (
            request.body
            .decode("utf-8")
        )

        import json

        data = json.loads(
            body
        )

    except Exception:

        return JsonResponse(
            {
                "message":
                    "Invalid JSON request.",

                "products":
                    []

            },
            status=400
        )

    # MESSAGE

    query = (
        str(
            data.get(
                "message",
                ""
            )
        )
        .strip()
    )


    if not query:

        return JsonResponse({
            "message":
                "Please enter a product request.",

            "products":
                []

        })


    print()
    print(
        "=" * 70
    )

    print(
        "CHAT REQUEST:",
        query
    )

    print(
        "=" * 70
    )


    try:

        # INTENT-AWARE SEARCH + DETERMINISTIC FILTERING

        search_result = get_commerce_search_service().search(
            user_query=query,
            retrieval_limit=20,
        )

        products = search_result["products"]


        print(
            "Candidates:",
            len(products)
        )


        # FRONTEND PRODUCTS

        frontend_products = []


        for product in products:

            item = dict(
                product
            )


            # IMAGE

            image_url = (

                item.get(
                    "image_url"
                )

                or

                item.get(
                    "image"
                )

                or

                item.get(
                    "thumbnail"
                )
            )


            item[
                "image_url"
            ] = image_url


            # PRICE

            if "price" in item:

                item[
                    "price"
                ] = make_json_safe(
                    item[
                        "price"
                    ]
                )

            # INR PRICE

            if "price_inr" in item:

                item[
                    "price_inr"
                ] = make_json_safe(
                    item[
                        "price_inr"
                    ]
                )

            # FX RATE

            if "fx_rate" in item:

                item[
                    "fx_rate"
                ] = make_json_safe(
                    item[
                        "fx_rate"
                    ]
                )

            # FX TIMESTAMP
            if "fx_timestamp" in item:

                item[
                    "fx_timestamp"
                ] = make_json_safe(
                    item[
                        "fx_timestamp"
                    ]
                )

            # SPECS

            if "specs" not in item:

                item[
                    "specs"
                ] = {}


            item[
                "specs"
            ] = make_json_safe(
                item[
                    "specs"
                ]
            )
            # PRODUCT

            frontend_products.append(
                make_json_safe(
                    item
                )
            )
        # RESPONSE MESSAGE

        if frontend_products:

            message = (
                f"I found "
                f"{len(frontend_products)} "
                f"products matching your search."
            )

        else:

            message = (
                "I couldn't find products "
                "matching your requirements."
            )


        print(
            "Eligible products:",
            len(frontend_products)
        )


        return JsonResponse(
            {
                "message":
                    message,

                "products":
                    frontend_products
            },
            status=200
        )


    except Exception as exc:

        # LOG

        print()
        print(
            "[CHAT ERROR]"
        )

        print(
            repr(exc)
        )

        # RETURN ERROR TO FRONTEND

        return JsonResponse(
            {
                "message":
                    "Something went wrong while searching the catalog.",

                "products": []
            },
            status=500
        )


# CREATE RAZORPAY CHECKOUT ORDER

@csrf_exempt
@require_POST
def create_checkout_order(
    request
):

    # PARSE JSON
    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON request"}, status=400)

    # ASIN

    asin = (
        data.get("asin", "")
        .strip()
    )


    if not asin:

        return JsonResponse(
            {
                "detail": "ASIN is required"
            },
            status=400
        )


    print()
    print(
        "=" * 70
    )

    print(
        "CHECKOUT REQUEST"
    )

    print(
        "ASIN:",
        asin
    )

    print(
        "=" * 70
    )

    # LOAD PRODUCT FROM POSTGRES

    sql = text(

        """
        SELECT

            product_id,

            asin,

            title,

            price,
            currency,

            price_selection_required,

            in_stock

        FROM products

        WHERE asin = :asin

        LIMIT 1
        """
    )


    try:

        with engine.connect() as conn:

            row = (

                conn.execute(

                    sql,

                    {
                        "asin":
                            asin
                    }

                )
                .mappings()
                .first()
            )


    except Exception as exc:

        print(
            "[DATABASE ERROR]",
            repr(exc)
        )


        return JsonResponse(
            {
                "detail": "Unable to load product"
            },
            status=500
        )


    # PRODUCT NOT FOUND

    if not row:

        return JsonResponse(
            {
                "detail": f"Product not found: {asin}"
            },
            status=404
        )

    if row["in_stock"] is False:
        return JsonResponse(
            {"detail": "This product is currently out of stock"},
            status=409
        )

    if row["price_selection_required"] is True:
        return JsonResponse(
            {"detail": "Select a priced variant or seller offer before checkout"},
            status=409
        )


    # PRODUCT PRICE

    price = row[
        "price"
    ]


    currency = row[
        "currency"
    ]


    if price is None:

        return JsonResponse(
            {
                "detail": "Product has no price"
            },
            status=400
        )


    if not currency:

        return JsonResponse(
            {
                "detail": "Product has no currency"
            },
            status=400
        )


    price = Decimal(
        str(price)
    )


    # FX CONVERSION

    try:

        fx_result = (

            fx_service
            .convert_to_inr(

                amount=
                    price,

                currency=
                    currency
            )
        )


    except Exception as exc:

        print(
            "[CHECKOUT FX ERROR]",
            repr(exc)
        )


        return JsonResponse(
            {
                "detail": (
                    "Unable to convert "
                    "product price to INR: "
                    + str(exc)
                )
            },
            status=502
        )


    # INR AMOUNT

    amount_inr = (

        fx_result[
            "target_amount"
        ]
    )


    amount_inr = Decimal(
        str(amount_inr)
    )


    # CONVERT INR → PAISE

    amount_subunits = (

        to_subunits(

            amount=
                amount_inr,

            currency=
                "INR"
        )
    )


    if amount_subunits <= 0:

        return JsonResponse(
            {
                "detail": "Invalid Razorpay amount"
            },
            status=400
        )


    # RAZORPAY CREDENTIALS

    key_id = (os.getenv(
        "RAZORPAY_KEY_ID"
    ) or "").strip()


    key_secret = (os.getenv(
        "RAZORPAY_KEY_SECRET"
    ) or "").strip()


    if not key_id:

        return JsonResponse(
            {
                "detail": "RAZORPAY_KEY_ID is not configured"
            },
            status=500
        )

    if not key_id.startswith("rzp_test_"):
        return JsonResponse(
            {"detail": "Only Razorpay Test Mode keys are allowed"},
            status=500
        )


    if not key_secret:

        return JsonResponse(
            {
                "detail": "RAZORPAY_KEY_SECRET is not configured"
            },
            status=500
        )


    # RECEIPT

    receipt = (
        "agent_"
        +
        uuid.uuid4().hex[:24]
    )


    # RAZORPAY REQUEST
    razorpay_payload = {

        "amount":
            amount_subunits,

        "currency":
            "INR",

        "receipt":
            receipt,

        "notes": {

            "asin":
                asin,

            "product_id":
                str(
                    row[
                        "product_id"
                    ]
                ),

            "source_currency":
                str(
                    fx_result[
                        "source_currency"
                    ]
                ),

            "source_amount":
                str(
                    price
                )
        }
    }


    print()
    print(
        "RAZORPAY ORDER"
    )

    print(
        "Original price:",
        price
    )

    print(
        "Original currency:",
        currency
    )

    print(
        "INR amount:",
        amount_inr
    )

    print(
        "Razorpay paise:",
        amount_subunits
    )


    # CREATE ORDER

    try:

        response = requests.post(

            "https://api.razorpay.com/v1/orders",

            auth=(

                key_id,

                key_secret
            ),

            json=
                razorpay_payload,

            headers={
                "Content-Type":
                    "application/json"
            },

            timeout=15
        )


    except requests.RequestException as exc:

        print(
            "[RAZORPAY CONNECTION ERROR]",
            repr(exc)
        )


        return JsonResponse(
            {
                "detail": "Unable to connect to Razorpay"
            },
            status=502
        )

    # RAZORPAY 

    if not response.ok:

        print()

        print(
            "[RAZORPAY ORDER ERROR]"
        )

        print(
            "Status:",
            response.status_code
        )

        print(
            "Response:",
            response.text
        )


        try:

            error_data = (
                response.json()
            )

        except Exception:

            error_data = {
                "error":
                    response.text
            }


        return JsonResponse(
            error_data,
            status=response.status_code
        )


    # ORDER

    order = (
        response.json()
    )


    print()
    print(
        "RAZORPAY ORDER CREATED"
    )

    print(
        "Order ID:",
        order.get("id")
    )

    print(
        "Amount:",
        order.get("amount")
    )

    print(
        "Currency:",
        order.get("currency")
    )

    print(
        "=" * 70
    )

    # Persist the server-authoritative order before returning its details
    # to the browser.  Webhooks use this record to bind payment amount,
    # currency, and order ID before changing transaction state.
    db = SessionLocal()
    transaction_id = f"txn_{order['id']}"
    mandate_id = f"checkout_{asin}_{uuid.uuid4().hex[:8]}"

    try:
        transaction_repository = TransactionRepository(db)
        transaction_repository.create(
            transaction_id=transaction_id,
            mandate_id=mandate_id,
            razorpay_order_id=order["id"],
            amount=amount_inr,
            currency="INR",
            source_amount=price,
            source_currency=fx_result["source_currency"],
            fx_rate=fx_result["rate"],
            fx_timestamp=fx_result["timestamp"],
        )
    except Exception as exc:
        db.rollback()
        print("[TRANSACTION PERSISTENCE ERROR]", repr(exc))
        return JsonResponse(
            {"detail": "Order created but could not be recorded locally"},
            status=500
        )
    finally:
        db.close()


    # FRONTEND RESPONSE

    return JsonResponse({
        "order_id":
            order["id"],

        "amount":
            order["amount"],

        "currency":
            order["currency"],

        "amount_inr":
            float(
                amount_inr
            ),

        "source_amount":
            float(
                price
            ),

        "source_currency":
            fx_result[
                "source_currency"
            ],

        "fx_rate":
            float(
                fx_result[
                    "rate"
                ]
            ),

        "fx_timestamp":
            make_json_safe(
                fx_result[
                    "timestamp"
                ]
            ),

        "key_id":
            key_id,

        "asin":
            asin,

        "product_id":
            row[
                "product_id"
            ],

        "title":
            row[
                "title"
            ],

        "transaction_id":
            transaction_id
    })


# VERIFY RAZORPAY PAYMENT

@csrf_exempt
@require_POST
def verify_payment(
    request
):

    # PARSE JSON
    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON request"}, status=400)

    razorpay_payment_id = data.get("razorpay_payment_id", "").strip()
    razorpay_order_id = data.get("razorpay_order_id", "").strip()
    razorpay_signature = data.get("razorpay_signature", "").strip()

    # SECRET
    key_secret = (os.getenv(
        "RAZORPAY_KEY_SECRET"
    ) or "").strip()


    if not key_secret:

        return JsonResponse(
            {
                "detail": "RAZORPAY_KEY_SECRET is not configured"
            },
            status=500
        )


    # MESSAGE
    #
    # Razorpay signature:
    #
    # order_id + "|" + payment_id

    message = (
        razorpay_order_id
        +
        "|"
        +
        razorpay_payment_id
    )

    # HMAC

    generated_signature = (
        hmac.new(

            key_secret.encode(
                "utf-8"
            ),

            message.encode(
                "utf-8"
            ),

            hashlib.sha256
        ).hexdigest()
    )
    # COMPARE

    valid = hmac.compare_digest(
        generated_signature,
        razorpay_signature
    )


    if not valid:

        print()
        print(
            "[PAYMENT VERIFICATION FAILED]"
        )

        print(
            "Order:",
            razorpay_order_id
        )

        print(
            "Payment:",
            razorpay_payment_id
        )


        return JsonResponse(
            {
                "detail": "Invalid Razorpay signature"
            },
            status=400
        )

    # A valid HMAC is necessary but not sufficient. The order must also
    # belong to a locally recorded checkout before it can affect state.
    db = SessionLocal()

    try:
        transaction_repository = TransactionRepository(db)
        transaction = transaction_repository.get_by_order_id(
            razorpay_order_id
        )

        if not transaction:
            return JsonResponse(
                {"detail": "Unknown Razorpay order"},
                status=404
            )

        transaction_service = TransactionService(
            transaction_repository
        )
        amount_subunits = to_subunits(
            Decimal(str(transaction.amount)),
            transaction.currency,
        )
        transaction_service.handle_payment_authorized(
            order_id=razorpay_order_id,
            payment_id=razorpay_payment_id,
            amount=amount_subunits,
            currency=transaction.currency,
        )
        transaction_status = transaction.status
    except ValueError as exc:
        db.rollback()
        return JsonResponse({"detail": str(exc)}, status=400)
    except Exception as exc:
        db.rollback()
        print("[PAYMENT STATE ERROR]", repr(exc))
        return JsonResponse(
            {"detail": "Payment was verified but could not be recorded"},
            status=500
        )
    finally:
        db.close()

    # SUCCESS

    print()
    print(
        "=" * 70
    )

    print(
        "RAZORPAY PAYMENT VERIFIED"
    )

    print(
        "Payment ID:",
        razorpay_payment_id
    )

    print(
        "Order ID:",
        razorpay_order_id
    )

    print(
        "=" * 70
    )


    return JsonResponse(
        {
            "status":
                "verified",

            "payment_id":
                razorpay_payment_id,

            "order_id":
                razorpay_order_id,

            "transaction_status":
                transaction_status
        }
    )


# ============================================================
# ECOMMERCE CATALOG LIST & FILTER API
# ============================================================

@require_GET
def products_list(request):
    """
    Search and filter products for the eCommerce storefront grid.
    Supports search query (hybrid search), category, brand, price ranges,
    RAM, rating, and sorting.
    """
    search_query = request.GET.get("search", "").strip()
    category = request.GET.get("category", "").strip()
    brand = request.GET.get("brand", "").strip()
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    min_rating = request.GET.get("min_rating", "").strip()
    ram_gb = request.GET.get("ram_gb", "").strip()
    sort_by = request.GET.get("sort", "featured").strip()

    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1

    try:
        limit = min(60, max(1, int(request.GET.get("limit", "24"))))
    except ValueError:
        limit = 24

    offset = (page - 1) * limit

    # When search keyword is present, utilize CommerceSearchService (hybrid search)
    if search_query:
        search_svc = get_commerce_search_service()
        results_data = search_svc.search(search_query, retrieval_limit=80)
        results = results_data.get("products", []) if isinstance(results_data, dict) else results_data
        filtered = []

        for p in results:
            if category and category.lower() != "all":
                bc = (p.get("breadcrumbs") or "").lower()
                title = (p.get("title") or "").lower()
                if category.lower() not in bc and category.lower() not in title:
                    continue
            if brand and brand.lower() != "all":
                if (p.get("brand") or "").lower() != brand.lower():
                    continue
            if min_price:
                try:
                    if (p.get("price_inr") or 0) < float(min_price):
                        continue
                except ValueError:
                    pass
            if max_price:
                try:
                    if (p.get("price_inr") or float("inf")) > float(max_price):
                        continue
                except ValueError:
                    pass
            if min_rating:
                try:
                    if (p.get("stars") or 0) < float(min_rating):
                        continue
                except ValueError:
                    pass
            if ram_gb:
                try:
                    if (p.get("specs", {}).get("ram_gb") or 0) < float(ram_gb):
                        continue
                except ValueError:
                    pass
            filtered.append(p)

        # Sorting
        if sort_by == "price_asc":
            filtered.sort(key=lambda x: x.get("price_inr") or float("inf"))
        elif sort_by == "price_desc":
            filtered.sort(key=lambda x: x.get("price_inr") or 0, reverse=True)
        elif sort_by == "rating":
            filtered.sort(key=lambda x: (x.get("stars") or 0, x.get("reviews_count") or 0), reverse=True)

        total = len(filtered)
        paginated = filtered[offset : offset + limit]

        return JsonResponse({
            "products": make_json_safe(paginated),
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if limit else 1
        })

    # Direct database query for default storefront browsing
    conditions = ["p.in_stock = true", "p.price IS NOT NULL"]
    params = {"limit": limit, "offset": offset}

    if category and category.lower() != "all":
        conditions.append("(p.breadcrumbs ILIKE :cat OR p.title ILIKE :cat)")
        params["cat"] = f"%{category}%"

    if brand and brand.lower() != "all":
        conditions.append("p.brand ILIKE :brand")
        params["brand"] = brand

    if min_rating:
        try:
            conditions.append("p.stars >= :min_rating")
            params["min_rating"] = float(min_rating)
        except ValueError:
            pass

    if ram_gb:
        try:
            conditions.append("s.ram_gb >= :ram_gb")
            params["ram_gb"] = float(ram_gb)
        except ValueError:
            pass

    if min_price:
        try:
            conditions.append("(CASE WHEN p.currency = 'INR' THEN p.price ELSE p.price * 96.3 END) >= :min_price")
            params["min_price"] = float(min_price)
        except ValueError:
            pass

    if max_price:
        try:
            conditions.append("(CASE WHEN p.currency = 'INR' THEN p.price ELSE p.price * 96.3 END) <= :max_price")
            params["max_price"] = float(max_price)
        except ValueError:
            pass

    where_sql = " AND ".join(conditions)

    if sort_by == "price_asc":
        order_sql = "(CASE WHEN p.currency = 'INR' THEN p.price ELSE p.price * 96.3 END) ASC NULLS LAST"
    elif sort_by == "price_desc":
        order_sql = "(CASE WHEN p.currency = 'INR' THEN p.price ELSE p.price * 96.3 END) DESC NULLS LAST"
    elif sort_by == "rating":
        order_sql = "p.stars DESC NULLS LAST, p.reviews_count DESC NULLS LAST"
    else:
        order_sql = "p.stars DESC NULLS LAST, p.reviews_count DESC NULLS LAST, p.product_id ASC"

    query_sql = text(f"""
        SELECT p.product_id, p.asin, p.title, p.brand, p.price, p.currency, p.stars, p.reviews_count, p.in_stock, p.breadcrumbs,
               ROUND(CAST(CASE WHEN p.currency = 'INR' THEN p.price ELSE p.price * 96.3 END AS numeric), 2) AS price_inr,
               s.ram_gb, s.storage_gb, s.gpu, s.cpu, s.screen_size_inches,
               (
                   SELECT m.url
                   FROM media m
                   WHERE m.product_id = p.product_id AND m.url IS NOT NULL
                     AND (m.media_type IN ('image', 'product_thumbnail', 'product_gallery', 'product_high_resolution')
                          OR m.media_type ILIKE '%image%' OR m.media_type ILIKE '%thumbnail%')
                   ORDER BY CASE m.media_type WHEN 'product_thumbnail' THEN 1 WHEN 'image' THEN 2 ELSE 3 END, m.media_id
                   LIMIT 1
               ) AS image_url
        FROM products p
        LEFT JOIN product_specs s ON s.product_id = p.product_id
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT :limit OFFSET :offset
    """)

    count_sql = text(f"""
        SELECT count(*)
        FROM products p
        LEFT JOIN product_specs s ON s.product_id = p.product_id
        WHERE {where_sql}
    """)

    with engine.connect() as conn:
        total = conn.execute(count_sql, params).scalar() or 0
        rows = conn.execute(query_sql, params).mappings().all()

    fx_rate = 96.3
    products = []
    for r in rows:
        p_dict = dict(r)
        price_inr = float(p_dict.get("price_inr") or 0)
        p_dict["price_inr"] = price_inr
        p_dict["fx_rate"] = fx_rate
        p_dict["image"] = p_dict.get("image_url")
        p_dict["specs"] = {
            "ram_gb": p_dict.get("ram_gb"),
            "storage_gb": p_dict.get("storage_gb"),
            "gpu": p_dict.get("gpu"),
            "cpu": p_dict.get("cpu"),
            "screen_size_inches": p_dict.get("screen_size_inches"),
        }
        products.append(p_dict)

    return JsonResponse({
        "products": make_json_safe(products),
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit else 1
    })


# ============================================================
# LANGCHAIN AI COPILOT CHAT & COMPARISON API
# ============================================================

@csrf_exempt
@require_POST
def copilot_chat(request):
    """
    Conversational AI Shopping Assistant using LangChain.
    Answers buyer queries, explains specifications, and recommends products.
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        body = {}

    message = (body.get("message") or "").strip()
    if not message:
        return JsonResponse({"reply": "Please enter a question or request.", "recommended_products": []})

    history = body.get("history") or []
    selected_asins = body.get("selected_asins") or []

    # Retrieve relevant products from catalog
    search_svc = get_commerce_search_service()
    search_res = search_svc.search(message, retrieval_limit=6)
    catalog_products = search_res.get("products", []) if isinstance(search_res, dict) else search_res

    # Fallback to hybrid search if strict filtering yielded 0 products
    if not catalog_products:
        try:
            catalog_products = CatalogSearchService().hybrid_search(message, limit=6)
        except Exception:
            catalog_products = []

    # Enrich products with image, image_url, and price_inr
    enriched_products = []
    asins_needing_images = []
    fx_rate = 96.3
    for raw_p in catalog_products:
        p = dict(raw_p)
        img = p.get("image") or p.get("image_url") or p.get("thumbnail")
        p["image"] = img
        p["image_url"] = img
        if not img and p.get("asin"):
            asins_needing_images.append(p["asin"])

        price = p.get("price")
        if price is not None:
            try:
                p["price"] = float(price)
                if not p.get("price_inr"):
                    p["price_inr"] = round(float(price) * fx_rate, 2)
            except (ValueError, TypeError):
                pass
        p["currency"] = p.get("currency") or "INR"
        enriched_products.append(p)

    # Batch lookup missing images from media table
    if asins_needing_images:
        try:
            placeholders = ", ".join(f":a_{i}" for i in range(len(asins_needing_images)))
            params = {f"a_{i}": a for i, a in enumerate(asins_needing_images)}
            img_sql = text(f"""
                SELECT p.asin, m.url
                FROM products p
                JOIN media m ON m.product_id = p.product_id
                WHERE p.asin IN ({placeholders}) AND m.url IS NOT NULL
                ORDER BY CASE m.media_type WHEN 'product_thumbnail' THEN 1 WHEN 'image' THEN 2 ELSE 3 END
            """)
            with engine.connect() as conn:
                img_rows = conn.execute(img_sql, params).mappings().all()
            img_map = {}
            for r in img_rows:
                if r["asin"] not in img_map:
                    img_map[r["asin"]] = r["url"]
            for p in enriched_products:
                if not p.get("image") and p.get("asin") in img_map:
                    p["image"] = img_map[p["asin"]]
                    p["image_url"] = img_map[p["asin"]]
        except Exception as e:
            print("[IMAGE ENRICHMENT ERROR]", e)

    catalog_products = enriched_products

    uid = _get_current_user_id(request)
    user_svc = get_user_commerce_service()
    user_persona = user_svc.get_user_persona(uid)

    copilot = get_langchain_copilot()
    result = copilot.chat(
        message=message,
        catalog_products=catalog_products,
        history=history,
        selected_asins=selected_asins,
        user_persona=user_persona,
        user_id=uid,
        user_commerce_service=user_svc,
    )
    return JsonResponse(make_json_safe(result))


@csrf_exempt
@require_POST
def copilot_compare(request):
    """
    Side-by-side product comparison using LangChain.
    Generates a structured comparison matrix, pros & cons, and buying recommendation.
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        body = {}

    asins = body.get("asins") or []
    if not asins:
        return JsonResponse({"detail": "Please select at least 2 products to compare."}, status=400)

    # Fetch product info for the requested ASINs
    placeholders = ", ".join(f":asin_{i}" for i in range(len(asins)))
    params = {f"asin_{i}": a.strip() for i, a in enumerate(asins)}

    sql = text(f"""
        SELECT p.product_id, p.asin, p.title, p.brand, p.price, p.currency, p.stars, p.reviews_count, p.description,
               s.ram_gb, s.storage_gb, s.gpu, s.cpu, s.screen_size_inches,
               (
                   SELECT m.url
                   FROM media m
                   WHERE m.product_id = p.product_id AND m.url IS NOT NULL
                     AND (m.media_type IN ('image', 'product_thumbnail', 'product_gallery', 'product_high_resolution')
                          OR m.media_type ILIKE '%image%' OR m.media_type ILIKE '%thumbnail%')
                   ORDER BY CASE m.media_type WHEN 'product_thumbnail' THEN 1 WHEN 'image' THEN 2 ELSE 3 END, m.media_id
                   LIMIT 1
               ) AS image_url
        FROM products p
        LEFT JOIN product_specs s ON s.product_id = p.product_id
        WHERE p.asin IN ({placeholders})
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()

    fx_rate = 96.3
    products = []
    for r in rows:
        p = dict(r)
        price_usd = float(p.get("price") or 0)
        p["price_inr"] = round(price_usd * fx_rate, 2)
        p["image"] = p.get("image_url")
        p["specs"] = {
            "ram_gb": p.get("ram_gb"),
            "storage_gb": p.get("storage_gb"),
            "gpu": p.get("gpu"),
            "cpu": p.get("cpu"),
            "screen_size_inches": p.get("screen_size_inches"),
        }
        products.append(p)

    copilot = get_langchain_copilot()
    comparison = copilot.compare_products(products)
    comparison["products"] = products

    return JsonResponse(make_json_safe(comparison))


@csrf_exempt
@require_POST
def copilot_compare_query(request):
    """
    Handle follow-up queries specifically about an active product comparison
    using LangChain.
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        body = {}

    query = (body.get("query") or "").strip()
    if not query:
        return JsonResponse({"detail": "Query cannot be empty."}, status=400)

    asins = body.get("asins") or []
    history = body.get("history") or []
    comparison_summary = body.get("comparison_summary", "")

    if not asins:
        return JsonResponse({"detail": "No product ASINs provided."}, status=400)

    # Fetch product info
    placeholders = ", ".join(f":asin_{i}" for i in range(len(asins)))
    params = {f"asin_{i}": a.strip() for i, a in enumerate(asins)}

    sql = text(f"""
        SELECT p.product_id, p.asin, p.title, p.brand, p.price, p.currency, p.stars, p.reviews_count, p.description,
               s.ram_gb, s.storage_gb, s.gpu, s.cpu, s.screen_size_inches,
               (
                   SELECT m.url
                   FROM media m
                   WHERE m.product_id = p.product_id AND m.url IS NOT NULL
                     AND (m.media_type IN ('image', 'product_thumbnail', 'product_gallery', 'product_high_resolution')
                          OR m.media_type ILIKE '%image%' OR m.media_type ILIKE '%thumbnail%')
                   ORDER BY CASE m.media_type WHEN 'product_thumbnail' THEN 1 WHEN 'image' THEN 2 ELSE 3 END, m.media_id
                   LIMIT 1
               ) AS image_url
        FROM products p
        LEFT JOIN product_specs s ON s.product_id = p.product_id
        WHERE p.asin IN ({placeholders})
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()

    fx_rate = 96.3
    products = []
    for r in rows:
        p = dict(r)
        price_usd = float(p.get("price") or 0)
        p["price_inr"] = round(price_usd * fx_rate, 2)
        p["image"] = p.get("image_url")
        p["specs"] = {
            "ram_gb": p.get("ram_gb"),
            "storage_gb": p.get("storage_gb"),
            "gpu": p.get("gpu"),
            "cpu": p.get("cpu"),
            "screen_size_inches": p.get("screen_size_inches"),
        }
        products.append(p)

    copilot = get_langchain_copilot()
    result = copilot.compare_followup(
        query=query,
        products=products,
        comparison_summary=comparison_summary,
        history=history,
    )
    result["products"] = products
    return JsonResponse(make_json_safe(result))


# ============================================================
# USER AUTHENTICATION & PROFILE VIEWS
# ============================================================

def _get_current_user_id(request) -> int:
    """Get active user id from session or fallback to default demo user."""
    uid = request.session.get("commerce_user_id")
    if not uid:
        svc = get_user_commerce_service()
        default_u = svc.get_default_user()
        uid = default_u.get("id") if default_u else 1
    return int(uid)


@require_GET
def user_profile(request):
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    user = svc.get_user_by_id(uid) or svc.get_default_user()
    return JsonResponse(make_json_safe(user))


@csrf_exempt
@require_POST
def user_signup(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}
    email = data.get("email", "").strip()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    full_name = data.get("full_name", "").strip()
    if not email or not password:
        return JsonResponse({"detail": "Email and password are required."}, status=400)
    if not username:
        username = email.split("@")[0]
    svc = get_user_commerce_service()
    try:
        user = svc.signup(username, email, password, full_name)
        request.session["commerce_user_id"] = user["id"]
        return JsonResponse(make_json_safe(user))
    except Exception as exc:
        return JsonResponse({"detail": str(exc)}, status=400)


@csrf_exempt
@require_POST
def user_login(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}
    key = data.get("email") or data.get("username") or ""
    password = data.get("password", "")
    svc = get_user_commerce_service()
    user = svc.login(key, password)
    if not user:
        return JsonResponse({"detail": "Invalid email/username or password."}, status=401)
    request.session["commerce_user_id"] = user["id"]
    return JsonResponse(make_json_safe(user))


@csrf_exempt
@require_POST
def user_logout(request):
    request.session.flush()
    return JsonResponse({"message": "Logged out successfully"})


@csrf_exempt
@require_POST
def user_update_profile(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    if "persona_info" in data:
        svc.update_user_persona(uid, data.get("persona_info") or "")
    user = svc.update_profile(
        user_id=uid,
        full_name=data.get("full_name", ""),
        address_line1=data.get("address_line1", ""),
        city=data.get("city", ""),
        state=data.get("state", ""),
        postal_code=data.get("postal_code", ""),
        phone=data.get("phone", ""),
    )
    return JsonResponse(make_json_safe(user))


@csrf_exempt
def user_persona_api(request):
    """
    GET: Retrieve current user's persona information.
    POST: Store or overwrite the user's personal information in account.
    """
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)

    if request.method == "GET":
        persona = svc.get_user_persona(uid)
        return JsonResponse({"persona_info": persona, "user_id": uid})
    elif request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            data = {}
        persona = (data.get("persona_info") or "").strip()
        updated = svc.update_user_persona(uid, persona)
        return JsonResponse({
            "persona_info": updated,
            "user_id": uid,
            "message": "Person information updated successfully in account.",
        })
    return JsonResponse({"detail": "Method not allowed."}, status=405)



# ============================================================
# CART CRUD VIEWS (Window for Quantity, Add, Update, Remove, Clear)
# ============================================================

@require_GET
def cart_get(request):
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    cart = svc.get_cart(uid)
    return JsonResponse(make_json_safe(cart))


@csrf_exempt
@require_POST
def cart_add(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}
    asin = (data.get("asin") or "").strip()
    if not asin:
        return JsonResponse({"detail": "ASIN is required."}, status=400)
    title = data.get("title") or "Selected Product"
    price_inr = float(data.get("price_inr") or 0)
    if price_inr <= 0 and data.get("price"):
        price_inr = round(float(data["price"]) * 96.3, 2)
    quantity = int(data.get("quantity") or 1)
    image_url = data.get("image_url") or data.get("image") or ""

    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    cart = svc.add_to_cart(
        user_id=uid,
        asin=asin,
        title=title,
        price_inr=price_inr,
        price_usd=float(data.get("price") or 0) if data.get("price") else None,
        image_url=image_url,
        quantity=quantity,
    )
    return JsonResponse(make_json_safe(cart))


@csrf_exempt
@require_POST
def cart_update_quantity(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}
    asin = (data.get("asin") or "").strip()
    quantity = int(data.get("quantity") if data.get("quantity") is not None else 1)
    if not asin:
        return JsonResponse({"detail": "ASIN is required."}, status=400)
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    cart = svc.update_cart_quantity(uid, asin, quantity)
    return JsonResponse(make_json_safe(cart))


@csrf_exempt
@require_POST
def cart_remove(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}
    asin = (data.get("asin") or "").strip()
    if not asin:
        return JsonResponse({"detail": "ASIN is required."}, status=400)
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    cart = svc.remove_from_cart(uid, asin)
    return JsonResponse(make_json_safe(cart))


@csrf_exempt
@require_POST
def cart_clear(request):
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    cart = svc.clear_cart(uid)
    return JsonResponse(make_json_safe(cart))


# ============================================================
# ORDERS & TRACKING LOGS VIEWS (Like Amazon)
# ============================================================

@require_GET
def orders_list(request):
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    orders = svc.get_orders(uid)
    return JsonResponse({"orders": make_json_safe(orders)})


@require_GET
def order_detail(request, order_number: str):
    svc = get_user_commerce_service()
    order = svc.get_order(order_number)
    if not order:
        return JsonResponse({"detail": "Order not found."}, status=404)
    return JsonResponse(make_json_safe(order))


@csrf_exempt
@require_POST
def order_create(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)

    items = data.get("items")
    from_cart = False
    if not items:
        # Pull from user's active cart
        cart = svc.get_cart(uid)
        items = cart.get("items", [])
        from_cart = True

    if not items:
        return JsonResponse({"detail": "No items to order."}, status=400)

    payment_method = data.get("payment_method") or "razorpay"
    diamonds_to_use = int(data.get("diamonds_to_use") or 0)
    shipping_address = data.get("shipping_address")
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")

    try:
        order = svc.create_order(
            user_id=uid,
            items=items,
            payment_method=payment_method,
            shipping_address=shipping_address,
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            diamonds_to_use=diamonds_to_use,
            from_cart=from_cart,
        )
        return JsonResponse(make_json_safe(order))
    except Exception as exc:
        return JsonResponse({"detail": str(exc)}, status=400)


@csrf_exempt
@require_POST
def order_cancel(request, order_number: str):
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    try:
        order = svc.cancel_order(uid, order_number)
        return JsonResponse(make_json_safe(order))
    except Exception as exc:
        return JsonResponse({"detail": str(exc)}, status=400)


# ============================================================
# WALLET & REWARDS / DIAMONDS VIEWS
# ============================================================

@require_GET
def wallet_info(request):
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    info = svc.get_wallet_info(uid)
    return JsonResponse(make_json_safe(info))


@csrf_exempt
@require_POST
def wallet_topup(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}
    amount = float(data.get("amount") or 0)
    if amount <= 0:
        return JsonResponse({"detail": "Amount must be greater than zero."}, status=400)
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    try:
        info = svc.topup_wallet(uid, amount)
        return JsonResponse(make_json_safe(info))
    except Exception as exc:
        return JsonResponse({"detail": str(exc)}, status=400)


@csrf_exempt
@require_POST
def rewards_claim_daily(request):
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    info = svc.claim_daily_diamonds(uid)
    return JsonResponse(make_json_safe(info))


# ============================================================
# BUY AGAIN VIEWS
# ============================================================

@require_GET
def buy_again_products(request):
    svc = get_user_commerce_service()
    uid = _get_current_user_id(request)
    products = svc.get_buy_again_products(uid)
    return JsonResponse({"products": make_json_safe(products)})