from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.db.models import IncidentRecord, WorkflowEventRecord
from app.utils.models.events import WorkflowEvent

log = structlog.get_logger(__name__)


async def persist_event(session: AsyncSession, event: WorkflowEvent) -> bool:
    """
    Idempotently store a WorkflowEvent.

    Returns True if the event was newly inserted, False if it was a duplicate.
    The AMQP message must be acked only AFTER this function returns successfully.
    """
    record = WorkflowEventRecord(
        event_id=event.event_id,
        event_type=event.event_type,
        workflow_id=event.workflow_id,
        job_id=event.job_id,
        job_instance_id=event.job_instance_id,
        scheduler_id=event.scheduler_id,
        status=event.status,
        timestamp=event.timestamp,
        raw_event=event.raw_event,
        created_at=datetime.now(timezone.utc),
    )
    session.add(record)
    try:
        await session.flush()
        log.info("event_persisted", event_id=event.event_id, event_type=event.event_type)
        return True
    except IntegrityError:
        await session.rollback()
        log.debug("event_duplicate", event_id=event.event_id)
        return False


async def get_or_create_incident(
    session: AsyncSession,
    event: WorkflowEvent,
) -> tuple[IncidentRecord, bool]:
    """
    Get or create an incident record for a failed job event.

    Returns (incident, created).
    Uses the unique constraint on (workflow_id, job_id, source_job_instance_id).
    """
    assert event.job_id is not None
    assert event.job_instance_id is not None

    stmt = select(IncidentRecord).where(
        IncidentRecord.workflow_id == event.workflow_id,
        IncidentRecord.job_id == event.job_id,
        IncidentRecord.source_job_instance_id == event.job_instance_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    incident = IncidentRecord(
        id=uuid.uuid4(),
        workflow_id=event.workflow_id,
        job_id=event.job_id,
        source_job_instance_id=event.job_instance_id,
        status="OPEN",
        attempt=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        version=0,
    )
    session.add(incident)
    try:
        await session.flush()
        log.info(
            "incident_created",
            incident_id=str(incident.id),
            workflow_id=event.workflow_id,
            job_id=event.job_id,
            job_instance_id=event.job_instance_id,
        )
        return incident, True
    except IntegrityError:
        # Race condition: another worker created it first
        await session.rollback()
        result = await session.execute(stmt)
        existing = result.scalar_one()
        return existing, False
