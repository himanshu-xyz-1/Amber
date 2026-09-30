# Amber System Design: Scalability Architecture

## 1. Scaling Philosophy

Amber embraces a "start simple, scale what bottlenecks" approach. The architecture is designed around stateless components communicating via Redis and PostgreSQL. The system starts as a tightly coupled set of containers (Single Node) and scales specific tiers horizontally based on independent resource demands.

## 2. Horizontal Scaling Strategy

*   **FastAPI Web Workers**: 
    *   Deployed via Gunicorn with Uvicorn worker classes.
    *   100% stateless. Scale horizontally behind a load balancer based on HTTP request volume.
*   **Redis**: 
    *   Starts with Redis Sentinel for High Availability (HA) and automatic failover.
    *   Migrates to Redis Cluster mode when stream memory or throughput exceeds single-node capacity.
*   **PostgreSQL**: 
    *   Primary instance for writes (incidents, execution state).
    *   Read replicas for read-heavy operations (dashboard queries, reporting).
    *   PgBouncer sits in front of all nodes for efficient connection pooling.
*   **LangGraph Task Workers**: 
    *   Celery or ARQ workers pull execution tasks from Redis.
    *   Scales independently of web workers since LLM operations are highly I/O bound and take seconds to complete.

## 3. Load Balancing

*   **Ingress**: Cloud Load Balancer (AWS ALB or Nginx) routes external webhook traffic to FastAPI workers.
*   **Health Checks**: `/health/liveness` (fast DB/Redis ping) and `/health/readiness` (deep dependency check).
*   **Sticky Sessions**: Not required. JWT authentication and execution state are fully externalized to Redis and PostgreSQL.

## 4. Auto-Scaling Triggers

*   **Web Workers**: Triggered by CPU > 70% or Webhook Request Rate > 400 req/sec per node (to safely handle the 500 alerts/sec NFR).
*   **LangGraph Workers**: Triggered by Queue Depth (e.g., > 100 pending execution steps) or Age of Oldest Task > 5 seconds.
*   **Database**: Storage > 80% utilization or Read IOPs consistently hitting provisioned limits.

## 5. Bottleneck Analysis

1.  **First Bottleneck - LLM API Rate Limits**: OpenAI/Anthropic token/minute or requests/minute limits will hit before infrastructure limits. (Mitigated by Fallback Chains).
2.  **Second Bottleneck - Redis Stream Consumers**: A single worker parsing 500 alerts/sec might lag. (Mitigated by Redis Consumer Groups sharing the load).
3.  **Third Bottleneck - DB Connections**: High concurrency hitting PostgreSQL. (Mitigated by PgBouncer transaction pooling).

## 6. LLM API Scaling

*   **Rate Limit Management**: Token bucket algorithm implemented in Redis to track consumption against vendor limits.
*   **Model Fallback Chains**: 
    *   Primary: GPT-4o (High accuracy, high cost, strict limits).
    *   Fallback 1: GPT-4o-mini (Faster, cheaper, higher limits - used if 4o rate limits or times out).
    *   Fallback 2: Local/Dedicated VLLM (Llama-3) for guaranteed availability during vendor outages.
*   **Request Queuing**: If all LLMs hit limits, Amber places the LangGraph execution node back onto the ARQ queue with exponential backoff.

## 7. Capacity Planning

*   **10 Incidents/Day**: 
    *   Web: 2x 2vCPU/4GB instances. 
    *   DB: 1x 4vCPU/16GB. 
    *   Redis: 1x 2vCPU/8GB.
*   **100 Incidents/Day** (Assuming ~50,000 raw alerts): 
    *   Web: 4x 4vCPU/8GB instances. 
    *   Workers: 8x 4vCPU/8GB instances (heavy LLM wait states). 
    *   DB: 8vCPU/32GB + 1 Replica.
*   **1,000 Incidents/Day** (Assuming ~500,000 raw alerts): 
    *   Web: 10x 8vCPU/16GB instances. 
    *   Workers: 20x 8vCPU/16GB instances. 
    *   DB: 16vCPU/64GB + 3 Replicas.

## 8. Database Scaling Path

1.  **Read Replicas**: Offload dashboard analytics, post-mortem generation, and audit logs.
2.  **Partitioning**: Monthly range partitions for the `alerts` table to keep index sizes in RAM.
3.  **Citus (Distributed SQL)**: If single-node write capacity is exhausted by incident state updates (unlikely for < 10,000 incidents/day, but the ultimate fallback).

## 9. Caching Strategy

*   **Runbook Embeddings**: Cache top 100 most frequently accessed runbook vectors in application memory to reduce pgvector load.
*   **Triage Decisions**: Cache known exact-match alert fingerprints to bypass the LLM triage node entirely (e.g., if a specific 'Disk Full' alert on Server X was triaged 5 mins ago, reuse the decision).
*   **Invalidation**: Webhook triggers invalidation of Runbook caches when content is updated.

## 10. Cost Optimization

*   **Spot Instances**: Used heavily for LangGraph ARQ/Celery workers since tasks are idempotent and can be re-run if a spot node is terminated.
*   **Reserved Instances**: Applied to PostgreSQL and Redis nodes which require 24/7 stability.
*   **LLM Cost Estimate**: 
    *   Average tokens per incident: ~10,000 (Triage + RAG + Guardrails).
    *   At GPT-4o pricing (~$5/1M input, $15/1M output), cost is roughly $0.10 - $0.20 per incident. 
    *   For 1,000 incidents/day = $150/day. High-volume triage steps are routed to GPT-4o-mini to reduce this by 80%.
