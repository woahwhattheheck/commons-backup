#!/usr/bin/env python3
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compiler  # noqa: E402
import workshare_compile  # noqa: E402
import workshare_verify  # noqa: E402

T1 = "2026-09-13T15:00:00Z"


def fixed_utc(text: str):
    instant = compiler._parse_utc(text, "test_time")
    stack = __import__("contextlib").ExitStack()
    stack.enter_context(mock.patch.object(workshare_compile, "_utc_now", return_value=instant))
    stack.enter_context(mock.patch.object(workshare_verify, "_utc_now", return_value=instant))
    return stack


def compile_current_at(candidate: dict, authority: dict, root: str, text: str = T1) -> dict:
    with fixed_utc(text):
        return compiler.compile_current(candidate, authority, root)


def verify_current_at(report: dict, root: str, text: str) -> dict:
    with fixed_utc(text):
        return compiler.verify_current(report, root)


def load_candidate() -> dict:
    return compiler.loads_strict((HERE / "fixtures" / "synthetic_packet.json").read_text(encoding="utf-8"))


def load_authority() -> dict:
    return compiler.loads_strict((HERE / "fixtures" / "synthetic_authority.json").read_text(encoding="utf-8"))


def clean_pair() -> tuple[dict, dict]:
    candidate = load_candidate()
    authority = load_authority()
    authority["sources"] = [row for row in authority["sources"] if row["source_id"] != "RIS-SEC-02"]
    for row in authority["sources"]:
        if row["source_id"] == "IAM-DEP-01":
            row["observed_at"] = "2026-08-24T12:00:00Z"
    template = copy.deepcopy(authority["sources"][0])
    template.update(
        {
            "source_id": "ESS-AI-01",
            "group": "ESS",
            "dimension": "ai_readiness",
            "evidence_kind": "interview",
            "source_ref": "synthetic://uiowa-rfq18649/ESS-AI-01",
            "source_content_sha256": compiler._sha256_bytes(b"synthetic ESS AI source\n"),
            "observed_at": "2026-08-27T12:00:00Z",
            "claim": "Synthetic interview records a governed AI evaluation gate.",
            "maturity": 2,
            "confidence_bp": 8000,
        }
    )
    authority["sources"].append(template)
    candidate["source_ids"] = sorted(row["source_id"] for row in authority["sources"])
    return candidate, authority


