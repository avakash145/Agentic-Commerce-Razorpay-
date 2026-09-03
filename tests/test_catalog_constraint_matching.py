from app.catalog.filter_service import ProductFilterService
from app.catalog.spec_extractor import ProductSpecExtractor


def test_gpu_constraint_falls_back_to_source_text_when_spec_is_missing():
    product = {
        "title": 'ASUS V16 RTX™ 5070 Gaming Laptop',
        "description": "",
        "breadcrumbs": "Traditional Laptops",
    }

    assert ProductFilterService._matches_gpu(
        product,
        {"gpu": None},
        "rtx 5070",
    )


def test_laptop_category_does_not_match_keyboard_breadcrumb():
    product = {
        "title": "Gaming Keyboard for Laptop",
        "breadcrumbs": "Gaming Keyboards",
    }

    assert not ProductFilterService._matches_category(product, "laptop")


def test_gpu_extractor_accepts_trademark_separator():
    assert ProductSpecExtractor.extract_gpu(
        "Laptop with RTX™ 5070 graphics"
    ) == "RTX™ 5070"
