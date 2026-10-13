# SPDX-License-Identifier: Apache-2.0
"""Evidence hook around the exact-current route-reference echo candidate.

The gameplay action is delegated unchanged to the independently reviewed
SOL-ACCRUAL carrier.  The optional evaluator hook exposes only a bounded,
JSON-safe copy of a naturally activated normalization receipt after the action
has returned.  It has no authority to mutate the action or canonical runtime.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
SOURCE_LANE = HERE.parent / "v3-route-reference-echo-sol-accrual"
SOURCE_CANDIDATE = SOURCE_LANE / "candidate.py"
if str(SOURCE_LANE) not in sys.path:
    sys.path.insert(0, str(SOURCE_LANE))

_spec = importlib.util.spec_from_file_location(
    "_titan_route_echo_current_source_candidate", SOURCE_CANDIDATE
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load source candidate: {SOURCE_CANDIDATE}")
_SOURCE = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _SOURCE
_spec.loader.exec_module(_SOURCE)

_LAST_TOKEN: str | None = None


def agent(observation, configuration=None):
    """Return the exact source-candidate action; reset evidence identity per game."""
    global _LAST_TOKEN
    step = observation.get("step")
    if step is None:
        cfg = dict(configuration or {})
        step = int(observation["day"]) * int(cfg.get("turnsPerDay", 24)) + int(
            observation["hour"]
        )
    if int(step) == 0:
        _LAST_TOKEN = None
    return _SOURCE.agent(observation, configuration)


def _json_copy(value: Any) -> Any:
    payload = deepcopy(value)
    # A diagnostic that cannot survive the evaluator's JSON protocol has no
    # evidentiary authority.  Round-trip also rejects NaN and custom objects.
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return json.loads(encoded)


def route_reference_echo_evidence() -> dict[str, Any] | None:
    """Return each affirmative normalization receipt once.

    The patched evaluator calls this hook only after ``agent`` has returned and
    records the result beside the pre-interpreter action digest for that step.
    """
    global _LAST_TOKEN
    canonical_main = getattr(_SOURCE, "_CANONICAL_MAIN", None)
    instance = getattr(canonical_main, "_INSTANCE", None)
    consumer = getattr(instance, "consumer", None)
    diagnostics = getattr(consumer, "diagnostics", None)
    report = (
        diagnostics.get("route_reference_echo")
        if isinstance(diagnostics, Mapping)
        else None
    )
    if not isinstance(report, Mapping) or report.get("changed") is not True:
        return None

    copied = _json_copy(dict(report))
    if copied.get("status") != "NORMALIZED":
        raise RuntimeError("affirmative route-reference receipt is not NORMALIZED")
    if int(copied.get("removed_quantity", 0)) <= 0:
        raise RuntimeError("affirmative route-reference receipt removed no quantity")
    token_bytes = json.dumps(
        copied, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    token = hashlib.sha256(token_bytes).hexdigest()
    if token == _LAST_TOKEN:
        return None
    _LAST_TOKEN = token
    return {
        "schema_version": 1,
        "operation": "titan-v3-route-reference-echo-current-activation-20260910-01",
        "source_operation": copied.get("operation"),
        "controller_route": getattr(getattr(instance, "controller", None), "cur", None),
        "runtime_status": (
            getattr(instance, "diagnostics", {}).get("status")
            if isinstance(getattr(instance, "diagnostics", None), Mapping)
            else None
        ),
        "receipt_sha256": token,
        "report": copied,
    }
