ALTER TABLE releases
DROP CONSTRAINT IF EXISTS releases_version_key;

CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_orders_customer_created
ON orders (customer_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_order_items_order
ON order_items (order_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_cart_items_customer
ON cart_items (customer_id);
