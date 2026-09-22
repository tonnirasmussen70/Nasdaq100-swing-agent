from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


DEFAULT_VOLATILE_KEYS = frozenset({"generated_at"})


def _strip_keys(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {key: _strip_keys(item, keys) for key, item in value.items() if key not in keys}
    if isinstance(value, list):
        return [_strip_keys(item, keys) for item in value]
    return value


def _load_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def write_json_if_changed(
    path: Path,
    payload: dict[str, Any],
    volatile_keys: Iterable[str] = DEFAULT_VOLATILE_KEYS,
) -> tuple[dict[str, Any], bool]:
    """Write a report only when its semantic payload changed.

    Volatile fields are ignored recursively when comparing against the existing
    report. The existing timestamp is therefore preserved across no-op polling
    runs instead of creating repository churn every few minutes.
    """
    ignored = set(volatile_keys)
    ignored.add("generated_at")
    existing = _load_object(path)

    if existing is not None and _strip_keys(existing, ignored) == _strip_keys(payload, ignored):
        return existing, False

    output = dict(payload)
    output["generated_at"] = datetime.now().astimezone().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output, True
