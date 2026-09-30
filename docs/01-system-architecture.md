# Amber System Architecture

## 1. System Overview

Amber is an Autonomous Incident Remediation & Site Reliability Engineering (SRE) Engine designed to alleviate alert fatigue and reduce Mean Time To Resolution (MTTR) by orchestrating autonomous investigation, triage, and targeted remediation. The core thesis of Amber is **"LLM proposes, deterministic policy decides."** While Large Language Models (LLMs) drive the non-deterministic reasoning (analyzing logs, hypothesizing root causes, formulating remediation steps), all actions are gated by strict, deterministic, policy-based guardrails (via rule engines, static analysis, or Human-in-the-Loop approvals).

Amber acts as an intelligent overlay on top of existing observability tools, executing read-only diagnostics autonomously, and securely orchestrating remediation steps across the infrastructure.

## 2. High-Level Architecture Diagram

```text
                                +-----------------------------------+
                                |                                   |
                                |       AMBER FRONTEND (Next.js)    |
                                |  Dashboards, Config, HITL Gateway |
                                |                                   |
                                +--------+-------------+------------+
                                         |             | WebSocket
                                         | REST        |
+-------------------+           +--------v-------------v------------+       +-------------------+
| OBSERVABILITY     | Webhooks  |                                   | Slack | NOTIFICATION      |
| PagerDuty, Sentry,+----------->      API GATEWAY (FastAPI)        <-------> Slack/Teams Bots  |
| Datadog, Prom.    |           |                                   |       |                   |
+-------------------+           +------------------+----------------+       +-------------------+
                                                   |
                                +------------------v----------------+
                                |  WEBHOOK INGESTION & EVENT QUEUE  |
                                |          (Redis Streams)          |
                                +------------------+----------------+
                                                   | Async Poll
                                +------------------v----------------+
                                |    ALERT CORRELATION ENGINE       |
                                | (Sliding Window Fingerprinting)   |
                                +------------------+----------------+
                                                   |
                                +------------------v----------------+       +-------------------+
                                |     AGENT ORCHESTRATION SERVICE   |       | RAG KNOWLEDGE BASE|
                                |      (LangGraph State Machine)    <-------> (PostgreSQL +     |
                                |                                   |       |  pgvector & BM25) |
                                |  [Triage] -> [Investigation]      |       +-------------------+
                                |       -> [Guardrail] -> [Remediate|
                                +------------------+----------------+
                                                   |
                                +------------------v----------------+
                                |     TOOL EXECUTION RUNTIME &      |
                                |        HITL APPROVAL GATEWAY      |
                                | (SHA-256 bound execution blocks)  |
                                +------------------+----------------+
                                                   |
                                +------------------v----------------+
                                |      TARGET INFRASTRUCTURE        |
                                |   (AWS/GCP, K8s, DBs, APIs)       |
                                +-----------------------------------+
```

## 3. Service Decomposition

### API Gateway Layer (FastAPI)
The central entry point for all synchronous HTTP traffic. It handles webhook ingestion, REST API calls from the frontend, authentication (JWT + bcrypt), and rate limiting. Built with FastAPI for high performance and native async support.

### Webhook Ingestion Service
Buffers incoming alerts rapidly to meet the <100ms p99 latency requirement. Writes raw webhook payloads directly to Redis Streams, acting as a shock absorber during alert storms.

### Alert Correlation Engine
Processes events from Redis Streams. Uses sliding window fingerprinting (based on service tags, error codes, and time locality) to group related alerts into a single incident entity. Reduces noise and prevents the orchestration engine from being overwhelmed.

### Agent Orchestration Service (LangGraph State Machine)
The core intelligence layer. Uses LangGraph to manage stateful, multi-agent workflows.
- **Triage Agent:** Classifies severity (P0-P4) within <3s.
- **Hybrid RAG Agent:** Interacts with the knowledge service to retrieve relevant runbooks and past post-mortems.
- **Investigation Agent:** Executes read-only diagnostic tools (fetching logs, querying metrics) within <25s.
- **Guardrail Validator:** Statically analyzes proposed remediation actions against pre-defined safety policies.

### RAG Knowledge Service (pgvector + BM25)
Hybrid search engine backing the Hybrid RAG Agent. Combines dense vector search (pgvector for semantic matching of past incident post-mortems and runbooks) with sparse keyword search (BM25 for exact error codes or trace IDs).

### Tool Execution Runtime
A sandboxed environment for executing diagnostic and remediation scripts. Validates parameters and handles API credentials securely. Prevents unauthorized lateral movement.

### HITL Approval Gateway
Manages Human-in-the-Loop approvals for high-risk actions. Generates a cryptographic SHA-256 hash of the exact execution plan and parameters. The approval link is valid for a 10-minute TTL. Uses WebSockets for real-time frontend updates and integrates with Slack for approvals.

### Health Verification Service
Executes health probes (e.g., HTTP checks, metric queries) post-remediation to verify the fix. Triggers auto-rollback workflows if probes fail.

### Post-Mortem Compiler
Automatically synthesizes the incident timeline, agent reasoning traces (fetched from Langfuse telemetry), and remediation actions into a structured Markdown post-mortem document.

### Dashboard & Frontend (Next.js)
React-based SPA providing the SRE command center. Visualizes incident graphs, agent reasoning, and pending HITL approvals.

## 4. Data Flow

