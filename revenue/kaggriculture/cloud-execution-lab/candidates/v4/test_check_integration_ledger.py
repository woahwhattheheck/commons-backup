#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import check_integration_ledger as ledger


SOURCE_BYTES = b"def current_component(value):\n    return value + 1\n"
TEST_BYTES = b"def test_current_component():\n    assert 2 == 1 + 1\n"
SECOND_TEST_BYTES = b"def test_current_component_zero():\n    assert 1 == 0 + 1\n"


def _git_blob_id(payload: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {len(payload)}\0".encode("ascii"))
    digest.update(payload)
    return digest.hexdigest()


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
        "workspace": canonical["workspace"],
        "landed": [],
        "recovered_not_yet_composed": [],
        "custody_blocked": [],
        "negative_or_parked": [],
    }
    return canonical, integration


def _write_root(
    root: Path,
    canonical: dict[str, object],
    integration: dict[str, object],
) -> None:
    _write_json(root / "CANONICAL.json", canonical)
    _write_json(root / "INTEGRATION.json", integration)


def _landed_component(
    path: str = "repairs/gameplay/current-component",
) -> dict[str, object]:
    return {
        "lane": "current component",
        "repair_path": path,
        "source_blob": _git_blob_id(SOURCE_BYTES),
        "test_blob": _git_blob_id(TEST_BYTES),
        "status": "source_component_tested_not_runtime_promoted",
    }


def _historical_row(
    path: str = "repairs/gameplay/current-component",
) -> dict[str, object]:
    return {
        "lane": "historical packet",
        "custody_path": path,
        "status": "historical_evidence_gap_not_source_blocker",
        "available": "exact current source and tests",
        "missing": "old benchmark receipt",
        "required": "archive exact old bytes if recovered; do not reconstruct",
    }


