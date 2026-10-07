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
    seller_portal_page,
    admin_verification_page,
    seller_submit_product,
    seller_list_products,
    seller_get_product,
    admin_list_submissions,
    admin_get_submission,
    admin_approve_submission,
    admin_reject_submission,
    delivery_portal_page,
    delivery_list_orders,
    delivery_mark_delivered,
    delivery_list_returns,
    delivery_approve_return,
    delivery_reject_return,
    delivery_list_agents,
    order_request_return,
    support_info_api,
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

    # SELLER CENTRAL & ADMIN QUALITY VERIFICATION PORTALS
    path("seller", seller_portal_page, name="seller-portal-page"),
    path("business", seller_portal_page, name="business-portal-page"),
    path("admin-seller", admin_verification_page, name="admin-verification-page"),
    path("admin-verification", admin_verification_page, name="admin-verification-page-slug"),

    # SELLER PRODUCT SUBMISSION & MANAGEMENT APIS
    path("api/seller/products/submit", seller_submit_product, name="seller-submit-product"),
    path("api/seller/products", seller_list_products, name="seller-list-products"),
    path("api/seller/products/<str:submission_id>", seller_get_product, name="seller-get-product"),

    # ADMIN VERIFICATION & APPROVAL APIS
    path("api/admin/submissions", admin_list_submissions, name="admin-list-submissions"),
    path("api/admin/submissions/<str:submission_id>", admin_get_submission, name="admin-get-submission"),
    path("api/admin/submissions/<str:submission_id>/approve", admin_approve_submission, name="admin-approve-submission"),
    path("api/admin/submissions/<str:submission_id>/reject", admin_reject_submission, name="admin-reject-submission"),

    # DELIVERY ASSOCIATE & COURIER LOGISTICS PORTAL
    path("delivery", delivery_portal_page, name="delivery-portal-page"),
    path("logistics", delivery_portal_page, name="logistics-portal-page"),
    path("api/delivery/orders", delivery_list_orders, name="delivery-list-orders"),
    path("api/delivery/orders/<str:order_number>/deliver", delivery_mark_delivered, name="delivery-mark-delivered"),
    path("api/delivery/returns", delivery_list_returns, name="delivery-list-returns"),
    path("api/delivery/returns/<str:order_number>/approve", delivery_approve_return, name="delivery-approve-return"),
    path("api/delivery/returns/<str:order_number>/reject", delivery_reject_return, name="delivery-reject-return"),
    path("api/delivery/agents", delivery_list_agents, name="delivery-list-agents"),

    # CUSTOMER ORDER RETURN (10-DAY POLICY CONSTRAINT)
    path("api/orders/<str:order_number>/return", order_request_return, name="order-request-return"),

    # 24x7 CUSTOMER HELPLINE & SUPPORT
    path("api/support/info", support_info_api, name="support-info-api"),

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
