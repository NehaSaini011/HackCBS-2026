---
lesson_id: les_5eed0003
title: Buyer purchase-history index missing
category: database_performance
source_shop: tealbox
severity: critical
status: verified
---

## Symptom
Buyer purchase-history queries may become slower after a deployment.

## Root cause
The required composite index on (buyer_id, placed_at DESC) is missing.

## Detection
Check whether idx_purchases_buyer_placed exists on the purchases table.

## Recommended fix
CREATE INDEX idx_purchases_buyer_placed
ON purchases (buyer_id, placed_at DESC);

## Verification
Run EXPLAIN ANALYZE on the buyer purchase-history query.
Confirm that PostgreSQL uses the expected index.

## Safety
Test the proposed index on an isolated database fork first.
Do not apply changes directly to production.

## Reusable insight
Indexes should match the application's filtering and sorting pattern.
