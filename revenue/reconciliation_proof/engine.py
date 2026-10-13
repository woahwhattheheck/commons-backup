from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from .common import ProofError, RECEIPT_SCHEMA, _json_value, _parse_utc_z, _sha, _text, validate_spec, MAX_FIELDS_PER_RECORD, _FIELD_RE, _SHA256_RE

def _validate_record(record: Any, *, side: str, index: int, as_of: datetime) -> dict[str, Any]:
    if type(record) is not dict:
        raise ProofError(f"{side}[{index}] must be an object")
    expected = {"record_id", "version", "observed_at", "fields", "evidence_sha256"}
    unknown = sorted(set(record) - expected)
    missing = sorted(expected - set(record))
    if unknown or missing:
        parts = []
        if missing:
            parts.append("missing=" + ",".join(missing))
        if unknown:
            parts.append("unknown=" + ",".join(unknown))
        raise ProofError(f"{side}[{index}] invalid shape ({'; '.join(parts)})")
    record_id = _text(record["record_id"], field=f"{side}[{index}].record_id", max_bytes=512)
    version = record["version"]
    if type(version) is not int or version < 1 or version > 2**31 - 1:
        raise ProofError(f"{side}[{index}].version must be a positive 32-bit integer")
    observed = _parse_utc_z(record["observed_at"], field=f"{side}[{index}].observed_at")
    if observed > as_of:
        raise ProofError(f"{side}[{index}] is future evidence relative to as_of")
    fields = record["fields"]
    if type(fields) is not dict:
        raise ProofError(f"{side}[{index}].fields must be an object")
    if len(fields) > MAX_FIELDS_PER_RECORD:
        raise ProofError(f"{side}[{index}].fields exceeds {MAX_FIELDS_PER_RECORD}")
    clean_fields: dict[str, Any] = {}
    for key, value in fields.items():
        if type(key) is not str or not _FIELD_RE.fullmatch(key):
            raise ProofError(f"{side}[{index}] has invalid field name")
        clean_fields[key] = _json_value(value, field=f"{side}[{index}].fields.{key}")
    evidence_sha = record["evidence_sha256"]
    if type(evidence_sha) is not str or not _SHA256_RE.fullmatch(evidence_sha):
        raise ProofError(f"{side}[{index}].evidence_sha256 must be lowercase SHA-256")
    normalized = {
        "record_id": record_id,
        "version": version,
        "observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fields": clean_fields,
        "evidence_sha256": evidence_sha,
    }
    normalized["record_digest"] = _sha(normalized)
    return normalized


def _index_side(
    records: Any,
    *,
    side: str,
    as_of: datetime,
    max_records: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], int, int, int, list[str]]:
    if type(records) is not list:
        raise ProofError(f"{side} records must be a list")
    if len(records) > max_records:
        raise ProofError(f"{side} exceeds max_records_per_side={max_records}")
    by_id_version: dict[tuple[str, int], dict[str, Any]] = {}
    conflicts: dict[str, list[str]] = {}
    exact_replays = 0
    unique_versions = 0
    conflicting_inputs = 0
    input_digests: list[str] = []
    for index, raw in enumerate(records):
        rec = _validate_record(raw, side=side, index=index, as_of=as_of)
        input_digests.append(rec["record_digest"])
        key = (rec["record_id"], rec["version"])
        prior = by_id_version.get(key)
        if prior is None:
            by_id_version[key] = rec
            unique_versions += 1
        elif prior["record_digest"] == rec["record_digest"]:
            exact_replays += 1
        else:
            conflicting_inputs += 1
            conflicts.setdefault(rec["record_id"], []).append("VERSION_CONFLICT")
    by_id: dict[str, list[dict[str, Any]]] = {}
    for (record_id, _version), rec in by_id_version.items():
        by_id.setdefault(record_id, []).append(rec)
    selected: dict[str, dict[str, Any]] = {}
    for record_id, versions in by_id.items():
        versions.sort(key=lambda rec: rec["version"])
        for prev, nxt in zip(versions, versions[1:]):
            if nxt["observed_at"] < prev["observed_at"]:
                conflicts.setdefault(record_id, []).append("VERSION_TIME_REGRESSION")
        selected[record_id] = versions[-1]
    for record_id, reasons in list(conflicts.items()):
        conflicts[record_id] = sorted(set(reasons))
    return selected, conflicts, exact_replays, unique_versions, conflicting_inputs, sorted(input_digests)


def _row_digest(record_id: str) -> str:
    return hashlib.sha256(record_id.encode("utf-8")).hexdigest()


