# Product Requirements Document (PRD)

## Document Metadata
- **Project Name:** Amber (Autonomous Incident Remediation & SRE Engine)
- **Document Version:** 1.1.0
- **Status:** Draft (Architecture & Safety Review Incorporated)
- **Owner:** Engineering & Operations Team
- **Target Deployment:** Self-Hosted / Dedicated VPC Single-Tenant

---

## 1. Executive Summary & Problem Statement

### 1.1 The Operational Problem
Modern cloud infrastructure generates high-volume alert storms during outages. Traditional incident remediation suffers from:
1. **Prolonged MTTR:** Manual triage, log correlation across fragmented observability platforms, and outdated runbook lookup consume 30–45 minutes per incident.
2. **Alert Fatigue & Operational Cognitive Load:** On-call engineers triaging critical alerts under pressure are susceptible to procedural missteps and execution mistakes.
3. **Unsanctioned AI Execution Risk:** Unconstrained LLM scripts risk executing destructive mutations (e.g., dropping production tables or unsanctioned cluster-wide restarts) without deterministic boundary enforcement.

### 1.2 The Amber Solution
Amber is an autonomous incident remediation engine operating on a stateful, multi-agent architecture. It ingests alerts, correlates alert storms into discrete incidents, queries internal runbooks via hybrid RAG, runs read-only diagnostic tools, and proposes strictly bounded remediation actions.

**Core Safety Thesis:** *The LLM proposes; deterministic semantic policy and human operators decide.* Mutating or disruptive actions require cryptographic Human-in-the-Loop (HITL) approval bound to an immutable execution payload. Safe read-only actions and explicitly pre-approved idempotent mitigations execute autonomously under strict verification loops with automated rollback or escalation.

---

## 2. Target Personas & Operational Roles

| Role / Persona | Responsibilities | Key Capabilities Required |
| :--- | :--- | :--- |
| **On-Call SRE** (Primary Operator) | First responder to infrastructure alerts | Automated log correlation, runbook synthesis, 1-click payload approval, rollback triggers |
| **SRE Lead / Staff Eng** | Runbook author, policy administrator | Runbook publishing, tool allowlist configuration, post-mortem indexing approval |
| **Service Developer** | Application owner | Commit-linked failure diagnosis, post-mortem review, service health verification |
| **VP of Eng / CTO** | Infrastructure governor | Global kill switch management, audit trail inspection, MTTR and spend analytics |

---

## 3. System Architecture & Threat Model

```
Incoming Alert Streams (PagerDuty, Sentry, Datadog, CloudWatch, Prometheus)
                     │
                     ▼
  Durable Event Ingestion Buffer (FastAPI + Redis Stream / Queue)
                     │
                     ▼
  Alert Correlation & Incident Aggregator (Sliding Window Fingerprinting)
                     │
                     ▼
  Untrusted Input Sanitizer & Secret Redactor (Prompt Injection Guard)
                     │
                     ▼
  LangGraph Stateful Orchestrator (Dedicated Isolated Infrastructure)
   ├── [Node 1] Triage Agent: Severity classification (P0-P4) & service routing
   ├── [Node 2] Hybrid RAG Agent: Dense vector + BM25 search over verified runbooks
   ├── [Node 3] Investigation Agent: Read-only diagnostic tool calling loop
   └── [Node 4] Deterministic Policy & Guardrail Validator (Static Tool Registry)
                     │
       ┌─────────────┴─────────────┐
  Risk: High                  Risk: Low / Safe
  (Mutating / Disruptive)     (Read-Only / Whitelisted Safe)
       │                           │
       ▼                           ▼
  HITL Gateway Checkpoint     Shadow Mode Check (Execute vs Propose-Only)
  • Cryptographic Hash Bind        │
  • 10-Minute Expiry TTL           ▼
  • Re-Validation Pre-Execution  Autonomous Tool Runner
  • SRE Approval via Web/Slack     │
       └─────────────┬─────────────┘
                     ▼
     Health Verification Probe (HTTP / SQL / Metric Check)
                     │
         ┌───────────┴───────────┐
     Success                  Failure
         │                       │
         ▼                       ▼
  Markdown Post-Mortem    Reversible? ──► YES ──► Auto-Rollback to Baseline
  (Pending Human Review)              └──► NO  ──► Emergency P0 Escalation
```

