# Amber — Autonomous Incident Remediation & SRE Engine

> **Status:** Phase 3 — Governed HITL Remediation & Live In-VPC Production Engine  
> **Live Web Platform:** [https://ambersre.xyz](https://ambersre.xyz)  
> **Interactive Telegram Bot:** [@ambersre_alert_bot](https://t.me/ambersre_alert_bot)  
> **License:** Source-Available / Enterprise Commercial Open Core

Amber is an autonomous incident remediation engine engineered for high-velocity infrastructure and backend engineering teams. It sits between incoming alert streams (PagerDuty, Datadog, Sentry, Prometheus) and production clusters to diagnose issues, fetch runbooks, and execute bounded remediation actions under strict cryptographic human supervision.

---

### Core Safety Thesis
> **LLMs propose; deterministic code and human operators decide.**

Amber never grants an LLM raw terminal access or unbounded database mutations. Mutating actions (killing stuck DB connections, restarting pods, rolling back deployments) require cryptographic Human-in-the-Loop (HITL) approval with a 10-minute TTL and SHA-256 payload binding. Read-only diagnostic tools run autonomously with strict sub-second timeouts.

---

## Production Multi-Container Architecture

```text
               Alert Ingestion (PagerDuty / Datadog / Sentry / Prometheus)
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │    amber-backend (FastAPI :8000)      │
                      │  Webhook Ingestion (<50ms Ack)        │
                      └───────────────────┬───────────────────┘
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │      amber-redis (Redis 7 Alpine)     │
                      │   Event Streams & Deduplication       │
                      └───────────────────┬───────────────────┘
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │       LangGraph Multi-Agent Engine    │
                      │  ├── Triage Node (P0–P4 in <3s)       │
                      │  ├── Hybrid RAG (pgvector + BM25)     │
                      │  ├── Bounded Diagnostic Tool Loop     │
                      │  └── Deterministic Guardrails         │
                      └───────────────────┬───────────────────┘
                                          │
                         ┌────────────────┴────────────────┐
                         │                                 │
                   [Low-Risk Action]               [High-Risk Action]
                         │                                 │
                         ▼                                 ▼
               Autonomous Execution               SHA-256 Bound HITL
               (Read-only queries)                (10-Minute TTL Window)
                                                           │
                                                           ▼
                                            ┌───────────────────────────────┐
                                            │ Unified Approval Service      │
                                            │ ├── Web: ambersre.xyz         │
                                            │ ├── Telegram: @ambersre_alert │
                                            │ ├── WhatsApp: Baileys Bridge  │
                                            │ └── Slack: Block Kit Cards    │
                                            └───────────────────────────────┘
                                                           │
                                                           ▼
                                            ┌───────────────────────────────┐
                                            │    PostgreSQL 16 + pgvector   │
                                            │  Audit Logs & State Machine   │
                                            └───────────────────────────────┘
```

---

## Implemented Production Stack

### 1. Multi-Container Orchestration (`docker-compose.yml`)
- **`amber-postgres` (Port 5432):** PostgreSQL 16 with `pgvector` extension for incident auditing, graph checkpoints, and vector embeddings.
- **`amber-redis` (Port 6379):** Redis 7 Streams for alert storm buffering, sliding window deduplication, and token revocation.
- **`amber-backend` (Port 8000):** Stateless async FastAPI gateway serving REST APIs, webhooks, and health endpoints (`/health/liveness`, `/health/readiness`).
- **`amber-whatsapp-bridge` (Port 3001):** Dedicated Node.js Baileys microservice with web QR authentication (`GET /`) and live alert dispatch.
- **`amber-telegram-bot`:** Standalone singleton worker polling `@ambersre_alert_bot`, providing in-app 1-click mobile approvals and eliminating Uvicorn multi-worker 409 conflicts.

### 2. Multi-Channel Approvals (`backend/app/services/approval_service.py`)
- **Cryptographic Binding:** SHA-256 hash generated over sorted JSON arguments. Any tampering immediately invalidates the approval token.
- **10-Minute Expiration Window:** Expired tokens are marked `EXPIRED` automatically.
- **Atomic Incident Transition:** Approving a tool atomically transitions the associated incident from `PROPOSED` → `EXECUTING` → `RESOLVED`.
- **Cross-Channel Synchronization:** Decisions made via Telegram, WhatsApp, Slack, or Web Dashboard instantly reflect across the entire system.

### 3. Agent Pipeline (`backend/app/agents/`)
- **Triage Node:** Evaluates alert payloads, logs, and stack traces into severity tiers (P0–P4) in <3 seconds.
- **Hybrid RAG Node:** Matches incident signatures against internal markdown runbooks using dense embeddings + BM25 keyword search.
- **Investigation Node:** Executes sandboxed, bounded diagnostic tools (`query_db_metrics`, `fetch_pod_logs`, `check_service_health`).
- **Guardrail Node:** Validates proposed remediation tools against a static code-compiled risk matrix. LLMs cannot modify tool risk levels.

### 4. Live Frontend Edge (`https://ambersre.xyz`)
- Built with React 19, TypeScript, Tailwind CSS, and Framer Motion.
- Edge-deployed to Cloudflare Workers with automated universal SSL (Google Trust Services).
- Includes an interactive alert storm simulator, Deep Proof inspection drawer, live incident matrices, and full SEO metadata (Schema.org JSON-LD, OpenGraph, Twitter Cards, `robots.txt`, and `sitemap.xml`).

---

## Quickstart

### Option A: Run Full Production Stack with Docker Compose (Recommended)

Boot all 5 services with one command:

```bash
docker compose up -d
```

Verify that all containers are healthy:
```bash
docker compose ps
```

Expected output:
```text
NAME                     IMAGE                  STATUS
amber-postgres           pgvector/pgvector:pg16 Up (healthy)
amber-redis              redis:7-alpine         Up (healthy)
amber-backend            amber-backend          Up (healthy) 0.0.0.0:8000->8000/tcp
amber-whatsapp-bridge    whatsapp-bridge        Up (healthy) 0.0.0.0:3001->3001/tcp
amber-telegram-bot       amber-backend          Up           (polling @ambersre_alert_bot)
```

To view live backend logs:
```bash
docker compose logs -f amber-backend amber-telegram-bot
```

---

### Option B: Local Python Development Setup

#### Prerequisites
- Python 3.10+
- `uv` (recommended) or standard `venv`

#### 1. Environment & Dependencies
```bash
# Clone the repository
git clone https://github.com/himanshu-xyz-1/Amber.git
cd Amber

# Set up virtual environment
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

#### 2. Run Database Migrations
```bash
python3 -c "
import asyncio
from backend.app.core.database import engine, Base
from backend.app.models import *
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(init())
"
```

#### 3. Run Test Suite
```bash
pytest tests/ -v
```
*(All 20 test cases pass out of the box).*

#### 4. Start Development Server
```bash
uvicorn backend.app.main:app --reload --port 8000
```

Interactive documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Telegram SRE Bot Commands

Connect to `@ambersre_alert_bot` on Telegram and use:
- `/status` — Check system health, database connection, and Redis status.
- `/incidents` — View the 5 most recent incidents and their status.
- `/pending` — List high-risk remediation actions awaiting human approval.
- `/approve <invocation_id>` — Approve a pending remediation action.
- `/reject <invocation_id>` — Reject a pending remediation action.
- `/simulate` — Trigger an instant P0 connection pool saturation simulation.

---

## Enterprise Commercial Licensing

Amber is distributed under a source-available, commercial open core model:

- **Community Edition:**
  - Ingestion buffer, fingerprint deduplication, incident triage, and bounded read-only diagnostics.
- **Enterprise Edition:**
  - Multi-channel 1-click approvals across Slack Block Kit, Telegram Bot, and Baileys WhatsApp bridges.
  - Autonomous mutating remediation with SHA-256 cryptographic human-in-the-loop verification.
  - Offline Ed25519 signature validation (zero DRM call-homes, fully air-gapped VPC compatible).

### License Key Activation
```bash
# Via CLI
python scripts/activate_key.py --key amb_live_...

# Via REST API
curl -X POST http://localhost:8000/api/v1/license/activate \
  -H "Content-Type: application/json" \
  -d '{"license_key": "amb_live_..."}'
```

To request a commercial license or book an architecture review, visit [https://ambersre.xyz](https://ambersre.xyz).