1. **Ingestion:** Datadog fires a webhook. FastAPI Gateway receives it, validates the signature, and pushes the payload to a Redis Stream (<100ms).
2. **Correlation:** The Correlation Engine reads the stream, identifies it matches an ongoing CPU spike incident on the `payment-service` based on tags and time window, and attaches the alert to the active incident.
3. **Triage:** The LangGraph Orchestrator routes the incident to the Triage Agent, which assigns it P1.
4. **Investigation:** The Investigation Agent queries the Hybrid RAG Agent for similar past CPU spikes. It proposes fetching pod logs and running `top`.
5. **Tool Execution:** The Tool Runtime executes the read-only commands and returns the logs to the agent.
6. **Remediation Proposal:** The agent identifies a stuck process and proposes a pod restart.
7. **Guardrail & HITL:** The Guardrail Validator flags pod restarts on `payment-service` as high-risk. The HITL Gateway generates a SHA-256 payload and pings the SRE Lead on Slack.
8. **Execution:** The SRE Lead approves. The Tool Runtime executes the restart.
9. **Verification:** The Health Verification Service checks the `/health` endpoint and CPU metrics for 2 minutes.
10. **Post-Mortem:** The Post-Mortem Compiler generates a report and saves it to the RAG database for future incidents.

## 5. Communication Patterns

- **Synchronous (HTTP/REST):** Frontend to API Gateway, Webhook reception, synchronous third-party API calls (e.g., executing a single PagerDuty ack). Chosen for immediate response requirements.
- **Asynchronous (Redis Streams):** Webhook ingestion to Correlation Engine, Agent task queues. Chosen to handle high throughput (500 alerts/sec) and decouple ingestion from processing.
- **Real-time (WebSockets):** API Gateway to Frontend for live incident updates and agent reasoning streaming. Chosen for low-latency UI updates without polling.
- **Telemetry (Async HTTP):** Langfuse trace reporting.

## 6. Deployment Topology

Amber is designed for a **Self-Hosted / Dedicated VPC Single-Tenant** deployment to ensure data privacy and security of infrastructure credentials.

- **VPC Peering/Transit Gateway:** Amber sits in its own dedicated management VPC, peered with the target application VPCs.
- **Network Segmentation:** Strict Security Groups allow Amber to reach target APIs (K8s API server, SSH Bastions) but prevent target infra from initiating connections to Amber (except via webhooks to the public-facing Gateway).
- **Container Strategy:**
  - `amber-api` (FastAPI) - Auto-scaled Deployment.
  - `amber-worker` (LangGraph/Correlation) - Auto-scaled Deployment based on Redis queue depth.
  - `amber-db` (PostgreSQL) - StatefulSet or Managed RDS.
  - `amber-redis` (Redis) - StatefulSet or Managed ElastiCache.

## 7. Technology Decisions Summary Table

| Component | Technology | Why Chosen | Alternatives Considered |
| :--- | :--- | :--- | :--- |
| **API Framework** | Python FastAPI | Native async, high throughput, deep ecosystem for LLMs (LangChain). | Node.js/Express (Lacks mature LLM orchestration libs). |
| **Orchestrator** | LangGraph | Excellent for cyclic, stateful multi-agent workflows. | AutoGen (too opaque), standard LangChain chains (inflexible). |
| **Primary Database** | PostgreSQL + pgvector | ACID compliance + native vector search simplifies architecture. | Pinecone/Weaviate (Adds operational overhead, split brain issues). |
| **Event Queue** | Redis Streams | Ultra-fast memory-based append-only log, handles 500/sec easily. | Kafka (Too heavy for standard single-tenant deployments). |
| **Authentication** | PyJWT + bcrypt | Stateless, easy to integrate with custom RBAC. | Auth0/Cognito (Avoids external dependency for self-hosted). |
| **Telemetry** | Langfuse | Purpose-built for LLM observability (cost, latency, traces). | Datadog APM (Harder to trace specific LLM reasoning steps). |
| **Frontend** | React / Next.js | Industry standard, rich ecosystem for dashboards. | Vue.js. |

## 8. Failure Modes & Resilience

- **Webhook API Failure:** If FastAPI goes down, load balancer returns 503. Observability tools must handle retries. To mitigate, the API layer is stateless and heavily scaled.
- **Redis Crash:** Unprocessed alerts in memory could be lost. **Mitigation:** Redis is configured with AOF (Append Only File) persistence.
- **LLM Provider Outage (e.g., OpenAI down):** Agents cannot reason. **Mitigation:** Fallback to deterministic runbook execution (e.g., automatically escalate to human SRE without triage). Circuit breakers on LLM API calls prevent cascading timeouts.
- **Tool Execution Timeout:** If a target system is unresponsive, the sandboxed runtime enforces a strict timeout (e.g., 30s). The failure is fed back to the agent as an observation.

## 9. Security Boundaries

- **Execution Sandbox:** The Tool Execution Runtime operates with least-privilege IAM roles. E.g., it cannot terminate EC2 instances unless explicitly granted.
- **Cryptographic HITL:** The SHA-256 payload binding ensures that if an SRE approves `Restart Pod X`, a malicious actor cannot intercept the approval and change it to `Drop Database`.
- **Secret Management:** API keys (OpenAI, Datadog) and SSH keys are stored in a dedicated Secrets Manager (AWS Secrets Manager or HashiCorp Vault), never in the database. Injected at runtime into the Tool Execution environment.
- **Network Isolation:** The Data plane (Postgres, Redis) is strictly isolated in private subnets with no inbound internet access.
