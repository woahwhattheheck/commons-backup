from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

SOURCES = {"district_gage", "usgs_gage", "noaa_rainfall", "noaa_coastal", "operator", "model"}
MODELS = {"StormWise", "SWMM", "HEC-RAS"}


def _reject_non_scalar_unicode(v: Any, name: str = "value") -> None:
    if isinstance(v, str):
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in v):
            raise ValueError(f"{name} contains non-scalar Unicode")
        return
    if isinstance(v, list):
        for item in v:
            _reject_non_scalar_unicode(item, name)
        return
    if isinstance(v, dict):
        for key, value in v.items():
            _reject_non_scalar_unicode(key, name)
            _reject_non_scalar_unicode(value, name)


def stable_json(v: Any) -> str:
    _reject_non_scalar_unicode(v)
    try:
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("value is not canonical JSON") from exc


def sha(v: Any) -> str:
    _reject_non_scalar_unicode(v)
    try:
        payload = v if isinstance(v, str) else stable_json(v)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    except UnicodeError as exc:
        raise ValueError("value contains invalid Unicode") from exc


def text(v: Any, name: str, max_len: int = 256) -> str:
    if not isinstance(v, str):
        raise ValueError(f"{name} invalid")
    _reject_non_scalar_unicode(v, name)
    value = v.strip()
    if not value or len(value) > max_len:
        raise ValueError(f"{name} invalid")
    return value


def _datetime(v: Any, name: str) -> datetime:
    s = text(v, name, 64)
    try:
        value = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601") from exc
    if value.tzinfo is None:
        raise ValueError(f"{name} needs timezone")
    return value.astimezone(timezone.utc)


def instant(v: Any, name: str) -> str:
    return _datetime(v, name).isoformat().replace("+00:00", "Z")


def _hash_hex(v: Any, name: str) -> str:
    value = text(v, name, 64).lower()
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be sha256 hex")
    return value


