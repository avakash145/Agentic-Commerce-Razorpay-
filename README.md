# Agentic Commerce

Agentic Commerce is a shopping agent that turns a natural-language request into a constrained product search and a secure Razorpay checkout. The important boundary is intentional: the AI can discover products and extract preferences, but the server owns price, stock, payment amount, signature verification, and transaction state.

## What is ready

- Intent-aware product discovery with semantic/lexical hybrid search.
- Deterministic filtering for budget, stock, rating, RAM, storage, GPU, and CPU.
- Server-authoritative Razorpay Test Mode order creation.
- Ed25519-signed payment mandates in the security layer.
- Local transaction recording with idempotent webhook processing.
- HMAC verification for Razorpay webhooks and checkout payment signatures.
- A responsive chat-to-checkout demo at `/`.

## Run locally

1. Create a PostgreSQL database with `pgvector` enabled and load the catalog tables expected by the app (`products`, `media`, `product_specs`, and `product_documents`).
2. Install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and add Razorpay Test Mode credentials and `DATABASE_URL`.
4. Create the local transaction/audit tables:

   ```bash
   python init_db.py
   ```

5. Start the app:

   ```bash
   uvicorn main_api:app --reload
   ```

   Open <http://localhost:8000>.

The embedding model is OpenCLIP `ViT-B-16`. It creates a shared
512-dimensional space for product text, specifications, images, and video
preview frames. The first index rebuild downloads the model and product
images; image files are cached outside the repository. Set
`EMBEDDING_DEVICE=cuda` only when CUDA is available. If the multimodal model
is unavailable, vector search automatically falls back to the existing text
index until the multimodal index is built.

## Catalog ingestion

Apify exports are processed by ASIN, not by file or row count. The repeatable
pipeline merges raw and processed records, fills missing values from duplicate
crawls, deduplicates attributes/reviews/images, extracts specs, and records a
quality status in `products.raw_data.pipeline`. Price resolution checks the
current product price, seller offers, priced variants, linked variant ASINs,
and finally a reported price range. The selected value is the lowest observed
price in one currency; `price_min`/`price_max` and
`price_selection_required` preserve the fact that it may be a starting price.
Products without a price remain available to browse, but cannot pass budget
filtering or checkout.

```bash
python catalog_pipeline.py --dry-run
python catalog_pipeline.py --kinds laptop,desktop,keyboard,mouse,mobile,tablet,monitor,headphone,camera,storage,networking,accessory
python index_products.py
```

`index_products.py` stores the 512-dimensional vectors in
`product_documents.embedding_multimodal`. It fuses text (title, category,
specs, features, and review summary), up to four product images, and available
video preview frames. Amazon HLS video URLs are represented by their crawler
preview frames; local/direct video files can additionally be sampled with
OpenCV.

Use [DATA_COLLECTION_QUERIES.md](DATA_COLLECTION_QUERIES.md) for the targeted
computer-category query set. `/api/products/{asin}` returns the complete detail
view, including images, attributes, specs, reviews, review summary, and similar
products.

## Razorpay setup

Use Test Mode keys while evaluating the project. In the Razorpay Dashboard, create a webhook pointing to:

```text
https://<your-public-host>/webhooks/razorpay
```

Use the same webhook secret in `RAZORPAY_WEBHOOK_SECRET` and enable `payment.authorized`, `payment.captured`, `payment.failed`, and `order.paid`. For local webhook testing, expose port 8000 with a secure tunnel and use the tunnel URL in the Dashboard.

The checkout never accepts an amount from the browser. It sends only the selected ASIN; the backend reloads the product and creates the order. The browser then forwards Razorpay's returned IDs and signature to `/api/checkout/verify-payment`. Webhooks remain the source of truth for the final captured state.

## Useful checks

```bash
python -m pytest tests -q
python -m compileall -q app web config main.py main_api.py
DJANGO_SETTINGS_MODULE=config.settings python -m django check
```

`main_api.py` is the canonical server entrypoint for the complete demo. The older Django files remain for the existing project structure, but the FastAPI entrypoint is the one that includes checkout and webhook routes.

