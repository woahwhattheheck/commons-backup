from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from revenue.rfp_clarification_questions import compiler


S1 = "1" * 64
S2 = "2" * 64
NOW = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)
AFTER = datetime(2100, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def pack() -> dict:
    return {
        "schema": "procurement-solicitation-ingest/pack/v1",
        "pack_id": "rfp-demo-1",
        "evaluated_at": "2026-09-16T12:00:00Z",
        "source_max_age_seconds": 31536000,
        "truth_boundary": "INTERNAL_OWNER_REVIEW_ONLY",
        "sources": [
            {
                "source_id": "sol-1",
                "source_class": "BUYER_OFFICIAL",
                "kind": "SOLICITATION",
                "identity": "buyer-rfp-v1",
                "ref": "buyer-rfp-v1.pdf",
                "sha256": S1,
                "captured_at": "2026-09-16T11:00:00Z",
                "sequence": 1,
                "supersedes_sources": [],
                "supersedes_lineages": [],
                "requirements": [
                    {
                        "lineage_id": "req-a",
                        "section_id": "sec-a",
                        "kind": "MANDATORY",
                        "family": "SECURITY",
                        "tags": ["security"],
                        "text": "The bidder must describe the required security evidence.",
                    },
                    {
                        "lineage_id": "req-b",
                        "section_id": "sec-b",
                        "kind": "SCORED",
                        "family": "DELIVERY",
                        "tags": ["delivery"],
                        "text": "Describe the delivery plan.",
                    },
                ],
                "deadline": {
                    "value": "2099-12-31T23:59:00Z",
                    "supersedes_deadline": False,
                },
                "attachments": [],
            },
            {
                "source_id": "amend-1",
                "source_class": "BUYER_OFFICIAL",
                "kind": "AMENDMENT",
                "identity": "buyer-amendment-1",
                "ref": "buyer-amendment-1.pdf",
                "sha256": S2,
                "captured_at": "2026-09-16T11:30:00Z",
                "sequence": 2,
                "supersedes_sources": [],
                "supersedes_lineages": ["req-b"],
                "requirements": [
                    {
                        "lineage_id": "req-b",
                        "section_id": "sec-b2",
                        "kind": "SCORED",
                        "family": "DELIVERY",
                        "tags": ["delivery"],
                        "text": "Describe the amended delivery plan and transition evidence.",
                    }
                ],
                "deadline": None,
                "attachments": [],
            },
        ],
    }


def question(
    *,
    qid: str = "q-a-1",
    intent: str = "intent-security-proof",
    gap_id: str = "human-evidence:req-a",
    qclass: str = "MANDATORY_AMBIGUITY",
    priority: int = 1,
    text: str = "Please clarify which security evidence is required for the mandatory response.",
    safe: bool = True,
    source_id: str = "sol-1",
    source_sha: str = S1,
    section: str = "sec-a",
    internal_note: str = "do not expose owner scoring strategy",
) -> dict:
    return {
        "question_id": qid,
        "intent_id": intent,
        "gap_id": gap_id,
        "question_class": qclass,
        "priority": priority,
        "question_text": text,
        "bid_risk": "Ambiguity may cause a mandatory response to be judged incomplete.",
        "buyer_safe": safe,
        "source_id": source_id,
        "source_sha256": source_sha,
        "section_id": section,
        "internal_note": internal_note,
    }


def raw_input() -> bytes:
    value = {
        "schema": compiler.INPUT,
        "truth_boundary": compiler.BOUNDARY,
        "solicitation_pack": pack(),
        "question_deadlines": [
            {
                "deadline_id": "questions-v1",
                "source_id": "amend-1",
                "source_sha256": S2,
                "section_id": "sec-questions",
                "value": "2099-12-20T17:00:00-05:00",
                "supersedes_deadline_ids": [],
            }
        ],
        "candidate_questions": [question()],
        "resolutions": [],
    }
    return compiler.canon(value)

class ClarificationTestBase(unittest.TestCase):
    def compile(self, raw: bytes | None = None, when: datetime = NOW):
        with patch.object(compiler, "_clock", return_value=when):
            return compiler.compile_current(raw or raw_input())

    def packet(self, output) -> dict:
        return compiler.load(output.packet, "packet")

    def mutate(self, raw: bytes, fn) -> bytes:
        value = compiler.load(raw)
        fn(value)
        return compiler.canon(value)
