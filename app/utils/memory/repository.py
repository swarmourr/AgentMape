from __future__ import annotations

"""
Episodic long-term memory repository.

Stores verified fix episodes in PostgreSQL memory_items and supports
retrieval by project, failure type, and transformation.

Phase 6 extension: add pgvector embedding column to memory_items and
switch find_similar to ANN search rather than exact-match filtering.
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.db.models import MemoryItemRecord

log = structlog.get_logger(__name__)


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store_episode(
        self,
        project_id: str,
        failure_type: str,
        transformation: str | None,
        execution_site: str | None,
        fix_action: str,
        outcome: str,
        configuration_delta: dict[str, Any],
        source_incident_id: UUID,
        confidence: float,
    ) -> None:
        """
        Persist a verified fix episode.

        If an identical (project, failure_type, fix_action, outcome) record
        already exists, increment its occurrence_count instead of inserting.
        """
        stmt = select(MemoryItemRecord).where(
            MemoryItemRecord.project_id == project_id,
            MemoryItemRecord.failure_type == failure_type,
            MemoryItemRecord.fix_action == fix_action,
            MemoryItemRecord.outcome == outcome,
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.occurrence_count += 1
            existing.confidence = max(existing.confidence, confidence)
            existing.updated_at = datetime.now(timezone.utc)
            log.info(
                "memory_episode_updated",
                project_id=project_id,
                failure_type=failure_type,
                fix_action=fix_action,
                occurrences=existing.occurrence_count,
            )
        else:
            record = MemoryItemRecord(
                id=uuid.uuid4(),
                project_id=project_id,
                failure_type=failure_type,
                transformation=transformation,
                execution_site=execution_site,
                fix_action=fix_action,
                outcome=outcome,
                configuration_delta=configuration_delta,
                source_incident_id=source_incident_id,
                confidence=confidence,
                occurrence_count=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self._session.add(record)
            log.info(
                "memory_episode_stored",
                project_id=project_id,
                failure_type=failure_type,
                fix_action=fix_action,
            )

        await self._session.flush()

    async def find_similar(
        self,
        project_id: str,
        failure_type: str | None,
        transformation: str | None,
        workflow_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Retrieve similar past episodes for a project.

        Filters by (project_id, failure_type) when known, then sorts by
        occurrence_count DESC so the most-proven fixes rank highest.

        Phase 6: replace this with pgvector ANN similarity search.
        """
        stmt = select(MemoryItemRecord).where(
            MemoryItemRecord.project_id == project_id,
        )
        if failure_type:
            stmt = stmt.where(MemoryItemRecord.failure_type == failure_type)
        if transformation:
            stmt = stmt.where(MemoryItemRecord.transformation == transformation)

        stmt = stmt.order_by(  # type: ignore[attr-defined]
            MemoryItemRecord.occurrence_count.desc(),
            MemoryItemRecord.confidence.desc(),
        ).limit(limit)

        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "failure_type": r.failure_type,
                "fix_action": r.fix_action,
                "outcome": r.outcome,
                "confidence": r.confidence,
                "occurrence_count": r.occurrence_count,
                "configuration_delta": r.configuration_delta,
            }
            for r in rows
        ]
