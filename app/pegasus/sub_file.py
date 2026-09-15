from __future__ import annotations

"""
Patch an HTCondor submit file (.sub) in-place with new resource requests.

HTCondor submit files are key = value text files (case-insensitive keys).
A Pegasus-generated submit file looks like:

    universe                = vanilla
    executable              = /usr/bin/pegasus-kickstart
    request_memory          = 4096
    request_disk            = 2048
    request_cpus            = 4
    +MaxRuntime             = 3600
    ...
    queue

This module maps FixProposal.proposed_configuration keys → submit file
attribute names and patches them in-place, preserving all other content.
"""

from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

# FailureContext / FixProposal config key → HTCondor submit attribute
_ATTR_MAP: dict[str, str] = {
    "memory_mb": "request_memory",
    "disk_mb": "request_disk",
    "cpus": "request_cpus",
    "runtime_seconds": "+MaxRuntime",
}


def apply_overlay_to_sub_file(
    sub_path: Path,
    new_config: dict,
) -> dict[str, str]:
    """
    Patch resource request values in an HTCondor submit file.

    For each key in new_config that maps to a known submit attribute:
      - If the attribute already exists in the file, the line is updated.
      - If not, the attribute is inserted immediately before the final
        ``queue`` statement.

    Returns a dict of {htcondor_attr: new_value_str} for every change made.
    Lines beginning with # and blank lines are left untouched.
    """
    text = sub_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    changes: dict[str, str] = {}

    for config_key, raw_value in new_config.items():
        if raw_value is None:
            continue
        htcondor_attr = _ATTR_MAP.get(config_key)
        if htcondor_attr is None:
            continue

        new_value = str(int(raw_value)) if isinstance(raw_value, float) else str(raw_value)
        # Strip leading '+' for matching purposes only
        match_key = htcondor_attr.lstrip("+").lower()

        patched = False
        for idx, line in enumerate(lines):
            stripped = line.strip()
            # Skip comments and blank lines
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue

            raw_key = stripped.split("=", 1)[0].strip().lstrip("+").lower()
            if raw_key == match_key:
                # Preserve original indentation and key casing
                indent = line[: len(line) - len(line.lstrip())]
                original_key = stripped.split("=", 1)[0].rstrip()
                lines[idx] = f"{indent}{original_key} = {new_value}"
                changes[htcondor_attr] = new_value
                patched = True
                break

        if not patched:
            # Attribute missing — insert before the first 'queue' line
            inserted = False
            for idx, line in enumerate(lines):
                if line.strip().lower().startswith("queue"):
                    lines.insert(idx, f"{htcondor_attr} = {new_value}")
                    changes[htcondor_attr] = new_value
                    inserted = True
                    break
            if not inserted:
                # No queue line found — append at end
                lines.append(f"{htcondor_attr} = {new_value}")
                changes[htcondor_attr] = new_value

    sub_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("sub_file_written", path=str(sub_path), changes=changes)
    return changes


def read_resource_requests(sub_path: Path) -> dict[str, int | None]:
    """
    Read current resource request values from a .sub file.

    Returns a dict with keys: memory_mb, disk_mb, cpus, runtime_seconds.
    Values are None when the attribute is absent from the file.
    """
    reverse_map = {v.lstrip("+").lower(): k for k, v in _ATTR_MAP.items()}
    result: dict[str, int | None] = {k: None for k in _ATTR_MAP}

    text = sub_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        raw_key, _, raw_val = stripped.partition("=")
        match_key = raw_key.strip().lstrip("+").lower()
        config_key = reverse_map.get(match_key)
        if config_key:
            try:
                result[config_key] = int(raw_val.strip())
            except (ValueError, TypeError):
                pass

    return result