## Security notes for submission

- Do not commit `.env` or any Razorpay secret.
- Keep Test Mode enabled until the entire order/webhook flow is verified.
- Configure HTTPS for any deployed checkout and webhook endpoint.
- Keep the catalog and transaction database private; only the browser-facing API should be public.

# Project Architecture:

                    AMAZON / APIFY DATA
                           |
                           v
                    RAW DATA STORAGE
                           |
                           v
                  EXTRACTION / ETL
                           |
                           v
                 NORMALIZED DATA
                           |
                           v
                    POSTGRESQL
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
       Products         Reviews           Media
          |                |                |
          |                |          +-----+-----+
          |                |          |           |
          |                |        Images      Video
          |                |          |           |
          |                |          v           v
          |                |       Vision      Video Model
          |                |       Model
          |                |          |
          +----------------+----------+
                           |
                           v
              STRUCTURED + TEXTUAL
                 REPRESENTATION
                           |
                           v
                   QUALITY FILTERING
                           |
                           v
                      EMBEDDINGS
                           |
                           v
                     VECTOR DB(pg vector)
                           |
                           v
                 HYBRID RETRIEVAL
                           |
                           v
                    OLLAMA + (TOOL/OUTPUT SELECTOR(ReAct based) -> DIFFERENT DB'S WITH DIFFERENT SURFACE (LIKE AMAZON, FLIPKART , MYNTRA))
                           |
                           v
                  AGENTIC COMMERCE

-----------------------------------+-------------------------------------------------------------------------------------+------------------------------



                    ┌──────────────────────────┐
                    │          USER            │
                    │  Natural Language Query  │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │      AI AGENT LAYER      │
                    │                          │
                    │  Intent Parser           │
                    │  Commerce Search Agent   │
                    │  Growth / Recommendation │
                    └────────────┬─────────────┘
                                 │
                                 ▼
              ┌────────────────────────────────────┐
              │       INTELLIGENT DISCOVERY        │
              │                                    │
              │  ┌────────────┐  ┌──────────────┐  │
              │  │  Semantic  │  │   Lexical    │  │
              │  │  Search    │  │    Search    │  │
              │  └─────┬──────┘  └──────┬───────┘  │
              │        └────────┬────────┘         │
              │                 ▼                  │
              │          Hybrid Retrieval          │
              │          (RRF Ranking)             │
              └────────────────┬───────────────────┘
                               │
                               ▼
              ┌────────────────────────────────────┐
              │       MULTIMODAL CATALOG           │
              │                                    │
              │  Text + Images + Video             │
              │  OpenCLIP Embeddings               │
              │  PostgreSQL + pgvector             │
              └────────────────┬───────────────────┘
                               │
                               ▼
              ┌────────────────────────────────────┐
              │    DETERMINISTIC COMMERCE LAYER    │
              │                                    │
              │  Price / Budget                    │
              │  Stock                             │
              │  Rating                            │
              │  Category                          │
              │  RAM / Storage / GPU / CPU         │
              │  Currency / FX                     │
              └────────────────┬───────────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │    POLICY ENGINE         │
                    │                          │
                    │  Purchase Rules          │
                    │  Budget Validation       │
                    │  Stock Validation        │
                    │  Confirmation Rules      │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │    PAYMENT SECURITY      │
                    │                          │
                    │  Payment Mandate         │
                    │  Ed25519 Signature       │
                    │  Authorization Gateway   │
                    │  Action Gateway          │
                    │  Idempotency             │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │      RAZORPAY            │
                    │   Test Payment Gateway   │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │       WEBHOOKS           |
                    │                          │
                    │  HMAC Verification       │
                    │  Event Idempotency       │
                    │  Payment State Machine   │
                    └────────────┬─────────────┘
                                 │
                                 ▼
              ┌────────────────────────────────────┐
              │       TRANSACTION + AUDIT DB       │
              │                                    │
              │  Transactions                      │
              │  Webhook Events                    │
              │  Audit Events                      │
              │  Mandates                          │
              └────────────────────────────────────┘
