#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import check_integration_ledger as ledger


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _base() -> tuple[dict[str, object], dict[str, object]]:
    canonical = {
        "canonical_branch": "main",
        "workspace": ledger.EXPECTED_WORKSPACE,
    }
    integration = {
        "schema": ledger.EXPECTED_SCHEMA,
        "canonical_branch": "main",
        "workspace": ledger.EXPECTED_WORKSPACE,
        "landed": [],
        "recovered_not_yet_composed": [],
        "custody_blocked": [],
        "negative_or_parked": [],
    }
    return canonical, integration


def _write_root(root: Path, canonical: dict[str, object], integration: dict[str, object]) -> None:
    _write_json(root / "CANONICAL.json", canonical)
    _write_json(root / "INTEGRATION.json", integration)


class IntegrationLedgerTrustTests(unittest.TestCase):
    def test_valid_minimal_ledger_remains_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            _write_root(root, canonical, integration)
            self.assertEqual([], ledger.validate(root))

    def test_landed_lane_cannot_also_be_custody_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["landed"] = [{"lane": "same", "status": "source_only"}]
            integration["custody_blocked"] = [{
                "lane": "same",
                "custody_path": "repairs/gameplay/same",
                "status": "historical_evidence_gap_not_source_blocker",
                "available": "current source",
                "missing": "old receipt",
                "required": "archive exact old bytes if recovered",
            }]
            (root / "repairs" / "gameplay" / "same").mkdir(parents=True)
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertIn("contradictory landed/blocked lanes: ['same']", errors)

    def test_lane_whitespace_alias_is_rejected_not_normalized_across_sections(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["landed"] = [{"lane": "same", "status": "source_only"}]
            integration["custody_blocked"] = [{
                "lane": " same ",
                "custody_path": "repairs/gameplay/same",
                "status": "historical_evidence_gap_not_source_blocker",
                "available": "current source",
                "missing": "old receipt",
                "required": "archive exact old bytes if recovered",
            }]
            (root / "repairs" / "gameplay" / "same").mkdir(parents=True)
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("lane must not have leading/trailing whitespace", errors[0])
        self.assertNotIn("contradictory landed/blocked", errors[0])

    def test_blocker_manifest_cannot_bind_whitespace_normalized_lane(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["custody_blocked"] = [{
                "lane": " raw guard ",
                "custody_path": "repairs/gameplay/raw-guard",
                "status": "awaiting_raw_payload",
            }]
            directory = root / "repairs" / "gameplay" / "raw-guard"
            directory.mkdir(parents=True)
            _write_root(root, canonical, integration)
            _write_json(directory / "MANIFEST.json", {
                "lane": "raw guard",
                "status": "awaiting_raw_payload",
                "required_next_step": "publish exact bytes",
            })
            errors = ledger.validate(root)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("lane must not have leading/trailing whitespace", errors[0])

    def test_custody_path_whitespace_alias_is_rejected_not_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["custody_blocked"] = [{
                "lane": "raw guard",
                "custody_path": " repairs/gameplay/raw-guard ",
                "status": "awaiting_raw_payload",
            }]
            directory = root / "repairs" / "gameplay" / "raw-guard"
            directory.mkdir(parents=True)
            _write_root(root, canonical, integration)
            _write_json(directory / "MANIFEST.json", {
                "lane": "raw guard",
                "status": "awaiting_raw_payload",
                "required_next_step": "publish exact bytes",
            })
            errors = ledger.validate(root)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("custody_path must not have leading/trailing whitespace", errors[0])

    def test_whitespace_only_negative_disposition_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["negative_or_parked"] = [{"lane": "parked", "disposition": "   "}]
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertEqual(["negative/parked lane 'parked' lacks disposition"], errors)

    def test_nonfinite_integration_constant_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, _ = _base()
            _write_json(root / "CANONICAL.json", canonical)
            (root / "INTEGRATION.json").write_text(
                '{"schema":"titan-v4-integration-ledger/v1",'
                '"canonical_branch":"main",'
                f'"workspace":{json.dumps(ledger.EXPECTED_WORKSPACE)},'
                '"landed":[],"recovered_not_yet_composed":[],"custody_blocked":[],"negative_or_parked":[],'
                '"poison":NaN}\n',
                encoding="utf-8",
            )
            errors = ledger.validate(root)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("non-finite JSON constant 'NaN'", errors[0])

    def test_nonfinite_manifest_constant_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["custody_blocked"] = [{
                "lane": "raw guard",
                "custody_path": "repairs/gameplay/raw-guard",
                "status": "awaiting_raw_payload",
            }]
            directory = root / "repairs" / "gameplay" / "raw-guard"
            directory.mkdir(parents=True)
            _write_root(root, canonical, integration)
            (directory / "MANIFEST.json").write_text(
                '{"lane":"raw guard","status":"awaiting_raw_payload",'
                '"required_next_step":"publish exact bytes","poison":Infinity}\n',
                encoding="utf-8",
            )
            errors = ledger.validate(root)
        self.assertTrue(any("non-finite JSON constant 'Infinity'" in error for error in errors), errors)

    def test_duplicate_integration_key_is_rejected_even_when_values_match(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, _ = _base()
            _write_json(root / "CANONICAL.json", canonical)
            (root / "INTEGRATION.json").write_text(
                '{"schema":"titan-v4-integration-ledger/v1",'
                '"schema":"titan-v4-integration-ledger/v1",'
                '"canonical_branch":"main",'
                f'"workspace":{json.dumps(ledger.EXPECTED_WORKSPACE)},'
                '"landed":[],"recovered_not_yet_composed":[],"custody_blocked":[],"negative_or_parked":[]}\n',
                encoding="utf-8",
            )
            errors = ledger.validate(root)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("duplicate JSON object key 'schema'", errors[0])

    def test_duplicate_canonical_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, integration = _base()
            (root / "CANONICAL.json").write_text(
                '{"canonical_branch":"main","canonical_branch":"main",'
                f'"workspace":{json.dumps(ledger.EXPECTED_WORKSPACE)}}}\n',
                encoding="utf-8",
            )
            _write_json(root / "INTEGRATION.json", integration)
            errors = ledger.validate(root)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("duplicate JSON object key 'canonical_branch'", errors[0])

    def test_duplicate_manifest_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["custody_blocked"] = [{
                "lane": "raw guard",
                "custody_path": "repairs/gameplay/raw-guard",
                "status": "awaiting_raw_payload",
            }]
            directory = root / "repairs" / "gameplay" / "raw-guard"
            directory.mkdir(parents=True)
            _write_root(root, canonical, integration)
            (directory / "MANIFEST.json").write_text(
                '{"lane":"raw guard","lane":"raw guard",'
                '"status":"awaiting_raw_payload",'
                '"required_next_step":"publish exact bytes"}\n',
                encoding="utf-8",
            )
            errors = ledger.validate(root)
        self.assertTrue(any("duplicate JSON object key 'lane'" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
