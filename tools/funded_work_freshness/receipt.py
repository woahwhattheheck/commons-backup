"""Deterministic receipt construction."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from constants import SCHEMA
from evaluation import iso
from models import Candidate


def receipt_hash(receipt: Mapping[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def base_receipt(candidate: Candidate, observed_at: datetime) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "generated_at": iso(observed_at),
        "candidate": {
            "url": candidate.candidate_url,
            "platform": candidate.platform,
            "advertised_amount": candidate.advertised_amount,
            "currency": candidate.currency,
            "canonical_url_hint": candidate.canonical_url,
        },
        "authority": "canonical_github_state",
        "financial_status": "advertised_not_accepted_awarded_or_paid",
        "provider_requests": "read_only",
    }


def finalize(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt["receipt_sha256"] = receipt_hash(receipt)
    return receipt
