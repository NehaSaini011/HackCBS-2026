
-- TEALBOX: Restore healthy v2.2 state.

DROP INDEX CONCURRENTLY IF EXISTS
idx_purchases_status_placed;

CREATE INDEX CONCURRENTLY IF NOT EXISTS
idx_purchases_buyer_placed
ON purchases (buyer_id, placed_at DESC);

INSERT INTO releases (version, description)
VALUES (
    'v2.2',
    'Reset: restored healthy buyer purchase-history index'
);
