import os
import pytest
from django.test import Client

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
    assert order_data["status"] in ["confirmed", "processing", "ordered"]
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





