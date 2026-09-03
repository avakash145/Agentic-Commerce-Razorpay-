from pathlib import Path
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
import json

import requests

from django.http import (
    JsonResponse,
    FileResponse,
    HttpResponse,
)

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from django.conf import settings

from app.catalog.search_service import (
    CatalogSearchService
)

from app.agent.commerce_search import (
    CommerceSearchService
)

# PATHS

BASE_DIR = Path(
    settings.BASE_DIR
)


STATIC_DIR = (
    BASE_DIR
    / "app"
    / "static"
)

# SERVICES

catalog_service = None
commerce_search_service = None


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


# CHAT PAGE

@require_GET
def chat_page(
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


def _delegated_api_error(exc):
    """Translate the canonical FastAPI error shape for Django callers."""

    detail = getattr(exc, "detail", "Request failed")
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("error") or "Request failed"
    return JsonResponse({"detail": str(detail)}, status=getattr(exc, "status_code", 500))


@csrf_exempt
@require_POST
def create_checkout_order(request):
    """Compatibility route; FastAPI remains the canonical implementation."""

    try:
        from main_api import CheckoutRequest, create_checkout_order as create_order
        payload = CheckoutRequest(**json.loads(request.body.decode("utf-8")))
        return JsonResponse(make_json_safe(create_order(payload)))
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON request"}, status=400)
    except Exception as exc:
        if hasattr(exc, "status_code") and hasattr(exc, "detail"):
            return _delegated_api_error(exc)
        print("[CHECKOUT ERROR]", repr(exc))
        return JsonResponse({"detail": "Unable to create checkout order"}, status=500)


@csrf_exempt
@require_POST
def verify_payment(request):
    """Compatibility route; delegates payment verification to FastAPI code."""

    try:
        from main_api import PaymentVerificationRequest
        from main_api import verify_payment as verify_order_payment
        payload = PaymentVerificationRequest(**json.loads(request.body.decode("utf-8")))
        return JsonResponse(make_json_safe(verify_order_payment(payload)))
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON request"}, status=400)
    except Exception as exc:
        if hasattr(exc, "status_code") and hasattr(exc, "detail"):
            return _delegated_api_error(exc)
        print("[PAYMENT VERIFICATION ERROR]", repr(exc))
        return JsonResponse({"detail": "Unable to verify payment"}, status=500)


# IMAGE PROXY


ALLOWED_IMAGE_HOSTS = {

    "m.media-amazon.com",

    "images-na.ssl-images-amazon.com",

    "images.amazon.com",

    "images-eu.ssl-images-amazon.com",

    "images-fe.ssl-images-amazon.com",

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

        # HYBRID SEARCH
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
                    "image"
                )

                or

                item.get(
                    "image_url"
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


            # PRICE INR

            if "price_inr" in item:

                item[
                    "price_inr"
                ] = make_json_safe(

                    item[
                        "price_inr"
                    ]

                )

            # SPECS

            specs = (

                item.get(
                    "specs"
                )

                or {}

            )


            if not specs:

                specs = {

                    "ram_gb":
                        item.get(
                            "ram_gb"
                        ),

                    "storage_gb":
                        item.get(
                            "storage_gb"
                        ),

                    "gpu":
                        item.get(
                            "gpu"
                        ),

                    "cpu":
                        item.get(
                            "cpu"
                        ),

                }


            item[
                "specs"
            ] = specs


            # JSON SAFE

            item = make_json_safe(
                item
            )


            frontend_products.append(
                item
            )

        # RESPONSE
        return JsonResponse(

            {

                "message":
                    (
                        f"Found "
                        f"{len(frontend_products)} "
                        f"products."
                    ),

                "products":
                    frontend_products

            },

            status=200

        )


    except Exception as exc:

        print(
            "[CHAT ERROR]",
            repr(exc)
        )


        return JsonResponse(

            {

                "message":
                    (
                        "Something went wrong "
                        "while searching the catalog."
                    ),

                "products":
                    []

            },

            status=500

        )
