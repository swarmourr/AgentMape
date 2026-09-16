from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


from typing import Literal

# Ordered hierarchy — higher index = more access
SCOPE_LEVELS = ["job", "script", "catalog", "workflow"]
ScopeLevel   = Literal["job", "script", "catalog", "workflow"]


def _scope_gte(current: str, required: str) -> bool:
    """Return True when current scope level includes required level."""
    try:
        return SCOPE_LEVELS.index(current) >= SCOPE_LEVELS.index(required)
    except ValueError:
        return False


class PolicyConfig(BaseModel):
    version: str = "1.0.0"
    failure_policies: dict[str, dict[str, Any]] = {}
    global_config: dict[str, Any] = {}
    scope_level: ScopeLevel = "job"

    def get_required_level(self, failure_type: str) -> str:
        return self.failure_policies.get(failure_type, {}).get("required_level", "job")

    def get_fallback_decision(self, failure_type: str) -> str:
        return self.failure_policies.get(failure_type, {}).get("fallback_decision", "ESCALATE")

    def scope_allows(self, failure_type: str) -> bool:
        """True when the current scope level meets the required level for this failure type."""
        return _scope_gte(self.scope_level, self.get_required_level(failure_type))

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

    raw_scope   = data.get("agent_scope", {})
    _yaml_level = raw_scope.get("level", "job")
    scope_level: ScopeLevel = _yaml_level if _yaml_level in SCOPE_LEVELS else "job"  # type: ignore[assignment]

    return PolicyConfig(
        version=data.get("version", "1.0.0"),
        failure_policies=data.get("failure_policies", {}),
        global_config=data.get("global", {}),
        scope_level=scope_level,
    )
