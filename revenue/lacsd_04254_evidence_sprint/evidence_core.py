"""Deterministic evidence sprint for AI/ML sewer-collection decision logs.

The package evaluates candidate outputs against an abstract synthetic portfolio.
It does not operate sewer infrastructure, dispatch maintenance, or claim field
performance.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

PORTFOLIO_SCHEMA = "lacsd-04254.synthetic-portfolio.v1"
CANDIDATE_SCHEMA = "lacsd-04254.candidate-log.v2"
CANDIDATE_BUILD_SCHEMA = "lacsd-04254.candidate-build.v1"
RECEIPT_SCHEMA = "lacsd-04254.evidence-receipt.v2"
EVENT_SCHEMA = "lacsd-04254.candidate-event.v2"
ALLOWED_DISPOSITIONS = {"ALERT", "CLEAR", "NO_DATA"}


class ValidationError(ValueError):
    """Raised when an artifact violates the strict evidence contract."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _strict_keys(value: Mapping[str, Any], required: set[str], *, label: str) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing or extra:
        raise ValidationError(f"{label} keys invalid; missing={missing}, extra={extra}")


def _str(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValidationError(f"{label} must be a finite number")
    return result


def _hex64(value: Any, *, label: str) -> str:
    value = _str(value, label=label)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValidationError(f"{label} must be lowercase 64-hex")
    return value


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    fault_class: str
    expected_disposition: str
    onset_s: int | None
    max_alert_latency_s: int | None
    interruption_end_s: int | None
    packets: tuple[dict[str, Any], ...]
    stream_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "fault_class": self.fault_class,
            "expected_disposition": self.expected_disposition,
            "onset_s": self.onset_s,
            "max_alert_latency_s": self.max_alert_latency_s,
            "interruption_end_s": self.interruption_end_s,
            "packets": list(self.packets),
            "stream_sha256": self.stream_sha256,
        }


def _packets(values: Sequence[tuple[str, int, float, float, bool]]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "packet_id": packet_id,
            "observed_at_s": observed_at_s,
            "flow_index": float(flow_index),
            "rain_index": float(rain_index),
            "transport_available": bool(transport_available),
        }
        for packet_id, observed_at_s, flow_index, rain_index, transport_available in values
    )


def _scenario(
    scenario_id: str,
    fault_class: str,
    expected: str,
    values: Sequence[tuple[str, int, float, float, bool]],
    *,
    onset_s: int | None = None,
    max_alert_latency_s: int | None = None,
    interruption_end_s: int | None = None,
) -> Scenario:
    packets = _packets(values)
    return Scenario(
        scenario_id=scenario_id,
        fault_class=fault_class,
        expected_disposition=expected,
        onset_s=onset_s,
        max_alert_latency_s=max_alert_latency_s,
        interruption_end_s=interruption_end_s,
        packets=packets,
        stream_sha256=canonical_sha256(list(packets)),
    )


