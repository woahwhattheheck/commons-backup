from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from revenue.teaming_conversion import (
    ControlError,
    DuplicateKeyError,
    canonical_bytes,
    compile_current_bytes,
    compile_historical_bytes,
    render_markdown,
    verify_current_bytes,
    verify_integrity_bytes,
)
from revenue.teaming_conversion.assets import asset_descriptor_sha256
from revenue.teaming_conversion.cli import main as cli_main
from revenue.teaming_conversion.common import digest_object, parse_json_bytes, sha256_bytes
from revenue.teaming_conversion.control import CURRENT_MODE, HISTORICAL_MODE
from revenue.teaming_conversion.evidence import evidence_section_digests
from revenue.teaming_conversion.io import read_bounded_regular, write_exclusive_pair
from revenue.teaming_conversion.parse import parse_evidence
from revenue.teaming_conversion.policy import POLICY_SHA256

UTC = timezone.utc
NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)


def ts(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def base_candidate() -> dict:
    return {
        "schema": "teaming-conversion-input/v2",
        "opportunity": {
            "opportunity_id": "opp-acme-1",
            "counterparty_ref": "counterparty-acme",
            "thread_id": "thread-acme-1",
        },
        "requested_asset_ids": ["asset-capability"],
        "required_commitment_ids": ["commit-price"],
    }


def base_evidence() -> dict:
    asset = {
        "asset_id": "asset-capability",
        "title": "Capability summary",
        "version": "v1",
        "sha256": "a" * 64,
        "release_class": "OWNER_APPROVAL_REQUIRED",
        "prep_state": "READY",
        "safe_snippets": ["Current capability summary for owner review."],
        "required_for_followup": True,
    }
    return {
        "schema": "teaming-conversion-retained-evidence/v2",
        "root_id": "root-acme-1",
        "generation": 1,
        "captured_at": ts(NOW - timedelta(minutes=10)),
        "opportunity": {
            "opportunity_id": "opp-acme-1",
            "counterparty_ref": "counterparty-acme",
            "thread_id": "thread-acme-1",
        },
        "counterparty_sender_refs": ["sender-acme"],
        "requirements": {
            "required_asset_ids": ["asset-capability"],
            "required_gate_ids": ["gate-prime"],
            "required_commitment_ids": ["commit-price"],
        },
        "observations": [
            {
                "observation_id": "obs-1",
                "message_ref": "gmail-msg-1",
                "source_class": "GMAIL",
                "sender_ref": "sender-acme",
                "thread_id": "thread-acme-1",
                "received_at": ts(NOW - timedelta(minutes=30)),
                "content_sha256": "1" * 64,
                "supersedes": None,
            }
        ],
        "interpretations": [
            {
                "interpretation_id": "interpretation-1",
                "observation_id": "obs-1",
                "message_ref": "gmail-msg-1",
                "content_sha256": "1" * 64,
                "decision": "POSITIVE_CONTINUE",
                "reviewed_at": ts(NOW - timedelta(minutes=25)),
                "owner_review_ref": "owner-review-1",
                "owner_review_sha256": "2" * 64,
            }
        ],
        "assets": [asset],
        "releases": [
            {
                "release_id": "release-1",
                "asset_id": "asset-capability",
                "asset_version": "v1",
                "asset_sha256": "a" * 64,
                "descriptor_sha256": asset_descriptor_sha256(asset),
                "released_at": ts(NOW - timedelta(minutes=20)),
                "release_ref": "owner-release-1",
                "release_sha256": "3" * 64,
            }
        ],
        "qualification_gates": [
            {
                "gate_id": "gate-prime",
                "mandatory": True,
                "state": "CLEAR",
                "owner_action": "Confirm prime qualification evidence.",
                "decided_at": ts(NOW - timedelta(minutes=20)),
                "decision_ref": "gate-decision-1",
                "decision_sha256": "4" * 64,
            }
        ],
        "commitments": [
            {
                "commitment_id": "commit-price",
                "mandatory": True,
                "approved": True,
                "safe_fact": "Discovery scope is available for owner review.",
                "decided_at": ts(NOW - timedelta(minutes=15)),
                "approval_ref": "commercial-approval-1",
                "approval_sha256": "5" * 64,
            }
        ],
    }


def build_roots(evidence: dict, *, mutate: dict | None = None) -> tuple[bytes, bytes]:
    evidence_bytes = canonical_bytes(evidence)
    parsed = parse_evidence(parse_json_bytes(evidence_bytes))
    digests = evidence_section_digests(parsed)
    row = {
        "root_id": evidence["root_id"],
        "opportunity_id": evidence["opportunity"]["opportunity_id"],
        "counterparty_ref": evidence["opportunity"]["counterparty_ref"],
        "thread_id": evidence["opportunity"]["thread_id"],
        "generation": evidence["generation"],
        "active_from": ts(NOW - timedelta(days=1)),
        "expires_at": ts(NOW + timedelta(days=30)),
        "policy_sha256": POLICY_SHA256,
        "evidence_sha256": sha256_bytes(evidence_bytes),
        **digests,
    }
    if mutate:
        row.update(mutate)
    roots = {
        "schema": "teaming-conversion-trusted-roots/v2",
        "roots": [row],
    }
    return evidence_bytes, canonical_bytes(roots)


def compile_fixture(
    *,
    candidate: dict | None = None,
    evidence: dict | None = None,
    at: datetime = NOW,
    root_mutate: dict | None = None,
):
    candidate_value = candidate or base_candidate()
    evidence_value = evidence or base_evidence()
    evidence_bytes, roots_bytes = build_roots(evidence_value, mutate=root_mutate)
    candidate_bytes = canonical_bytes(candidate_value)
    receipt = compile_historical_bytes(
        candidate_bytes,
        evidence_bytes,
        roots_bytes,
        evaluated_at=at,
    )
    return candidate_bytes, evidence_bytes, roots_bytes, receipt
