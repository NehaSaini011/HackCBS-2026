---
lesson_id: les_5eed0004
title: Validate database fixes before production rollout
category: deployment_safety
source_shop: portfolio_network
severity: high
status: verified
---

## Symptom
A proposed database fix appears correct but may not improve
the receiving company's actual workload.

## Root cause
Database schemas, data distributions and query plans can differ
between portfolio companies.

## Recommended procedure
1. Create an isolated fork of the receiving company's database.
2. Record the baseline query plan and execution time.
3. Apply the proposed fix only to the fork.
4. Run ANALYZE where appropriate.
5. Execute the same representative query again.
6. Confirm that the intended index exists.
7. Confirm that the query planner actually uses it.
8. Record before-and-after measurements.

## Approval criteria
The fix passes only when the required index exists and
the query plan uses it.

## Safety
The original database must remain unchanged during testing.
A passing test is evidence for human approval, not automatic
authorization to deploy.

## Reusable insight
A fix proven in one company should be re-tested against
the receiving company's own database before rollout.
