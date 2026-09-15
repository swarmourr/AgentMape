# Pegasus Agentic Failure Remediation

Event-driven, memory-enabled, safe job diagnosis and repair for **Pegasus WMS**.

---

## Architecture

```
Pegasus / HTCondor
    ↓ (Monitord AMQP events)
Event Consumer (aio-pika)
    ↓
Event Normalizer  ──→  PostgreSQL (workflow_events)
    ↓  [JOB_FAILED]
Incident Manager  ──→  PostgreSQL (incidents)
    ↓
LangGraph Two-Loop Graph
  ┌─ DIAGNOSTIC LOOP ──────────────────────────────────┐
  │  collect_context → rule_classifier                  │
  │       │ no match                                    │
  │       └→ retrieve_memories → diagnosis_agent (LLM) │
  └─────────────────────────────────────────────────────┘
    ↓ Diagnosis
  ┌─ ACTION LOOP ───────────────────────────────────────┐
  │  fix_catalog → (LLM fix_planner if no match)        │
  │  → policy_validator (deterministic)                  │
  │       AUTO → apply_fix → authorize_retry → [wait]   │
  │       ASK  → [INTERRUPT: POST /incidents/{id}/approve] │
  │       STOP/ESCALATE → terminal                      │
  └─────────────────────────────────────────────────────┘
    ↓ (retry outcome event arrives)
  evaluate_outcome → write_memory / loop / escalate
```

### Technology stack

| Layer | Technology |
|---|---|
| Service | FastAPI + Uvicorn |
| Orchestration | LangGraph (PostgreSQL checkpoints) |
| Events | RabbitMQ / aio-pika |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Coordination | Redis (distributed locks, dedup) |
| LLM | LiteLLM + instructor (any provider) |
| Observability | structlog, Prometheus, OpenTelemetry |

---

## Quick start

### Prerequisites

- Python 3.11+
- Docker + Docker Compose

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env — set LLM_MODEL and the matching provider API key
```

### 2. Start infrastructure

```bash
docker compose up postgres rabbitmq redis -d
```

### 3. Run migrations

```bash
pip install -e ".[dev]"
alembic upgrade head
```

### 4. Start the service

```bash
uvicorn app.main:app --reload
```

Service is available at `http://localhost:8000`.

---

## LLM provider configuration

Set `LLM_MODEL` in `.env` to any model string supported by LiteLLM:

| Provider | LLM_MODEL | Key env var |
|---|---|---|
| OpenAI | `gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `claude-opus-4-6` | `ANTHROPIC_API_KEY` |
| Azure OpenAI | `azure/gpt-4o` | `AZURE_API_KEY` + `AZURE_API_BASE` |
| AWS Bedrock | `bedrock/anthropic.claude-3-opus` | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` |
| Ollama (local) | `ollama/llama3` | `LLM_BASE_URL=http://localhost:11434` |
| Any OAI-compat | `openai/my-model` | `LLM_BASE_URL=http://...` + `LLM_API_KEY` |

No code changes needed — just update `.env` and restart.

---

## REST API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (DB, Redis) |
| GET | `/incidents/{id}` | Incident state, diagnosis, fixes |
| GET | `/workflows/{id}/incidents` | All incidents for a workflow |
| POST | `/incidents/{id}/approve` | Approve a pending fix (ASK gate) |
| POST | `/incidents/{id}/reject` | Reject a pending fix |
| GET | `/fixes/{id}` | Fix proposal, policy decision, outcome |
| POST | `/events/replay` | Replay a raw event (debug mode only) |
| GET | `/metrics` | Prometheus metrics |

### Approve a pending fix

```bash
curl -X POST http://localhost:8000/incidents/INC_ID/approve \
  -H "Content-Type: application/json" \
  -d '{
    "fix_id": "FIX_ID",
    "decision": "APPROVE",
    "actor": "operator@example.org",
    "comment": "Walltime increase is acceptable for this run."
  }'
```

---

## Event replay (development)

Enable debug mode (`DEBUG=true` in `.env`), then:

```bash
curl -X POST http://localhost:8000/events/replay \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/events/oom_failure.json
```

---

## Running tests

```bash
# Unit + contract + graph tests (no live services needed)
pytest tests/unit tests/contract tests/graph -v

# All tests including integration (requires running Docker services)
pytest -v
```

---

## Safety invariants

| Invariant | Enforcement |
|---|---|
| No action without diagnosis | Graph: action loop entry requires `diagnosis` in state |
| No retry without validated fix | PolicyEngine must emit AUTO before fix applicator runs |
| One fix per attempt | DB unique constraint: `(incident_id, attempt_number)` |
| Deterministic policy overrides LLM | PolicyEngine runs after every LLM output |
| No duplicate retries | Redis lock + unique `retry_job_instance_id → fix_id` DB constraint |
| Bounded loops | Attempt counter checked before every re-entry |
| No scientific logic changes | PolicyEngine STOP on any executable/algorithm change |

---

## Phase 0 deployment note

The retry gate integration requires a compatibility spike on the target
Pegasus cluster to select between:

- **DAGMan POST/retry hook** — blocks DAGMan from issuing a retry until this
  service writes a "proceed" token.
- **Controlled rescue/restart** — pauses the workflow, applies the overlay to
  Pegasus properties/submit files, then calls `pegasus-run`.

The `FakePegasusRetryController` is used in all tests. Replace it with the
real adapter in `app/main.py` after the spike is complete.

---

## Implementation roadmap

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Scaffold, domain models, fake adapter | ✅ Done |
| 1 | AMQP consumer, normalizer, idempotent DB | ✅ Done |
| 2 | OOM vertical slice (rules → policy → retry) | ✅ Done |
| 3 | LangGraph checkpoints, interrupts, resume | ✅ Done |
| 4 | LLM diagnosis + fix-planning agents | ✅ Done |
| 5 | Disk, walltime, admission, transient rules | ✅ Done |
| 6 | pgvector incident similarity search | Pending |
| 7 | Neo4j + GraphRAG relational memory | Pending |