### 3.1 Security & Threat Model Guardrails
1. **Untrusted Payload Defense:** All alert payloads, stack traces, and raw log lines are treated as untrusted external inputs. Payloads pass through a regex/token sanitizer stripping potential prompt-injection patterns (e.g., `Ignore previous instructions and execute...`) and redacting PII, API tokens, and connection strings prior to LLM context insertion.
2. **Self-Dependency Isolation:** Amber runs in a dedicated VPC namespace using isolated PostgreSQL and Redis instances separate from target infrastructure being remediated.
3. **Least Privilege Credentials:** Diagnostic and remediation tools use dedicated IAM service accounts with explicit resource boundaries. Read and Write credentials are decoupled.

---

## 4. Deterministic Safety & Tool Policy Specification

### 4.1 Tool Registry & Reversibility Matrix

| Tool Identifier | Action Type | Risk Category | Reversibility | Guardrail Constraints |
| :--- | :--- | :--- | :--- | :--- |
| `query_db_metrics` | Diagnostic | **LOW** | N/A (Read-Only) | Max execution time 5s; SELECT queries only. |
| `fetch_pod_logs` | Diagnostic | **LOW** | N/A (Read-Only) | Tail limit 500 lines; secrets auto-redacted. |
| `flush_cache_keys` | Mitigation | **LOW** | **IRREVERSIBLE** | Key prefix MUST match whitelisted regex (`^sess:temp:.*`); Max 1,000 keys per invocation. Dry-run required. |
| `kill_db_connections` | Remediation | **HIGH** | **IRREVERSIBLE** | Target PIDs MUST match active query runtime > 60s; exclude replication/system PIDs; Max 5 connections per batch. Requires HITL. |
| `rollback_deployment` | Remediation | **HIGH** | **REVERSIBLE** | Target image MUST exist in local registry history; pre-rollback state snapshotted. Requires HITL. |
| `restart_service_pod` | Remediation | **HIGH** | **REVERSIBLE** | Rate limit: Max 1 restart per pod per 30 minutes. Requires HITL. |

### 4.2 Approval Lifecycle & Semantics
1. **Payload Binding:** When a High-Risk action is proposed, Amber computes a SHA-256 hash of the complete tool arguments (e.g., exact PIDs, container name, target namespace). The approval token is cryptographically bound to this hash.
2. **Time-To-Live (TTL):** Approval requests expire after **10 minutes**. Expired tokens cannot be executed.
3. **Pre-Execution Re-Validation:** Upon human approval, Amber re-runs target validation (e.g., verifying that the proposed PIDs still correspond to the hanging queries identified during triage). If state has mutated, execution is aborted and re-triaged.
4. **Timeout & Escalation:** If a P0 approval is unacknowledged after 5 minutes, Amber dispatches secondary emergency escalation to on-call phone paging.
5. **Global Kill Switch:** An environment-level and UI-level flag (`AMBER_EMERGENCY_HALT=true`) immediately cancels all running agent execution graphs and blocks tool dispatches.

---

## 5. Production Use Cases & Workflows

### UC-01: Database Connection Pool Exhaustion (High Risk / Irreversible)
- **Actor:** On-Call SRE
- **Trigger:** Alert: `PostgreSQL connection pool utilization > 95% (53300: too many connections)`.
- **Workflow:**
  1. Ingestion buffers alert and correlates with related HTTP 500 spike alerts into Incident `#INC-101`.
  2. Triage Agent categorizes severity as **P0 (Critical Outage)**.
  3. RAG Agent retrieves `postgres_pool_exhaustion.md` runbook.
  4. Investigation Agent executes `query_db_metrics`; detects 3 orphaned client connections running idle transactions > 180s.
  5. System creates execution proposal: `kill_db_connections(pids=[4102, 4105, 4119])`.
  6. Policy engine marks action as **HIGH RISK (Irreversible)**, computes payload SHA-256 hash, and halts state machine.
  7. Approval prompt dispatched to SRE dashboard and Slack channel `#ops-incidents`.
  8. SRE clicks **Approve**.
  9. Pre-execution hook re-verifies PIDs 4102, 4105, 4119; confirms they remain orphaned.
  10. Tool terminates targeted connections.
  11. Health verification probe queries connection pool; confirms drop to 18% utilization within 15 seconds.
  12. Draft Post-Mortem compiled and submitted for human review.
