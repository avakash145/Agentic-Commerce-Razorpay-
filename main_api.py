from pathlib import Path
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from collections import defaultdict

import os
import uuid
import hmac
import hashlib

import requests

from fastapi import (
    FastAPI,
    HTTPException,
    Query
)

from fastapi.responses import (
    FileResponse,
    Response
)

from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, Field

from sqlalchemy import text


# APPLICATION 

from app.api.webhook import (
    router as webhook_router
)

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


# PATHS

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)


STATIC_DIR = (
    BASE_DIR
    / "app"
    / "static"
)


# FASTAPI

app = FastAPI(

    title="Agentic Commerce",

    version="1.0.0"
)


# STATIC FILES

app.mount(

    "/static",

    StaticFiles(
        directory=STATIC_DIR
    ),

    name="static"
)


# SERVICES

catalog_service = None

commerce_search_service = None


fx_service = (
    FXService()
)


# WEBHOOK ROUTER

app.include_router(
    webhook_router
)


# REQUEST MODELS


class ChatRequest(
    BaseModel
):

    message: str


class CheckoutRequest(
    BaseModel
):

    asin: str = Field(min_length=1, max_length=32)


class PaymentVerificationRequest(
    BaseModel
):

    razorpay_payment_id: str = Field(min_length=1, max_length=64)

    razorpay_order_id: str = Field(min_length=1, max_length=64)

    razorpay_signature: str = Field(min_length=1, max_length=128)


def get_commerce_search_service():
    """Build the intent-aware search service once, after app startup."""

    global commerce_search_service

    if commerce_search_service is None:
        commerce_search_service = CommerceSearchService(
            search_service=get_catalog_search_service()
        )

    return commerce_search_service


def get_catalog_search_service():
    """Load the embedding model only when a search is requested."""

    global catalog_service

    if catalog_service is None:
        catalog_service = CatalogSearchService()

    return catalog_service


# JSON SAFE

def make_json_safe(
    value: Any
):

    # NONE

    if value is None:

        return None
    # DECIMAL
    if isinstance(
        value,
        Decimal
    ):

        return float(
            value
        )

    # DICT

    if isinstance(
        value,
        dict
    ):

        return {

            str(key):
                make_json_safe(
                    item
                )

            for key, item
            in value.items()
        }


    # LIST

    if isinstance(
        value,
        list
    ):

        return [

            make_json_safe(
                item
            )

            for item in value
        ]


    # TUPLE

    if isinstance(
        value,
        tuple
    ):

        return [

            make_json_safe(
                item
            )

            for item in value
        ]


    # DATETIME

    if hasattr(
        value,
        "isoformat"
    ):

        return value.isoformat()

    # NORMAL

    return value

# HEALTH

@app.get(
    "/health"
)
def health():

    return {

        "status":
            "ok",

        "service":
            "agentic-commerce"
    }


# CHAT PAGE

@app.get(
    "/"
)
def home_page():
    return FileResponse(STATIC_DIR / "chatbot.html")


@app.get(
    "/chat"
)
def chat_page():

    return FileResponse(

        STATIC_DIR
        / "chatbot.html"
    )


@app.get(
    "/checkout"
)
def checkout_page():
    return FileResponse(STATIC_DIR / "checkout.html")


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


@app.get(
    "/api/image-proxy"
)
def image_proxy(

    url: str = Query(...)
):

    # PARSE URL

    try:

        parsed = urlparse(
            url
        )

    except Exception:

        raise HTTPException(

            status_code=400,

            detail=
                "Invalid image URL"
        )


    # PROTOCOL

    if parsed.scheme not in {

        "http",

        "https"

    }:

        raise HTTPException(

            status_code=400,

            detail=
                "Only HTTP/HTTPS images are allowed"
        )


    # HOST

    hostname = (

        parsed.hostname
        or ""
    ).lower()


    if hostname not in (
        ALLOWED_IMAGE_HOSTS
    ):

        raise HTTPException(

            status_code=403,

            detail=
                "Image domain is not allowed"
        )


    # DOWNLOAD

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
                        "Chrome/140 "
                        "Safari/537.36"
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
                    "https://www.amazon.com/"

            },

            timeout=15,

            stream=True
        )


        response.raise_for_status()


    except requests.RequestException as exc:

        raise HTTPException(

            status_code=502,

            detail=(
                "Unable to load Amazon image: "
                + str(exc)
            )
        )


    # CONTENT TYPE

    content_type = (

        response.headers.get(

            "content-type",

            ""
        )
    )


    if not content_type.startswith(
        "image/"
    ):

        raise HTTPException(

            status_code=415,

            detail=
                "Remote resource is not an image"
        )

    # IMAGE

    image_bytes = (
        response.content
    )


    # RESPONSE
    return Response(

        content=image_bytes,

        media_type=content_type,

        headers={

            "Cache-Control":
                "public, max-age=86400"
        }
    )


# CHAT API

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


