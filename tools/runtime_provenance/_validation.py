"""Structural validation helpers for fleet runtime provenance records."""

from __future__ import annotations

from typing import Any

from ._model import (
    EVIDENCE_KINDS, LIFECYCLES, PROBE_RESULTS, RegistryError, UNKNOWN,
    _REQUIRED_RECORD_KEYS, _RUNTIME_ID_RE, _contains_secret_like_data,
    _parse_time, _require_exact_type, _require_nonempty_string, _validate_commitment,
)

def _validate_record_shape(record: Any, index: int) -> dict[str, Any]:
    label = f"records[{index}]"
    record = _require_exact_type(record, dict, label)
    if set(record) != _REQUIRED_RECORD_KEYS:
        missing = sorted(_REQUIRED_RECORD_KEYS - set(record))
        extra = sorted(set(record) - _REQUIRED_RECORD_KEYS)
        raise RegistryError(f"{label}: key mismatch missing={missing} extra={extra}")

    runtime_id = _require_nonempty_string(record["runtime_id"], f"{label}.runtime_id")
    if not _RUNTIME_ID_RE.fullmatch(runtime_id):
        raise RegistryError(f"{label}.runtime_id: invalid stable id")

    provider_ids = _require_exact_type(record["provider_ids"], dict, f"{label}.provider_ids")
    if not provider_ids:
        raise RegistryError(f"{label}.provider_ids: at least one stable provider id required")
    for key, value in provider_ids.items():
        _require_nonempty_string(key, f"{label}.provider_ids key")
        value = _require_nonempty_string(value, f"{label}.provider_ids.{key}")
        if value == UNKNOWN:
            raise RegistryError(f"{label}.provider_ids.{key}: stable provider id cannot be UNKNOWN")

    for key in (
        "custodian",
        "runtime_surface",
        "config_location",
        "deployed_generation",
        "decision_contract",
        "deployment_at",
        "evidence_at",
        "lifecycle",
    ):
        _require_nonempty_string(record[key], f"{label}.{key}")

    if record["lifecycle"] not in LIFECYCLES:
        raise RegistryError(f"{label}.lifecycle: unsupported value")

    _validate_commitment(record["source_commitment"], f"{label}.source_commitment")
    _validate_commitment(record["config_commitment"], f"{label}.config_commitment")

    trigger = _require_exact_type(record["trigger"], dict, f"{label}.trigger")
    if set(trigger) != {"mechanism", "cadence"}:
        raise RegistryError(f"{label}.trigger: keys must be exactly mechanism,cadence")
    _require_nonempty_string(trigger["mechanism"], f"{label}.trigger.mechanism")
    _require_nonempty_string(trigger["cadence"], f"{label}.trigger.cadence")

    authority_surfaces = _require_exact_type(
        record["authority_surfaces"], list, f"{label}.authority_surfaces"
    )
    for surface in authority_surfaces:
        _require_nonempty_string(surface, f"{label}.authority_surfaces[]")
    if len(authority_surfaces) != len(set(authority_surfaces)):
        raise RegistryError(f"{label}.authority_surfaces: duplicates forbidden")

    probe = _require_exact_type(record["probe"], dict, f"{label}.probe")
    if set(probe) != {"suite", "generation", "observed_at", "result"}:
        raise RegistryError(
            f"{label}.probe: keys must be exactly suite,generation,observed_at,result"
        )
    _require_nonempty_string(probe["suite"], f"{label}.probe.suite")
    _require_nonempty_string(probe["generation"], f"{label}.probe.generation")
    probe_result = _require_nonempty_string(probe["result"], f"{label}.probe.result")
    if probe_result not in PROBE_RESULTS:
        raise RegistryError(f"{label}.probe.result: unsupported value")
    if probe["observed_at"] is not None:
        _parse_time(probe["observed_at"], f"{label}.probe.observed_at")

    evidence = _require_exact_type(record["evidence"], list, f"{label}.evidence")
    seen_evidence = set()
    for ev_index, item in enumerate(evidence):
        ev_label = f"{label}.evidence[{ev_index}]"
        item = _require_exact_type(item, dict, ev_label)
        if set(item) != {"kind", "ref", "observed_at", "generation"}:
            raise RegistryError(
                f"{ev_label}: keys must be exactly kind,ref,observed_at,generation"
            )
        kind = _require_nonempty_string(item["kind"], f"{ev_label}.kind")
        if kind not in EVIDENCE_KINDS:
            raise RegistryError(f"{ev_label}.kind: unsupported value")
        for key in ("ref", "observed_at", "generation"):
            value = _require_nonempty_string(item[key], f"{ev_label}.{key}")
            if value == UNKNOWN:
                raise RegistryError(f"{ev_label}.{key}: evidence rows must be concrete")
        _parse_time(item["observed_at"], f"{ev_label}.observed_at")
        fingerprint = (item["kind"], item["ref"], item["observed_at"], item["generation"])
        if fingerprint in seen_evidence:
            raise RegistryError(f"{ev_label}: duplicate evidence row")
        seen_evidence.add(fingerprint)

    secret_hit = _contains_secret_like_data(record, label)
    if secret_hit:
        raise RegistryError(secret_hit)
    return record


def _unknown(value: Any) -> bool:
    if value == UNKNOWN:
        return True
    if type(value) is dict and value == {"kind": UNKNOWN, "value": UNKNOWN}:
        return True
    return False


def _critical_unknowns(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    scalar_fields = (
        "custodian",
        "runtime_surface",
        "config_location",
        "deployed_generation",
        "decision_contract",
        "deployment_at",
        "evidence_at",
    )
    for key in scalar_fields:
        if _unknown(record[key]):
            reasons.append(f"UNKNOWN_{key.upper()}")
    if _unknown(record["source_commitment"]):
        reasons.append("UNKNOWN_SOURCE_COMMITMENT")
    if _unknown(record["config_commitment"]):
        reasons.append("UNKNOWN_CONFIG_COMMITMENT")
    if record["trigger"]["mechanism"] == UNKNOWN:
        reasons.append("UNKNOWN_TRIGGER_MECHANISM")
    if record["trigger"]["cadence"] == UNKNOWN:
        reasons.append("UNKNOWN_TRIGGER_CADENCE")
    if not record["authority_surfaces"] or UNKNOWN in record["authority_surfaces"]:
        reasons.append("UNKNOWN_AUTHORITY_SURFACES")
    if record["probe"]["suite"] == UNKNOWN:
        reasons.append("UNKNOWN_PROBE_SUITE")
    if record["probe"]["generation"] == UNKNOWN:
        reasons.append("UNKNOWN_PROBE_GENERATION")
    if record["probe"]["observed_at"] is None:
        reasons.append("UNKNOWN_PROBE_TIME")
    if record["probe"]["result"] == UNKNOWN:
        reasons.append("UNKNOWN_PROBE_RESULT")
    return reasons