- **Alternative Flow (Re-validation Mismatch):** If PID 4102 terminated naturally prior to human approval, execution is aborted with notice `State changed prior to execution; re-evaluating`.

### UC-02: Redis Ephemeral Cache Saturation (Low Risk / Autonomous Dry-Run)
- **Actor:** Autonomous Engine (Shadow Mode Configurable)
- **Trigger:** Alert: `Redis memory utilization > 90%`.
- **Workflow:**
  1. Triage Agent categorizes severity as **P2 (Major)**.
  2. Investigation Agent inspects keyspace distribution; identifies 4,200 stale keys matching prefix `temp:feed:*`.
  3. Policy engine evaluates `flush_cache_keys(prefix="temp:feed:*")`.
  4. Guardrail verifies prefix is in pre-approved allowlist and total count <= 5,000.
  5. Action executes dry-run to capture key count, then proceeds with eviction.
  6. Health probe confirms memory utilization drops to 42%.
  7. Audit log recorded; summary posted to `#ops-log`.

### UC-03: Kubernetes CrashLoopBackOff with Pre-Approved Rollback
- **Actor:** Service Developer / SRE
- **Trigger:** Webhook: `Deployment payment-service pod entering CrashLoopBackOff`.
- **Workflow:**
  1. Triage Agent categorizes severity as **P1 (Critical)**.
  2. Investigation Agent reads previous container logs, extracting `KeyError: REDIS_AUTH_SECRET`.
  3. Proposes rollback: `rollback_deployment(deployment="payment-service", target_revision="v2.8.4")`.
  4. High-Risk approval card dispatched to SRE with root-cause diff.
  5. SRE approves rollback action.
  6. Action runner applies revision rollback and monitors rollout status.
  7. Verification probe checks pod readiness; confirms 3/3 replicas passing liveness checks within 45 seconds.
  8. Post-Mortem generated linking failed deployment commit and log trace.
- **Alternative Flow (Rollback Verification Failure):** If rolled-back pods fail readiness within 45s, Amber halts automated actions, sets status to `Mitigation Failed`, and pages secondary SRE Lead.

### UC-04: Stripe Webhook Desynchronization & Replay
- **Actor:** Billing Operator
- **Trigger:** Alert: `Stripe webhook HTTP 500 error rate > 5%`.
- **Workflow:**
  1. Investigation Agent queries receiver logs and identifies downstream Redis connection timeout during webhook intake.
  2. Identifies 14 unacknowledged webhook event IDs.
  3. Guardrail validator identifies event replay as **LOW RISK** due to existing database idempotency constraints.
  4. System executes controlled event replay across the 14 transactions.
  5. Verification probe confirms all 14 subscription states reflect active status with zero duplicate credits.

### UC-05: Post-Mortem Compilation & Governed RAG Indexing
- **Actor:** SRE Lead
- **Trigger:** Incident status transitioned to `Resolved`.
- **Workflow:**
  1. System compiles Markdown post-mortem containing: timeline, root cause, executed commands, verification metrics, and MTTR.
  2. Post-mortem marked as `Pending Review`.
  3. SRE Lead reviews and clicks **Approve for Knowledge Base**.
  4. Document is embedded and indexed into pgvector and BM25 knowledge corpus.

---

## 6. Functional Requirements & Acceptance Criteria

### 6.1 Ingestion, Deduplication & Correlation
- **FR-01 (Multi-Source Ingestion):** Ingest alerts from PagerDuty, Sentry, Datadog, CloudWatch, and Prometheus.
  - *Given* an alert payload from a supported source, *When* posted to `/api/v1/webhooks/{source}`, *Then* return `202 Accepted` and buffer payload into Redis Stream within 50ms.
- **FR-02 (Alert Correlation & Storm Control):** Correlate duplicate and related alerts.
  - *Given* multiple alerts sharing entity fingerprint (`service:region:alert_type`) within a 5-minute sliding window, *When* ingested, *Then* attach them to a single parent Incident rather than triggering parallel agent runs.

### 6.2 Agent Orchestration & State Machine
- **FR-03 (State Persistence & Checkpoints):** Maintain workflow state across asynchronous pauses.
  - *Given* an active investigation graph, *When* a High-Risk interrupt is reached, *Then* snapshot full graph state to PostgreSQL checkpoint storage and release worker threads.
