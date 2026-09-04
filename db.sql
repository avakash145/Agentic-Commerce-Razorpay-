
CREATE TABLE products (
    product_id BIGSERIAL PRIMARY KEY,

    asin TEXT UNIQUE NOT NULL,
    original_asin TEXT,

    title TEXT NOT NULL,
    brand TEXT,
    url TEXT,

    price NUMERIC,
    currency TEXT,
    list_price NUMERIC,
    shipping_price NUMERIC,

    in_stock BOOLEAN,
    in_stock_text TEXT,

    stars NUMERIC,	
    reviews_count INTEGER,
    answered_questions INTEGER,

    breadcrumbs TEXT,

    description TEXT,

    delivery TEXT,
    fastest_delivery TEXT,
    return_policy TEXT,
    condition TEXT,

    is_amazon_choice BOOLEAN,
    amazon_choice_text TEXT,

    video_count INTEGER DEFAULT 0,

    raw_data JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE product_attributes (
    attribute_id BIGSERIAL PRIMARY KEY,

    product_id BIGINT NOT NULL
        REFERENCES products(product_id)
        ON DELETE CASCADE,

    attribute_name TEXT NOT NULL,
    attribute_value TEXT
);

CREATE TABLE reviews (
    review_id TEXT PRIMARY KEY,

    product_id BIGINT NOT NULL
        REFERENCES products(product_id)
        ON DELETE CASCADE,

    username TEXT,

    rating NUMERIC,

    title TEXT,
    review_text TEXT,

    review_date DATE,

    review_url TEXT,

    reaction TEXT,

    is_verified BOOLEAN,
    is_amazon_vine BOOLEAN,

    variant TEXT,

    raw_data JSONB
);


CREATE TABLE product_variants (
    variant_id BIGSERIAL PRIMARY KEY,

    product_id BIGINT NOT NULL
        REFERENCES products(product_id)
        ON DELETE CASCADE,

    asin TEXT,

    name TEXT,

    price NUMERIC,

    thumbnail_url TEXT,

    raw_data JSONB
);

--truncate products cascade;

SELECT
    asin,
    raw_data->'media'->'thumbnail' AS thumbnail,
    raw_data->'media'->'gallery' AS gallery,
    raw_data->'media'->'high_resolution' AS high_resolution
FROM products
LIMIT 1;

ALTER TABLE media
ADD CONSTRAINT unique_media
UNIQUE (product_id, review_id, media_type, url);

SELECT
    media_type,
    COUNT(*)
FROM media
GROUP BY media_type;

SELECT
    p.asin,
    p.title,
    m.media_type,
    m.url
FROM products p
JOIN media m
    ON p.product_id = m.product_id
LIMIT 200;

select product_id,raw_data from products;

select * from reviews;




SELECT COUNT(DISTINCT review_id) AS unique_reviews
FROM reviews;


SELECT
    p.asin,
    p.title,
    COUNT(r.review_id) AS review_count
FROM products p
LEFT JOIN reviews r
    ON p.product_id = r.product_id
GROUP BY
    p.product_id,
    p.asin,
    p.title
ORDER BY review_count DESC
LIMIT 10;	