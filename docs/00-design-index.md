# Amber — System Design Documentation Index

> **Amber**: Autonomous Incident Remediation & SRE Engine  
> **Status**: Phase 0 — Architecture & Design  
> **Last Updated**: 2026-10-01

---

## Reading Order

Start with the PRD, then follow the numbered sequence. Each document is self-contained but cross-references related docs.

---

## Documents

| # | Document | What It Covers |
|---|----------|----------------|
| — | [PRD.md](./PRD.md) | Product Requirements — problem statement, use cases, functional requirements, NFRs, safety specification, rollout phases |
| 01 | [System Architecture](./01-system-architecture.md) | Overall system topology, service decomposition, data flow, communication patterns, deployment topology, technology decisions, failure modes, security boundaries |
| 02 | [Database Design](./02-database-design.md) | PostgreSQL + pgvector + Redis selection rationale, full schema design with ER diagram, indexing strategy, connection pooling, migrations, Redis key patterns, backup & DR, data retention |
| 03 | [Security & Token Architecture](./03-security-and-token-architecture.md) | Zero-trust token model, inbound webhook HMAC-SHA256 verification, single-use HITL tokens (SHA-256 bound, 10m TTL), RBAC & service IAM, threat model |
| 04 | [HITL Permission & Verification](./04-hitl-permission-system.md) | Human-in-the-loop omni-channel dispatch (Slack/WhatsApp/Telegram), 1-click mobile approvals, automated health verification probes, instant auto-rollback |
| 05 | [Rate Limiter](./05-rate-limiter.md) | Algorithm selection (sliding window + token bucket), 3-layer rate limiting, Redis implementation design, rate limit tiers, webhook ingestion control, LLM API rate management, DDoS protection |
| 06 | [Scalability](./06-scalability.md) | Horizontal scaling strategy, auto-scaling triggers, bottleneck analysis, LLM API scaling & fallback chains, capacity planning (10/100/1000 incidents/day), caching, cost optimization |
| 07 | [Version Control](./07-version-control.md) | Monorepo strategy, trunk-based development, commit conventions, PR process, protected branches, CODEOWNERS, release management, environment mapping |
| 08 | [CI/CD Pipeline](./08-cicd-pipeline.md) | GitHub Actions pipeline, CI stages (lint/test/scan/build), CD stages (Docker/staging/production), Docker strategy, secret management, database migrations in deploy, rollback strategy |
| 09 | [API Management](./09-api-management.md) | API versioning (/api/v1), full endpoint map, request/response standards, cursor-based pagination, webhook security, OpenAPI spec, API gateway considerations, SDK roadmap |
| 10 | [Future Growth](./10-future-growth.md) | Product roadmap phases, multi-tenancy migration path, Kubernetes migration, observability stack, billing/monetization, plugin architecture, SOC 2 compliance, team scaling |
| 11 | [Privacy Policy & Data](./11-privacy-policy.md) | Data collection boundaries, zero-training guarantee, in-memory PII/secret scrubbing, LLM isolation, data residency, retention & GDPR purge |
| 12 | [Terms of Service & Security](./12-terms-of-service.md) | Subscription tiers (Observer, Autopilot, Partner) & usage limits, zero-hallucination safe execution guarantee, emergency kill-switch, SLA & liability |

---

## Quick Reference — Tech Stack Decisions

| Component | Technology | Justification Doc |
|-----------|-----------|-------------------|
| Backend API | FastAPI + Uvicorn | [01 Architecture](./01-system-architecture.md) |
| Agent Orchestration | LangGraph | [01 Architecture](./01-system-architecture.md) |
| Primary Database | PostgreSQL | [02 Database](./02-database-design.md) |
| Vector Store | pgvector (PG extension) | [02 Database](./02-database-design.md) |
| Event Queue / Cache | Redis Streams | [02 Database](./02-database-design.md) |
| Security & HITL | HMAC-SHA256 + Cryptographic Action Tokens | [03 Security](./03-security-and-token-architecture.md) |
| Rate Limiting | Redis sliding window + token bucket | [05 Rate Limiter](./05-rate-limiter.md) |
| CI/CD | GitHub Actions | [08 CI/CD](./08-cicd-pipeline.md) |
| Containers | Docker (multi-stage) | [08 CI/CD](./08-cicd-pipeline.md) |
| Frontend | Next.js / React | [01 Architecture](./01-system-architecture.md) |
| Observability | Langfuse (LLM) + Prometheus + Grafana (future) | [10 Future](./10-future-growth.md) |
| Billing | Stripe | [10 Future](./10-future-growth.md) |

---

## Phase Roadmap (from PRD)

```
Phase 0: Architecture & Safety Core (← YOU ARE HERE)
   │
Phase 1: Read-Only Diagnostics & Ingestion Buffer
   │
Phase 2: Shadow Mode (Propose only, execute nothing)
   │
Phase 3: Governed HITL Remediation
   │
Phase 4: Autonomous Safe Mitigations
   │
Phase 5: Multi-Tenant SaaS
```

---

## Decision Log

| Date | Decision | Rationale | Doc |
|------|----------|-----------|-----|
| 2026-10-01 | PostgreSQL over MongoDB/MySQL | ACID compliance, JSONB, pgvector extension, relational model fits incident hierarchy | [02](./02-database-design.md) |
| 2026-10-01 | pgvector over Pinecone/Weaviate | Same-DB simplicity, no sync overhead, hybrid queries with org_id filtering | [02](./02-database-design.md) |
| 2026-10-01 | JWT over session-based auth | Stateless API, VPC deployment (no Auth0 dependency), HITL token binding | [03](./03-authentication-system.md) |
| 2026-10-01 | Trunk-based dev over GitFlow | Small team (<5), fast iteration, less merge complexity | [07](./07-version-control.md) |
| 2026-10-01 | GitHub Actions over Jenkins/CircleCI | Native GitHub integration, free tier, marketplace actions | [08](./08-cicd-pipeline.md) |
| 2026-10-01 | URL-path API versioning over header | Simplicity, cacheability, explicit contract | [09](./09-api-management.md) |
| 2026-10-01 | Sliding Window + Token Bucket for rate limiting | Accuracy + burst tolerance, Redis-native | [05](./05-rate-limiter.md) |
