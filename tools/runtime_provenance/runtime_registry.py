#!/usr/bin/env python3
"""Fail-closed fleet runtime deployment provenance verifier.

Descriptive evidence only. It never grants provider, outbound, payment, credential,
or deployment authority.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Union

from ._model import (
    MAX_AGE_SECONDS_DEFAULT, SCHEMA, UNKNOWN, RecordAssessment, RegistryError,
    _contains_secret_like_data, _parse_time, _require_exact_type,
    _require_nonempty_string, canonical_json, registry_digest,
)
from ._validation import _critical_unknowns, _unknown, _validate_record_shape


def assess_record(
    record: dict[str, Any],
    *,
    now: datetime,
    max_age_seconds: int = MAX_AGE_SECONDS_DEFAULT,
) -> RecordAssessment:
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise RegistryError("now: timezone-aware UTC datetime required")
    if type(max_age_seconds) is not int or isinstance(max_age_seconds, bool) or max_age_seconds <= 0:
        raise RegistryError("max_age_seconds: positive integer required")

    lifecycle = record["lifecycle"]
    runtime_id = record["runtime_id"]
    reasons = _critical_unknowns(record)

    deployment_at = _parse_time(record["deployment_at"], "deployment_at")
    evidence_at = _parse_time(record["evidence_at"], "evidence_at")
    probe_at = _parse_time(record["probe"]["observed_at"], "probe.observed_at", allow_null=True)

    dated: Iterable[tuple[str, Optional[datetime]]] = (
        ("DEPLOYMENT", deployment_at),
        ("EVIDENCE", evidence_at),
        ("PROBE", probe_at),
    )
    for name, timestamp in dated:
        if timestamp is not None and timestamp > now:
            reasons.append(f"FUTURE_{name}_TIME")

    evidence_rows = record["evidence"]
    for item in evidence_rows:
        ev_time = _parse_time(item["observed_at"], "evidence[].observed_at")
        if ev_time is not None and ev_time > now:
            reasons.append("FUTURE_EVIDENCE_ROW")

    if deployment_at and evidence_at and evidence_at < deployment_at:
        reasons.append("EVIDENCE_PREDATES_DEPLOYMENT")
    if deployment_at and probe_at and probe_at < deployment_at:
        reasons.append("PROBE_PREDATES_DEPLOYMENT")

    if evidence_at and (now - evidence_at).total_seconds() > max_age_seconds:
        reasons.append("STALE_EVIDENCE")
    if probe_at and (now - probe_at).total_seconds() > max_age_seconds:
        reasons.append("STALE_PROBE")

    generation = record["deployed_generation"]
    if record["probe"]["generation"] not in (UNKNOWN, generation):
        reasons.append("PROBE_GENERATION_MISMATCH")

    deployment_evidence = [
        item for item in evidence_rows if item["kind"] in {"DEPLOYMENT_RECEIPT", "PROVIDER_RUNTIME"}
    ]
    probe_evidence = [item for item in evidence_rows if item["kind"] == "BLACK_BOX_PROBE"]
    if not deployment_evidence:
        reasons.append("NO_DEPLOYMENT_EVIDENCE")
    if not probe_evidence:
        reasons.append("NO_BLACK_BOX_EVIDENCE")

    current_deployment_evidence = (
        [item for item in deployment_evidence if item["generation"] == generation]
        if generation != UNKNOWN else []
    )
    current_probe_evidence = (
        [item for item in probe_evidence if item["generation"] == generation]
        if generation != UNKNOWN else []
    )

    if generation != UNKNOWN:
        if deployment_evidence and not current_deployment_evidence:
            reasons.append("DEPLOYMENT_EVIDENCE_GENERATION_MISMATCH")
        if probe_evidence and not current_probe_evidence:
            reasons.append("PROBE_EVIDENCE_GENERATION_MISMATCH")

    if deployment_at is not None:
        if any(
            _parse_time(item["observed_at"], "deployment_evidence.observed_at") < deployment_at
            for item in current_deployment_evidence
        ):
            reasons.append("DEPLOYMENT_EVIDENCE_PREDATES_DEPLOYMENT")
        if any(
            _parse_time(item["observed_at"], "probe_evidence.observed_at") < deployment_at
            for item in current_probe_evidence
        ):
            reasons.append("BLACK_BOX_EVIDENCE_PREDATES_DEPLOYMENT")

    # Fresh top-level timestamps are not independent claims: they must be backed by
    # a typed evidence row for this exact deployed generation at the same instant.
    if evidence_at is not None and generation != UNKNOWN:
        if not any(
            _parse_time(item["observed_at"], "deployment_evidence.observed_at") == evidence_at
            for item in current_deployment_evidence
        ):
            reasons.append("EVIDENCE_TIME_UNBOUND")
    if probe_at is not None and generation != UNKNOWN:
        if not any(
            _parse_time(item["observed_at"], "probe_evidence.observed_at") == probe_at
            for item in current_probe_evidence
        ):
            reasons.append("PROBE_TIME_UNBOUND")

    if record["probe"]["result"] == "FAIL":
        reasons.append("BLACK_BOX_PROBE_FAILED")

    reasons = sorted(set(reasons))
    deployment_proven = lifecycle == "DEPLOYMENT_PROVEN" and not reasons

    if lifecycle == "RETIRED":
        effective = "RETIRED"
        deployment_proven = False
    elif any(reason.startswith("STALE_") for reason in reasons):
        effective = "STALE"
        deployment_proven = False
    elif lifecycle == "DEPLOYMENT_PROVEN" and reasons:
        effective = "UNKNOWN"
        deployment_proven = False
    elif lifecycle == "SOURCE_BOUND":
        source_ready = (
            record["runtime_surface"] != UNKNOWN
            and record["config_location"] != UNKNOWN
            and not _unknown(record["source_commitment"])
            and not _unknown(record["config_commitment"])
        )
        if source_ready:
            effective = "SOURCE_BOUND"
        else:
            effective = "UNKNOWN"
            if "SOURCE_BINDING_INCOMPLETE" not in reasons:
                reasons.append("SOURCE_BINDING_INCOMPLETE")
                reasons.sort()
        deployment_proven = False
    elif lifecycle in {"DECLARED", "UNKNOWN", "STALE"}:
        effective = lifecycle
        deployment_proven = False
    else:
        effective = lifecycle

    return RecordAssessment(
        runtime_id=runtime_id,
        declared_lifecycle=lifecycle,
        effective_lifecycle=effective,
        deployment_proven=deployment_proven,
        reasons=tuple(reasons),
    )


def verify_registry(
    registry: dict[str, Any],
    *,
    now: datetime,
    max_age_seconds: int = MAX_AGE_SECONDS_DEFAULT,
) -> dict[str, Any]:
    registry = _require_exact_type(registry, dict, "registry")
    if set(registry) != {"schema", "registry_generation", "records"}:
        raise RegistryError("registry: keys must be exactly schema,registry_generation,records")
    if registry["schema"] != SCHEMA:
        raise RegistryError(f"registry.schema: expected {SCHEMA}")
    _require_nonempty_string(registry["registry_generation"], "registry.registry_generation")
    records = _require_exact_type(registry["records"], list, "registry.records")
    if not records:
        raise RegistryError("registry.records: at least one record required")

    secret_hit = _contains_secret_like_data(registry, "registry")
    if secret_hit:
        raise RegistryError(secret_hit)

    seen_ids: set[str] = set()
    assessments: list[RecordAssessment] = []
    for index, candidate in enumerate(records):
        record = _validate_record_shape(candidate, index)
        if record["runtime_id"] in seen_ids:
            raise RegistryError(f"duplicate runtime_id: {record['runtime_id']}")
        seen_ids.add(record["runtime_id"])
        assessments.append(assess_record(record, now=now, max_age_seconds=max_age_seconds))

    return {
        "schema": SCHEMA,
        "registry_generation": registry["registry_generation"],
        "registry_sha256": registry_digest(registry),
        "records": [assessment.as_dict() for assessment in assessments],
        "deployment_proven_runtime_ids": [
            assessment.runtime_id for assessment in assessments if assessment.deployment_proven
        ],
        "external_send_authorized": False,
        "provider_mutation_authorized": False,
        "payment_authorized": False,
        "credential_authorized": False,
        "deployment_mutation_authorized": False,
    }


def load_registry(path: Union[str, Path]) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _require_exact_type(payload, dict, "registry")


def main(argv: Optional[list[str]] = None) -> int:
    from ._cli import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
