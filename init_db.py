from sqlalchemy import text

from app.db.database import engine
from app.db.models import Base


Base.metadata.create_all(
    bind=engine
)

# The original prototype used an integer amount column.  Checkout now keeps
# paise-safe INR values, so upgrade an existing PostgreSQL install as well as
# creating the table on a fresh database.
if engine.dialect.name == "postgresql":
    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE product_documents "
            "ADD COLUMN IF NOT EXISTS embedding_multimodal vector(512)"
        ))
        for statement in (
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_min NUMERIC",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_max NUMERIC",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_source TEXT",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_is_exact BOOLEAN",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_selection_required BOOLEAN",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_options_count INTEGER",
            "CREATE TABLE IF NOT EXISTS product_variants ("
            "variant_id BIGSERIAL PRIMARY KEY,"
            "product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,"
            "asin TEXT, name TEXT, price NUMERIC, currency TEXT,"
            "thumbnail_url TEXT, in_stock BOOLEAN, raw_data JSONB)",
            "ALTER TABLE product_variants ADD COLUMN IF NOT EXISTS currency TEXT",
            "ALTER TABLE product_variants ADD COLUMN IF NOT EXISTS in_stock BOOLEAN",
            "CREATE TABLE IF NOT EXISTS product_offers ("
            "offer_id BIGSERIAL PRIMARY KEY,"
            "product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,"
            "provider TEXT, seller_name TEXT, seller_id TEXT, url TEXT,"
            "price NUMERIC, currency TEXT, shipping_price NUMERIC,"
            "in_stock BOOLEAN, condition TEXT, raw_data JSONB)",
            "CREATE INDEX IF NOT EXISTS product_offers_product_id_idx "
            "ON product_offers(product_id)",
        ):
            connection.execute(text(statement))
        connection.execute(text(
            "ALTER TABLE transactions "
            "ALTER COLUMN amount TYPE NUMERIC(20, 2) "
            "USING amount::numeric"
        ))

print("Database tables created.")
