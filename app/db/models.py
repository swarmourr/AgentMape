from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class WorkflowEventRecord(Base):
    """Normalised, immutable record of every Monitord AMQP event."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_workflow_events_event_id"),
        Index("ix_workflow_events_workflow_job", "workflow_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    job_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    job_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduler_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_event: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class IncidentRecord(Base):
    """One remediation case per failed job attempt."""

    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "job_id",
            "source_job_instance_id",
            name="uq_incident_per_failed_instance",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    source_job_instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="OPEN")
    # attempt tracks which remediation cycle we are in (resets per incident)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optimistic concurrency lock
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    diagnoses: Mapped[list[DiagnosisRecord]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    fixes: Mapped[list[FixRecord]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    evidence_items: Mapped[list[EvidenceRecord]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class EvidenceRecord(Base):
    """Raw evidence collected for an incident (logs, metrics, scheduler data)."""

    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    incident: Mapped[IncidentRecord] = relationship(back_populates="evidence_items")


class DiagnosisRecord(Base):
    """Rule or LLM classification result for an incident."""

    __tablename__ = "diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True
    )
    failure_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # RULE | LLM
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_diagnosis: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    incident: Mapped[IncidentRecord] = relationship(back_populates="diagnoses")


class FixRecord(Base):
    """Fix proposal lifecycle summary — one per attempt per incident."""

    __tablename__ = "fixes"
    __table_args__ = (
        UniqueConstraint(
            "incident_id", "attempt_number", name="uq_one_fix_per_attempt"
        ),
        # retry_job_instance_id → fix_id is 1:1
        UniqueConstraint("retry_job_instance_id", name="uq_retry_instance_fix"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    old_configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    proposed_configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    config_hash_before: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_hash_after: Mapped[str | None] = mapped_column(String(64), nullable=True)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # PROPOSED → VALIDATED → APPROVED → APPLIED → RETRIED → EVALUATED
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROPOSED")
    retry_job_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    incident: Mapped[IncidentRecord] = relationship(back_populates="fixes")
    events: Mapped[list[FixEventRecord]] = relationship(
        back_populates="fix", cascade="all, delete-orphan"
    )
    policy_decisions: Mapped[list[PolicyDecisionRecord]] = relationship(
        back_populates="fix", cascade="all, delete-orphan"
    )


class FixEventRecord(Base):
    """Append-only log of fix state transitions."""

    __tablename__ = "fix_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fix_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fixes.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    fix: Mapped[FixRecord] = relationship(back_populates="events")


class PolicyDecisionRecord(Base):
    """Immutable record of every AUTO/ASK/STOP/ESCALATE decision."""

    __tablename__ = "policy_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fix_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fixes.id"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    checks_passed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    checks_failed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    fix: Mapped[FixRecord] = relationship(back_populates="policy_decisions")


class JobAttemptRecord(Base):
    """Tracks original and retry job instances."""

    __tablename__ = "job_attempts"
    __table_args__ = (
        Index("ix_job_attempts_wf_job", "workflow_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    job_instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fix_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class MemoryItemRecord(Base):
    """Generalised retrievable knowledge promoted from verified episodes."""

    __tablename__ = "memory_items"
    __table_args__ = (
        Index("ix_memory_items_project_type", "project_id", "failure_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    failure_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    transformation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    execution_site: Mapped[str | None] = mapped_column(String(256), nullable=True)
    fix_action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    configuration_delta: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_incident_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
