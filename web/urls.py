from django.urls import path

from .views import (
    health,
    store_page,
    chat_page,
    legacy_chat_page,
    products_list,
    copilot_chat,
    copilot_compare,
    copilot_compare_query,
    chat,
    image_proxy,
    product_detail,
    checkout_page,
    create_checkout_order,
    verify_payment,
    user_profile,
    user_signup,
    user_login,
    user_logout,
    user_update_profile,
    user_persona_api,
    cart_get,
    cart_add,
    cart_update_quantity,
    cart_remove,
    cart_clear,
    orders_list,
    order_detail,
    order_create,
    order_cancel,
    wallet_info,
    wallet_topup,
    rewards_claim_daily,
    buy_again_products,
)
from app.api.webhook import razorpay_webhook


urlpatterns = [
    # STOREFRONT & CHAT
    path(
        "",
        store_page,
        name="home-page"
    ),
    path(
        "store",
        store_page,
        name="store-page"
    ),
    path(
        "chat",
        chat_page,
        name="chat-page"
    ),
    path(
        "legacy-chat",
        legacy_chat_page,
        name="legacy-chat-page"
    ),
    path(
        "checkout",
        checkout_page,
        name="checkout-page"
    ),

    # STORE CATALOG & LANGCHAIN COPILOT APIS
    path(
        "api/products",
        products_list,
        name="products-list"
    ),
    path(
        "api/copilot/chat",
        copilot_chat,
        name="copilot-chat"
    ),
    path(
        "api/copilot/compare",
        copilot_compare,
        name="copilot-compare"
    ),
    path(
        "api/copilot/compare-query",
        copilot_compare_query,
        name="copilot-compare-query"
    ),

    # HEALTH & CHAT
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

    # PRODUCT DETAIL
    path(
        "api/products/<str:asin>",
        product_detail,
        name="product-detail"
    ),
    path(
        "api/products/<str:asin>/",
        product_detail,
        name="product-detail-slash"
    ),

    # CHECKOUT
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

    # USER AUTH & PROFILE
    path("api/user/profile", user_profile, name="user-profile"),
    path("api/user/signup", user_signup, name="user-signup"),
    path("api/user/login", user_login, name="user-login"),
    path("api/user/logout", user_logout, name="user-logout"),
    path("api/user/update-profile", user_update_profile, name="user-update-profile"),
    path("api/user/persona", user_persona_api, name="user-persona-api"),

    # CART CRUD
    path("api/cart", cart_get, name="cart-get"),
    path("api/cart/add", cart_add, name="cart-add"),
    path("api/cart/update", cart_update_quantity, name="cart-update"),
    path("api/cart/remove", cart_remove, name="cart-remove"),
    path("api/cart/clear", cart_clear, name="cart-clear"),

    # ORDERS & TRACKING LOGS
    path("api/orders", orders_list, name="orders-list"),
    path("api/orders/create", order_create, name="orders-create"),
    path("api/orders/<str:order_number>", order_detail, name="order-detail"),
    path("api/orders/<str:order_number>/cancel", order_cancel, name="order-cancel"),

    # WALLET & REWARDS / DIAMONDS
    path("api/wallet", wallet_info, name="wallet-info"),
    path("api/wallet/topup", wallet_topup, name="wallet-topup"),
    path("api/rewards/claim-daily", rewards_claim_daily, name="rewards-claim-daily"),

    # BUY AGAIN
    path("api/buy-again", buy_again_products, name="buy-again-products"),

    # WEBHOOKS
    path(
        "webhooks/razorpay",
        razorpay_webhook,
        name="razorpay-webhook"
    ),
    path(
        "webhooks/razorpay/",
        razorpay_webhook,
        name="razorpay-webhook-slash"
    ),
    path(
        "api/webhooks/razorpay",
        razorpay_webhook,
        name="api-razorpay-webhook"
    ),
    path(
        "api/webhooks/razorpay/",
        razorpay_webhook,
        name="api-razorpay-webhook-slash"
    ),
]