@app.get(
    "/api/products/{asin}"
)
def product_detail(
    asin: str,
    reviews_limit: int = Query(12, ge=1, le=50),
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
            raise HTTPException(status_code=404, detail="Product not found")

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
    return make_json_safe(response)

@app.post(
    "/chat"
)
@app.post(
    "/api/chat"
)
def chat(
    request: ChatRequest
):

    query = (
        request.message
        .strip()
    )


    # EMPTY QUERY

    if not query:

        return {

            "message":
                "Please enter a product request.",

            "products": []
        }


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


        return {

            "message":
                message,

            "products":
                frontend_products
        }


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

        return {

            "message":
                "Something went wrong while searching the catalog.",

            "products": []
        }

# CREATE RAZORPAY CHECKOUT ORDER

@app.post(
    "/api/checkout/create-order"
)
def create_checkout_order(

    request:
        CheckoutRequest
):

    # ASIN

    asin = (

        request.asin
        .strip()
    )


    if not asin:

        raise HTTPException(

            status_code=400,

            detail=
                "ASIN is required"
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


        raise HTTPException(

            status_code=500,

            detail=
                "Unable to load product"
        )


    # PRODUCT NOT FOUND

    if not row:

        raise HTTPException(

            status_code=404,

            detail=(
                "Product not found: "
                + asin
            )
        )

    if row["in_stock"] is False:
        raise HTTPException(
            status_code=409,
            detail="This product is currently out of stock",
        )

    if row["price_selection_required"] is True:
        raise HTTPException(
            status_code=409,
            detail=(
                "Select a priced variant or seller offer before checkout"
            ),
        )


    # PRODUCT PRICE

    price = row[
        "price"
    ]


    currency = row[
        "currency"
    ]


    if price is None:

        raise HTTPException(

            status_code=400,

            detail=
                "Product has no price"
        )


    if not currency:

        raise HTTPException(

            status_code=400,

            detail=
                "Product has no currency"
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


        raise HTTPException(

            status_code=502,

            detail=(
                "Unable to convert "
                "product price to INR: "
                + str(exc)
            )
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

        raise HTTPException(

            status_code=400,

            detail=
                "Invalid Razorpay amount"
        )


    # RAZORPAY CREDENTIALS

    key_id = os.getenv(
        "RAZORPAY_KEY_ID"
    )


    key_secret = os.getenv(
        "RAZORPAY_KEY_SECRET"
    )


    if not key_id:

        raise HTTPException(

            status_code=500,

            detail=
                "RAZORPAY_KEY_ID is not configured"
        )

    if not key_id.startswith("rzp_test_"):
        raise HTTPException(
            status_code=500,
            detail="Only Razorpay Test Mode keys are allowed",
        )


    if not key_secret:

        raise HTTPException(

            status_code=500,

            detail=
                "RAZORPAY_KEY_SECRET is not configured"
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


        raise HTTPException(

            status_code=502,

            detail=
                "Unable to connect to Razorpay"
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


        raise HTTPException(

            status_code=
                response.status_code,

            detail=
                error_data
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
        raise HTTPException(
            status_code=500,
            detail="Order created but could not be recorded locally",
        )
    finally:
        db.close()


    # FRONTEND RESPONSE

    return {

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
    }


# VERIFY RAZORPAY PAYMENT

@app.post(
    "/api/checkout/verify-payment"
)
def verify_payment(

    request:
        PaymentVerificationRequest
):

    # SECRET
    key_secret = os.getenv(
        "RAZORPAY_KEY_SECRET"
    )


    if not key_secret:

        raise HTTPException(

            status_code=500,

            detail=
                "RAZORPAY_KEY_SECRET is not configured"
        )


    # MESSAGE
    #
    # Razorpay signature:
    #
    # order_id + "|" + payment_id

    message = (

        request.razorpay_order_id

        +

        "|"

        +

        request.razorpay_payment_id
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

        request.razorpay_signature
    )


    if not valid:

        print()

        print(
            "[PAYMENT VERIFICATION FAILED]"
        )

        print(
            "Order:",
            request.razorpay_order_id
        )

        print(
            "Payment:",
            request.razorpay_payment_id
        )


        raise HTTPException(

            status_code=400,

        detail=
                "Invalid Razorpay signature"
        )

    # A valid HMAC is necessary but not sufficient. The order must also
    # belong to a locally recorded checkout before it can affect state.
    db = SessionLocal()

    try:
        transaction_repository = TransactionRepository(db)
        transaction = transaction_repository.get_by_order_id(
            request.razorpay_order_id
        )

        if not transaction:
            raise HTTPException(
                status_code=404,
                detail="Unknown Razorpay order",
            )

        transaction_service = TransactionService(
            transaction_repository
        )
        amount_subunits = to_subunits(
            Decimal(str(transaction.amount)),
            transaction.currency,
        )
        transaction_service.handle_payment_authorized(
            order_id=request.razorpay_order_id,
            payment_id=request.razorpay_payment_id,
            amount=amount_subunits,
            currency=transaction.currency,
        )
        transaction_status = transaction.status
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        print("[PAYMENT STATE ERROR]", repr(exc))
        raise HTTPException(
            status_code=500,
            detail="Payment was verified but could not be recorded",
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
        request.razorpay_payment_id
    )

    print(
        "Order ID:",
        request.razorpay_order_id
    )

    print(
        "=" * 70
    )


    return {

        "status":
            "verified",

        "payment_id":
            request.razorpay_payment_id,

        "order_id":
            request.razorpay_order_id,

        "transaction_status":
            transaction_status
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main_api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