def build_proof(
    spec: Any,
    left_records: Any,
    right_records: Any,
    *,
    as_of: str,
) -> dict[str, Any]:
    clean_spec = validate_spec(spec)
    as_of_dt = _parse_utc_z(as_of, field="as_of")
    max_records = clean_spec["max_records_per_side"]
    left, left_conflicts, left_replays, left_versions, left_conflicting_inputs, left_input_digests = _index_side(
        left_records, side="left", as_of=as_of_dt, max_records=max_records
    )
    right, right_conflicts, right_replays, right_versions, right_conflicting_inputs, right_input_digests = _index_side(
        right_records, side="right", as_of=as_of_dt, max_records=max_records
    )
    required = set(clean_spec["required_fields"])
    ignored = set(clean_spec["ignored_fields"])
    outcomes: list[dict[str, Any]] = []
    counts = {
        "matched": 0,
        "mismatched": 0,
        "missing_left": 0,
        "missing_right": 0,
        "conflicted": 0,
    }
    all_ids = sorted(set(left) | set(right) | set(left_conflicts) | set(right_conflicts))
    for record_id in all_ids:
        lrec = left.get(record_id)
        rrec = right.get(record_id)
        reasons: list[str] = []
        mismatch_fields: list[str] = []
        reasons.extend(f"LEFT_{r}" for r in left_conflicts.get(record_id, []))
        reasons.extend(f"RIGHT_{r}" for r in right_conflicts.get(record_id, []))
        if lrec is None:
            reasons.append("MISSING_LEFT")
        if rrec is None:
            reasons.append("MISSING_RIGHT")
        if lrec is not None and rrec is not None:
            lfields = lrec["fields"]
            rfields = rrec["fields"]
            missing_required = sorted(
                field for field in required if field not in lfields or field not in rfields
            )
            if missing_required:
                reasons.append("REQUIRED_FIELD_MISSING")
                mismatch_fields.extend(missing_required)
            if clean_spec["require_version_identity"] and lrec["version"] != rrec["version"]:
                reasons.append("VERSION_MISMATCH")
            if (
                clean_spec["require_evidence_identity"]
                and lrec["evidence_sha256"] != rrec["evidence_sha256"]
            ):
                reasons.append("EVIDENCE_MISMATCH")
            comparable = sorted((set(lfields) | set(rfields)) - ignored)
            for field in comparable:
                if field not in lfields or field not in rfields or _sha(lfields[field]) != _sha(rfields[field]):
                    mismatch_fields.append(field)
            if mismatch_fields:
                reasons.append("FIELD_MISMATCH")
        reasons = sorted(set(reasons))
        mismatch_fields = sorted(set(mismatch_fields))
        if not reasons:
            outcome = "MATCH"
            counts["matched"] += 1
        else:
            outcome = "HOLD"
            if "MISSING_LEFT" in reasons:
                counts["missing_left"] += 1
            if "MISSING_RIGHT" in reasons:
                counts["missing_right"] += 1
            if any("CONFLICT" in reason or "REGRESSION" in reason for reason in reasons):
                counts["conflicted"] += 1
            else:
                counts["mismatched"] += 1
        outcomes.append(
            {
                "record_key_sha256": _row_digest(record_id),
                "outcome": outcome,
                "reasons": reasons,
                "mismatch_fields": mismatch_fields,
                "left_version": lrec["version"] if lrec is not None else None,
                "right_version": rrec["version"] if rrec is not None else None,
                "left_digest": lrec["record_digest"] if lrec is not None else None,
                "right_digest": rrec["record_digest"] if rrec is not None else None,
            }
        )
    status = "RECONCILED_FOR_HUMAN_REVIEW" if outcomes and counts["matched"] == len(outcomes) else "HOLD"
    # Bind every input record, including historical versions, exact replays, and
    # conflicting same-version payloads. Sorting makes input order irrelevant.
    left_manifest = left_input_digests
    right_manifest = right_input_digests
    payload: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "profile": clean_spec["profile"],
        "status": status,
        "as_of": as_of,
        "spec_sha256": _sha(clean_spec),
        "input_manifest_sha256": _sha({"left": left_manifest, "right": right_manifest}),
        "counts": {
            **counts,
            "left_input": len(left_records),
            "right_input": len(right_records),
            "left_unique_versions": left_versions,
            "right_unique_versions": right_versions,
            "left_exact_replays": left_replays,
            "right_exact_replays": right_replays,
            "left_conflicting_inputs": left_conflicting_inputs,
            "right_conflicting_inputs": right_conflicting_inputs,
            "record_keys": len(outcomes),
        },
        "outcomes": outcomes,
        "authority": {
            "buyer_acceptance": False,
            "production_release": False,
            "data_migration": False,
            "external_transmission": False,
            "payment": False,
            "recognized_revenue": False,
        },
    }
    payload["receipt_sha256"] = _sha(payload)
    return payload