class IntegrationLedgerCustodyContractTests(unittest.TestCase):
    def validate_with(
        self,
        row: dict[str, object],
        *,
        manifest: dict[str, object] | None = None,
        landed: list[dict[str, object]] | None = None,
        custody_files: dict[str, bytes] | None = None,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["landed"] = landed or []
            integration["custody_blocked"] = [row]
            _write_root(root, canonical, integration)

            custody_path = row.get("custody_path")
            if isinstance(custody_path, str) and not Path(custody_path).is_absolute():
                directory = root / custody_path
                directory.mkdir(parents=True)
                if custody_files is None and landed:
                    custody_files = {
                        "current_component.py": SOURCE_BYTES,
                        "test_current_component.py": TEST_BYTES,
                    }
                for relative, payload in (custody_files or {}).items():
                    target = directory / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                if manifest is not None:
                    _write_json(directory / "MANIFEST.json", manifest)

            return ledger.validate(root)

    def test_live_raw_payload_blocker_remains_strict(self):
        row = {
            "lane": "raw guard pack",
            "custody_path": "repairs/gameplay/raw-guard",
            "status": "awaiting_raw_payload",
        }
        manifest = {
            "lane": "raw guard pack",
            "status": "awaiting_raw_payload",
            "required_next_step": "publish exact bytes",
        }
        self.assertEqual([], self.validate_with(row, manifest=manifest))

    def test_live_raw_payload_blocker_without_manifest_fails_closed(self):
        row = {
            "lane": "raw guard pack",
            "custody_path": "repairs/gameplay/raw-guard",
            "status": "awaiting_raw_payload",
        }
        errors = self.validate_with(row)
        self.assertTrue(any("MANIFEST.json" in error for error in errors), errors)

    def test_nonblocking_historical_gap_does_not_require_awaiting_manifest(self):
        self.assertEqual(
            [],
            self.validate_with(_historical_row(), landed=[_landed_component()]),
        )

    def test_nonblocking_historical_gap_requires_explicit_missing_scope(self):
        row = _historical_row()
        row["missing"] = ""
        errors = self.validate_with(row, landed=[_landed_component()])
        self.assertIn(
            "historical evidence gap lane 'historical packet' lacks missing",
            errors,
        )

    def test_historical_gap_requires_exactly_one_landed_component_binding(self):
        errors = self.validate_with(_historical_row())
        self.assertIn(
            "historical evidence gap lane 'historical packet' requires exactly one landed component in its custody_path",
            errors,
        )

    def test_historical_gap_requires_valid_landed_source_and_test_blob_refs(self):
        landed = [_landed_component()]
        landed[0]["source_blob"] = "not-a-git-object"
        landed[0]["test_blob"] = "also-not-a-git-object"
        errors = self.validate_with(_historical_row(), landed=landed)
        self.assertIn(
            "historical evidence gap lane 'historical packet' landed component lacks a valid source_blob",
            errors,
        )
        self.assertIn(
            "historical evidence gap lane 'historical packet' landed component lacks valid test blob references",
            errors,
        )

    def test_shape_valid_but_nonexistent_blob_ids_fail_closed(self):
        landed = [_landed_component()]
        landed[0]["source_blob"] = "1" * 40
        landed[0]["test_blob"] = "2" * 40
        errors = self.validate_with(_historical_row(), landed=landed)
        self.assertTrue(
            any("source_blob" in error and "does not identify" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("test blob" in error and "does not identify" in error for error in errors),
            errors,
        )

    def test_content_drift_invalidates_recorded_source_blob(self):
        errors = self.validate_with(
            _historical_row(),
            landed=[_landed_component()],
            custody_files={
                "current_component.py": SOURCE_BYTES + b"# changed generation\n",
                "test_current_component.py": TEST_BYTES,
            },
        )
        self.assertTrue(
            any("source_blob" in error and "does not identify" in error for error in errors),
            errors,
        )

    def test_blob_elsewhere_in_root_cannot_satisfy_custody_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            row = _historical_row()
            integration["landed"] = [_landed_component()]
            integration["custody_blocked"] = [row]
            custody = root / str(row["custody_path"])
            custody.mkdir(parents=True)
            (custody / "test_current_component.py").write_bytes(TEST_BYTES)
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            (elsewhere / "current_component.py").write_bytes(SOURCE_BYTES)
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertTrue(
            any("source_blob" in error and "does not identify" in error for error in errors),
            errors,
        )

    def test_all_declared_test_blobs_must_bind_beneath_custody_path(self):
        landed = [_landed_component()]
        landed[0].pop("test_blob")
        landed[0]["test_blobs"] = [
            _git_blob_id(TEST_BYTES),
            _git_blob_id(SECOND_TEST_BYTES),
        ]
        errors = self.validate_with(
            _historical_row(),
            landed=landed,
            custody_files={
                "current_component.py": SOURCE_BYTES,
                "test_current_component.py": TEST_BYTES,
            },
        )
        missing = _git_blob_id(SECOND_TEST_BYTES)
        self.assertTrue(
            any(missing in error and "does not identify" in error for error in errors),
            errors,
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlinked_file_cannot_import_outside_blob_custody(self):
        with tempfile.TemporaryDirectory() as parent_td:
            parent = Path(parent_td)
            root = parent / "v4"
            root.mkdir()
            canonical, integration = _base()
            row = _historical_row()
            integration["landed"] = [_landed_component()]
            integration["custody_blocked"] = [row]
            custody = root / str(row["custody_path"])
            custody.mkdir(parents=True)
            (custody / "test_current_component.py").write_bytes(TEST_BYTES)
            outside = parent / "outside_source.py"
            outside.write_bytes(SOURCE_BYTES)
            os.symlink(outside, custody / "current_component.py")
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertTrue(
            any("source_blob" in error and "does not identify" in error for error in errors),
            errors,
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlinked_directory_cannot_import_outside_blob_custody(self):
        with tempfile.TemporaryDirectory() as parent_td:
            parent = Path(parent_td)
            root = parent / "v4"
            root.mkdir()
            canonical, integration = _base()
            row = _historical_row()
            integration["landed"] = [_landed_component()]
            integration["custody_blocked"] = [row]
            custody = root / str(row["custody_path"])
            custody.mkdir(parents=True)
            (custody / "test_current_component.py").write_bytes(TEST_BYTES)
            outside = parent / "outside_tree"
            outside.mkdir()
            (outside / "current_component.py").write_bytes(SOURCE_BYTES)
            os.symlink(outside, custody / "linked")
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertTrue(
            any("source_blob" in error and "does not identify" in error for error in errors),
            errors,
        )

    def test_unknown_custody_status_is_rejected(self):
        row = {
            "lane": "mystery packet",
            "custody_path": "repairs/gameplay/mystery",
            "status": "maybe_blocked",
        }
        errors = self.validate_with(row)
        self.assertIn(
            "custody lane 'mystery packet' has unsupported status 'maybe_blocked'",
            errors,
        )

    def test_duplicate_lane_in_same_section_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["landed"] = [
                {"lane": "same", "status": "default_off"},
                {"lane": "same", "status": "source_only"},
            ]
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertIn(
            "INTEGRATION.json 'landed' duplicates lane 'same' at indexes 0 and 1",
            errors,
        )

    def test_malformed_integration_json_returns_invalid_result_not_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, _ = _base()
            _write_json(root / "CANONICAL.json", canonical)
            (root / "INTEGRATION.json").write_text("{not-json", encoding="utf-8")
            errors = ledger.validate(root)
        self.assertEqual(1, len(errors))
        self.assertIn("cannot load", errors[0])
        self.assertIn("INTEGRATION.json", errors[0])

    def test_malformed_utf8_returns_invalid_result_not_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, _ = _base()
            _write_json(root / "CANONICAL.json", canonical)
            (root / "INTEGRATION.json").write_bytes(b"\xff\xfe\x80")
            errors = ledger.validate(root)
        self.assertEqual(1, len(errors))
        self.assertIn("cannot load", errors[0])
        self.assertIn("INTEGRATION.json", errors[0])

    def test_missing_required_section_returns_invalid_result_not_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            del integration["landed"]
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertIn("INTEGRATION.json 'landed' must be a list", errors)

    def test_schema_identity_is_pinned(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["schema"] = "titan-v4-integration-ledger/v999"
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertIn(
            "schema must be 'titan-v4-integration-ledger/v1', got 'titan-v4-integration-ledger/v999'",
            errors,
        )

    def test_workspace_identity_is_pinned_even_when_files_agree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            canonical["workspace"] = "elsewhere/v4"
            integration["workspace"] = "elsewhere/v4"
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertIn(
            f"workspace must be {ledger.EXPECTED_WORKSPACE!r}, got 'elsewhere/v4'",
            errors,
        )

    def test_parent_traversal_cannot_satisfy_custody(self):
        with tempfile.TemporaryDirectory() as parent_td:
            parent = Path(parent_td)
            root = parent / "v4"
            root.mkdir()
            outside = parent / "outside-custody"
            outside.mkdir()
            canonical, integration = _base()
            integration["custody_blocked"] = [{
                "lane": "raw guard pack",
                "custody_path": "../outside-custody",
                "status": "awaiting_raw_payload",
            }]
            _write_root(root, canonical, integration)
            _write_json(
                outside / "MANIFEST.json",
                {
                    "lane": "raw guard pack",
                    "status": "awaiting_raw_payload",
                    "required_next_step": "external bytes must not count",
                },
            )
            errors = ledger.validate(root)
        self.assertTrue(
            any("escapes integration root" in error for error in errors),
            errors,
        )

    def test_absolute_custody_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["custody_blocked"] = [{
                "lane": "raw guard pack",
                "custody_path": str(root.resolve()),
                "status": "awaiting_raw_payload",
            }]
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertTrue(
            any("must be relative to the integration root" in error for error in errors),
            errors,
        )

    def test_do_not_activate_retirement_conflicts_with_active_landed_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical, integration = _base()
            integration["landed"] = [{
                "lane": "retired",
                "status": "runtime_enabled",
            }]
            integration["negative_or_parked"] = [{
                "lane": "retired",
                "disposition": "KILL_bad_economics_do_not_stack_or_activate",
            }]
            _write_root(root, canonical, integration)
            errors = ledger.validate(root)
        self.assertIn(
            "retired/NO_BUILD lane 'retired' is also represented as active landed work",
            errors,
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlinked_custody_directory_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as parent_td:
            parent = Path(parent_td)
            root = parent / "v4"
            root.mkdir()
            outside = parent / "outside-custody"
            outside.mkdir()
            (root / "repairs").mkdir()
            os.symlink(outside, root / "repairs" / "escape")
            canonical, integration = _base()
            integration["custody_blocked"] = [{
                "lane": "raw guard pack",
                "custody_path": "repairs/escape",
                "status": "awaiting_raw_payload",
            }]
            _write_root(root, canonical, integration)
            _write_json(
                outside / "MANIFEST.json",
                {
                    "lane": "raw guard pack",
                    "status": "awaiting_raw_payload",
                    "required_next_step": "external bytes must not count",
                },
            )
            errors = ledger.validate(root)
        self.assertTrue(
            any("escapes integration root" in error for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