def _strict_int(v: Any, name: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if type(v) is not int:
        raise ValueError(f"{name} must be integer")
    if minimum is not None and v < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and v > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return v


def normalize_input(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("input must be object")
    required = {"source", "source_id", "observed_at", "fetched_at", "payload_hash"}
    allowed = required | {"input_id"}
    if not required.issubset(raw) or set(raw) - allowed:
        raise ValueError("input fields invalid")
    source = text(raw.get("source"), "source", 32)
    if source not in SOURCES:
        raise ValueError("unsupported source")
    observed = instant(raw.get("observed_at"), "observed_at")
    fetched = instant(raw.get("fetched_at"), "fetched_at")
    if _datetime(fetched, "fetched_at") < _datetime(observed, "observed_at"):
        raise ValueError("fetched_at precedes observed_at")
    out = {
        "source": source,
        "source_id": text(raw.get("source_id"), "source_id", 160),
        "observed_at": observed,
        "fetched_at": fetched,
        "payload_hash": _hash_hex(raw.get("payload_hash"), "payload_hash"),
    }
    out["input_id"] = sha(out)
    if "input_id" in raw and _hash_hex(raw.get("input_id"), "input_id") != out["input_id"]:
        raise ValueError("input_id does not match input")
    return out


def _normalize_limits(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise ValueError("max_age_minutes must be object")
    limits: dict[str, int] = {}
    for source, value in raw.items():
        if source not in SOURCES:
            raise ValueError("freshness limit has unsupported source")
        limits[source] = _strict_int(value, f"max_age_minutes[{source}]", minimum=1)
    return dict(sorted(limits.items()))


def assess_freshness(
    inputs: Iterable[dict[str, Any]], *, as_of: str, max_age_minutes: dict[str, int]
) -> dict[str, Any]:
    as_of_value = instant(as_of, "as_of")
    now = _datetime(as_of_value, "as_of")
    limits = _normalize_limits(max_age_minutes)
    try:
        rows = [normalize_input(x) for x in inputs]
    except TypeError as exc:
        raise ValueError("inputs must be iterable") from exc
    stale: list[dict[str, Any]] = []
    if not rows:
        stale.append({"reason": "NO_INPUTS"})
    for row in rows:
        observed = _datetime(row["observed_at"], "observed_at")
        fetched = _datetime(row["fetched_at"], "fetched_at")
        age = (now - observed).total_seconds() / 60
        limit = limits.get(row["source"])
        if observed > now or fetched > now:
            stale.append(
                {
                    "input_id": row["input_id"],
                    "source": row["source"],
                    "age_minutes": age,
                    "limit_minutes": limit,
                    "reason": "EVIDENCE_AFTER_AS_OF",
                }
            )
        elif limit is None or age > limit:
            stale.append(
                {
                    "input_id": row["input_id"],
                    "source": row["source"],
                    "age_minutes": age,
                    "limit_minutes": limit,
                    "reason": "MISSING_LIMIT" if limit is None else "OUTSIDE_FRESHNESS_WINDOW",
                }
            )
    result = {
        "as_of": as_of_value,
        "max_age_minutes": limits,
        "inputs": rows,
        "stale": stale,
        "status": "pass" if not stale else "review_required",
    }
    result["evidence_hash"] = sha(result)
    return result


def validate_freshness(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("freshness result must be object")
    required = {"as_of", "max_age_minutes", "inputs", "stale", "status", "evidence_hash"}
    if set(raw) != required:
        raise ValueError("freshness result fields invalid")
    expected = assess_freshness(
        raw["inputs"], as_of=raw["as_of"], max_age_minutes=raw["max_age_minutes"]
    )
    if stable_json(raw) != stable_json(expected):
        raise ValueError("freshness result does not match bound evidence")
    return expected


def build_scenario(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("scenario must be object")
    required = {"scenario_id", "kind", "parameters", "created_at"}
    allowed = required | {"authority", "scenario_hash"}
    if not required.issubset(raw) or set(raw) - allowed:
        raise ValueError("scenario fields invalid")
    kind = text(raw.get("kind"), "kind", 40)
    if kind not in {"baseline", "rainfall_override", "structure_operation", "temporary_pump"}:
        raise ValueError("unsupported scenario")
    params = raw.get("parameters")
    if not isinstance(params, dict):
        raise ValueError("parameters must be object")
    json.loads(stable_json(params))
    out = {
        "scenario_id": text(raw.get("scenario_id"), "scenario_id", 120),
        "kind": kind,
        "parameters": params,
        "created_at": instant(raw.get("created_at"), "created_at"),
        "authority": "analytical_scenario_only",
    }
    out["scenario_hash"] = sha(out)
    if "authority" in raw and raw.get("authority") != out["authority"]:
        raise ValueError("scenario authority mismatch")
    if "scenario_hash" in raw and _hash_hex(raw.get("scenario_hash"), "scenario_hash") != out["scenario_hash"]:
        raise ValueError("scenario_hash does not match scenario")
    return out


def build_run_manifest(
    *,
    run_id: str,
    model_name: str,
    model_hash: str,
    horizon_hours: int,
    interval_minutes: int,
    inputs: list[dict[str, Any]],
    scenario: dict[str, Any],
    output_hash: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    if model_name not in MODELS:
        raise ValueError("unsupported model family")
    horizon = _strict_int(horizon_hours, "horizon_hours", minimum=72)
    interval = _strict_int(interval_minutes, "interval_minutes", minimum=1, maximum=60)
    normalized_inputs = sorted((normalize_input(x) for x in inputs), key=lambda x: x["input_id"])
    if not normalized_inputs:
        raise ValueError("run requires at least one input")
    input_ids = [x["input_id"] for x in normalized_inputs]
    if len(input_ids) != len(set(input_ids)):
        raise ValueError("duplicate run input")
    scen = build_scenario(scenario)
    start = instant(started_at, "started_at")
    end = instant(completed_at, "completed_at")
    if _datetime(end, "completed_at") < _datetime(start, "started_at"):
        raise ValueError("completion before start")
    manifest = {
        "run_id": text(run_id, "run_id", 160),
        "model_name": model_name,
        "model_hash": _hash_hex(model_hash, "model_hash"),
        "horizon_hours": horizon,
        "interval_minutes": interval,
        "inputs": input_ids,
        "scenario_hash": scen["scenario_hash"],
        "output_hash": _hash_hex(output_hash, "output_hash"),
        "started_at": start,
        "completed_at": end,
        "authority": "forecast_evidence_only",
    }
    manifest["manifest_hash"] = sha(manifest)
    return manifest


def validate_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("manifest must be object")
    required = {
        "run_id", "model_name", "model_hash", "horizon_hours", "interval_minutes",
        "inputs", "scenario_hash", "output_hash", "started_at", "completed_at",
        "authority", "manifest_hash",
    }
    if set(raw) != required:
        raise ValueError("manifest fields invalid")
    if raw.get("model_name") not in MODELS:
        raise ValueError("unsupported model family")
    inputs = raw.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("manifest inputs must be non-empty list")
    input_ids = [_hash_hex(value, "input_id") for value in inputs]
    if len(input_ids) != len(set(input_ids)):
        raise ValueError("duplicate manifest input")
    start = instant(raw.get("started_at"), "started_at")
    end = instant(raw.get("completed_at"), "completed_at")
    if _datetime(end, "completed_at") < _datetime(start, "started_at"):
        raise ValueError("completion before start")
    payload = {
        "run_id": text(raw.get("run_id"), "run_id", 160),
        "model_name": raw.get("model_name"),
        "model_hash": _hash_hex(raw.get("model_hash"), "model_hash"),
        "horizon_hours": _strict_int(raw.get("horizon_hours"), "horizon_hours", minimum=72),
        "interval_minutes": _strict_int(raw.get("interval_minutes"), "interval_minutes", minimum=1, maximum=60),
        "inputs": input_ids,
        "scenario_hash": _hash_hex(raw.get("scenario_hash"), "scenario_hash"),
        "output_hash": _hash_hex(raw.get("output_hash"), "output_hash"),
        "started_at": start,
        "completed_at": end,
        "authority": raw.get("authority"),
    }
    if payload["authority"] != "forecast_evidence_only":
        raise ValueError("manifest authority mismatch")
    expected_hash = sha(payload)
    if _hash_hex(raw.get("manifest_hash"), "manifest_hash") != expected_hash:
        raise ValueError("manifest_hash does not match manifest")
    payload["manifest_hash"] = expected_hash
    return payload


def compare_replay(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    left = validate_manifest(a)
    right = validate_manifest(b)
    comparable = ("model_name", "model_hash", "horizon_hours", "interval_minutes", "inputs", "scenario_hash")
    same_inputs = all(left[k] == right[k] for k in comparable)
    same_output = left["output_hash"] == right["output_hash"]
    result = {
        "left": left,
        "right": right,
        "same_inputs": same_inputs,
        "same_output": same_output,
        "status": "pass" if same_inputs and same_output else "review_required",
        "forecast_accuracy_claim": False,
        "safety_decision_authority": False,
    }
    result["evidence_hash"] = sha(result)
    return result


def validate_replay(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("replay result must be object")
    required = {
        "left", "right", "same_inputs", "same_output", "status",
        "forecast_accuracy_claim", "safety_decision_authority", "evidence_hash",
    }
    if set(raw) != required:
        raise ValueError("replay result fields invalid")
    expected = compare_replay(raw["left"], raw["right"])
    if stable_json(raw) != stable_json(expected):
        raise ValueError("replay result does not match bound manifests")
    return expected


def acceptance_gate(freshness: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    fresh = validate_freshness(freshness)
    repeated = validate_replay(replay)
    fresh_input_ids = sorted(row["input_id"] for row in fresh["inputs"])
    left_input_ids = sorted(repeated["left"]["inputs"])
    right_input_ids = sorted(repeated["right"]["inputs"])
    input_binding_status = (
        "pass"
        if fresh_input_ids == left_input_ids == right_input_ids
        else "review_required"
    )
    gate = {
        "freshness_hash": fresh["evidence_hash"],
        "replay_hash": repeated["evidence_hash"],
        "fresh_input_ids": fresh_input_ids,
        "replay_left_input_ids": left_input_ids,
        "replay_right_input_ids": right_input_ids,
        "input_binding_status": input_binding_status,
        "ready_for_owner_review": (
            fresh["status"] == "pass"
            and repeated["status"] == "pass"
            and input_binding_status == "pass"
        ),
        "release_authority": "owner_review_required",
        "forecast_accuracy_authority": False,
        "emergency_action_authority": False,
        "production_release_authority": False,
    }
    gate["gate_hash"] = sha(gate)
    return gate
