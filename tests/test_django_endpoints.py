import os
import json
import pytest
from django.test import Client
from sqlalchemy import text
from app.db.database import engine

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


@pytest.fixture
def client():
    import django
    django.setup()
    return Client()


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["framework"] == "django"


def test_frontend_pages(client):
    res_home = client.get("/")
    assert res_home.status_code == 200

    res_chat = client.get("/chat")
    assert res_chat.status_code == 200

    res_checkout = client.get("/checkout")
    assert res_checkout.status_code == 200


def test_chat_api_empty_query(client):
    response = client.post(
        "/api/chat",
        data='{"message": ""}',
        content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert "Please enter a product request." in data["message"]


def test_webhook_missing_headers(client):
    response = client.post(
        "/webhooks/razorpay",
        data='{"event": "payment.captured"}',
        content_type="application/json"
    )
    assert response.status_code == 400


def test_webhook_invalid_signature(client):
    response = client.post(
        "/webhooks/razorpay",
        data='{"event": "payment.captured"}',
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE="invalidsig",
        HTTP_X_RAZORPAY_EVENT_ID="evt_123"
    )
    assert response.status_code == 400
    data = response.json()
    assert "Invalid webhook signature" in data["detail"]


def test_checkout_create_order_missing_asin(client):
    response = client.post(
        "/api/checkout/create-order",
        data='{}',
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "ASIN is required"


def test_image_proxy_validation(client):
    res_missing = client.get("/api/image-proxy")
    assert res_missing.status_code == 400

    res_disallowed = client.get("/api/image-proxy?url=https://evil.com/image.jpg")
    assert res_disallowed.status_code == 403


def test_products_list_endpoint(client):
    res = client.get("/api/products?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert "products" in data
    assert isinstance(data["products"], list)
    assert len(data["products"]) > 0
    assert "total" in data


def test_copilot_chat_endpoint(client):
    res = client.post(
        "/api/copilot/chat",
        data='{"message": "tell me about gaming laptops"}',
        content_type="application/json"
    )
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert len(data["reply"]) > 0


def test_copilot_compare_endpoint(client):
    # Retrieve two ASINs first
    list_res = client.get("/api/products?limit=2")
    products = list_res.json().get("products", [])
    if len(products) >= 2:
        asins = [products[0]["asin"], products[1]["asin"]]
        res = client.post(
            "/api/copilot/compare",
            data=f'{{"asins": ["{asins[0]}", "{asins[1]}"]}}',
            content_type="application/json"
        )
        assert res.status_code == 200
        data = res.json()
        assert "analysis_markdown" in data
        assert "products" in data


def test_copilot_compare_query_endpoint(client):
    list_res = client.get("/api/products?limit=2")
    products = list_res.json().get("products", [])
    if len(products) >= 2:
        asins = [products[0]["asin"], products[1]["asin"]]
        res = client.post(
            "/api/copilot/compare-query",
            data=f'{{"query": "Which laptop is better for battery life and portability?", "asins": ["{asins[0]}", "{asins[1]}"]}}',
            content_type="application/json"
        )
        assert res.status_code == 200
        data = res.json()
        assert "reply" in data
        assert len(data["reply"]) > 0
        assert "products" in data


def test_copilot_compare_query_validation(client):
    res_empty = client.post(
        "/api/copilot/compare-query",
        data='{"query": ""}',
        content_type="application/json"
    )
    assert res_empty.status_code == 400

    res_no_asins = client.post(
        "/api/copilot/compare-query",
        data='{"query": "Which one is better?", "asins": []}',
        content_type="application/json"
    )
    assert res_no_asins.status_code == 400


def test_copilot_chat_returns_enriched_recommendations(client):
    res = client.post(
        "/api/copilot/chat",
        data='{"message": "gaming laptop"}',
        content_type="application/json"
    )
    assert res.status_code == 200
    data = res.json()
    assert "recommended_products" in data
    for p in data["recommended_products"]:
        assert "asin" in p
        assert "title" in p


def test_user_profile_and_auth(client):
    res_prof = client.get("/api/user/profile")
    assert res_prof.status_code == 200
    user_data = res_prof.json()
    assert "email" in user_data
    assert "full_name" in user_data

    # Update profile
    res_update = client.post(
        "/api/user/update-profile",
        data='{"full_name": "Alex Johnson", "city": "Bengaluru", "state": "Karnataka"}',
        content_type="application/json"
    )
    assert res_update.status_code == 200
    updated = res_update.json()
    assert updated["city"] == "Bengaluru"


def test_cart_crud_operations(client):
    # 1. Fetch active cart
    res_cart = client.get("/api/cart")
    assert res_cart.status_code == 200

    # 2. Add an item
    res_add = client.post(
        "/api/cart/add",
        data='{"asin": "TESTASIN001", "title": "Test Gaming Laptop", "price_inr": 85000, "quantity": 1}',
        content_type="application/json"
    )
    assert res_add.status_code == 200
    cart_data = res_add.json()
    assert any(i["asin"] == "TESTASIN001" for i in cart_data["items"])

    # 3. Update quantity (Quantity Window)
    res_qty = client.post(
        "/api/cart/update",
        data='{"asin": "TESTASIN001", "quantity": 3}',
        content_type="application/json"
    )
    assert res_qty.status_code == 200
    cart_updated = res_qty.json()
    item = next(i for i in cart_updated["items"] if i["asin"] == "TESTASIN001")
    assert item["quantity"] == 3
    assert item["line_total_inr"] == 255000.0

    # 4. Remove item
    res_del = client.post(
        "/api/cart/remove",
        data='{"asin": "TESTASIN001"}',
        content_type="application/json"
    )
    assert res_del.status_code == 200
    cart_final = res_del.json()
    assert not any(i["asin"] == "TESTASIN001" for i in cart_final["items"])


def test_wallet_and_rewards_flow(client):
    # 1. Check wallet balance
    res_wallet = client.get("/api/wallet")
    assert res_wallet.status_code == 200
    w_data = res_wallet.json()
    assert "wallet_balance" in w_data
    assert "diamonds_balance" in w_data

    # 2. Top-up wallet
    res_topup = client.post(
        "/api/wallet/topup",
        data='{"amount": 500}',
        content_type="application/json"
    )
    assert res_topup.status_code == 200
    w_topup = res_topup.json()
    assert w_topup["wallet_balance"] >= 500

    # 3. Claim daily streak
    res_claim = client.post("/api/rewards/claim-daily")
    assert res_claim.status_code == 200
    claim_data = res_claim.json()
    assert "diamonds_balance" in claim_data


def test_orders_and_buy_again_flow(client):
    # 1. Add item to cart
    client.post(
        "/api/cart/add",
        data='{"asin": "TESTORDER001", "title": "Reorderable Device", "price_inr": 2000, "quantity": 1}',
        content_type="application/json"
    )

    # 2. Top up wallet to cover cost
    client.post(
        "/api/wallet/topup",
        data='{"amount": 5000}',
        content_type="application/json"
    )

    # 3. Place order via wallet
    res_order = client.post(
        "/api/orders/create",
        data='{"payment_method": "wallet", "diamonds_to_use": 0}',
        content_type="application/json"
    )
    assert res_order.status_code == 200
    order_data = res_order.json()
    assert "order_number" in order_data
    assert order_data["status"] in ["confirmed", "processing", "ordered", "shipped"]
    assert len(order_data["tracking_logs"]) > 0

    # 4. View orders list
    res_orders = client.get("/api/orders")
    assert res_orders.status_code == 200
    all_orders = res_orders.json()["orders"]
    assert any(o["order_number"] == order_data["order_number"] for o in all_orders)

    # 5. Buy again contains ordered items
    res_buy_again = client.get("/api/buy-again")
    assert res_buy_again.status_code == 200
    ba_data = res_buy_again.json()
    assert "products" in ba_data
    assert any(p["asin"] == "TESTORDER001" for p in ba_data["products"])


def test_products_list_price_filtering_and_pagination(client):
    """
    Test that filtering by max_price=50000 on category=laptop:
    1. Returns a full page of 24 items (or exact total if <24).
    2. Every item's price_inr <= 50000.
    3. Total accurately reflects the filtered count.
    4. Pages accurately calculated.
    5. Page 2 returns items also within the budget.
    """
    res = client.get("/api/products?page=1&limit=24&category=laptop&max_price=50000")
    assert res.status_code == 200
    data = res.json()
    assert "products" in data
    assert data["total"] > 0
    assert data["page"] == 1
    assert data["limit"] == 24
    expected_pages = (data["total"] + 24 - 1) // 24
    assert data["pages"] == expected_pages

    # Page 1 should have 24 items if total >= 24
    if data["total"] >= 24:
        assert len(data["products"]) == 24
    else:
        assert len(data["products"]) == data["total"]

    for p in data["products"]:
        assert p["price_inr"] <= 50000.0

    # Test Page 2 if multiple pages
    if data["pages"] >= 2:
        res2 = client.get("/api/products?page=2&limit=24&category=laptop&max_price=50000")
        assert res2.status_code == 200
        data2 = res2.json()
        assert len(data2["products"]) > 0
        for p in data2["products"]:
            assert p["price_inr"] <= 50000.0


def test_copilot_tool_selector_routes(client):
    """
    Verify copilot tool selector accurately routes queries:
    - off_topic_query: e.g. "generate the cpp code for two sum"
    - none_query: e.g. "zxcvbnm qwrtyp"
    - formatted_product_info: e.g. "specs of this laptop"
    - comparison_best_output: e.g. "compare laptops side by side"
    """
    # 1. Off-topic query (C++ Two Sum)
    res_off = client.post(
        "/api/copilot/chat",
        data='{"message": "generate the cpp code for two sum"}',
        content_type="application/json"
    )
    assert res_off.status_code == 200
    off_data = res_off.json()
    assert off_data.get("tool_used") == "off_topic_query"
    assert "C++" in off_data.get("reply", "") or "sum" in off_data.get("reply", "").lower()

    # 2. None / unintelligible query
    res_none = client.post(
        "/api/copilot/chat",
        data='{"message": "zxcvbnm qwrtyp"}',
        content_type="application/json"
    )
    assert res_none.status_code == 200
    none_data = res_none.json()
    assert none_data.get("tool_used") == "none_query"

    # 3. Formatted product info query
    res_info = client.post(
        "/api/copilot/chat",
        data='{"message": "specs of this laptop"}',
        content_type="application/json"
    )
    assert res_info.status_code == 200
    info_data = res_info.json()
    assert info_data.get("tool_used") == "formatted_product_info"
    assert "Hardware Specification" in info_data.get("reply", "")

    # 4. Comparison query
    res_comp = client.post(
        "/api/copilot/chat",
        data='{"message": "compare laptops side by side"}',
        content_type="application/json"
    )
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert comp_data.get("tool_used") == "comparison_best_output"


def test_copilot_personal_profile_query_and_persona_persistence(client):
    """
    Test personal profile query workflow:
    1. If user has no persona saved, returns questionnaire to collect requirements.
    2. Saving persona persists to DB (capped at 800 words).
    3. Subsequent query uses saved persona to provide tailored recommendations.
    """
    from app.commerce.user_commerce_service import get_user_commerce_service
    from app.agent.langchain_copilot import LangChainCommerceCopilot
    from sqlalchemy import text
    from app.db.database import engine

    svc = get_user_commerce_service()
    test_email = "personatest@amazon.com"

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM commerce_users WHERE email = :e"), {"e": test_email})
        conn.commit()

    user = svc.signup("personatest", test_email, "pass123", "Persona Test User")
    uid = user["id"]

    # Verify initial persona is empty
    initial_persona = svc.get_user_persona(uid)
    assert initial_persona == ""

    # Test questionnaire trigger
    copilot = LangChainCommerceCopilot()
    res_q = copilot.chat(
        message="which is best for me",
        catalog_products=[],
        user_persona="",
        user_id=uid,
        user_commerce_service=svc
    )
    assert res_q["tool_used"] in ["personal_profile_query", "persona_fetcher"]
    assert "Primary Workflow" in res_q["reply"] or "use /iam" in res_q["reply"].lower() or "tell me a little bit" in res_q["reply"]

    # Save a persona text
    persona_text = "I am a computer science university student doing machine learning and Android development. My budget is 60000 INR."
    updated = svc.update_user_persona(uid, persona_text)
    assert "computer science" in updated

    # Check persistence
    persisted = svc.get_user_persona(uid)
    assert "machine learning" in persisted

    # Check 800 word cap
    long_text = "word " * 1000
    capped = svc.update_user_persona(uid, long_text)
    assert len(capped.split()) <= 800


def test_persona_api_and_iam_me_flow(client):
    """
    Test the full /iam and /me workflow:
    1. GET /api/user/persona returns persona
    2. POST /api/user/persona updates persona
    3. Copilot query with /me when NO persona exists gives:
       "use /iam ---text--- under 100-200 characters"
    4. Copilot query with /iam <text> stores and confirms persona in account
    5. Copilot query with 'which laptop specs will be better for /me' fetches persona and gives specs
    6. Copilot query with /iam <new text> overwrites the persona
    7. Copilot query with 'who am i' or 'give all the information about me you have' returns full account & persona info
    8. Copilot query with 'who are you' returns assistant identity
    """
    from app.commerce.user_commerce_service import get_user_commerce_service
    from sqlalchemy import text
    from app.db.database import engine
    from app.agent.langchain_copilot import LangChainCommerceCopilot

    svc = get_user_commerce_service()
    test_email = "iamtest@amazon.com"

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM commerce_users WHERE email = :e"), {"e": test_email})
        conn.commit()

    user = svc.signup("iamtest", test_email, "pass123", "IAM Test User")
    uid = user["id"]

    # 1. Clear persona to test "not found" scenario
    svc.update_user_persona(uid, "")
    copilot = LangChainCommerceCopilot()

    # 2. Query for /me when NO persona exists -> instructs to use /iam
    res_not_found = copilot.chat(
        message="which laptop specs will be better for /me",
        catalog_products=[],
        user_persona="",
        user_id=uid,
        user_commerce_service=svc
    )
    assert res_not_found["tool_used"] == "persona_fetcher"
    assert res_not_found["persona_found"] is False
    assert "use /iam ---text--- under 100-200 characters" in res_not_found["reply"].lower()

    # 3. Use /iam to set person's information
    persona_v1 = "I am person A and I am a college student from XYZ college studying computer science."
    res_set = copilot.chat(
        message=f"/iam {persona_v1}",
        catalog_products=[],
        user_persona="",
        user_id=uid,
        user_commerce_service=svc
    )
    assert res_set["tool_used"] == "persona_iam_setter"
    assert res_set["persona_saved"] is True
    assert "person A" in res_set["updated_persona"]
    # Check DB was updated
    assert svc.get_user_persona(uid) == persona_v1

    # 4. Now query 'which laptop specs will be better for /me' -> should fetch persona and provide specs
    res_specs = copilot.chat(
        message="which laptop specs will be better for /me",
        catalog_products=[{"asin": "TEST1", "title": "CS Student Laptop", "price_inr": 55000, "specs": {"ram_gb": 16, "cpu": "Intel i5"}}],
        user_persona=persona_v1,
        user_id=uid,
        user_commerce_service=svc
    )
    assert res_specs["tool_used"] == "persona_fetcher"
    assert res_specs["persona_found"] is True
    assert "Recommended Laptop Specifications" in res_specs["reply"]
    assert "XYZ college" in res_specs["reply"] or "student" in res_specs["reply"].lower()

    # 5. Overwrite persona with next /iam call
    persona_v2 = "I am person B and I am a software engineer working with Docker and Python."
    res_overwrite = copilot.chat(
        message=f"/iam {persona_v2}",
        catalog_products=[],
        user_persona=persona_v1,
        user_id=uid,
        user_commerce_service=svc
    )
    assert res_overwrite["tool_used"] == "persona_iam_setter"
    assert svc.get_user_persona(uid) == persona_v2

    # 6. Query 'give all the information about me you have'
    res_info = copilot.chat(
        message="give all the information about me you have",
        catalog_products=[],
        user_persona=persona_v2,
        user_id=uid,
        user_commerce_service=svc
    )
    assert res_info["tool_used"] == "persona_fetcher"
    assert "IAM Test User" in res_info["reply"] or test_email in res_info["reply"]
    assert "person B" in res_info["reply"]

    # 7. Query 'who are you'
    res_who_are_you = copilot.chat(
        message="who are you",
        catalog_products=[],
        user_persona="",
        user_id=uid,
        user_commerce_service=svc
    )
    assert res_who_are_you["tool_used"] == "assistant_identity"
    assert "Agentic AI Shopping Copilot" in res_who_are_you["reply"]

    # 8. Test HTTP endpoint GET and POST /api/user/persona
    res_post_api = client.post(
        "/api/user/persona",
        data='{"persona_info": "Updated via HTTP API"}',
        content_type="application/json"
    )
    assert res_post_api.status_code == 200
    assert res_post_api.json()["persona_info"] == "Updated via HTTP API"

    res_get_api = client.get("/api/user/persona")
    assert res_get_api.status_code == 200
    assert "persona_info" in res_get_api.json()


def test_seller_portal_and_admin_pages(client):
    """Verify Seller Central and Admin Quality Verification pages load with 200 OK."""
    for path in ["/seller", "/business", "/admin-seller", "/admin-verification"]:
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]


def test_seller_submission_percentage_and_cashback_deals(client):
    """
    Test Seller product submission with:
    1. Percentage deal (k% off)
    2. Cashback offer (n rupees cashback)
    3. Input validation for quality standards & manufacturing license
    """
    # 1. Percentage discount deal (25% off)
    payload_pct = {
        "business_name": "Titanium Compute Systems India Ltd",
        "seller_name": "Rohan Deshmukh",
        "seller_email": "rohan@titaniumcompute.in",
        "seller_phone": "+91 99887 66554",
        "business_registration_no": "27AABCT9988K1Z3",
        "business_address": "Plot 10, MIDC Cyber Park, Pune 411057",
        "origin_country": "India",
        "title": "Titanium Stealth 15 - Intel Core i9 13th Gen, 32GB RAM, 1TB NVMe, RTX 4070",
        "brand": "Titanium",
        "category": "Gaming Laptops",
        "description": "Military-grade magnesium chassis creator laptop with 240Hz QHD display.",
        "original_price_inr": 120000.0,
        "selling_price_inr": 100000.0,
        "stock_quantity": 40,
        "image_url": "https://images.unsplash.com/photo-1541807084-5c52b6b3adef?w=600",
        "cpu": "Intel Core i9-13900H",
        "ram_gb": 32.0,
        "storage_gb": 1024.0,
        "gpu": "NVIDIA GeForce RTX 4070 8GB",
        "screen_size_inches": 15.6,
        "manufacturer_name": "Titanium Precision Assembly Pune",
        "factory_address": "Sector 3, Bhosari Industrial Area, Pune 411026",
        "manufacturing_license_no": "MFG-LIC-MH-2026-90123",
        "quality_certifications": "BIS Certified (R-41099881), ISO 9001:2015, CE, RoHS",
        "quality_inspection_notes": "Passed 100% factory stress benchmark and 70W cooling test.",
        "warranty_terms": "2 Years Comprehensive Onsite Warranty",
        "deal_type": "limited_time_deal",
        "discount_type": "percentage",
        "discount_percentage": 25.0,
        "cashback_inr": 0.0,
        "deal_headline": "Limited Time Deal: Flat 25% Off Titanium Stealth!",
        "deal_duration_hours": 48
    }

    res_pct = client.post("/api/seller/products/submit", data=json.dumps(payload_pct), content_type="application/json")
    assert res_pct.status_code == 201
    data_pct = res_pct.json()
    assert data_pct["submission_id"].startswith("SUB-")
    assert data_pct["verification_status"] == "pending"
    assert data_pct["discount_type"] == "percentage"
    assert data_pct["discount_percentage"] == 25.0
    # 120000 * (1 - 0.25) = 90000
    assert data_pct["deal_price_inr"] == 90000.0

    # 2. Cashback deal (₹3,500 cashback)
    payload_cb = {
        "business_name": "Horizon Electronics Labs Pvt Ltd",
        "seller_name": "Meera Nambiar",
        "seller_email": "meera@horizonlabs.in",
        "seller_phone": "+91 98450 11223",
        "business_registration_no": "29AABCH4455P1Z7",
        "business_address": "Koramangala 4th Block, Bengaluru 560034",
        "origin_country": "India",
        "title": "Horizon Swift 13 Ultra - Intel Evo i5 13th Gen, 16GB RAM, 512GB SSD",
        "brand": "Horizon",
        "category": "Laptops",
        "description": "Featherlight 990g magnesium ultrabook with 18-hour battery life.",
        "original_price_inr": 65000.0,
        "selling_price_inr": 58000.0,
        "stock_quantity": 50,
        "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600",
        "cpu": "Intel Core i5-1335U",
        "ram_gb": 16.0,
        "storage_gb": 512.0,
        "gpu": "Intel Iris Xe",
        "screen_size_inches": 13.3,
        "manufacturer_name": "Horizon Assembly Plant Bengaluru",
        "factory_address": "Plot 12, Peenya Industrial Area, Bengaluru 560058",
        "manufacturing_license_no": "MFG-LIC-KA-2026-33214",
        "quality_certifications": "BIS Certified (R-41033441), ISO 14001, RoHS",
        "warranty_terms": "1 Year Onsite Warranty",
        "deal_type": "limited_time_deal",
        "discount_type": "cashback",
        "discount_percentage": 0.0,
        "cashback_inr": 3500.0,
        "deal_headline": "Special Offer: ₹3,500 Instant Cashback into Amazon Wallet!",
        "deal_duration_hours": 72
    }

    res_cb = client.post("/api/seller/products/submit", data=json.dumps(payload_cb), content_type="application/json")
    assert res_cb.status_code == 201
    data_cb = res_cb.json()
    assert data_cb["verification_status"] == "pending"
    assert data_cb["discount_type"] == "cashback"
    assert data_cb["cashback_inr"] == 3500.0
    assert data_cb["deal_price_inr"] == 58000.0

    # 3. Missing mandatory quality certs validation
    bad_payload = dict(payload_pct)
    bad_payload["quality_certifications"] = ""
    res_bad = client.post("/api/seller/products/submit", data=json.dumps(bad_payload), content_type="application/json")
    assert res_bad.status_code == 400


def test_admin_verification_approval_and_catalog_publishing(client):
    """
    Test Amazon Seller Verification workflow:
    1. Admin reviews pending submission
    2. Admin executes approval: generates ASIN, inserts into store catalog
    3. Storefront /api/products returns the verified product with active deal and seller info
    4. Product detail /api/products/<asin> returns compliance and manufacturing details
    """
    # Create submission
    payload = {
        "business_name": "Spectra Tech Systems Pvt Ltd",
        "seller_name": "Siddharth Jain",
        "seller_email": "sid@spectratech.com",
        "business_registration_no": "06AABCS7788R1Z1",
        "title": "Spectra Quantum Pro 16 - AMD Ryzen 9 7945HX, 32GB RAM, 2TB SSD, RTX 4080",
        "brand": "Spectra",
        "category": "Gaming Laptops",
        "original_price_inr": 180000.0,
        "selling_price_inr": 150000.0,
        "cpu": "AMD Ryzen 9 7945HX",
        "ram_gb": 32.0,
        "storage_gb": 2048.0,
        "gpu": "NVIDIA GeForce RTX 4080 12GB",
        "screen_size_inches": 16.0,
        "manufacturer_name": "Spectra Precision Manufacturing Gurugram",
        "factory_address": "Sector 18, Udyog Vihar, Gurugram, Haryana 122015",
        "manufacturing_license_no": "MFG-LIC-HR-2026-55441",
        "quality_certifications": "BIS Certified (R-41055662), ISO 9001:2015, CE, RoHS",
        "deal_type": "limited_time_deal",
        "discount_type": "percentage",
        "discount_percentage": 20.0,
        "deal_headline": "Limited Time Deal: 20% Off Spectra Quantum Pro!",
        "deal_duration_hours": 48
    }

    sub_res = client.post("/api/seller/products/submit", data=json.dumps(payload), content_type="application/json")
    assert sub_res.status_code == 201
    sid = sub_res.json()["submission_id"]

    # Admin inspects submission
    detail_res = client.get(f"/api/admin/submissions/{sid}")
    assert detail_res.status_code == 200
    assert detail_res.json()["verification_status"] == "pending"

    # Admin approves submission
    approve_res = client.post(
        f"/api/admin/submissions/{sid}/approve",
        data=json.dumps({
            "verified_by": "Amazon Senior Compliance Officer",
            "admin_notes": "All factory licenses and BIS safety registration numbers verified. Published to live catalog."
        }),
        content_type="application/json"
    )
    assert approve_res.status_code == 200
    appr_data = approve_res.json()
    assert appr_data["verification_status"] == "approved"
    published_asin = appr_data["published_asin"]
    assert published_asin.startswith("B0SEL")

    # Verify published in store catalog
    prod_res = client.get(f"/api/products/{published_asin}")
    assert prod_res.status_code == 200
    prod_data = prod_res.json()
    assert prod_data["product"]["title"] == payload["title"]
    assert prod_data["deal"]["deal_type"] == "limited_time_deal"
    assert prod_data["deal"]["discount_percentage"] == 20.0
    assert prod_data["quality_verification"]["is_quality_certified"] is True
    assert prod_data["quality_verification"]["manufacturer_name"] == payload["manufacturer_name"]
    assert prod_data["seller"]["name"] == payload["business_name"]


def test_admin_verification_rejection(client):
    """Test Admin rejecting submission with compliance reason."""
    payload = {
        "business_name": "Faulty Devices Corp",
        "seller_name": "Test Seller",
        "seller_email": "faulty@seller.com",
        "title": "Unverified Laptop Model X",
        "brand": "Unverified",
        "original_price_inr": 30000.0,
        "manufacturer_name": "Unknown Factory",
        "factory_address": "Unknown Address",
        "manufacturing_license_no": "INVALID-LIC",
        "quality_certifications": "Unverified Standard",
        "deal_type": "limited_time_deal",
        "discount_type": "percentage",
        "discount_percentage": 10.0
    }
    sub_res = client.post("/api/seller/products/submit", data=json.dumps(payload), content_type="application/json")
    sid = sub_res.json()["submission_id"]

    rej_res = client.post(
        f"/api/admin/submissions/{sid}/reject",
        data=json.dumps({
            "verified_by": "Amazon Compliance Inspection",
            "admin_notes": "Manufacturing license INVALID-LIC could not be verified in state registry."
        }),
        content_type="application/json"
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["verification_status"] == "rejected"
    assert "INVALID-LIC" in rej_res.json()["admin_notes"]


def test_order_with_cashback_deal_credits_wallet(client):
    """
    Test placing an order with a product featuring a cashback deal:
    1. Check initial user wallet balance
    2. Place order containing item with cashback
    3. Verify user wallet is credited with the cashback amount
    4. Verify tracking logs contain cashback confirmation
    """
    from app.commerce.user_commerce_service import get_user_commerce_service
    svc = get_user_commerce_service()

    # Create demo submission with ₹2,000 cashback
    from app.commerce.seller_verification_service import get_seller_verification_service
    seller_svc = get_seller_verification_service()
    sub = seller_svc.submit_product(
        business_name="Cashback Test Electronics Ltd",
        seller_name="Karan Malhotra",
        seller_email="karan@cashbacktest.in",
        title="Cashback Special Ultrabook 14",
        brand="CashbackBrand",
        original_price_inr=50000.0,
        selling_price_inr=45000.0,
        manufacturer_name="Cashback Test Factory",
        factory_address="Plot 5, Electronic City Phase 2, Bengaluru",
        manufacturing_license_no="MFG-LIC-KA-2026-77889",
        quality_certifications="BIS Certified (R-41099221), ISO 9001",
        deal_type="limited_time_deal",
        discount_type="cashback",
        cashback_inr=2000.0,
        deal_headline="Limited Time Deal: ₹2,000 Wallet Cashback!"
    )
    approved = seller_svc.approve_submission(sub["submission_id"])
    asin = approved["published_asin"]

    # Sign up or retrieve a fresh test user
    test_email = "cashbackbuyer@amazon.com"
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM commerce_users WHERE email = :e"), {"e": test_email})

    user = svc.signup("cbuser", test_email, "pass123", "Cashback Test Buyer")
    uid = user["id"]
    initial_wallet = float(user["wallet_balance"])

    # Create order directly
    order = svc.create_order(
        user_id=uid,
        items=[{
            "asin": asin,
            "title": "Cashback Special Ultrabook 14",
            "price_inr": 45000.0,
            "quantity": 1,
            "cashback_inr": 2000.0
        }],
        payment_method="razorpay",
        from_cart=False
    )

    assert order["status"] in ["confirmed", "shipped"]

    # Verify wallet received ₹2,000 credit
    user_after = svc.get_user_by_id(uid)
    new_wallet = float(user_after["wallet_balance"])
    assert new_wallet == initial_wallet + 2000.0

    # Verify tracking log has cashback entry
    logs = order.get("tracking_logs", [])
    has_cashback_log = any(
        log.get("status") == "cashback_credited" or "Cashback" in log.get("description", "")
        for log in logs
    )
    assert has_cashback_log is True


def test_search_tokenization_expansion(client):
    """Test alphanumeric boundary expansion so 'laptop rtx3050' matches 'RTX 3050'."""
    res = client.get("/api/products?search=laptop+rtx3050")
    assert res.status_code == 200
    data = res.json()
    assert "products" in data
    products = data["products"]
    assert len(products) > 0
    # Confirm matching titles contain RTX 3050
    has_rtx = any("3050" in p["title"] for p in products)
    assert has_rtx is True


def test_helpline_and_support_info(client):
    """Test 24x7 Customer Care Helpline info endpoint and Copilot /help tool."""
    res = client.get("/api/support/info")
    assert res.status_code == 200
    data = res.json()
    assert data["helpline_phone"] == "9909665466"
    assert data["return_policy_window_days"] == 10
    assert data["doorstep_inspection"] is True

    # Also test Copilot LangChain agent tool selection for /help
    from web.views import get_langchain_copilot
    copilot = get_langchain_copilot()
    help_resp = copilot.chat("please call helpline 9909665466 or /help for order returns")
    assert "9909665466" in help_resp["reply"]
    assert "10-Day" in help_resp["reply"] or "10 days" in help_resp["reply"].lower()


def test_delivery_portal_and_agent_list(client):
    """Test Delivery Partner portal and associate listings."""
    # Front-end delivery associate page
    page_res = client.get("/delivery")
    assert page_res.status_code == 200

    # API agents list
    agents_res = client.get("/api/delivery/agents")
    assert agents_res.status_code == 200
    agents_data = agents_res.json()
    assert "agents" in agents_data
    assert len(agents_data["agents"]) >= 3
    assert any("ATS" in (a.get("badge_id") or a.get("badge") or "") for a in agents_data["agents"])

    # API delivery orders
    orders_res = client.get("/api/delivery/orders")
    assert orders_res.status_code == 200
    assert "orders" in orders_res.json()


def test_doorstep_return_ten_day_policy_constraint(client):
    """Test strict 10-day return policy constraint."""
    from app.commerce.user_commerce_service import get_user_commerce_service
    svc = get_user_commerce_service()

    test_email = "returntest@amazon.com"
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM commerce_users WHERE email = :e"), {"e": test_email})

    user = svc.signup("returnuser", test_email, "pass123", "Return Test User")
    uid = user["id"]

    # Log in client
    client.post("/api/user/login", data=json.dumps({"email": test_email, "password": "pass123"}), content_type="application/json")

    # 1. Place order within 10-day window
    order = svc.create_order(
        user_id=uid,
        items=[{
            "asin": "RET-ASIN-01",
            "title": "Eligible Laptop Under 10 Days",
            "price_inr": 40000.0,
            "quantity": 1
        }],
        payment_method="razorpay",
        from_cart=False
    )
    ord_num = order["order_number"]

    # Request return within 10 days -> should succeed
    ret_res = client.post(
        f"/api/orders/{ord_num}/return",
        data=json.dumps({"reason": "Display issue (screen flicker)"}),
        content_type="application/json"
    )
    assert ret_res.status_code == 200
    ret_data = ret_res.json()
    assert ret_data["return_status"] == "pickup_assigned"
    assert "return_otp" in ret_data
    assert len(ret_data["return_otp"]) == 4

    # 2. Simulate order created > 10 days ago (e.g. 15 days)
    old_order = svc.create_order(
        user_id=uid,
        items=[{
            "asin": "OLD-ASIN-02",
            "title": "Expired Laptop Over 10 Days",
            "price_inr": 60000.0,
            "quantity": 1
        }],
        payment_method="razorpay",
        from_cart=False
    )
    old_num = old_order["order_number"]

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE commerce_orders SET created_at = NOW() - INTERVAL '15 days' WHERE order_number = :num"),
            {"num": old_num}
        )

    # Request return on >10 days order -> MUST fail with 400 constraint violation
    expired_res = client.post(
        f"/api/orders/{old_num}/return",
        data=json.dumps({"reason": "No longer needed"}),
        content_type="application/json"
    )
    assert expired_res.status_code == 400
    assert "10 days" in expired_res.json()["detail"]


def test_doorstep_return_mobile_approval_and_instant_wallet_refund(client):
    """
    Test delivery associate inspecting item at doorstep and approving via mobile portal:
    1. Customer requests return (<10 days)
    2. Associate arrives, inputs return OTP + passes condition checklist
    3. Approval triggers instant full refund to customer Amazon Wallet
    4. Order status updates to 'returned' with audit log
    """
    from app.commerce.user_commerce_service import get_user_commerce_service
    svc = get_user_commerce_service()

    test_email = "doorsteprefund@amazon.com"
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM commerce_users WHERE email = :e"), {"e": test_email})

    user = svc.signup("refunduser", test_email, "pass123", "Doorstep Refund Customer")
    uid = user["id"]
    initial_wallet = float(user["wallet_balance"])

    # Log in client
    client.post("/api/user/login", data=json.dumps({"email": test_email, "password": "pass123"}), content_type="application/json")

    # Create order for ₹25,000
    order_amount = 25000.0
    order = svc.create_order(
        user_id=uid,
        items=[{
            "asin": "LAPTOP-REFUND-001",
            "title": "Doorstep Return Gaming Laptop",
            "price_inr": order_amount,
            "quantity": 1
        }],
        payment_method="razorpay",
        from_cart=False
    )
    ord_num = order["order_number"]

    # Customer requests doorstep return
    ret_req = client.post(
        f"/api/orders/{ord_num}/return",
        data=json.dumps({"reason": "Defective HDMI port"}),
        content_type="application/json"
    )
    assert ret_req.status_code == 200
    otp = ret_req.json()["return_otp"]

    # Delivery associate opens mobile portal and submits doorstep approval
    approval_payload = {
        "agent_name": "Rajesh Kumar",
        "agent_badge": "ATS-8821",
        "otp": otp,
        "checklist": {
            "original_box": True,
            "charger_included": True,
            "device_condition_pass": True,
            "serial_match": True
        },
        "notes": "Original box and serial number verified. Product in pristine physical condition."
    }

    appr_res = client.post(
        f"/api/delivery/returns/{ord_num}/approve",
        data=json.dumps(approval_payload),
        content_type="application/json"
    )
    assert appr_res.status_code == 200
    appr_data = appr_res.json()
    assert appr_data["return_status"] == "approved"
    assert appr_data["status"] == "returned"

    # Verify customer wallet received instant refund credit
    user_after = svc.get_user_by_id(uid)
    assert float(user_after["wallet_balance"]) == initial_wallet + order_amount

    # Verify wallet transaction log
    with engine.connect() as conn:
        tx = conn.execute(
            text("SELECT * FROM commerce_wallet_transactions WHERE user_id = :uid AND transaction_type = 'refund'"),
            {"uid": uid}
        ).mappings().first()
        assert tx is not None
        assert float(tx["amount"]) == order_amount
        assert ord_num in tx["description"]


def test_doorstep_return_mobile_rejection(client):
    """Test delivery associate rejecting return at doorstep when criteria fail."""
    from app.commerce.user_commerce_service import get_user_commerce_service
    svc = get_user_commerce_service()

    test_email = "rejectreturn@amazon.com"
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM commerce_users WHERE email = :e"), {"e": test_email})

    user = svc.signup("rejectuser", test_email, "pass123", "Reject Return Customer")
    uid = user["id"]

    client.post("/api/user/login", data=json.dumps({"email": test_email, "password": "pass123"}), content_type="application/json")

    order = svc.create_order(
        user_id=uid,
        items=[{
            "asin": "LAPTOP-REJ-001",
            "title": "Damaged Laptop",
            "price_inr": 35000.0,
            "quantity": 1
        }],
        payment_method="razorpay",
        from_cart=False
    )
    ord_num = order["order_number"]

    ret_req = client.post(
        f"/api/orders/{ord_num}/return",
        data=json.dumps({"reason": "Performance issue"}),
        content_type="application/json"
    )
    assert ret_req.status_code == 200

    # Associate arrives and rejects inspection
    rej_res = client.post(
        f"/api/delivery/returns/{ord_num}/reject",
        data=json.dumps({
            "agent_name": "Rajesh Kumar",
            "rejection_reason": "Device screen cracked and original power brick missing."
        }),
        content_type="application/json"
    )
    assert rej_res.status_code == 200
    rej_data = rej_res.json()
    assert rej_data["return_status"] == "rejected"
    assert "screen cracked" in (rej_data.get("return_notes") or "")







