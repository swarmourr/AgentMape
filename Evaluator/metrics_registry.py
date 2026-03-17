"""
Metrics Registry — built-in + user-defined evaluation metrics
"""

import json
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

BUILTIN_METRICS: List[Dict[str, Any]] = [
    {
        "name": "correctness",
        "description": "Does the plan directly address the root cause identified by the Analyzer? "
                       "High score means the plan targets the actual failure, not a symptom.",
        "weight": 3,
        "type": "builtin"
    },
    {
        "name": "safety",
        "description": "Are all commands non-destructive and reversible? "
                       "Penalise commands like rm -rf, dd, chmod 777, or anything that could cause data loss.",
        "weight": 5,
        "type": "builtin"
    },
    {
        "name": "completeness",
        "description": "Does the plan address ALL problems identified by the Analyzer, not just the first one?",
        "weight": 3,
        "type": "builtin"
    },
    {
        "name": "actionability",
        "description": "Are all commands concrete and immediately executable? "
                       "Penalise placeholder values like <PATH>, TODO, or vague instructions.",
        "weight": 2,
        "type": "builtin"
    },
    {
        "name": "consistency",
        "description": "Is the plan internally consistent? Steps should not contradict each other "
                       "or undo previous steps in the same plan.",
        "weight": 2,
        "type": "builtin"
    }
]


class MetricsRegistry:
    """Manages built-in and user-defined evaluation metrics"""

    def __init__(self, config_file: str = "evaluator_config.json"):
        self.config_file = config_file
        self._user_metrics: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        """Load user-defined metrics from config"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                self._user_metrics = config.get("user_defined_metrics", [])
                logger.info(f"Loaded {len(self._user_metrics)} user-defined metric(s)")
        except Exception as e:
            logger.error(f"Failed to load metrics from config: {e}")
            self._user_metrics = []

    def _save(self):
        """Persist user-defined metrics back to config"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    config = json.load(f)
            else:
                config = {}
            config["user_defined_metrics"] = self._user_metrics
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save metrics to config: {e}")

    def get_all(self) -> List[Dict[str, Any]]:
        """Return all active metrics (builtin + user-defined)"""
        return BUILTIN_METRICS + [
            {**m, "type": "user_defined"} for m in self._user_metrics
        ]

    def get_names(self) -> List[str]:
        return [m["name"] for m in self.get_all()]

    def add_metric(self, name: str, description: str, weight: int = 2) -> bool:
        """Add a user-defined metric. Returns False if name already exists."""
        all_names = self.get_names()
        if name in all_names:
            logger.warning(f"Metric '{name}' already exists")
            return False
        self._user_metrics.append({
            "name": name,
            "description": description,
            "weight": weight
        })
        self._save()
        logger.info(f"Added user metric: {name} (weight={weight})")
        return True

    def update_metric(self, name: str, description: str = None, weight: int = None) -> bool:
        """Update an existing user-defined metric"""
        for m in self._user_metrics:
            if m["name"] == name:
                if description is not None:
                    m["description"] = description
                if weight is not None:
                    m["weight"] = weight
                self._save()
                return True
        logger.warning(f"User metric '{name}' not found for update")
        return False

    def remove_metric(self, name: str) -> bool:
        """Remove a user-defined metric. Cannot remove builtins."""
        builtin_names = [m["name"] for m in BUILTIN_METRICS]
        if name in builtin_names:
            logger.warning(f"Cannot remove builtin metric '{name}'")
            return False
        before = len(self._user_metrics)
        self._user_metrics = [m for m in self._user_metrics if m["name"] != name]
        if len(self._user_metrics) < before:
            self._save()
            return True
        return False

    def merge_request_metrics(self, base: List[Dict], request_metrics: List[Dict]) -> List[Dict]:
        """Merge per-request custom metrics into the base metric list (no persistence)"""
        existing_names = {m["name"] for m in base}
        merged = list(base)
        for m in request_metrics:
            if m.get("name") and m["name"] not in existing_names:
                merged.append({**m, "type": "request_custom"})
        return merged
