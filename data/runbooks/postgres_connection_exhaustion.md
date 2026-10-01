# Runbook: Postgres Connection Pool Exhaustion & Advisory Lock Contention

**Category:** Database / PostgreSQL  
**Severity Tier:** P0 / P1  
**Target Services:** `payment-db-prod`, `orders-db`, `auth-db`  

---

## 1. Incident Overview
PostgreSQL client connection count reaches ≥ 90% of `max_connections`, leading to connection starvation for downstream microservices, elevated `504 Gateway Timeout` errors, and client request dropouts.

## 2. Diagnostic Investigation
1. Execute `query_db_metrics` with `threshold_seconds=60`.
2. Inspect `pg_stat_activity` for queries in state `idle in transaction` or waiting on advisory locks (`SELECT pg_advisory_lock`).
3. Identify top 5 longest-running blocking PIDs holding locks.

## 3. Safe Remediation Protocol
- **Action:** Propose `kill_db_connections` with specific target PIDs.
- **Safety Bounds:**
  - Maximum 5 PIDs per batch.
  - Never terminate PID ≤ 1 or internal PostgreSQL processes (`checkpointer`, `walwriter`).
  - Require SHA-256 cryptographic HITL approval token with 10-minute TTL.
- **Post-Execution Verification:**
  - Pool utilization must drop below 25% within 5.0 seconds.
  - Verification probes must report p99 latency ≤ 100ms.
  - Disarm auto-rollback upon 12 consecutive healthy probes.
