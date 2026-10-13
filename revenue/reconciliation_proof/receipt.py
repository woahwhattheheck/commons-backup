from __future__ import annotations

from typing import Any, Mapping

from .common import ProofError, RECEIPT_SCHEMA, _PROFILE_RE, _SHA256_RE, _parse_utc_z, _sha

def _exact_keys(obj: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    missing = sorted(expected - set(obj))
    extra = sorted(set(obj) - expected)
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise ProofError(f"{field} invalid shape ({'; '.join(detail)})")


def verify_receipt(receipt: Any) -> bool:
    if type(receipt) is not dict:
        raise ProofError("receipt must be an object")
    _exact_keys(
        receipt,
        {
            "schema",
            "profile",
            "status",
            "as_of",
            "spec_sha256",
            "input_manifest_sha256",
            "counts",
            "outcomes",
            "authority",
            "receipt_sha256",
        },
        field="receipt",
    )
    if receipt["schema"] != RECEIPT_SCHEMA:
        raise ProofError("unsupported receipt schema")
    if type(receipt["profile"]) is not str or not _PROFILE_RE.fullmatch(receipt["profile"]):
        raise ProofError("receipt.profile is invalid")
    if receipt["status"] not in {"RECONCILED_FOR_HUMAN_REVIEW", "HOLD"}:
        raise ProofError("receipt.status is invalid")
    _parse_utc_z(receipt["as_of"], field="receipt.as_of")
    for field in ("spec_sha256", "input_manifest_sha256", "receipt_sha256"):
        if type(receipt[field]) is not str or not _SHA256_RE.fullmatch(receipt[field]):
            raise ProofError(f"receipt.{field} is invalid")
    counts = receipt["counts"]
    if type(counts) is not dict:
        raise ProofError("receipt.counts must be an object")
    expected_counts = {
        "matched",
        "mismatched",
        "missing_left",
        "missing_right",
        "conflicted",
        "left_input",
        "right_input",
        "left_unique_versions",
        "right_unique_versions",
        "left_exact_replays",
        "right_exact_replays",
        "left_conflicting_inputs",
        "right_conflicting_inputs",
        "record_keys",
    }
    _exact_keys(counts, expected_counts, field="receipt.counts")
    for key, value in counts.items():
        if type(value) is not int or value < 0:
            raise ProofError(f"receipt.counts.{key} must be a non-negative integer")
    if counts["left_unique_versions"] + counts["left_exact_replays"] + counts["left_conflicting_inputs"] != counts["left_input"]:
        raise ProofError("left input cardinality is inconsistent")
    if counts["right_unique_versions"] + counts["right_exact_replays"] + counts["right_conflicting_inputs"] != counts["right_input"]:
        raise ProofError("right input cardinality is inconsistent")
    outcomes = receipt["outcomes"]
    if type(outcomes) is not list or len(outcomes) != counts["record_keys"]:
        raise ProofError("receipt.outcomes cardinality is inconsistent")
    observed = {"matched": 0, "mismatched": 0, "missing_left": 0, "missing_right": 0, "conflicted": 0}
    seen_keys: set[str] = set()
    for idx, row in enumerate(outcomes):
        if type(row) is not dict:
            raise ProofError(f"receipt.outcomes[{idx}] must be an object")
        _exact_keys(
            row,
            {
                "record_key_sha256",
                "outcome",
                "reasons",
                "mismatch_fields",
                "left_version",
                "right_version",
                "left_digest",
                "right_digest",
            },
            field=f"receipt.outcomes[{idx}]",
        )
        key = row["record_key_sha256"]
        if type(key) is not str or not _SHA256_RE.fullmatch(key):
            raise ProofError("outcome record key is invalid")
        if key in seen_keys:
            raise ProofError("receipt.outcomes contains duplicate record key")
        seen_keys.add(key)
        if row["outcome"] not in {"MATCH", "HOLD"}:
            raise ProofError("outcome status is invalid")
        for list_field in ("reasons", "mismatch_fields"):
            values = row[list_field]
            if type(values) is not list or any(type(v) is not str for v in values):
                raise ProofError(f"outcome {list_field} must be a string list")
            if values != sorted(set(values)):
                raise ProofError(f"outcome {list_field} must be sorted and unique")
        for version_field in ("left_version", "right_version"):
            version = row[version_field]
            if version is not None and (type(version) is not int or version < 1):
                raise ProofError("outcome version is invalid")
        for digest_field in ("left_digest", "right_digest"):
            digest = row[digest_field]
            if digest is not None and (type(digest) is not str or not _SHA256_RE.fullmatch(digest)):
                raise ProofError("outcome digest is invalid")
        reasons = row["reasons"]
        if row["outcome"] == "MATCH":
            if reasons or row["mismatch_fields"]:
                raise ProofError("MATCH outcome cannot carry reasons or mismatches")
            observed["matched"] += 1
        else:
            if not reasons:
                raise ProofError("HOLD outcome requires at least one reason")
            if "MISSING_LEFT" in reasons:
                observed["missing_left"] += 1
            if "MISSING_RIGHT" in reasons:
                observed["missing_right"] += 1
            if any("CONFLICT" in reason or "REGRESSION" in reason for reason in reasons):
                observed["conflicted"] += 1
            else:
                observed["mismatched"] += 1
    if any(counts[key] != value for key, value in observed.items()):
        raise ProofError("receipt outcome counts are inconsistent")
    authority = receipt["authority"]
    expected_authority = {
        "buyer_acceptance",
        "production_release",
        "data_migration",
        "external_transmission",
        "payment",
        "recognized_revenue",
    }
    if type(authority) is not dict:
        raise ProofError("receipt.authority must be an object")
    _exact_keys(authority, expected_authority, field="receipt.authority")
    if any(value is not False for value in authority.values()):
        raise ProofError("receipt cannot grant external authority")
    expected_status = "RECONCILED_FOR_HUMAN_REVIEW" if counts["record_keys"] and counts["matched"] == counts["record_keys"] else "HOLD"
    if receipt["status"] != expected_status:
        raise ProofError("receipt.status does not match outcomes")
    supplied = receipt["receipt_sha256"]
    unsigned = dict(receipt)
    del unsigned["receipt_sha256"]
    if _sha(unsigned) != supplied:
        raise ProofError("receipt checksum mismatch")
    return True


