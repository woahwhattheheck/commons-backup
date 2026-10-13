#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("postimage", HERE / "build_composed_postimage.py")
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class PostimageUnitTests(unittest.TestCase):
    def test_git_blob_known(self):
        self.assertEqual(m.git_blob(b"test content\n"), "d670460b4b4aece5915caf5c68d12f560a9fe3e4")

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(m.MaterializationError):
                m.load_json(p)

    def test_surface_file(self):
        self.assertEqual(m._surface_file("titan_runtime.py::TitanAgent.act:x"), "titan_runtime.py")
        self.assertEqual(m._surface_file("scheduler.py"), "scheduler.py")
        with self.assertRaises(m.MaterializationError):
            m._surface_file("../scheduler.py::x")

    def test_blob_id_strict(self):
        value = "a" * 40
        self.assertEqual(m._blob_id("git-blob:" + value), value)
        for bad in ("a" * 40, "git-blob:" + "A" * 40, "git-blob:abc"):
            with self.assertRaises(m.MaterializationError):
                m._blob_id(bad)

    def test_tree_digest_order_independent(self):
        a = {"b": {"bytes": 1, "git_blob": "1", "sha256": "2"},
             "a": {"bytes": 2, "git_blob": "3", "sha256": "4"}}
        b = {"a": a["a"], "b": a["b"]}
        self.assertEqual(m._tree_digest(a), m._tree_digest(b))

    def test_copy_tree_rejects_symlink(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            src = base / "src"
            src.mkdir()
            (src / "real").write_text("x")
            try:
                (src / "link").symlink_to(src / "real")
            except OSError:
                self.skipTest("symlink creation denied")
            with self.assertRaises(m.MaterializationError):
                m._copy_tree(src, base / "dst")

    def test_component_transforms_reject_duplicate_surface_file(self):
        comp = {"id": "x", "transforms": [
            {"surface": "a.py::x", "input_identity": "git-blob:" + "a"*40,
             "output_identity": "git-blob:" + "b"*40},
            {"surface": "a.py::y", "input_identity": "git-blob:" + "b"*40,
             "output_identity": "git-blob:" + "c"*40},
        ]}
        with self.assertRaises(m.MaterializationError):
            m._component_transforms(comp)


class ContractTests(unittest.TestCase):
    def _workspace(self, root: Path):
        (root / "adapter.py").write_text("def f(): return 1\n", encoding="utf-8")
        comp = {
            "id": "x", "state": "compose", "entrypoints": ["adapter.py"],
            "transforms": [{
                "surface": "x.py",
                "input_identity": "git-blob:" + "a"*40,
                "output_identity": "git-blob:" + "b"*40,
            }],
        }
        manifest = {"components": [comp]}
        graph = {"ok": True, "plan": ["x"]}
        def runner(*args): return []
        adapters = {"x": {"entrypoints": {"adapter.py": m.git_blob((root / "adapter.py").read_bytes())},
                          "runner": runner}}
        return manifest, graph, adapters

    def test_unsupported_compose_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, graph, _ = self._workspace(root)
            with self.assertRaisesRegex(m.MaterializationError, "lacks reviewed adapter"):
                m.validate_execution_contract(root, manifest, graph, {})

    def test_tampered_adapter_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, graph, adapters = self._workspace(root)
            (root / "adapter.py").write_text("def f(): return 2\n", encoding="utf-8")
            with self.assertRaisesRegex(m.MaterializationError, "adapter source drift"):
                m.validate_execution_contract(root, manifest, graph, adapters)

    def test_entrypoint_order_is_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, graph, adapters = self._workspace(root)
            manifest["components"][0]["entrypoints"] = []
            with self.assertRaisesRegex(m.MaterializationError, "entrypoints differ"):
                m.validate_execution_contract(root, manifest, graph, adapters)

    def test_blocked_component_needs_no_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, graph, adapters = self._workspace(root)
            manifest["components"].append({"id": "blocked", "state": "blocked"})
            loaded = m.validate_execution_contract(root, manifest, graph, adapters)
            self.assertEqual(set(loaded), {"x"})

    def test_checker_plan_must_equal_active_set(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, graph, adapters = self._workspace(root)
            graph["plan"] = []
            with self.assertRaisesRegex(m.MaterializationError, "active compose set"):
                m.validate_execution_contract(root, manifest, graph, adapters)


class PipelineShapeTests(unittest.TestCase):
    def test_fast_adapter_rejects_wrong_surface(self):
        comp = {"id": "fast-tape-clone-current-runtime",
                "entrypoints": ["repairs/performance/fast-tape-clone/port_current_runtime.py"],
                "transforms": [{"surface": "wrong.py", "input_identity": "git-blob:"+"a"*40,
                                "output_identity": "git-blob:"+"b"*40}]}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaisesRegex(m.MaterializationError, "owns only titan_runtime"):
                m._run_fast_tape(comp, root, root, {}, {})

    def test_scoped_adapter_rejects_wrong_surface(self):
        ep = "repairs/performance/compose_scoped_constructor.py"
        comp = {"id": "scoped-construction", "entrypoints": [ep],
                "transforms": [{"surface": "wrong.py", "input_identity": "git-blob:"+"a"*40,
                                "output_identity": "git-blob:"+"b"*40}]}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaisesRegex(m.MaterializationError, "owns only scheduler"):
                m._run_scoped_construction(comp, root, root, {}, {})

    def test_projection_adapter_rejects_wrong_surface(self):
        ep = "repairs/performance/projection-state-clone/compose.py"
        comp = {"id": "projection-state-clone", "entrypoints": [ep],
                "transforms": [{"surface": "wrong.py", "input_identity": "git-blob:"+"a"*40,
                                "output_identity": "git-blob:"+"b"*40}]}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaisesRegex(m.MaterializationError, "owns only frozen_selected"):
                m._run_projection_clone(comp, root, root, {}, {})

    def test_h3_adapter_rejects_wrong_surface(self):
        ep = "research/sale-window-engagement/compose_current_h3s420.py"
        comp = {"id": "h3s420-sale-window", "entrypoints": [ep],
                "transforms": [{"surface": "wrong.py", "input_identity": "git-blob:"+"a"*40,
                                "output_identity": "git-blob:"+"b"*40}]}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaisesRegex(m.MaterializationError, "owns only frozen_selected"):
                m._run_h3s420(comp, root, root, {}, {})

    def test_h3_adapter_materializes_declared_bytes(self):
        ep = "research/sale-window-engagement/compose_current_h3s420.py"
        before = b"value = 'before'\n"
        after = b"value = 'after'\n"
        comp = {"id": "h3s420-sale-window", "entrypoints": [ep],
                "transforms": [{"surface": "frozen_selected.py",
                                "input_identity": "git-blob:" + m.git_blob(before),
                                "output_identity": "git-blob:" + m.git_blob(after)}]}
        module = type("H3", (), {"compose": staticmethod(
            lambda source, *, enabled: after if enabled else source)})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "frozen_selected.py").write_bytes(before)
            rows = m._run_h3s420(comp, root, root, {ep: module}, {})
            self.assertEqual((root / "frozen_selected.py").read_bytes(), after)
            self.assertEqual(rows[0]["before_git_blob"], m.git_blob(before))
            self.assertEqual(rows[0]["after_git_blob"], m.git_blob(after))

    def test_support_output_refuses_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "helper.py").write_bytes(b"old")
            with self.assertRaisesRegex(m.MaterializationError, "differs from pinned source"):
                m._write_support(root, "helper.py", b"new")
            self.assertEqual((root / "helper.py").read_bytes(), b"old")

    def test_funding_adapter_rejects_wrong_source_order(self):
        eps = [
            "repairs/performance/funding-replay/apply_town_funding.py",
            "repairs/runtime/joint-unit-projection/compose.py",
            "repairs/performance/funding-replay/apply_funding_replay.py",
            "repairs/performance/funding-replay/compose_funding_capacity.py",
        ]
        comp = {"id": "funding-capacity-stack", "entrypoints": eps,
                "source_order": list(reversed(eps)), "transforms": []}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaisesRegex(m.MaterializationError, "source_order"):
                m._run_funding_stack(comp, root, root, {}, {})


if __name__ == "__main__":
    unittest.main()