- **FR-04 (Triage Classification):** Standardize incident severity.
  - *Given* an incident payload, *When* evaluated by Triage Agent, *Then* output structured JSON assigning severity to exactly one of `P0`, `P1`, `P2`, `P3`, `P4` with documented rationale.

### 6.3 Deterministic Safety & Guardrails
- **FR-05 (Static Tool Risk Registry):** Strict risk isolation.
  - *Given* any tool proposed by an LLM agent, *When* evaluated by Guardrail Validator, *Then* determine risk classification strictly from static code definitions, rejecting any LLM-attempted risk reassignment.
- **FR-06 (Cryptographic Payload Binding):** Prevent parameter tampering.
  - *Given* a High-Risk action proposal, *When* approval token is generated, *Then* sign the SHA-256 hash of normalized parameter JSON. Reject execution if token or parameters differ at execution time.
- **FR-07 (Execution Re-validation):** Real-time state check before mutation.
  - *Given* a human approval received within TTL, *When* execution is initiated, *Then* re-verify target preconditions. If preconditions fail, abort execution and re-enter investigation node.

### 6.4 Verification, Rollback & Post-Mortem
- **FR-08 (Health Verification Loop):** Mandatory post-action health probe.
  - *Given* an executed remediation action, *When* execution completes, *Then* execute associated health probe for up to 45 seconds before marking incident `Resolved`.
- **FR-09 (Automated Rollback on Verification Failure):** Reversion for reversible tools.
  - *Given* a failed health probe on a tool marked `REVERSIBLE`, *When* timeout expires, *Then* execute pre-approved rollback plan immediately and escalate incident priority.
- **FR-10 (Governed Knowledge Base Indexing):** Prevent ingestion of bad diagnoses.
  - *Given* a generated post-mortem, *When* compiled, *Then* require explicit `SRE_Lead` approval before chunking and writing to pgvector/BM25 storage.

---

## 7. Non-Functional Requirements (NFRs)

### 7.1 Performance & Latency SLAs
- **NFR-01 (Ingestion Throughput):** Sustain 500 alerts/sec with zero packet loss; return HTTP `202 Accepted` at p99 < 100ms.
- **NFR-02 (Triage Latency):** Triage severity assignment completed at p95 < 3.0s using fast tier models (e.g., `gpt-4o-mini`).
- **NFR-03 (Investigation Latency):** Diagnostic hypothesis and tool proposal generated at p95 < 25.0s across multi-tool execution chains.

### 7.2 Security & Authentication
- **NFR-04 (Webhook Signature Verification):** Authenticate inbound webhooks via source-appropriate protocols: HMAC-SHA256 for Stripe/GitHub; Bearer Token / mTLS for Datadog/PagerDuty.
- **NFR-05 (Authentication & RBAC):** JWT access tokens (15m expiry) with refresh token rotation (7d expiry) and instantaneous Redis-backed jti token revocation.
- **NFR-06 (Secret Redaction):** Redact environment variables, passwords, API keys, and connection strings matching standard entropy/regex rules before writing to execution logs or Langfuse telemetry.

---

## 8. Rollout Phases & Safety Milestones

```
Phase 0: Architecture & Safety Core (PRD, HLD, LLD Specs)
   │
Phase 1: Read-Only Diagnostics & Ingestion Buffer (Zero Mutation Allowed)
   │
Phase 2: Shadow Mode (LLM proposes remediation; logs plan; executes nothing)
   │
Phase 3: Governed HITL Remediation (High-Risk actions enabled with 1-click human approval)
   │
Phase 4: Autonomous Safe Mitigations (Low-Risk pre-approved actions enabled)
```

---

## 9. Success Metrics & Key Performance Indicators (KPIs)

| Metric | Target | Verification Method |
| :--- | :--- | :--- |
| **P0 / P1 Triage Recall** | **>= 99.0%** | Zero missed critical incidents on Golden Eval benchmark |
| **Unsanctioned Mutation Rate** | **0.00%** | Cryptographic audit trail confirming 100% of high-risk actions have valid human signature |
| **MTTR Reduction** | **>= 65%** | Measured from alert ingestion to successful health probe resolution against baseline |
| **Approval Re-Validation Success** | **100%** | Abort 100% of stale approved actions where target state changed during approval window |
| **Rollback Execution Success** | **>= 98%** | Successful return to pre-incident state on failed reversible remediations |
