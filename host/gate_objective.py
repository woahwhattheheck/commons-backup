"""Strict, versioned paired-gate objective loader and reducer.

Experiments should import this module instead of restating the score direction or
candidate/control subtraction convention in prose.  The returned receipt binds
its result to the exact objective bytes via SHA-256.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable, Mapping, Any


SCHEMA = "commons-gate-objective/v1"


class ObjectiveError(ValueError):
    """Raised when an objective or paired score row is not strict enough to use."""


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ObjectiveError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ObjectiveError(f"{where} keys mismatch: missing={missing} extra={extra}")


def _strict_text(value: Any, where: str) -> str:
    if type(value) is not str or not value:
        raise ObjectiveError(f"{where} must be a non-empty string")
    return value


@dataclass(frozen=True)
class GateObjective:
    schema: str
    objective_id: str
    score_unit: str
    direction: str
    candidate_field: str
    control_field: str
    delta: str
    primary: str
    counts: tuple[str, str, str]
    sample_size: str
    sha256: str


def parse_objective_bytes(raw: bytes) -> GateObjective:
    """Parse one objective definition, rejecting ambiguity and schema drift."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ObjectiveError("objective must be UTF-8") from exc
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except json.JSONDecodeError as exc:
        raise ObjectiveError(f"invalid objective JSON: {exc.msg}") from exc
    if type(data) is not dict:
        raise ObjectiveError("objective root must be an object")

    _exact_keys(
        data,
        {"schema", "objective_id", "score_unit", "direction", "pairing", "summary"},
        "objective",
    )
    if data["schema"] != SCHEMA:
        raise ObjectiveError(f"unsupported objective schema: {data['schema']!r}")
    objective_id = _strict_text(data["objective_id"], "objective_id")
    score_unit = _strict_text(data["score_unit"], "score_unit")
    if data["direction"] != "maximize":
        raise ObjectiveError("v1 direction must be 'maximize'")

    pairing = data["pairing"]
    if type(pairing) is not dict:
        raise ObjectiveError("pairing must be an object")
    _exact_keys(pairing, {"candidate_field", "control_field", "delta"}, "pairing")
    candidate_field = _strict_text(pairing["candidate_field"], "pairing.candidate_field")
    control_field = _strict_text(pairing["control_field"], "pairing.control_field")
    if candidate_field == control_field:
        raise ObjectiveError("candidate_field and control_field must differ")
    if pairing["delta"] != "candidate_minus_control":
        raise ObjectiveError("v1 delta must be 'candidate_minus_control'")

    summary = data["summary"]
    if type(summary) is not dict:
        raise ObjectiveError("summary must be an object")
    _exact_keys(summary, {"primary", "counts", "sample_size"}, "summary")
    if summary["primary"] != "mean_delta":
        raise ObjectiveError("v1 primary must be 'mean_delta'")
    counts = summary["counts"]
    if type(counts) is not list or counts != ["better", "equal", "worse"]:
        raise ObjectiveError("v1 counts must be ['better', 'equal', 'worse']")
    if summary["sample_size"] != "pairs":
        raise ObjectiveError("v1 sample_size must be 'pairs'")

    return GateObjective(
        schema=SCHEMA,
        objective_id=objective_id,
        score_unit=score_unit,
        direction="maximize",
        candidate_field=candidate_field,
        control_field=control_field,
        delta="candidate_minus_control",
        primary="mean_delta",
        counts=("better", "equal", "worse"),
        sample_size="pairs",
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_objective(path: str | Path) -> GateObjective:
    return parse_objective_bytes(Path(path).read_bytes())


def _finite_number(value: Any, where: str) -> float:
    # bool is a subclass of int in Python and must not silently become 0/1 score.
    if type(value) not in (int, float):
        raise ObjectiveError(f"{where} must be an int or float, not {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ObjectiveError(f"{where} must be finite")
    return number


def reduce_pairs(objective: GateObjective, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce paired evaluator scores under the exact declared objective."""
    deltas: list[float] = []
    better = equal = worse = 0
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ObjectiveError(f"row[{index}] must be an object")
        if objective.candidate_field not in row:
            raise ObjectiveError(f"row[{index}] missing {objective.candidate_field!r}")
        if objective.control_field not in row:
            raise ObjectiveError(f"row[{index}] missing {objective.control_field!r}")
        candidate = _finite_number(row[objective.candidate_field], f"row[{index}].{objective.candidate_field}")
        control = _finite_number(row[objective.control_field], f"row[{index}].{objective.control_field}")
        delta = candidate - control
        if not math.isfinite(delta):
            raise ObjectiveError(f"row[{index}] delta is not finite")
        deltas.append(delta)
        if delta > 0:
            better += 1
        elif delta < 0:
            worse += 1
        else:
            equal += 1

    if not deltas:
        raise ObjectiveError("at least one paired row is required")

    total = math.fsum(deltas)
    mean = total / len(deltas)
    if not math.isfinite(total) or not math.isfinite(mean):
        raise ObjectiveError("aggregate is not finite")
    return {
        "schema": "commons-gate-objective-receipt/v1",
        "objective_id": objective.objective_id,
        "objective_sha256": objective.sha256,
        "score_unit": objective.score_unit,
        "direction": objective.direction,
        "sample_size": len(deltas),
        "sum_delta": total,
        "mean_delta": mean,
        "better": better,
        "equal": equal,
        "worse": worse,
    }
