"""Canonical receipts for observed ARC3 visual-effect factorization."""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from factorizer import ActionSequence, factor_action, sequence_digest

SCHEMA = "arc3.sage.visual-effect-factorization.v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return sha256(canonical_json(value).encode()).hexdigest()


def build_receipt(seq: ActionSequence) -> dict[str, Any]:
    result = factor_action(seq).to_dict()
    body = {
        "schema": SCHEMA,
        "input_sha256": sequence_digest(seq),
        "result": result,
        "claim_boundary": {
            "unique_physical_causality_claimed": False,
            "official_arc_score_claimed": False,
            "competition_submission_authorized": False,
            "provider_or_device_action_authorized": False,
            "prize_payment_or_revenue_claimed": False,
        },
    }
    return {**body, "receipt": {"payload_sha256": _hash(body), "schema": SCHEMA}}


def verify_receipt(receipt: Any, seq: ActionSequence) -> bool:
    if not isinstance(receipt, dict):
        return False
    marker = receipt.get("receipt")
    if not isinstance(marker, dict) or marker.get("schema") != SCHEMA:
        return False
    body = dict(receipt)
    body.pop("receipt", None)
    if marker.get("payload_sha256") != _hash(body):
        return False
    if body.get("input_sha256") != sequence_digest(seq):
        return False
    if body.get("result") != factor_action(seq).to_dict():
        return False
    boundary = body.get("claim_boundary")
    required_false = (
        "unique_physical_causality_claimed", "official_arc_score_claimed",
        "competition_submission_authorized", "provider_or_device_action_authorized",
        "prize_payment_or_revenue_claimed",
    )
    return isinstance(boundary, dict) and all(boundary.get(k) is False for k in required_false)
