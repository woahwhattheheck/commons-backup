from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib
import os
from pathlib import Path
import tempfile
import unittest

from tools.exact_head_ship_fence import fence
from tools.exact_head_ship_fence.cli import _write_bundle
from tools.exact_head_ship_fence.test_fence import packet


class SealedGeneration(unittest.TestCase):
    def test_no_importable_core_module(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("tools.exact_head_ship_fence._core")

    def test_public_authority_is_immutable_and_rebind_irrelevant(self):
        with self.assertRaises(TypeError):
            fence.AUTHORITY["merge_authorized"] = True
        old = fence.AUTHORITY
        try:
            fence.AUTHORITY = {"merge_authorized": True}
            report = fence.compile_current(packet())
            self.assertFalse(any(report["authority"].values()))
        finally:
            fence.AUTHORITY = old

    def test_public_helper_names_are_not_semantic_dependencies(self):
        injected = []
        try:
            for name in ("_build", "_class", "_sha"):
                setattr(fence, name, lambda *a, **k: None)
                injected.append(name)
            report = fence.compile_current(packet())
            self.assertEqual(report["verdict"], "READY_TO_MERGE_EVIDENCE")
            self.assertFalse(any(report["authority"].values()))
        finally:
            for name in injected:
                delattr(fence, name)

    def test_reviewer_quorum_uses_current_head_canonical_identity(self):
        evidence = packet(); evidence["review_policy"]["min_passes"] = 2
        replay = deepcopy(evidence["reviews"][0]); replay["review_id"] = "review-2"
        evidence["reviews"].append(replay)
        with self.assertRaises(fence.EvidenceError):
            fence.compile_current(evidence)
        evidence["reviews"][1]["reviewer"] = evidence["reviews"][0]["reviewer"].upper()
        with self.assertRaises(fence.EvidenceError):
            fence.compile_current(evidence)
        evidence["reviews"][1]["reviewer"] = "second-independent-reviewer"
        self.assertEqual(fence.compile_current(evidence)["verdict"], "READY_TO_MERGE_EVIDENCE")

    def test_same_reviewer_may_rereview_after_head_move(self):
        evidence = packet()
        stale = deepcopy(evidence["reviews"][0])
        stale["review_id"] = "review-old-head"
        stale["head_sha"] = "9" * 40
        stale["reviewer"] = stale["reviewer"].upper()
        evidence["reviews"].insert(0, stale)
        self.assertEqual(fence.compile_current(evidence)["verdict"], "READY_TO_MERGE_EVIDENCE")

    def test_public_clock_and_source_digest_rebind_are_irrelevant_after_load(self):
        old_clock = fence._CURRENT_CLOCK
        old_digest = fence._CORE_SOURCE_SHA256
        try:
            fence._CURRENT_CLOCK = lambda: datetime(2000, 1, 1, tzinfo=timezone.utc)
            fence._CORE_SOURCE_SHA256 = "0" * 64
            self.assertEqual(fence.compile_current(packet())["verdict"], "READY_TO_MERGE_EVIDENCE")
        finally:
            fence._CURRENT_CLOCK = old_clock
            fence._CORE_SOURCE_SHA256 = old_digest
        with self.assertRaises(TypeError):
            fence.compile_current(packet(), _clock=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc))


class OutputCustody(unittest.TestCase):
    def test_output_directory_remint_is_detected_and_foreign_dir_preserved(self):
        report = fence.compile_current(packet())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); out = root / "out"; displaced = root / "displaced"
            def remint(path: Path) -> None:
                os.rename(path, displaced)
                os.mkdir(path, 0o700)
            with self.assertRaises(fence.EvidenceError):
                _write_bundle(out, report, _after_first=remint)
            self.assertTrue(out.is_dir())
            self.assertEqual(list(out.iterdir()), [])
            self.assertTrue(displaced.is_dir())

    def test_rollback_preserves_foreign_member_successor(self):
        report = fence.compile_current(packet())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            def replace_and_block(path: Path) -> None:
                os.rename(path / "report.json", path / "owned.old")
                (path / "report.json").write_text("FOREIGN", encoding="utf-8")
                (path / "report.md").write_text("BLOCK", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                _write_bundle(out, report, _after_first=replace_and_block)
            self.assertEqual((out / "report.json").read_text(encoding="utf-8"), "FOREIGN")
            self.assertEqual((out / "report.md").read_text(encoding="utf-8"), "BLOCK")
            self.assertTrue((out / "owned.old").exists())


class ZZReloadStability(unittest.TestCase):
    def test_reload_rebuilds_canonical_private_generation(self):
        old_compile = fence.compile_current
        fence.AUTHORITY = {"merge_authorized": True}
        fence._build = lambda *_a, **_k: None
        reloaded = importlib.reload(fence)
        new_report = reloaded.compile_current(packet())
        old_report = old_compile(packet())
        self.assertEqual(new_report["verdict"], "READY_TO_MERGE_EVIDENCE")
        self.assertEqual(old_report["verdict"], "READY_TO_MERGE_EVIDENCE")
        self.assertFalse(any(new_report["authority"].values()))
        self.assertFalse(any(old_report["authority"].values()))
        self.assertFalse(hasattr(reloaded, "_build"))


if __name__ == "__main__":
    unittest.main()
