import json

from catalog_pipeline import build_catalog


def test_pipeline_merges_sources_by_asin_and_keeps_missing_price_partial(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "crawl.json").write_text(json.dumps([
        {
            "asin": "B012345678",
            "title": "Example laptop",
            "price": None,
            "inStock": True,
            "breadCrumbs": "Computers > Laptops",
            "thumbnailImage": "https://m.media-amazon.com/image.jpg",
        }
    ]))
    processed_file = tmp_path / "products.json"
    processed_file.write_text(json.dumps([
        {
            "identity": {
                "asin": "B012345678",
                "title": "Example laptop",
            },
            "commerce": {
                "price": {"value": 499.99, "currency": "$"},
                "in_stock": True,
            },
            "classification": {
                "breadcrumbs": "Computers > Laptops",
            },
            "media": {
                "thumbnail": "https://m.media-amazon.com/image.jpg",
            },
        }
    ]))

    catalog, report = build_catalog(raw_dir, processed_file)

    assert len(catalog) == 1
    assert catalog[0]["price"] == 499.99
    assert catalog[0]["quality"]["status"] == "ready"
    assert report["duplicate_records_collapsed"] == 1


def test_pipeline_marks_product_without_price_partial(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "crawl.json").write_text(json.dumps([
        {
            "asin": "B012345679",
            "title": "Unpriced laptop",
            "inStock": True,
            "breadCrumbs": "Computers > Laptops",
            "thumbnailImage": "https://m.media-amazon.com/image.jpg",
        }
    ]))
    processed_file = tmp_path / "products.json"
    processed_file.write_text("[]")

    catalog, report = build_catalog(raw_dir, processed_file)

    assert catalog[0]["quality"]["status"] == "partial"
    assert report["partial_products"] == 1


def test_pipeline_uses_variant_price_range_and_requires_selection(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "crawl.json").write_text(json.dumps([
        {
            "asin": "B012345670",
            "title": "Variant laptop",
            "inStock": True,
            "breadCrumbs": "Computers > Laptops",
            "thumbnailImage": "https://m.media-amazon.com/image.jpg",
            "variantDetails": [
                {"asin": "B012345671", "name": "8GB", "price": {"value": 499, "currency": "$"}},
                {"asin": "B012345672", "name": "16GB", "price": {"value": 699, "currency": "$"}},
            ],
        }
    ]))

    catalog, _ = build_catalog(raw_dir, tmp_path / "products.json")

    assert catalog[0]["price"] == 499
    assert catalog[0]["price_min"] == 499
    assert catalog[0]["price_max"] == 699
    assert catalog[0]["price_source"] == "lowest_variant"
    assert catalog[0]["price_selection_required"] is True


def test_pipeline_uses_lowest_offer_and_keeps_provider_options(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "crawl.json").write_text(json.dumps([
        {
            "asin": "B012345673",
            "title": "Multi-seller keyboard",
            "price": None,
            "inStock": True,
            "breadCrumbs": "Computers > Keyboards",
            "thumbnailImage": "https://m.media-amazon.com/image.jpg",
            "offers": [
                {"provider": "Seller A", "price": {"value": 40, "currency": "$"}},
                {"provider": "Seller B", "price": {"value": 35, "currency": "$"}},
            ],
        }
    ]))

    catalog, _ = build_catalog(raw_dir, tmp_path / "products.json")

    assert catalog[0]["price"] == 35
    assert catalog[0]["price_source"] == "lowest_offer"
    assert catalog[0]["price_options_count"] == 2
    assert catalog[0]["price_selection_required"] is True
    assert len(catalog[0]["offers"]) == 2
