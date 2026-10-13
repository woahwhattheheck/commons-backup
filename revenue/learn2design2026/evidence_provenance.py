"""Recorded provider evidence, independently retrieved from GitHub Actions.

This catalogue is historical evidence, not a signature or live CI attestation.
Admission requires BOTH the exact retained member bytes and the exact canonical
JSON content. A logically equal caller-authored dict cannot mint provenance.
"""
from __future__ import annotations

from typing import Any
from evidence_contract import EvidenceError, canonical_sha256

_RECORDED_RECEIPTS = {
    "serial_v1": {
        "raw": "74ec227c9673c09b26b0f00a6cbb975b67fb3b241a1b237628c96fa8cf8f0c3b",
        "canonical": "74ec227c9673c09b26b0f00a6cbb975b67fb3b241a1b237628c96fa8cf8f0c3b",
    },
    "vectorized_v2": {
        "raw": "8a46fca8106e6113a725919efecefe5b1dd1508bcbca80b82f6c297bd937dcbc",
        "canonical": "8a46fca8106e6113a725919efecefe5b1dd1508bcbca80b82f6c297bd937dcbc",
    },
}

def recorded_provenance(receipt: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, dict) or not isinstance(receipt.get("candidate"), dict):
        raise EvidenceError("receipt candidate must be an object")
    try:
        digest = canonical_sha256(receipt)
    except (TypeError, ValueError, OverflowError, EvidenceError) as exc:
        raise EvidenceError("receipt must be JSON") from exc
    label = receipt["candidate"].get("label")
    expected = _RECORDED_RECEIPTS.get(label)
    raw_digest = getattr(receipt, "_raw_sha256", None)
    if expected is None or digest != expected["canonical"] or raw_digest != expected["raw"]:
        raise EvidenceError(
            "measurement provenance unrecorded; exact retained bytes and canonical content are required"
        )
    return {
        "kind": "RECORDED_GITHUB_ACTIONS_ARTIFACT",
        "historicalEvidence": True,
        "liveCiStatusAttested": False,
        "cryptographicExecutionAttestation": False,
        "repository": "woahwhattheheck/commons",
        "runId": "34938483198",
        "runAttempt": "1",
        "jobId": "104281505774",
        "jobName": "public-development-evidence",
        "observedConclusion": "success",
        "headSha": "36be284452141d26cdff4b74efb8f185b27c4b32",
        "checkoutSha": "a1e6c04b5b73accfe930567b99f094db076b82bc",
        "workflowPath": ".github/workflows/learn2design-public-evidence.yml",
        "workflowGitBlobSha1": "448315c9722dc08c325076bc33a1baab5c886743",
        "artifactId": "10384626623",
        "artifactSha256": "e9a57d1e87adfad905b5617e8b987545a346f461052a2c8d633db310649a3bcb",
        "artifactCreatedAt": "2026-09-15T06:53:43Z",
        "artifactExpiresAt": "2026-09-29T06:53:43Z",
        "receiptRawSha256": raw_digest,
        "receiptCanonicalSha256": digest,
    }