def build_portfolio() -> dict[str, Any]:
    """Return the fixed deterministic 10-scenario synthetic portfolio."""
    scenarios = (
        _scenario(
            "normal-diurnal-01", "normal_diurnal", "CLEAR",
            [("n1-0", 0, 0.45, 0.0, True), ("n1-1", 300, 0.72, 0.0, True), ("n1-2", 600, 0.52, 0.0, True)],
        ),
        _scenario(
            "normal-diurnal-02", "normal_diurnal", "CLEAR",
            [("n2-0", 0, 0.50, 0.0, True), ("n2-1", 300, 0.80, 0.0, True), ("n2-2", 600, 0.58, 0.0, True)],
        ),
        _scenario(
            "blockage-drift-01", "blockage_drift", "ALERT",
            [("b1-0", 0, 0.48, 0.0, True), ("b1-1", 300, 0.62, 0.0, True), ("b1-2", 480, 1.30, 0.0, True), ("b1-3", 540, 1.55, 0.0, True), ("b1-4", 720, 1.70, 0.0, True)],
            onset_s=480, max_alert_latency_s=120,
        ),
        _scenario(
            "blockage-drift-02", "blockage_drift", "ALERT",
            [("b2-0", 0, 0.44, 0.0, True), ("b2-1", 420, 0.71, 0.0, True), ("b2-2", 600, 1.42, 0.0, True), ("b2-3", 720, 1.66, 0.0, True)],
            onset_s=600, max_alert_latency_s=180,
        ),
        _scenario(
            "storm-ii-01", "storm_inflow_infiltration", "ALERT",
            [("s1-0", 0, 0.50, 0.0, True), ("s1-1", 300, 0.75, 0.9, True), ("s1-2", 420, 1.80, 1.0, True), ("s1-3", 540, 2.10, 0.9, True)],
            onset_s=420, max_alert_latency_s=180,
        ),
        _scenario(
            "storm-ii-02", "storm_inflow_infiltration", "ALERT",
            [("s2-0", 0, 0.55, 0.0, True), ("s2-1", 360, 0.90, 0.8, True), ("s2-2", 480, 1.95, 1.0, True), ("s2-3", 660, 2.20, 0.7, True)],
            onset_s=480, max_alert_latency_s=240,
        ),
        _scenario(
            "sensor-dropout-01", "sensor_dropout", "NO_DATA",
            [("d1-0", 0, 0.48, 0.0, True), ("d1-1", 300, 0.52, 0.0, True), ("d1-2", 600, 0.0, 0.0, False)],
        ),
        _scenario(
            "sensor-dropout-02", "sensor_dropout", "NO_DATA",
            [("d2-0", 0, 0.51, 0.0, True), ("d2-1", 300, 0.54, 0.0, True), ("d2-2", 600, 0.0, 0.0, False), ("d2-3", 900, 0.0, 0.0, False)],
        ),
        _scenario(
            "duplicate-replay-01", "duplicate_packet_replay", "ALERT",
            [("r1-0", 0, 0.46, 0.0, True), ("r1-1", 300, 0.70, 0.0, True), ("r1-2", 480, 1.60, 0.0, True), ("r1-2", 481, 1.60, 0.0, True), ("r1-2", 482, 1.60, 0.0, True)],
            onset_s=480, max_alert_latency_s=120,
        ),
        _scenario(
            "recovery-after-interruption-01", "transport_interruption_recovery", "ALERT",
            [("x1-0", 0, 0.47, 0.0, True), ("x1-1", 420, 1.50, 0.0, False), ("x1-1", 500, 1.50, 0.0, False), ("x1-1", 560, 1.50, 0.0, True), ("x1-2", 620, 1.62, 0.0, True)],
            onset_s=420, max_alert_latency_s=240, interruption_end_s=560,
        ),
    )
    data = {
        "schema": PORTFOLIO_SCHEMA,
        "portfolio_id": "lacsd-04254-synthetic-evidence-v1",
        "purpose": "software evidence mechanics only; not field/challenge performance",
        "scenarios": [scenario.to_dict() for scenario in scenarios],
    }
    data["portfolio_sha256"] = canonical_sha256(data)
    return data


def candidate_build_record(
    *, candidate_id: str, model_id: str, model_version: str, artifact_sha256: str
) -> dict[str, str]:
    """Return the canonical build-identity object committed by every event."""
    return {
        "schema": CANDIDATE_BUILD_SCHEMA,
        "candidate_id": candidate_id,
        "model_id": model_id,
        "model_version": model_version,
        "artifact_sha256": artifact_sha256,
    }


def candidate_build_sha256(
    *, candidate_id: str, model_id: str, model_version: str, artifact_sha256: str
) -> str:
    return canonical_sha256(
        candidate_build_record(
            candidate_id=candidate_id,
            model_id=model_id,
            model_version=model_version,
            artifact_sha256=artifact_sha256,
        )
    )


