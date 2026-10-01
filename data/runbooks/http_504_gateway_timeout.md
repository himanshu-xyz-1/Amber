# Runbook: Microservice HTTP 504 Gateway Timeout Cascade

**Category:** Networking / Ingress  
**Severity Tier:** P1 / P2  
**Target Services:** `api-gateway`, `checkout-svc`, `ingress-controller`  

---

## 1. Incident Overview
Edge ingress or API gateway returns HTTP 504 Gateway Timeout to external clients. Client error rate spikes above 5% while p99 request latency exceeds 2,000ms.

## 2. Diagnostic Investigation
1. Execute `check_service_health` against upstream service `/health` and `/ready` endpoints.
2. Determine whether failure is caused by thread pool exhaustion in the gateway or downstream blocking database queries.
3. Correlate with downstream connection pool metrics via `query_db_metrics`.

## 3. Safe Remediation Protocol
- **Action:** If downstream database is saturated, mitigate database locks via `kill_db_connections`.
- If gateway worker thread deadlock is isolated, restart failing pod replica via `restart_service_pod`.
- **Verification:**
  - Automated probes verify HTTP 200 OK response with latency < 100ms within 10 seconds.
