from django.urls import path

from .views import (
    health,
    chat_page,
    chat,
    image_proxy,
    checkout_page,
    create_checkout_order,
    verify_payment,
)


urlpatterns = [

    path(
        "",
        chat_page,
        name="home-page"
    ),

    # FRONTEND

    path(
        "chat",
        chat_page,
        name="chat-page"
    ),

    path(
        "checkout",
        checkout_page,
        name="checkout-page"
    ),

    # API

    path(
        "health",
        health,
        name="health"
    ),

    path(
        "api/chat",
        chat,
        name="chat-api"
    ),

    path(
        "api/image-proxy",
        image_proxy,
        name="image-proxy"
    ),

    path(
        "api/checkout/create-order",
        create_checkout_order,
        name="create-checkout-order"
    ),

    path(
        "api/checkout/verify-payment",
        verify_payment,
        name="verify-payment"
    ),

]
