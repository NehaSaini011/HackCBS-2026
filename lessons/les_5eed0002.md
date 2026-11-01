---
lesson_id: les_5eed0002
title: Incorrect replacement index after deployment
category: database_performance
source_shop: pinecart
severity: high
status: verified
---

## Symptom
A deployment replaces a frequently used index with an index
that does not match the application's query pattern.

## Root cause
The replacement index uses status and created_at,
while the hot query filters by customer_id and sorts by created_at.

## Detection
Compare the query's WHERE and ORDER BY columns with the available indexes.
Inspect the query plan using EXPLAIN ANALYZE.

## Recommended fix
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);

## Verification
Confirm that the expected index exists and is selected by the query planner.

## Safety
Test the replacement on a disposable database fork before approval.

## Reusable insight
An index existing on a table does not guarantee that it helps
the application's most important query.
