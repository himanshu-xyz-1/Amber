# Future Growth & Roadmap

This document outlines the strategic roadmap for **Amber**'s product evolution, scaling, and long-term vision as an Autonomous SRE Engine.

## 1. Product Roadmap Phases

- **Phase 0 (NOW): Architecture & Docs** — Establishing the foundation, design docs, and CI/CD pipelines.
- **Phase 1: Read-only Diagnostics + Ingestion** — Ingesting alerts and performing read-only investigations. Zero mutation capabilities.
- **Phase 2: Shadow Mode** — Amber proposes remediation plans and analyzes what *would* happen, but does not execute them.
- **Phase 3: HITL Remediation** — Human-In-The-Loop. Amber executes remediation steps only after explicit approval from an SRE.
- **Phase 4: Autonomous Safe Mitigations** — Amber autonomously executes pre-approved, safe, and reversible mitigations for known incident types.
- **Phase 5: Multi-tenant SaaS** — Transition from single-tenant VPC deployments to a fully managed multi-tenant SaaS platform.

## 2. Multi-Tenancy Path

Transitioning from a self-hosted single-tenant model to a SaaS model involves staged isolation:
- **Phase A (Current):** Single-tenant, self-hosted in customer VPC.
- **Phase B (Logical Isolation):** Row-level tenant isolation using an `org_id` foreign key in all tables.
- **Phase C (Schema Isolation):** Schema-per-tenant for stronger data separation.
- **Phase D (Physical Isolation):** Dedicated DB instances per tenant for enterprise customers.
- **Compute Isolation:** Moving from shared generic workers to tenant-isolated worker pools to prevent noisy neighbor issues and limit blast radius.

## 3. Kubernetes Migration

Currently, Amber uses Docker/Docker Compose. As we scale:
- **Triggers for Migration:** When managing standalone containers becomes complex, or when we transition to SaaS.
- **Implementation:** Introduce Helm charts for packaging the application.
- **Tenancy in K8s:** Utilize Kubernetes namespaces to isolate tenant workloads (Namespace-per-tenant pattern).

## 4. Observability Stack

Amber must be highly observable to monitor its own LLM agents and system health:
- **Metrics:** Prometheus for scraping system and agent metrics.
- **Dashboards:** Grafana for visualization.
- **Logging:** Structured logging using `structlog` (JSON format) to easily query logs.
- **Tracing:** OpenTelemetry for distributed tracing across FastAPI, LangGraph, and background workers.

## 5. Billing & Monetization

- **Integration:** Stripe for processing payments and managing subscriptions.
- **Pricing Model Evolution:**
  - Early stage: Per-seat (SRE user) or flat platform fee.
  - Growth stage: Value-based pricing (per-incident resolved, per-integration connected).
- **Metering:** Implement usage metering for API calls and LLM token consumption.

## 6. Plugin Architecture

To support a wide ecosystem without bloating the core engine:
- **Alert Sources:** Standardized webhooks to add Datadog, PagerDuty, Prometheus alerts.
- **Diagnostic Tools:** A modular Python interface allowing customers to inject custom scripts (e.g., specific AWS CLI checks).
- **LLM Providers:** Abstracted via LangChain to allow hot-swapping between OpenAI, Anthropic, or self-hosted open-source models based on data privacy needs.

## 7. Compliance Roadmap

Enterprise adoption requires strict compliance:
- **SOC 2 Type II:** Establish audit trails, access controls, and security policies early.
- **GDPR:** Implement data deletion (right to be forgotten) and localized data storage if operating in the EU.
- **Data Security:** Ensure encryption at rest (AWS KMS) and in transit (TLS 1.3).

## 8. Team Scaling

- **< 5 Engineers (Now):** Full-stack engineers, high autonomy, monolithic repo.
- **10 Engineers:** Specialization begins (Backend/AI vs Frontend vs Platform). Introduction of robust on-call rotations.
- **25+ Engineers:** Formal domain teams, designated platform team, stricter ownership boundaries, and potential service extraction if the monolith becomes a bottleneck.

## 9. International Expansion

- **Multi-Region:** Deploying instances in EU (Frankfurt) and APAC (Tokyo) to reduce latency and comply with local data residency laws.
- **Localization:** UI translations and timezone-aware incident reporting.

## 10. Exit Strategy / Long-term Vision

Amber's goal is to become the default AI-driven operations layer for modern software companies.
- **B2B SaaS Metrics:** Target high Net Retention Rate (NRR > 120%) by continually adding value through new integrations, and maintain a strong LTV:CAC ratio.
- **Positioning:** Prime acquisition target for massive observability platforms (e.g., Datadog, New Relic) or cloud providers looking to natively integrate AIOps.
