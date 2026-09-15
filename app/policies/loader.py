from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class PolicyConfig(BaseModel):
    version: str = "1.0.0"
    failure_policies: dict[str, dict[str, Any]] = {}
    global_config: dict[str, Any] = {}

    def get_decision(self, failure_type: str) -> str:
        return self.failure_policies.get(failure_type, {}).get("decision", "ASK")

    def get_max_attempts(self, failure_type: str) -> int:
        specific = self.failure_policies.get(failure_type, {}).get("maximum_attempts")
        if specific is not None:
            return int(specific)
        return int(self.global_config.get("maximum_attempts", 3))

    def get_multiplier(self, failure_type: str) -> float:
        return float(self.failure_policies.get(failure_type, {}).get("multiplier", 1.5))

    def get_ceiling(self, failure_type: str, key: str) -> int | None:
        val = self.failure_policies.get(failure_type, {}).get(key)
        return int(val) if val is not None else None

    def as_snapshot_dict(self) -> dict[str, Any]:
        return self.model_dump()


def load_policy(path: str) -> PolicyConfig:
    p = Path(path)
    if not p.exists():
        return PolicyConfig()
    with p.open() as f:
        data = yaml.safe_load(f) or {}
    return PolicyConfig(
        version=data.get("version", "1.0.0"),
        failure_policies=data.get("failure_policies", {}),
        global_config=data.get("global", {}),
    )
