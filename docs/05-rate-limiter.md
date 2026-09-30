# Rate Limiting & Traffic Control

## 1. Why Rate Limiting Matters for Amber

As an Autonomous Incident Remediation & SRE Engine, Amber operates at the intersection of unpredictable alert streams and expensive, rate-limited LLM APIs. Rate limiting is critical for:

- **Alert Storm Protection:** Preventing cascading failures when a systemic outage generates thousands of redundant alerts per second.
- **LLM API Cost & Quota Control:** Safeguarding against runaway LLM inference costs and exhausting upstream API quotas.
- **Abuse Prevention:** Protecting the REST API from malicious actors or misconfigured internal scripts.
- **Fair Usage:** Ensuring multi-tenant fairness so one noisy organization doesn't degrade performance for others.

## 2. Algorithm Selection

Amber requires different rate-limiting algorithms depending on the use case.

| Algorithm | Pros | Cons | Amber Use Case |
|-----------|------|------|----------------|
| **Token Bucket** | Allows bursts, memory efficient | Requires concurrent safe updates | **Webhook Ingestion** (allows short bursts of alerts while enforcing sustained limits) |
| **Sliding Window Counter** | Accurate, memory efficient (stores window counters, not logs) | Slight loss of precision at window boundaries | **API Endpoints & Dashboard** (smooth rate enforcement) |
| **Sliding Window Log** | 100% precise | High memory usage, expensive to compute | Not used |
| **Fixed Window** | Simplest, lowest memory | Bursts at window edges (2x limit possible) | Not used |
| **Leaky Bucket** | Smooths out bursts entirely | Delays processing (queueing) | **LLM API Requests** (strict adherence to upstream limits) |

**Decision:**
- **Token Bucket** for webhook ingestion to tolerate sudden alert spikes.
- **Sliding Window Counter** for standard REST API endpoints (accuracy + efficiency).
- **Leaky Bucket (Queueing)** for downstream LLM API calls.

## 3. Rate Limiting Layers

Amber implements defense-in-depth through multi-layered rate limiting:

- **Layer 1: Global (Infrastructure/WAF Level)**
  - Handled by Cloudflare/AWS WAF and Nginx.
  - IP-based limits, connection limits, and basic volumetric DDoS protection.
- **Layer 2: Application (FastAPI Middleware)**
  - Enforced per-tenant (`org_id`), per-user, or per-API-key.
  - Granular control over specific endpoints (e.g., `/api/v1/incidents/approve`).
- **Layer 3: Downstream (LLM API Integration)**
  - Managed within LangGraph / worker nodes.
  - Enforces per-model RPM (Requests Per Minute) and TPM (Tokens Per Minute).

## 4. Redis Implementation Design

Rate limiting across multiple FastAPI workers requires a centralized, fast datastore. We use Redis for atomic operations.

**Key Patterns:**
- `rl:org:{org_id}:api:{endpoint}:{window_timestamp}`
- `rl:ip:{ip_address}:{window_timestamp}`
- `rl:webhook:{source_id}:{window_timestamp}`

**Lua Script Execution:**
To prevent race conditions, increments and TTL sets are executed atomically via a Redis Lua script.

```lua
-- Sliding Window Counter simplified atomic increment
local current_key = KEYS[1]
local previous_key = KEYS[2]
local limit = tonumber(ARGV[1])
local current_time = tonumber(ARGV[2])

local current_count = tonumber(redis.call('get', current_key) or "0")
local previous_count = tonumber(redis.call('get', previous_key) or "0")

-- Calculate weighted count based on overlap
local overlap_ratio = 1 - (current_time % 60) / 60
local estimated_count = (previous_count * overlap_ratio) + current_count

if estimated_count >= limit then
    return 0 -- Rate limited
end

redis.call('incr', current_key)
redis.call('expire', current_key, 120)
return 1 -- Allowed
```

## 5. Rate Limit Tiers

Different limits apply based on the organization's subscription plan.

- **Free Tier:** 100 API req/min, 50 webhooks/sec, 10 concurrent LLM ops.
- **Pro Tier:** 1,000 API req/min, 500 webhooks/sec, 50 concurrent LLM ops.
- **Enterprise Tier:** Custom API req/min, 2,000+ webhooks/sec, dedicated LLM quota.

## 6. Webhook Ingestion Rate Control

Amber must sustain 500 alerts/sec with zero packet loss.
- **Endpoint:** POST `/api/v1/webhooks/{source}`
- **Mechanism:** The FastAPI endpoint does minimal work. It authenticates the request, validates the payload size, and immediately pushes it to a **Redis Stream**.
- **Backpressure:** If the webhook rate exceeds the token bucket limit, Amber responds with `429 Too Many Requests` to the provider (PagerDuty/Datadog), relying on their native webhook retry mechanisms with exponential backoff.

## 7. LLM API Rate Management

LLM providers (OpenAI, Anthropic) have strict RPM and TPM limits.
- **Token Bucket per Model:** Amber tracks estimated token usage per provider.
- **Fallback Chain:** If OpenAI GPT-4o hits a rate limit, the LangGraph agent automatically falls back to Anthropic Claude 3.5 Sonnet.
- **Cost Caps:** Enforced at the `org_id` level. If an org exceeds its daily budget, remediation transitions to "Read-Only/Suggest" mode without executing autonomous actions.

## 8. Response Headers

All API responses include standard rate limit headers to allow clients to throttle themselves.

- `X-RateLimit-Limit`: The maximum number of requests allowed in the current window.
- `X-RateLimit-Remaining`: The number of requests remaining in the current window.
- `X-RateLimit-Reset`: The Unix timestamp when the limits will reset.
- `Retry-After`: (On `429` responses) The number of seconds the client should wait before retrying.

## 9. DDoS Protection

- **Connection Limits:** Nginx limits concurrent connections per IP.
- **Payload Size Limits:** FastAPI rejects payloads > 1MB at the middleware level to prevent memory exhaustion.
- **Geographic Blocking:** Optional via WAF for Enterprise customers with data sovereignty requirements.
- **WAF Integration:** Cloudflare in front of the API for layer 7 protection.

## 10. Monitoring & Alerting

- **Metrics:** Rate limit hits are tracked as Prometheus counters (`amber_rate_limit_exceeded_total{org_id, endpoint}`).
- **Dashboards:** Grafana dashboards visualize rate limit consumption vs. capacity per organization.
- **Alerting:** If an organization consistently hits > 90% of its rate limit capacity, a notification is sent to the Amber Customer Success team (or the org admin) to discuss upgrading tiers or investigating potential misconfigurations.
