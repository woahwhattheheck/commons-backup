#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import check_integration_ledger as ledger


SOURCE_BYTES = b"def current_component(value):\n    return value + 1\n"
TEST_BYTES = b"def test_current_component():\n    assert 2 == 1 + 1\n"


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
        "landed": [{
            "lane": "current component",
            "repair_path": "repairs/gameplay/current-component",
            "source_blob": _git_blob_id(SOURCE_BYTES),
            "test_blob": _git_blob_id(TEST_BYTES),
            "status": "source_component_tested_not_runtime_promoted",
        }],
        "recovered_not_yet_composed": [],
        "custody_blocked": [{
            "lane": "historical packet",
            "custody_path": "repairs/gameplay/current-component",
            "status": "historical_evidence_gap_not_source_blocker",
            "available": "exact current source and tests",
            "missing": "old benchmark receipt",
            "required": "archive exact old bytes if recovered; do not reconstruct",
        }],
        "negative_or_parked": [],
    }
    return canonical, integration


def _write_root(root: Path) -> Path:
    canonical, integration = _base()
    _write_json(root / "CANONICAL.json", canonical)
    _write_json(root / "INTEGRATION.json", integration)
    custody = root / "repairs/gameplay/current-component"
    custody.mkdir(parents=True)
    return custody


def _descriptor_supported() -> bool:
    return (
        hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and os.open in getattr(os, "supports_dir_fd", set())
        and os.stat in getattr(os, "supports_dir_fd", set())
        and os.stat in getattr(os, "supports_follow_symlinks", set())
        and os.listdir in getattr(os, "supports_fd", set())
    )


@contextmanager
def _hostile_open(racing_open):
    # Replacing os.open changes its identity, so the capability probe would
    # fail closed before the race. Keep that probe on the real builtins.
    with mock.patch.object(ledger, "_require_descriptor_relative_custody"):
        with mock.patch.object(ledger.os, "open", side_effect=racing_open):
            yield


@unittest.skipUnless(_descriptor_supported(), "descriptor-relative traversal unavailable")
class DescriptorCustodyTests(unittest.TestCase):
    def test_nested_regular_files_satisfy_custody(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            custody = _write_root(root)
            nested = custody / "nested"
            nested.mkdir()
            (nested / "current_component.py").write_bytes(SOURCE_BYTES)
            (custody / "test_current_component.py").write_bytes(TEST_BYTES)
            self.assertEqual([], ledger.validate(root))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_child_directory_replacement_with_outside_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory() as parent_td:
            parent = Path(parent_td)
            root = parent / "v4"
            root.mkdir()
            custody = _write_root(root)
            nested = custody / "nested"
            nested.mkdir()
            (nested / "current_component.py").write_bytes(SOURCE_BYTES)
            (custody / "test_current_component.py").write_bytes(TEST_BYTES)

            outside = parent / "outside"
            outside.mkdir()
            (outside / "current_component.py").write_bytes(SOURCE_BYTES)

            real_open = os.open
            swapped = False

            def racing_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal swapped
                if (
                    not swapped
                    and path == "nested"
                    and dir_fd is not None
                    and flags & os.O_DIRECTORY
                ):
                    os.rename(nested, custody / "nested-owned")
                    os.symlink(outside, nested)
                    swapped = True
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with _hostile_open(racing_open):
                errors = ledger.validate(root)

            self.assertTrue(swapped, "hostile did not trigger at child-directory open")
            self.assertTrue(
                any(
                    "cannot verify current custody bytes" in error
                    and "cannot open custody directory" in error
                    for error in errors
                ),
                errors,
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_preexisting_ancestor_symlink_to_matching_outside_tree_fails_before_walk(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            outside = parent / "outside"
            custody = outside / "custody"
            custody.mkdir(parents=True)
            (custody / "current_component.py").write_bytes(SOURCE_BYTES)

            apparent = parent / "apparent"
            apparent.symlink_to(outside, target_is_directory=True)
            target = apparent / "custody"
            wanted = {_git_blob_id(SOURCE_BYTES)}

            with mock.patch.object(
                ledger,
                "_walk_custody_dir",
                side_effect=AssertionError("outside tree must not be walked"),
            ):
                with self.assertRaises(ledger.LedgerError) as raised:
                    ledger._custody_blob_ids(target, wanted)

            self.assertIn("not a directory", str(raised.exception))

    def test_root_component_swap_between_stat_and_open_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            custody = parent / "custody"
            custody.mkdir()
            (custody / "current_component.py").write_bytes(SOURCE_BYTES)
            wanted = {_git_blob_id(SOURCE_BYTES)}

            real_open = os.open
            swapped = False

            def racing_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal swapped
                if (
                    not swapped
                    and path == "custody"
                    and dir_fd is not None
                    and flags & os.O_DIRECTORY
                ):
                    os.rename(custody, parent / "custody-owned")
                    custody.mkdir()
                    (custody / "current_component.py").write_bytes(SOURCE_BYTES)
                    swapped = True
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with _hostile_open(racing_open):
                with self.assertRaises(ledger.LedgerError) as raised:
                    ledger._custody_blob_ids(custody, wanted)

            self.assertTrue(swapped, "hostile did not trigger at root-component open")
            self.assertIn("changed during acquisition", str(raised.exception))

    def test_dotdot_root_is_rejected_before_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            target = Path(str(parent / "child" / ".." / "custody"))
            with self.assertRaises(ledger.LedgerError):
                ledger._open_custody_root(target)


if __name__ == "__main__":
    unittest.main()
