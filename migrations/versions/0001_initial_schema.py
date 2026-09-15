"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", sa.String(length=256), nullable=False),
        sa.Column("job_id", sa.String(length=256), nullable=True),
        sa.Column("job_instance_id", sa.Integer(), nullable=True),
        sa.Column("scheduler_id", sa.String(length=256), nullable=True),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_event", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_workflow_events_event_id"),
    )
    op.create_index("ix_workflow_events_event_id", "workflow_events", ["event_id"], unique=True)
    op.create_index("ix_workflow_events_workflow_id", "workflow_events", ["workflow_id"])
    op.create_index("ix_workflow_events_job_id", "workflow_events", ["job_id"])
    op.create_index(
        "ix_workflow_events_workflow_job", "workflow_events", ["workflow_id", "job_id"]
    )

    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", sa.String(length=256), nullable=False),
        sa.Column("job_id", sa.String(length=256), nullable=False),
        sa.Column("source_job_instance_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_id", "job_id", "source_job_instance_id",
            name="uq_incident_per_failed_instance",
        ),
    )
    op.create_index("ix_incidents_workflow_id", "incidents", ["workflow_id"])
    op.create_index("ix_incidents_job_id", "incidents", ["job_id"])

    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("content", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_incident_id", "evidence", ["incident_id"])

    op.create_table(
        "diagnoses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("failure_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("missing_evidence", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("raw_diagnosis", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_diagnoses_incident_id", "diagnoses", ["incident_id"])

    op.create_table(
        "fixes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("parameters", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("old_configuration", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("proposed_configuration", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("config_hash_before", sa.String(length=64), nullable=True),
        sa.Column("config_hash_after", sa.String(length=64), nullable=True),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("retry_job_instance_id", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id", "attempt_number", name="uq_one_fix_per_attempt"),
        sa.UniqueConstraint("retry_job_instance_id", name="uq_retry_instance_fix"),
    )
    op.create_index("ix_fixes_incident_id", "fixes", ["incident_id"])

    op.create_table(
        "fix_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fix_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("data", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fix_id"], ["fixes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fix_events_fix_id", "fix_events", ["fix_id"])

    op.create_table(
        "policy_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fix_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("checks_passed", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("checks_failed", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fix_id"], ["fixes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_decisions_fix_id", "policy_decisions", ["fix_id"])

    op.create_table(
        "job_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.String(length=256), nullable=False),
        sa.Column("job_id", sa.String(length=256), nullable=False),
        sa.Column("job_instance_id", sa.Integer(), nullable=False),
        sa.Column("fix_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_attempts_wf_job", "job_attempts", ["workflow_id", "job_id"])

    op.create_table(
        "memory_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.String(length=256), nullable=False),
        sa.Column("failure_type", sa.String(length=64), nullable=False),
        sa.Column("transformation", sa.String(length=256), nullable=True),
        sa.Column("execution_site", sa.String(length=256), nullable=True),
        sa.Column("fix_action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column(
            "configuration_delta", postgresql.JSON(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("source_incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_items_project_type", "memory_items", ["project_id", "failure_type"]
    )


def downgrade() -> None:
    op.drop_table("memory_items")
    op.drop_table("job_attempts")
    op.drop_table("policy_decisions")
    op.drop_table("fix_events")
    op.drop_table("fixes")
    op.drop_table("diagnoses")
    op.drop_table("evidence")
    op.drop_table("incidents")
    op.drop_table("workflow_events")
