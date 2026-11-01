
DROP INDEX CONCURRENTLY IF EXISTS
idx_orders_status_created;

CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_orders_customer_created
ON orders (customer_id, created_at DESC);

INSERT INTO releases (version, description)
VALUES (
    'v2.2',
    'Reset: restored healthy customer order-history index'
);
