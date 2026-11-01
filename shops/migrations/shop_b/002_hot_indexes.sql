

ALTER TABLE releases
DROP CONSTRAINT IF EXISTS releases_version_key;

CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_purchases_buyer_placed
ON purchases (buyer_id, placed_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_purchase_items_purchase
ON purchase_items (purchase_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_basket_items_buyer
ON basket_items (buyer_id);
