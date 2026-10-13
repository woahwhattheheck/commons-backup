from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from revenue.trusted_claim_policy.policy import (
    load_trusted_policy,
    make_packet,
    sha256_bytes,
    sha256_text,
)
from revenue.trusted_evidence_authority.strict_json import canonical_json

UTC = timezone.utc
BASE = datetime(2026, 9, 15, 1, 30, tzinfo=UTC)

def policy_value() -> dict:
    statement = "The submission deadline is 2026-09-16T03:00:00Z."
    optional_statement = "The buyer may split an award across service lines."
    return {
        "schema": "trusted-claim-policy/v1",
        "policy_id": "buyer.alpha.2026-09",
        "issued_at": "2026-09-15T01:10:00Z",
        "valid_from": "2026-09-15T01:00:00Z",
        "valid_before": "2026-09-16T03:00:00Z",
        "period_end": "2026-09-15T01:00:00Z",
        "sources": [
            {
                "source_id": "official.notice",
                "provider": "buyer.alpha",
                "scope": "solicitation.42",
                "resource": "notice.v3",
                "generation": 3,
                "content_sha256": "a" * 64,
                "captured_at": "2026-09-15T01:05:00Z",
                "max_age_seconds": 3600,
                "complete": True,
            },
            {
                "source_id": "official.addenda",
                "provider": "buyer.alpha",
                "scope": "solicitation.42.addenda",
                "resource": "index.v2",
                "generation": 2,
                "content_sha256": "b" * 64,
                "captured_at": "2026-09-15T01:06:00Z",
                "max_age_seconds": 3600,
                "complete": True,
            },
        ],
        "claims": [
            {
                "claim_id": "deadline",
                "statement": statement,
                "statement_sha256": sha256_text(statement),
                "source_ids": ["official.notice", "official.addenda"],
                "required": True,
                "requires_closed_period": True,
            },
            {
                "claim_id": "split-award",
                "statement": optional_statement,
                "statement_sha256": sha256_text(optional_statement),
                "source_ids": ["official.notice"],
                "required": False,
                "requires_closed_period": False,
            },
        ],
    }

def trusted_policy(value: dict | None = None):
    value = policy_value() if value is None else value
    raw = canonical_json(value).encode("utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "policy.json"
        path.write_bytes(raw)
        return load_trusted_policy(path, expected_file_sha256=sha256_bytes(raw))

def source_packet_rows(value: dict | None = None) -> list[dict]:
    value = policy_value() if value is None else value
    return [
        {
            key: row[key]
            for key in (
                "source_id",
                "provider",
                "scope",
                "resource",
                "generation",
                "content_sha256",
                "captured_at",
            )
        }
        for row in value["sources"]
    ]

def claim_packet_rows(value: dict | None = None, *, include_optional: bool = False) -> list[dict]:
    value = policy_value() if value is None else value
    rows = value["claims"] if include_optional else [row for row in value["claims"] if row["required"]]
    return [
        {
            key: row[key]
            for key in ("claim_id", "statement", "statement_sha256", "source_ids")
        }
        for row in rows
    ]

def packet(value: dict | None = None, *, include_optional: bool = False) -> dict:
    value = policy_value() if value is None else value
    return make_packet(
        policy_id=value["policy_id"],
        subject_id="opportunity.42",
        decision_id="qualification.7",
        context={"route": "teaming", "authorized": False},
        sources=source_packet_rows(value),
        claims=claim_packet_rows(value, include_optional=include_optional),
    )
