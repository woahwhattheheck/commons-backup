from __future__ import annotations

"""Private adapter for the frozen v1 evidence engine.

The exact predecessor source is stored as non-importable package data so its former
caller-clock ``evaluate(..., evaluated_at=...)`` entry point cannot accidentally be
used as a current-authority API. This adapter executes that frozen source into an
isolated namespace and exposes only a truth-labelled historical replay seam to the
supported wrapper in ``gate.py``.
"""

from datetime import datetime as _DateTime, timezone as _timezone
from pathlib import Path
from typing import Any

HISTORICAL_TEMPORAL_AUTHORITY = "HISTORICAL_INTEGRITY_ONLY"

_SOURCE_PATH = Path(__file__).with_name("_legacy_engine_source.pydata")
_source = _SOURCE_PATH.read_text(encoding="utf-8")
_namespace: dict[str, Any] = {
    "__name__": f"{__name__}._frozen_v1",
    "__file__": str(_SOURCE_PATH),
}
exec(compile(_source, str(_SOURCE_PATH), "exec"), _namespace, _namespace)

GateInputError = _namespace["GateInputError"]


def _parse_utc(value: Any, *, name: str):
    """Compatibility parser without retaining the executed predecessor namespace."""
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > 64
        or not value.endswith("Z")
    ):
        raise GateInputError(f"{name} must be bounded UTC with a trailing Z")
    try:
        parsed = _DateTime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GateInputError(f"{name} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != _timezone.utc.utcoffset(parsed):
        raise GateInputError(f"{name} must be UTC")
    return parsed


def _bind_historical(raw_evaluate, raw_sha256):
    def historical(policy: Any, snapshot: Any, *, evaluated_at: str) -> dict[str, Any]:
        result = raw_evaluate(policy, snapshot, evaluated_at=evaluated_at)
        receipt = result["receipt"]
        receipt["temporal_authority"] = HISTORICAL_TEMPORAL_AUTHORITY
        core = dict(receipt)
        core.pop("receipt_sha256", None)
        receipt["receipt_sha256"] = raw_sha256(core)
        return result

    return historical


_evaluate_historical_at = _bind_historical(
    _namespace["evaluate"],
    _namespace["_sha256"],
)


def evaluate(*args, **kwargs):
    """Fail closed: the frozen engine has no current-authority entry point."""
    raise GateInputError(
        "frozen v1 engine is historical-only; use the supported gate.evaluate current API"
    )


# Drop ordinary module-level handles to the executed predecessor namespace and source
# text. The supported adapter retains only the historical closure above.
del _namespace
del _source
del _bind_historical
