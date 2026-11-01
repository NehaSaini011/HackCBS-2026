---
lesson_id: les_5eed0001
title: Missing customer order-history index
category: database_performance
source_shop: pinecart
severity: critical
status: verified
---

## Symptom
Customer order-history requests become slower after a deployment.

## Root cause
The deployment removed the composite index on (customer_id, created_at DESC).

## Detection
Check whether idx_orders_customer_created exists on the orders table.

## Recommended fix
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);

## Verification
Run EXPLAIN ANALYZE on the customer order-history query.
Confirm that PostgreSQL uses the expected index.

## Safety
Apply and benchmark the fix on an isolated database fork first.
Never modify the receiving company's production database automatically.

## Reusable insight
Queries filtering by customer_id and sorting by created_at DESC
may benefit from a matching composite index.
