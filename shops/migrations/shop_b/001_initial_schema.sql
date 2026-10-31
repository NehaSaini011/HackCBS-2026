
-- =========================================================
-- TEALBOX (SHOP B)
-- Migration: 001_initial_schema
-- Initial database schema
-- =========================================================

CREATE TABLE buyers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(255) NOT NULL UNIQUE,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    details TEXT,
    product_type VARCHAR(100),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    available_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (available_quantity >= 0),
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE purchases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    buyer_id BIGINT NOT NULL REFERENCES buyers(id),
    purchase_status VARCHAR(30) NOT NULL DEFAULT 'placed',
    purchase_total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    placed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE purchase_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    purchase_id BIGINT NOT NULL
        REFERENCES purchases(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(id),
    item_quantity INTEGER NOT NULL CHECK (item_quantity > 0),
    price_at_purchase NUMERIC(10, 2) NOT NULL
        CHECK (price_at_purchase >= 0)
);

CREATE TABLE basket_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    buyer_id BIGINT NOT NULL REFERENCES buyers(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    item_quantity INTEGER NOT NULL DEFAULT 1
        CHECK (item_quantity > 0),
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (buyer_id, product_id)
);

-- Release tracking
CREATE TABLE releases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version VARCHAR(20) NOT NULL UNIQUE,
    description TEXT,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Request metrics
CREATE TABLE request_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    endpoint TEXT NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER NOT NULL,
    total_latency_ms DOUBLE PRECISION NOT NULL,
    db_latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0
);

INSERT INTO releases (version, description)
VALUES ('v2.2', 'Initial healthy Tealbox schema');
