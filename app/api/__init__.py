from __future__ import annotations

"""
FastAPI application — lifecycle, health endpoints, and REST API.

Endpoints (§15):
  GET  /health
  GET  /ready
  GET  /incidents/{id}
  GET  /workflows/{id}/incidents
  POST /incidents/{id}/approve
  POST /incidents/{id}/reject
  POST /incidents/{id}/outcome          (internal: called by event ingestor)
  POST /events/replay                   (dev only)
  GET  /fixes/{id}
  GET  /metrics                         (Prometheus)
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.config import settings
from app.utils.db.models import FixRecord, IncidentRecord
from app.utils.db.session import async_session_factory, get_session
from app.utils.events.consumer import AMQPConsumer
from app.utils.events.persistence import get_or_create_incident, persist_event
from app.graph import create_graph_with_checkpointer
from app.utils.llm import build_diagnosis_provider, build_fix_planning_provider, build_llm_provider
from app.utils.models.events import WorkflowEvent
from app.utils.models.fixes import FixOutcome
from app.utils.observability import configure_logging, metrics
from app.utils.models.evidence import RawEvidence
from app.utils.pegasus.dagman_retry_controller import DAGManRetryController
from app.utils.pegasus.fake import FakePegasusRetryController
from app.utils.policies import PolicyEngine, load_policy

log = structlog.get_logger(__name__)

# ── Application-level singletons (set in lifespan) ────────────────────────────
_graph = None
_amqp_consumer: AMQPConsumer | None = None
_redis: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    global _graph, _amqp_consumer, _redis
    configure_logging()

    log.info(
        "service_starting",
        model=settings.llm_model,
        diagnosis_model=settings.diagnosis_llm_model or settings.llm_model,
        fix_planning_model=settings.fix_planning_llm_model or settings.llm_model,
    )

    # Build services
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    policy_config = load_policy(settings.policy_file)
    policy_engine = PolicyEngine(policy_config, settings.confidence_threshold)
    llm_provider = build_llm_provider()
    diagnosis_llm  = build_diagnosis_provider()
    fix_planning_llm = build_fix_planning_provider()
    retry_controller = FakePegasusRetryController()  # swap for real adapter

    # Build LangGraph — PostgreSQL if configured, SQLite otherwise
    pg_conn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    _graph = await create_graph_with_checkpointer(
        pg_url=pg_conn,
        sqlite_path=settings.sqlite_path,
    )

    # Wire services into node kwargs via a closure
    node_services = {
        "llm": llm_provider,             # shared fallback
        "diagnosis_llm": diagnosis_llm,  # DiagnosisAgent (multi-step ReAct)
        "fix_planning_llm": fix_planning_llm,  # FixPlanningAgent (single call)
        "policy": policy_config,
        "policy_engine": policy_engine,
        "retry_controller": retry_controller,
        "redis": _redis,
        "lock_ttl": settings.redis_lock_ttl_seconds,
    }
    app.state.graph = _graph
    app.state.services = node_services
    app.state.redis = _redis

    # Start AMQP consumer only if explicitly enabled
    if settings.amqp_enabled:
        _amqp_consumer = AMQPConsumer(
            handler=lambda event: _handle_event(event, node_services)
        )
        asyncio.create_task(_amqp_consumer.start())
        log.info("amqp_consumer_enabled", url=settings.amqp_url)
    else:
        log.info("amqp_consumer_disabled", hint="set AMQP_ENABLED=true to enable")

    log.info("service_ready")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    if _amqp_consumer:
        await _amqp_consumer.stop()
    if _redis:
        await _redis.aclose()
    log.info("service_stopped")


app = FastAPI(title="Pegasus Remediation Service", version="0.1.0", lifespan=lifespan)


# ── Event handler (called by AMQP consumer) ───────────────────────────────────

async def _handle_event(event: WorkflowEvent, services: dict[str, Any]) -> None:
    """
    Persist event, create/update incident, trigger or resume the graph.
    """
    async with async_session_factory() as session:
        async with session.begin():
            is_new = await persist_event(session, event)
            if not is_new:
                metrics.duplicate_events_total.inc()
                return

        metrics.events_consumed_total.labels(event_type=event.event_type).inc()

        # Only act on failure events
        if not event.is_failure or not event.job_id or not event.job_instance_id:
            return

        async with session.begin():
            incident, created = await get_or_create_incident(session, event)

        if created:
            metrics.incidents_created_total.inc()
            metrics.incidents_open.inc()
            # Start the remediation graph for this new incident
            initial_state = {
                "incident_id": str(incident.id),
                "workflow_id": event.workflow_id,
                "job_id": event.job_id,
                "source_job_instance_id": event.job_instance_id,
                "failure_event": event.model_dump(mode="json"),
                "attempt": 1,
                "errors": [],
            }
            config = {"configurable": {"thread_id": str(incident.id), **services}}
            await app.state.graph.ainvoke(initial_state, config=config)
        else:
            # Check if this is the outcome event for a pending retry
            await _maybe_resume_on_outcome(incident, event, services)


async def _maybe_resume_on_outcome(
    incident: IncidentRecord,
    event: WorkflowEvent,
    services: dict[str, Any],
) -> None:
    """Resume the graph if the incoming event is the retry outcome."""
    async with async_session_factory() as session:
        # Find an active fix awaiting this job_instance_id
        stmt = select(FixRecord).where(
            FixRecord.incident_id == incident.id,
            FixRecord.retry_job_instance_id == event.job_instance_id,
            FixRecord.status == "RETRIED",
        )
        result = await session.execute(stmt)
        fix = result.scalar_one_or_none()

    if fix is None:
        return

    # Map event type to FixOutcome
    if event.event_type == "JOB_SUCCEEDED":
        outcome = FixOutcome.EFFECTIVE.value
    elif event.event_type == "JOB_FAILED":
        # Could be INEFFECTIVE or NEW_FAILURE — let evaluate_outcome node decide
        outcome = FixOutcome.INEFFECTIVE.value
    else:
        outcome = FixOutcome.INCONCLUSIVE.value

    config = {"configurable": {"thread_id": str(incident.id), **services}}
    resume_state = {
        "retry_outcome": outcome,
        "attempt": (incident.attempt or 1) + 1,
    }
    await app.state.graph.ainvoke(resume_state, config=config)


# ── Health / readiness ────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    checks: dict[str, str] = {}

    # Database
    try:
        async with async_session_factory() as s:
            await s.execute(select(1))  # type: ignore[arg-type]
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # Redis
    try:
        r = app.state.redis
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
        status_code=200 if all_ok else 503,
    )


# ── Incident API ──────────────────────────────────────────────────────────────

@app.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        uid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident_id")

    stmt = select(IncidentRecord).where(IncidentRecord.id == uid)
    result = await session.execute(stmt)
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return {
        "incident_id": str(incident.id),
        "workflow_id": incident.workflow_id,
        "job_id": incident.job_id,
        "source_job_instance_id": incident.source_job_instance_id,
        "status": incident.status,
        "attempt": incident.attempt,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
    }


@app.get("/workflows/{workflow_id}/incidents")
async def get_workflow_incidents(
    workflow_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    stmt = select(IncidentRecord).where(IncidentRecord.workflow_id == workflow_id)
    result = await session.execute(stmt)
    incidents = result.scalars().all()
    return [
        {
            "incident_id": str(i.id),
            "job_id": i.job_id,
            "status": i.status,
            "attempt": i.attempt,
        }
        for i in incidents
    ]


# ── Approval API ──────────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    fix_id: str
    decision: str   # "APPROVE" | "REJECT"
    actor: str
    comment: str = ""


@app.post("/incidents/{incident_id}/approve")
async def approve_fix(
    incident_id: str,
    body: ApprovalRequest,
) -> dict[str, str]:
    """Resume a graph interrupted waiting for human approval."""
    if body.decision not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    config = {"configurable": {"thread_id": incident_id, **app.state.services}}
    resume_state = {
        "human_approved": body.decision == "APPROVE",
        "policy_decision": "AUTO" if body.decision == "APPROVE" else "STOP",
    }
    await app.state.graph.ainvoke(resume_state, config=config)
    log.info(
        "human_approval",
        incident_id=incident_id,
        decision=body.decision,
        actor=body.actor,
        fix_id=body.fix_id,
    )
    return {"status": "resumed", "decision": body.decision}


@app.post("/incidents/{incident_id}/reject")
async def reject_fix(
    incident_id: str,
    body: ApprovalRequest,
) -> dict[str, str]:
    body.decision = "REJECT"
    return await approve_fix(incident_id, body)


# ── Fix API ───────────────────────────────────────────────────────────────────

@app.get("/fixes/{fix_id}")
async def get_fix(
    fix_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        uid = uuid.UUID(fix_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid fix_id")

    stmt = select(FixRecord).where(FixRecord.id == uid)
    result = await session.execute(stmt)
    fix = result.scalar_one_or_none()
    if not fix:
        raise HTTPException(status_code=404, detail="Fix not found")

    return {
        "fix_id": str(fix.id),
        "incident_id": str(fix.incident_id),
        "action": fix.action,
        "status": fix.status,
        "outcome": fix.outcome,
        "old_configuration": fix.old_configuration,
        "proposed_configuration": fix.proposed_configuration,
        "config_hash_before": fix.config_hash_before,
        "config_hash_after": fix.config_hash_after,
        "justification": fix.justification,
        "retry_job_instance_id": fix.retry_job_instance_id,
        "created_at": fix.created_at.isoformat(),
    }


# ── DAGMan POST script synchronous endpoint ───────────────────────────────────

class DiagnoseAndFixRequest(BaseModel):
    """Request body sent by the DAGMan POST script."""
    job_id: str
    job_instance_id: int
    workflow_id: str
    exit_code: int
    submit_dir: str
    condor_job_id: str | None = None   # HTCondor cluster.proc (e.g. "1234.0")
    retry_number: int = 0
    max_retries: int = 3
    # Optional job metadata (enriches diagnosis)
    execution_site: str | None = None
    transformation: str | None = None
    scheduler_reason: str | None = None
    # Raw file contents collected by the POST script on the submit host
    raw_evidence: RawEvidence | None = None


class DiagnoseAndFixResponse(BaseModel):
    """
    Returned synchronously to the POST script before DAGMan decides to retry.

    decision values:
      RETRY     — .sub file patched; POST script should exit 1 so DAGMan retries
      ASK       — fix computed but needs human approval; POST script should exit 0
      STOP      — terminal failure; POST script should exit 0
      ESCALATE  — unknown failure requiring operator attention; POST script exits 0
    """
    decision: str
    incident_id: str
    failure_type: str | None = None
    confidence: float | None = None
    explanation: str | None = None
    evidence_sources: list[str] = []
    fix_id: str | None = None
    fix_proposed: dict[str, Any] | None = None   # action + configuration changes
    justification: str | None = None
    approval_url: str | None = None              # set when decision == ASK
    missing_evidence: list[str] = []


@app.post("/diagnose-and-fix", response_model=DiagnoseAndFixResponse)
async def diagnose_and_fix(body: DiagnoseAndFixRequest) -> DiagnoseAndFixResponse:
    """
    Synchronous entry-point for the DAGMan POST script integration.

    The POST script calls this endpoint for every failed job.  The service
    diagnoses the failure, selects and validates a fix, patches the HTCondor
    submit file in-place (for AUTO decisions), and returns a structured
    decision before the POST script exits.

    Execution flow:
      collect_context → rule_classifier → [diagnosis_agent]
      → fix_catalog   → [fix_planner]
      → policy_engine → apply_fix (patches .sub) → authorize_retry
      → return decision
    """
    import hashlib
    import json
    from datetime import datetime, timezone

    # ── Build a synthetic WorkflowEvent from the POST script args ─────────────
    raw: dict[str, Any] = {
        "workflow_id": body.workflow_id,
        "job_id": body.job_id,
        "job_instance_id": body.job_instance_id,
        "exit_code": body.exit_code,
        "scheduler_id": body.condor_job_id,
        "scheduler_reason": body.scheduler_reason,
        "source": "post_script",
    }
    event_id = hashlib.sha256(
        json.dumps(raw, sort_keys=True).encode()
    ).hexdigest()

    event = WorkflowEvent(
        event_id=event_id,
        event_type="JOB_FAILED",
        workflow_id=body.workflow_id,
        job_id=body.job_id,
        job_instance_id=body.job_instance_id,
        scheduler_id=body.condor_job_id,
        status=body.exit_code,
        timestamp=datetime.now(timezone.utc),
        raw_event=raw,
    )

    # ── Persist event and create/fetch incident ────────────────────────────────
    async with async_session_factory() as session:
        async with session.begin():
            await persist_event(session, event)
        async with session.begin():
            incident, _ = await get_or_create_incident(session, event)

    incident_id = str(incident.id)

    # ── Build per-request services with the real DAGManRetryController ────────
    retry_controller = DAGManRetryController(
        submit_dir=body.submit_dir,
        job_id=body.job_id,
        job_instance_id=body.job_instance_id,
    )
    per_request_services: dict[str, Any] = {
        **app.state.services,
        "retry_controller": retry_controller,
        "submit_dir": body.submit_dir,
        "raw_evidence": body.raw_evidence.model_dump() if body.raw_evidence else {},
    }

    # ── Run the remediation graph synchronously ────────────────────────────────
    initial_state: dict[str, Any] = {
        "incident_id": incident_id,
        "workflow_id": body.workflow_id,
        "job_id": body.job_id,
        "source_job_instance_id": body.job_instance_id,
        "failure_event": event.model_dump(mode="json"),
        "attempt": body.retry_number + 1,
        "errors": [],
    }
    config = {"configurable": {"thread_id": incident_id, **per_request_services}}

    try:
        final_state: dict[str, Any] = await app.state.graph.ainvoke(
            initial_state, config=config
        )
    except Exception as exc:
        log.error(
            "diagnose_and_fix_graph_error",
            incident_id=incident_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Graph execution error: {exc}")

    # ── Map graph state → POST script decision ─────────────────────────────────
    policy_decision: str = final_state.get("policy_decision", "ESCALATE")
    diagnosis_data: dict[str, Any] = final_state.get("diagnosis", {})
    fix_data: dict[str, Any] = final_state.get("proposed_fix", {})

    failure_type = diagnosis_data.get("failure_type")
    confidence = diagnosis_data.get("confidence")
    explanation = diagnosis_data.get("explanation")
    evidence_sources = diagnosis_data.get("evidence_ids", [])
    missing_evidence = diagnosis_data.get("missing_evidence", [])
    fix_id = fix_data.get("fix_id") or final_state.get("fix_id")
    justification = fix_data.get("justification")

    if policy_decision == "AUTO":
        decision = "RETRY"
        approval_url = None
    elif policy_decision == "ASK":
        decision = "ASK"
        approval_url = f"/incidents/{incident_id}/approve"
    else:
        # STOP or ESCALATE
        decision = policy_decision
        approval_url = None

    log.info(
        "diagnose_and_fix_complete",
        incident_id=incident_id,
        job_id=body.job_id,
        failure_type=failure_type,
        policy_decision=policy_decision,
        decision=decision,
    )
    metrics.fixes_by_decision_total.labels(decision=decision).inc()

    return DiagnoseAndFixResponse(
        decision=decision,
        incident_id=incident_id,
        failure_type=failure_type,
        confidence=confidence,
        explanation=explanation,
        evidence_sources=evidence_sources,
        fix_id=str(fix_id) if fix_id else None,
        fix_proposed=fix_data if fix_data else None,
        justification=justification,
        approval_url=approval_url,
        missing_evidence=missing_evidence,
    )


# ── Dev-only event replay ─────────────────────────────────────────────────────

@app.post("/events/replay")
async def replay_event(event: dict[str, Any]) -> dict[str, str]:
    """Replay a raw event payload for local development and testing."""
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Replay only available in debug mode")
    from app.utils.events.schemas import normalize_event
    routing_key = event.pop("_routing_key", "stampede.job_inst.main.failure")
    workflow_event = normalize_event(routing_key, event)
    if not workflow_event:
        raise HTTPException(status_code=400, detail="Event could not be normalised")
    await _handle_event(workflow_event, app.state.services)
    return {"status": "replayed", "event_id": workflow_event.event_id}


# ── Prometheus metrics ────────────────────────────────────────────────────────

@app.get("/metrics")
async def prometheus_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
