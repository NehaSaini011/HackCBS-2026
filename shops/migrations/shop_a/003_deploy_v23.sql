DROP INDEX CONCURRENTLY IF EXISTS
idx_orders_customer_created;

CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_orders_status_created
ON orders (status, created_at DESC);

INSERT INTO releases (version, description)
VALUES (
    'v2.3',
    'Faulty deployment: customer order-history index removed'
);