def _validate_candidate(candidate: Mapping[str, Any], portfolio: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        raise ValidationError("candidate must be an object")
    required = {
        "schema", "candidate_id", "model_id", "model_version",
        "artifact_sha256", "candidate_build_sha256", "portfolio_sha256", "events",
    }
    _strict_keys(candidate, required, label="candidate")
    if candidate["schema"] != CANDIDATE_SCHEMA:
        raise ValidationError("unsupported candidate schema")

    candidate_id = _str(candidate["candidate_id"], label="candidate_id")
    model_id = _str(candidate["model_id"], label="model_id")
    model_version = _str(candidate["model_version"], label="model_version")
    artifact_sha = _hex64(candidate["artifact_sha256"], label="artifact_sha256")
    supplied_build_sha = _hex64(candidate["candidate_build_sha256"], label="candidate_build_sha256")
    expected_build_sha = candidate_build_sha256(
        candidate_id=candidate_id,
        model_id=model_id,
        model_version=model_version,
        artifact_sha256=artifact_sha,
    )
    if supplied_build_sha != expected_build_sha:
        raise ValidationError("candidate_build_sha256 does not match exact candidate/model/artifact identity")

    portfolio_sha = _hex64(candidate["portfolio_sha256"], label="portfolio_sha256")
    if portfolio_sha != portfolio["portfolio_sha256"]:
        raise ValidationError("candidate portfolio_sha256 does not match exact synthetic portfolio")
    events = candidate["events"]
    if not isinstance(events, list):
        raise ValidationError("events must be a list")

    scenarios = {row["scenario_id"]: row for row in portfolio["scenarios"]}
    normalized_events: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    effect_bindings: dict[str, tuple[str, str, str]] = {}
    for idx, raw in enumerate(events):
        if not isinstance(raw, Mapping):
            raise ValidationError(f"event[{idx}] must be an object")
        keys = {
            "schema", "event_id", "scenario_id", "source_packet_id", "observed_at_s",
            "disposition", "effect_id", "input_sha256", "candidate_build_sha256",
        }
        _strict_keys(raw, keys, label=f"event[{idx}]")
        if raw["schema"] != EVENT_SCHEMA:
            raise ValidationError(f"event[{idx}] unsupported schema")
        event_id = _str(raw["event_id"], label=f"event[{idx}].event_id")
        if event_id in event_ids:
            raise ValidationError(f"duplicate event_id: {event_id}")
        event_ids.add(event_id)

        event_build_sha = _hex64(
            raw["candidate_build_sha256"], label=f"event[{idx}].candidate_build_sha256"
        )
        if event_build_sha != expected_build_sha:
            raise ValidationError(f"event[{idx}] candidate build identity mismatch")

        scenario_id = _str(raw["scenario_id"], label=f"event[{idx}].scenario_id")
        if scenario_id not in scenarios:
            raise ValidationError(f"event[{idx}] unknown scenario_id: {scenario_id}")
        scenario = scenarios[scenario_id]
        packet_id = _str(raw["source_packet_id"], label=f"event[{idx}].source_packet_id")
        packet_occurrences = [p for p in scenario["packets"] if p["packet_id"] == packet_id]
        if not packet_occurrences:
            raise ValidationError(f"event[{idx}] source_packet_id not present in scenario stream")
        observed = _number(raw["observed_at_s"], label=f"event[{idx}].observed_at_s")
        if observed < 0:
            raise ValidationError(f"event[{idx}].observed_at_s must be >= 0")
        exact_occurrences = [p for p in packet_occurrences if float(p["observed_at_s"]) == observed]
        if not exact_occurrences:
            raise ValidationError(
                f"event[{idx}] observed_at_s must equal an occurrence time for source_packet_id"
            )

        disposition = _str(raw["disposition"], label=f"event[{idx}].disposition")
        if disposition not in ALLOWED_DISPOSITIONS:
            raise ValidationError(f"event[{idx}] invalid disposition: {disposition}")
        if disposition == "NO_DATA" and not any(not p["transport_available"] for p in exact_occurrences):
            raise ValidationError(f"event[{idx}] NO_DATA must bind an unavailable packet occurrence")
        if disposition in {"ALERT", "CLEAR"} and not any(p["transport_available"] for p in exact_occurrences):
            raise ValidationError(f"event[{idx}] {disposition} must bind an available packet occurrence")

        input_sha = _hex64(raw["input_sha256"], label=f"event[{idx}].input_sha256")
        effect_id = raw["effect_id"]
        if disposition == "ALERT":
            effect_id = _str(effect_id, label=f"event[{idx}].effect_id")
            binding = (event_build_sha, scenario_id, input_sha)
            previous = effect_bindings.get(effect_id)
            if previous is not None and previous != binding:
                raise ValidationError(
                    f"effect_id {effect_id!r} reused across distinct build/scenario/input binding"
                )
            effect_bindings[effect_id] = binding
        elif effect_id is not None:
            raise ValidationError(f"event[{idx}] non-ALERT effect_id must be null")

        normalized_events.append({
            "schema": EVENT_SCHEMA,
            "event_id": event_id,
            "scenario_id": scenario_id,
            "source_packet_id": packet_id,
            "observed_at_s": observed,
            "disposition": disposition,
            "effect_id": effect_id,
            "input_sha256": input_sha,
            "candidate_build_sha256": event_build_sha,
        })

    normalized_events.sort(key=lambda e: (e["scenario_id"], e["observed_at_s"], e["event_id"]))
    return {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "model_id": model_id,
        "model_version": model_version,
        "artifact_sha256": artifact_sha,
        "candidate_build_sha256": expected_build_sha,
        "portfolio_sha256": portfolio_sha,
        "events": normalized_events,
    }
