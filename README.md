# Amber

> **Status:** Active Development / Building Phase (Phase 1: Ingestion & Backend Core)

Amber is an autonomous incident remediation engine for infrastructure and backend services. It sits between incoming alert streams (PagerDuty, Datadog, Sentry) and production environments to diagnose issues, fetch runbooks, and propose bounded remediation actions.

### Core Safety Thesis
LLMs propose; deterministic code and human operators decide.

Amber never gives an LLM raw terminal access or uncontrolled database write permissions. Mutating actions (killing connections, restarting pods, rolling back deployments) require cryptographic Human-in-the-Loop (HITL) approval with a 10-minute TTL. Read-only diagnostic tools run autonomously with strict time limits.

---

## Current Architecture & Implementation Status

```
Alert Ingestion (Webhooks)
          │
          ▼
Fingerprint & Sliding Window Correlation
          │
          ▼
LangGraph Orchestrator
   ├── Triage Node (P0-P4 severity classification)
   ├── Hybrid RAG Node (Runbook lookup)
   ├── Investigation Node (Read-only diagnostic tool loop)
   └── Guardrail Validator (Deterministic risk enforcement)
          │
     ┌────┴────┐
High Risk   Low Risk
     │         │
     ▼         ▼
HITL Gateway  Autonomous Runner
(SHA-256 bound)
```

### What is Built So Far:

1. **System Design & Specs (`docs/`):**
   - 11 production design documents covering database architecture, auth lifecycle, sliding-window rate limiting, horizontal scaling, CI/CD, and API management.
   - Complete Product Requirements Document (PRD) with failure modes and threat model.

2. **Core & Database Layer (`backend/app/core/`, `backend/app/models/`):**
   - Async SQLAlchemy 2.0 with connection pooling and session management.
   - SQLite for local dev, PostgreSQL + pgvector target for production.
   - Core relational models: `incidents`, `alerts`, `tool_invocations`, `users`, `runbooks`.

3. **Tool Registry (`backend/app/tools/`):**
   - Static risk classification (`LOW` vs `HIGH`). Risk levels cannot be overridden by LLMs.
   - Diagnostic tools (Read-only): `query_db_metrics`, `fetch_pod_logs`, `check_service_health`.
   - Remediation tools (Mutating): `kill_db_connections`, `rollback_deployment`, `restart_service_pod`.
   - Payload hashing (SHA-256) on tool arguments before human approval requests.

4. **Agent Pipeline (`backend/app/agents/`):**
   - LangGraph state machine orchestrating: `triage -> rag -> investigation -> guardrail`.
   - Automatic execution halt when a proposed tool is marked `HIGH` risk.

5. **API Gateway (`backend/app/api/v1/`):**
   - Fast webhook ingestion endpoint (`/api/v1/webhooks/{source}`) returning 202 Accepted.
   - Incident management CRUD and execution timeline endpoints.
   - Cryptographic approval submission endpoint (`/api/v1/approvals`).
   - Liveness and readiness health checks.

---

## What is Being Improved Right Now

- **Redis Stream Ingestion Buffer:** Moving from direct database writes to a high-throughput Redis Stream to safely absorb alert storms up to 500 alerts/sec.
- **Real LLM Integration:** Replacing heuristic mock logic in the triage and investigation nodes with Claude 3.5 Sonnet / GPT-4o-mini structured tool calling.
- **pgvector Runbook Search:** Adding dense vector embeddings + BM25 keyword search for matching incident signatures against internal markdown runbooks.
- **Slack Block Kit Integration:** Interactive Slack message cards allowing SREs to expand diagnostic proof and approve remediation with 1 click.

---

## Local Development Setup

### Prerequisites
- Python 3.10+
- `uv` (recommended) or standard `venv`

### Installation

```bash
# Clone the repository
git clone https://github.com/himanshu-xyz-1/Amber.git
cd Amber

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Run database migrations / initialize tables
python3 -c "
import asyncio
from backend.app.core.database import engine, Base
from backend.app.models import *
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(init())
"

# Start development server
uvicorn backend.app.main:app --reload --port 8000
```

Interactive API documentation available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
