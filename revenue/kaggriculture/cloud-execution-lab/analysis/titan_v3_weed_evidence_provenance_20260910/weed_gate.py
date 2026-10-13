# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any, Mapping, Sequence

from weed_model import CLAIM_SCHEMA, GATE_SCHEMA, Decision, Semantics
from weed_receipt import _artifact_hash_map, _validate_receipt_integrity

def gate_claim(receipt: Mapping[str, Any], claim: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": GATE_SCHEMA,
        "claim_id": claim.get("claim_id"),
        "receipt_id": receipt.get("receipt_id"),
        "decision": Decision.INVALID.value,
        "reason_codes": [],
    }
    reasons = _validate_receipt_integrity(receipt)
    if claim.get("schema_version") != CLAIM_SCHEMA:
        reasons.append("CLAIM_SCHEMA_MISMATCH")
    claim_id = claim.get("claim_id")
    if not isinstance(claim_id, str) or not claim_id.strip():
        reasons.append("CLAIM_ID_MISSING")
    if claim.get("receipt_id") != receipt.get("receipt_id"):
        reasons.append("CLAIM_RECEIPT_ID_MISMATCH")
    bound = claim.get("artifact_sha256")
    if not isinstance(bound, Mapping) or dict(bound) != _artifact_hash_map(receipt):
        reasons.append("CLAIM_ARTIFACT_HASH_MISMATCH")
    declared = claim.get("declared_weed_semantics")
    allowed_declared = {"W0", "W1", "LEGACY_PRE_GATE_W1"}
    if declared not in allowed_declared:
        reasons.append("CLAIM_DECLARATION_INVALID")
    labels = claim.get("labels", [])
    if not isinstance(labels, list) or not all(isinstance(item, str) for item in labels):
        reasons.append("CLAIM_LABELS_INVALID")
        labels = []
    label_tokens = {token.upper() for label in labels for token in label.replace("-", "_").split()}
    implicit_w0 = any("R0P0O0" in label.upper().replace("-", "") for label in labels)
    if implicit_w0 and declared != "W0":
        reasons.append("R0P0O0_REQUIRES_EXPLICIT_W0_DECLARATION")
    if "W0" in label_tokens and declared != "W0":
        reasons.append("W0_LABEL_DECLARATION_CONFLICT")
    if "W1" in label_tokens and declared != "W1":
        reasons.append("W1_LABEL_DECLARATION_CONFLICT")

    integrity_reasons = list(reasons)
    if integrity_reasons:
        result["reason_codes"] = sorted(set(integrity_reasons))
        return result

    classification = Semantics(str(receipt["classification"]))
    accepted = (
        (declared == "W0" and classification == Semantics.EXPLICIT_W0)
        or (declared == "W1" and classification == Semantics.EXPLICIT_W1)
        or (
            declared == "LEGACY_PRE_GATE_W1"
            and classification == Semantics.LEGACY_PRE_GATE_W1
        )
    )
    if accepted:
        result["decision"] = Decision.ACCEPT.value
        result["reason_codes"] = ["DECLARATION_MATCHES_BOUND_SEMANTICS"]
    else:
        result["decision"] = Decision.QUARANTINE.value
        result["reason_codes"] = [
            f"DECLARED_{declared}_DOES_NOT_MATCH_{classification.value}",
            "FAIL_CLOSED_EVIDENCE_QUARANTINE",
        ]
    return result


def build_claim(
    receipt: Mapping[str, Any], claim_id: str, declared: str, labels: Sequence[str]
) -> dict[str, Any]:
    return {
        "schema_version": CLAIM_SCHEMA,
        "claim_id": claim_id,
        "declared_weed_semantics": declared,
        "labels": list(labels),
        "receipt_id": receipt.get("receipt_id"),
        "artifact_sha256": _artifact_hash_map(receipt),
    }
