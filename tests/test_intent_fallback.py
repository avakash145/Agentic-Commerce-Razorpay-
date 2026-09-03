from app.agent.intent_parser import IntentParser


def test_local_intent_fallback_extracts_explicit_constraints(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    intent = IntentParser().parse(
        "Find a gaming laptop under ₹80,000 with at least 16GB RAM, "
        "512GB storage, an RTX GPU and 4 star rating"
    )

    assert intent.category == "laptop"
    assert intent.max_price_inr == 80000
    assert intent.min_ram_gb == 16
    assert intent.min_storage_gb == 512
    assert intent.gpu == "rtx"
    assert intent.min_rating == 4


def test_local_intent_fallback_keeps_specific_gpu_model(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    intent = IntentParser().parse("laptops with gpu rtx 3050")

    assert intent.category == "laptop"
    assert intent.gpu == "rtx 3050"
    assert intent.search_query == "laptop rtx 3050"
