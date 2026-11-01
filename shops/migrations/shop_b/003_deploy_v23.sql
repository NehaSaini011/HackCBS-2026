
-- TEALBOX: Simulate faulty v2.3 deployment.

DROP INDEX CONCURRENTLY IF EXISTS
idx_purchases_buyer_placed;

-- Wrong index for the buyer purchase-history query.
CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_purchases_status_placed
ON purchases (purchase_status, placed_at DESC);

INSERT INTO releases (version, description)
VALUES (
    'v2.3',
    'Faulty deployment: buyer purchase-history index removed'
);
