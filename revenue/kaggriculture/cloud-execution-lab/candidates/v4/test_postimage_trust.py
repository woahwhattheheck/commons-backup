from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import postimage_trust as m


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(m.TrustError, "duplicate JSON key"):
                m.strict_load_json(p)

    def test_nonfinite_constants_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as td:
                p = Path(td) / "x.json"
                p.write_text('{"x":' + token + '}', encoding="utf-8")
                with self.assertRaisesRegex(m.TrustError, "non-finite JSON constant"):
                    m.strict_load_json(p)

    def test_top_level_object_required(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(m.TrustError, "top-level object"):
                m.strict_load_json(p)


class TrustPathTests(unittest.TestCase):
    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(m.TrustError, "unsafe relative path"):
                m.checked_under(Path(td), "../x")

    def test_symlink_ancestor_rejected_even_inside_root(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real"
            real.mkdir()
            (real / "adapter.py").write_text("x=1\n", encoding="utf-8")
            try:
                (root / "alias").symlink_to(real, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation denied")
            with self.assertRaisesRegex(m.TrustError, "symlink ancestry"):
                m.checked_under(root, "alias/adapter.py")

    def test_final_symlink_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "real.py").write_text("x=1\n", encoding="utf-8")
            try:
                (root / "link.py").symlink_to(root / "real.py")
            except OSError:
                self.skipTest("symlink creation denied")
            with self.assertRaisesRegex(m.TrustError, "symlink ancestry"):
                m.checked_under(root, "link.py")


class ControlBindingTests(unittest.TestCase):
    def _workspace(self, root: Path):
        manifest = root / m.MANIFEST_NAME
        checker = root / m.CHECKER_NAME
        runner = root / m.RUNNER_NAME
        manifest.write_text(json.dumps({"canonical_root": "v4"}) + "\n", encoding="utf-8")
        checker.write_text("x=1\n", encoding="utf-8")
        runner.write_text("x=2\n", encoding="utf-8")
        pins = {
            m.MANIFEST_NAME: m.git_blob(manifest.read_bytes()),
            m.CHECKER_NAME: m.git_blob(checker.read_bytes()),
            m.RUNNER_NAME: m.git_blob(runner.read_bytes()),
        }
        return pins

    def test_exact_canonical_control_set_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pins = self._workspace(root)
            manifest, raw, paths = m.verify_control_sources(root, pins=pins)
            self.assertEqual(manifest["canonical_root"], "v4")
            self.assertEqual(m.git_blob(raw), pins[m.MANIFEST_NAME])
            self.assertEqual(paths[m.MANIFEST_NAME], (root / m.MANIFEST_NAME).resolve())

    def test_alternate_manifest_refused_even_if_schema_like(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pins = self._workspace(root)
            alt = root / "ALT.json"
            alt.write_text((root / m.MANIFEST_NAME).read_text(), encoding="utf-8")
            with self.assertRaisesRegex(m.TrustError, "alternate manifest refused"):
                m.verify_control_sources(root, manifest_path=alt, pins=pins)

    def test_manifest_drift_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pins = self._workspace(root)
            (root / m.MANIFEST_NAME).write_text('{"canonical_root":"v4","components":[]}\n', encoding="utf-8")
            with self.assertRaisesRegex(m.TrustError, "source drift for COMPOSITION"):
                m.verify_control_sources(root, pins=pins)

    def test_checker_drift_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pins = self._workspace(root)
            (root / m.CHECKER_NAME).write_text("raise SystemExit('tampered')\n", encoding="utf-8")
            with self.assertRaisesRegex(m.TrustError, "source drift for check_composition_graph"):
                m.verify_control_sources(root, pins=pins)

    def test_runner_drift_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pins = self._workspace(root)
            (root / m.RUNNER_NAME).write_text("raise SystemExit('tampered')\n", encoding="utf-8")
            with self.assertRaisesRegex(m.TrustError, "source drift for build_composed_postimage"):
                m.verify_control_sources(root, pins=pins)


class AdapterCustodyTests(unittest.TestCase):
    def _tree(self, base: Path):
        repo = base / "repo"
        workspace = repo / "x" / "v4"
        workspace.mkdir(parents=True)
        local = workspace / "repairs" / "adapter.py"
        local.parent.mkdir(parents=True)
        local.write_text("x=1\n", encoding="utf-8")
        shared = repo / "shared" / "helper.py"
        shared.parent.mkdir(parents=True)
        shared.write_text("y=1\n", encoding="utf-8")
        manifest = {"canonical_root": "x/v4"}
        adapters = {
            "x": {
                "entrypoints": {"repairs/adapter.py": m.git_blob(local.read_bytes())},
                "sources": {"repo:shared/helper.py": m.git_blob(shared.read_bytes())},
                "support_outputs": ["support.py"],
            }
        }
        return repo, workspace, manifest, adapters

    def test_adapter_and_repo_support_pins_pass(self):
        with tempfile.TemporaryDirectory() as td:
            _repo, workspace, manifest, adapters = self._tree(Path(td))
            m.verify_adapter_paths(workspace, manifest, adapters)

    def test_adapter_symlink_ancestor_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            _repo, workspace, manifest, adapters = self._tree(Path(td))
            real = workspace / "repairs"
            moved = workspace / "real_repairs"
            real.rename(moved)
            try:
                real.symlink_to(moved, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation denied")
            with self.assertRaisesRegex(m.TrustError, "symlink ancestry"):
                m.verify_adapter_paths(workspace, manifest, adapters)


if __name__ == "__main__":
    unittest.main()
