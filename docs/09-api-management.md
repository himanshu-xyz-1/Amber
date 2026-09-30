# API Management & Design

## 1. API Design Philosophy

Amber's API is designed to be **RESTful, resource-oriented, predictable, and consistent**.
- **Resources:** URIs represent nouns (resources), not verbs (actions), with the exception of specific workflow state changes (e.g., `/approve`).
- **Predictability:** Standard HTTP methods (GET, POST, PUT, PATCH, DELETE) map to standard CRUD operations.
- **Consistency:** Uniform response structures, pagination patterns, and error formatting across all endpoints.

## 2. Versioning Strategy

**Strategy:** URL path versioning (e.g., `/api/v1/incidents`).

**Why URL versioning?**
- **Simplicity & Visibility:** The version is explicit in the route, making it easy to see in logs and metrics.
- **Cacheability:** Proxies and CDNs treat different versions as distinct URLs natively.
- **Routing:** Simplifies routing at the API Gateway or Nginx level.

**Deprecation Policy:**
- Amber supports the current version (N) and the previous major version (N-1).
- When a version is deprecated, a 6-month sunset window is announced via email and the `Deprecation` HTTP header.

## 3. API Structure

### Webhooks
- `POST /api/v1/webhooks/{source}`: Ingest alerts from PagerDuty, Datadog, etc. (Returns `202 Accepted`).

### Incidents
- `GET /api/v1/incidents`: List incidents (supports filtering and cursor pagination).
- `POST /api/v1/incidents`: Manually create an incident.
- `GET /api/v1/incidents/{id}`: Get details of a specific incident.
- `PATCH /api/v1/incidents/{id}`: Update incident status/severity.
- `GET /api/v1/incidents/{id}/timeline`: Retrieve the execution timeline (LangGraph state steps).
- `POST /api/v1/incidents/{id}/approve`: HITL (Human-in-the-Loop) approval for pending actions.

### Runbooks & Tools
- `GET /api/v1/runbooks`: List available runbooks.
- `POST /api/v1/runbooks`: Create a new runbook.
- `GET /api/v1/tools`: List registered tools and their risk matrix (Safe/Destructive).

### Organization & Users
- `GET /api/v1/users`: List users in the org.
- `POST /api/v1/users`: Invite a user.
- `GET /api/v1/orgs/current`: Get current organization details and usage.

### Analytics & Settings
- `GET /api/v1/analytics`: Retrieve MTTR and incident resolution statistics.
- `GET /api/v1/settings`: Retrieve system config.
- `POST /api/v1/settings/killswitch`: Emergency stop all autonomous actions.

### Real-time
- `WS /ws/incidents`: WebSocket for real-time incident timeline updates and HITL prompts.

## 4. Request/Response Standards

- **Validation:** All incoming payloads are strictly validated using **Pydantic >= 2.7.4** models.
- **Data Format:** JSON exclusively (`Content-Type: application/json`).
- **HTTP Status Codes:**
  - `200 OK`: Successful read/update.
  - `201 Created`: Successful creation.
  - `202 Accepted`: Async processing started (used for webhooks).
  - `400 Bad Request`: Validation error.
  - `401 Unauthorized`: Missing/invalid token.
  - `403 Forbidden`: Insufficient permissions.
  - `404 Not Found`: Resource does not exist.
  - `429 Too Many Requests`: Rate limit exceeded.

**Error Response Format:**
```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid field format",
    "details": [{"loc": ["body", "severity"], "msg": "value must be 'high', 'medium', or 'low'"}],
    "request_id": "req_12345abcde"
  }
}
```

## 5. Pagination

- **Cursor-based Pagination:** Used for high-velocity data like `/api/v1/incidents` and alerts.
  - *Why:* Prevents skipped or duplicated records when items are added during pagination. Consistent with streaming data.
  - *Params:* `?limit=50&cursor=eyJpZCI6MTIzNH0=`
- **Offset/Page-based Pagination:** Used for slow-moving data like `/api/v1/runbooks` or `/api/v1/users`.
  - *Params:* `?page=1&size=20`

## 6. Webhook Security

Given Amber ingests data from external systems, webhook endpoints must be highly secure.

- **Signature Verification:**
  - Stripe/GitHub/Custom: Enforced via `HMAC-SHA256` payload signatures.
  - Datadog/PagerDuty: Enforced via static Bearer tokens or specific webhook secrets.
- **Timestamp Validation:** Payloads must include a timestamp, and Amber rejects payloads with > 5-minute clock skew to prevent replay attacks.
- **Idempotency:** Webhook processing relies on external IDs (e.g., PagerDuty incident ID) to ensure duplicate webhook deliveries do not trigger duplicate LangGraph remediation graphs.

## 7. OpenAPI / Swagger

- **Auto-generation:** Leveraging FastAPI, the OpenAPI 3.1 specification is automatically generated.
- **Documentation:** Hosted at `/docs` (Swagger UI) and `/redoc` (ReDoc).
- **Export:** The versioned spec is exported during CI/CD to update developer documentation portals and generate client SDKs.

## 8. API Gateway Considerations

- **Current State (V1):** FastAPI handles routing, JWT validation, and rate limiting via middleware. Nginx acts as the reverse proxy.
- **Future State:** As Amber scales to multi-region deployments or requires complex API monetization (Stripe integration per endpoint), we will evaluate dedicated API Gateways like Kong or API6.

## 9. SDK & Client Libraries Roadmap

1. **Python SDK:** Official `amber-python` library for seamless integration into customer's internal scripts and custom LangChain/LangGraph flows.
2. **TypeScript SDK:** For internal dashboard usage and customer portal integrations.
3. **Amber CLI:** A command-line tool (`amberctl`) for managing runbooks and triggering incidents from terminal environments.

## 10. API Changelog & Migration Guide

- **Changelog:** Published via the Amber Developer Portal.
- **Breaking Changes:** Require a major version bump (`/api/v2`). Minor additions (new fields) are added to the existing version.
- **Communication:** Registered developers receive proactive emails 30 days before deprecations take effect.
