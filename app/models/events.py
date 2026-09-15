from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "JOB_SUBMITTED",
    "JOB_STARTED",
    "JOB_HELD",
    "JOB_FAILED",
    "JOB_SUCCEEDED",
    "WORKFLOW_FAILED",
    "WORKFLOW_SUCCEEDED",
]

TERMINAL_FAILURE_TYPES: set[EventType] = {"JOB_FAILED", "WORKFLOW_FAILED"}


class WorkflowEvent(BaseModel):
    event_id: str
    event_type: EventType
    workflow_id: str
    job_id: str | None = None
    job_instance_id: int | None = None
    scheduler_id: str | None = None
    status: int | None = None
    timestamp: datetime
    raw_event: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def make_event_id(cls, raw: dict[str, Any]) -> str:
        """Stable SHA-256 fingerprint from the raw AMQP payload."""
        canonical = json.dumps(raw, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @property
    def is_failure(self) -> bool:
        return self.event_type in TERMINAL_FAILURE_TYPES
