from __future__ import annotations

import copy
import inspect
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from revenue.lawrence_youth_ai_training import gate
from revenue.lawrence_youth_ai_training import _test_api as test_api

SHA = "a" * 64
OTHER = "b" * 64
SOURCE_SHA = "d" * 64
NOW = "2026-09-15T22:00:00Z"
VERIFY_NOW = datetime(2026, 9, 15, 22, 30, tzinfo=timezone.utc)
OBSERVED = "2026-09-15T20:00:00Z"


def key_document(key_hex: str = "11" * 32):
    return {
        "schema": gate.AUTHORITY_KEY_SCHEMA,
        "key_id": "lawrence-host-v1",
        "key_hex": key_hex,
    }


def unsigned_envelope(
    *,
    now: str = NOW,
    document_sha: str = SHA,
    good_issuer: str = "Massachusetts Department of Revenue",
    good_issued_at: str = "2026-09-14T12:00:00Z",
    verified_at: str = "2026-09-15T21:00:00Z",
    audit_most_recent: bool = True,
):
    return {
        "schema": gate.AUTHORITY_ENVELOPE_SCHEMA,
        "key_id": "lawrence-host-v1",
        "generation_id": "lawrence-semantic-generation-1",
        "issued_at": now,
        "attestations": [
            {
                "attestation_id": "good-standing-1",
                "document_id": gate.GOOD_STANDING_DOCUMENT,
                "document_evidence_sha256": document_sha,
                "semantic_kind": "CURRENT_ISSUER_DOCUMENT",
                "issuer": good_issuer,
                "issued_at": good_issued_at,
                "period_end_at": None,
                "most_recent": None,
                "verified_at": verified_at,
                "source_ref": "retained-dor-evidence-1",
                "source_evidence_sha256": SOURCE_SHA,
            },
            {
                "attestation_id": "audit-1",
                "document_id": gate.AUDIT_DOCUMENT,
                "document_evidence_sha256": document_sha,
                "semantic_kind": "MOST_RECENT_FINANCIAL_ASSURANCE",
                "issuer": None,
                "issued_at": None,
                "period_end_at": "2025-12-31T00:00:00Z",
                "most_recent": audit_most_recent,
                "verified_at": verified_at,
                "source_ref": "retained-audit-evidence-1",
                "source_evidence_sha256": SOURCE_SHA,
            },
        ],
    }


def signed_envelope(**kwargs):
    key = key_document()
    return test_api.sign_envelope(unsigned_envelope(**kwargs), key)


def authority_context(**kwargs):
    return gate._authenticate_envelope(signed_envelope(**kwargs), key_document())


def ready_doc():
    return {
        "status": "READY",
        "evidence_sha256": SHA,
        "observed_at": OBSERVED,
        "expires_at": None,
    }


def snapshot(*, now: str = NOW):
    contract = gate._load_source_contract()
    return {
        "schema": gate.SNAPSHOT_SCHEMA,
        "source_capture": {
            "bid_id": contract["bid_id"],
            "document_url": contract["official_rfp_url"],
            "document_sha256": SHA,
            "captured_at": "2026-09-15T19:00:00Z",
            "updates_checked_at": "2026-09-15T21:30:00Z",
            "addenda_complete": True,
            "questions_answers_complete": False,
        },
        "bidder": {
            "bidder_id": "tokenjunkielabs",
            "organization_type": "CORPORATE",
            "hard_constraints": [],
            "documents": {
                doc_id: ready_doc()
                for doc_id in contract["mandatory_document_requirements"]
            },
        },
        "partners": [],
        "capability_evidence": [
            {
                "evidence_id": "bidder-all",
                "provider_id": "tokenjunkielabs",
                "covers": list(contract["capability_requirements"]),
                "status": "VERIFIED",
                "evidence_sha256": SHA,
                "observed_at": OBSERVED,
                "expires_at": None,
            }
        ],
    }


def evaluate_test(snap=None, *, now: str = NOW, envelope=None, emulate_host=True):
    return test_api.evaluate_with_authenticated_authority(
        snap or snapshot(),
        evaluated_at=now,
        expected_rfp_sha256=SHA,
        envelope=envelope or signed_envelope(now=now),
        key_document=key_document(),
        emulate_host=emulate_host,
    )


