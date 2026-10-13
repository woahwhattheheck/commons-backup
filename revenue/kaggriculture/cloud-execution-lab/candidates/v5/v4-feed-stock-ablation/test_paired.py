# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import inspect
from pathlib import Path
import tempfile
import unittest

import paired
from feed_stock_ablation import sha256_bytes


class PairedCustodyTest(unittest.TestCase):
    def test_capture_regular_is_detached_from_later_swap(self):
        raw = b"VALUE = 7\n"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.py"
            path.write_bytes(raw)
            captured = paired.capture_regular(path)
            path.write_bytes(b"VALUE = 99\n")
            self.assertEqual(captured, raw)
            self.assertNotEqual(path.read_bytes(), captured)

    def test_load_captured_does_not_reopen_origin(self):
        raw = b"VALUE = 11\n"
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td) / "module.py"
            origin.write_bytes(b"VALUE = 101\n")
            module = paired.load_captured(raw, origin, "feed_stock_test_captured")
            self.assertEqual(module.VALUE, 11)

    def test_captured_harness_survives_source_swap_after_auth(self):
        raw = b"VALUE = 13\n"
        expected = sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td) / "evaluator.py"
            origin.write_bytes(raw)
            captured = paired.capture_sha256(origin, expected)
            origin.write_bytes(b"VALUE = 999\n")
            module = paired.load_captured(captured, origin, "feed_stock_swap_captured")
            self.assertEqual(module.VALUE, 13)
            self.assertNotEqual(origin.read_bytes(), captured)

    def test_captured_harness_survives_source_delete_after_auth(self):
        raw = b"VALUE = 17\n"
        expected = sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td) / "pack.py"
            origin.write_bytes(raw)
            captured = paired.capture_sha256(origin, expected)
            origin.unlink()
            module = paired.load_captured(captured, origin, "feed_stock_delete_captured")
            self.assertEqual(module.VALUE, 17)
            self.assertFalse(origin.exists())

    def test_private_loader_uses_captured_bytes_not_visible_poison(self):
        raw = b"VALUE = 23\n"
        expected = sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            visible = root / "public-evidence-loader.py"
            visible.write_bytes(raw)
            captured = paired.capture_sha256(visible, expected)
            visible.write_bytes(b"VALUE = 404\n")
            private = root / "private-runtime" / "evaluate.py"
            self.assertEqual(
                paired.write_private_runtime_bytes(captured, private, expected), private
            )
            self.assertEqual(private.read_bytes(), raw)
            self.assertNotEqual(private.read_bytes(), visible.read_bytes())

    def test_private_loader_rejects_wrong_captured_digest(self):
        raw = b"VALUE = 29\n"
        expected = sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as td:
            private = Path(td) / "private-runtime" / "evaluate.py"
            with self.assertRaisesRegex(
                ValueError, "private runtime bytes do not match authenticated SHA256"
            ):
                paired.write_private_runtime_bytes(b"VALUE = 30\n", private, expected)
            self.assertFalse(private.exists())

    def test_private_engine_survives_public_swap_and_delete(self):
        raws = {
            name: (name + "-trusted\n").encode("utf-8")
            for name in paired.ENGINE_FILES
        }
        evaluator = type("Evaluator", (), {
            "ENGINE_BLOBS": {
                name: paired.git_blob_bytes(raw) for name, raw in raws.items()
            }
        })
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            public = root / "public-engine"
            public.mkdir()
            for name, raw in raws.items():
                (public / name).write_bytes(raw)
            private, receipt = paired.capture_private_engine(
                public, evaluator, root / "private-runtime"
            )
            (public / "kaggriculture.py").write_bytes(b"POISON\n")
            (public / "utils.py").unlink()
            self.assertEqual(
                (private / "kaggriculture.py").read_bytes(), raws["kaggriculture.py"]
            )
            self.assertEqual((private / "utils.py").read_bytes(), raws["utils.py"])
            self.assertEqual(
                receipt["kaggriculture.json"]["git_blob"],
                evaluator.ENGINE_BLOBS["kaggriculture.json"],
            )

    def test_private_engine_rejects_wrong_preimage_before_public_output(self):
        raws = {
            name: (name + "-trusted\n").encode("utf-8")
            for name in paired.ENGINE_FILES
        }
        evaluator = type("Evaluator", (), {
            "ENGINE_BLOBS": {
                name: paired.git_blob_bytes(raw) for name, raw in raws.items()
            }
        })
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            public = root / "public-engine"
            public.mkdir()
            for name, raw in raws.items():
                (public / name).write_bytes(raw)
            (public / "kaggriculture.json").write_bytes(b"wrong\n")
            with self.assertRaisesRegex(ValueError, "Official source mismatch"):
                paired.capture_private_engine(public, evaluator, root / "private-runtime")
            self.assertFalse((root / "private-runtime" / "engine").exists())

    def test_private_engine_requires_exact_official_manifest(self):
        evaluator = type("Evaluator", (), {"ENGINE_BLOBS": {"kaggriculture.py": "x"}})
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "evaluator engine manifest changed"):
                paired.capture_private_engine(Path(td), evaluator, Path(td) / "private")

    def test_main_keeps_generated_executable_paths_out_of_public_output(self):
        source = inspect.getsource(paired.main)
        self.assertIn('runtime[opponent] = private_root / "opponents" / opponent', source)
        self.assertIn('prefix=f"{cell_id}-{arm}-", dir=private_root', source)
        self.assertNotIn('runtime[opponent] = output / "opponents" / opponent', source)
        self.assertNotIn('prefix=f"{cell_id}-{arm}-", dir=output', source)

    def test_main_uses_private_engine_for_every_execution_path(self):
        source = inspect.getsource(paired.main)
        self.assertIn("capture_private_engine(", source)
        self.assertIn("evaluator.verify_sources(private_engine)", source)
        self.assertIn("evaluator.get_engine(private_engine, loader)", source)
        self.assertNotIn("evaluator.get_engine(engine_dir, loader)", source)
        self.assertIn('"engine_files": engine_capture', source)
        self.assertEqual(paired.SCHEMA, "astra.v5.v4-feed-stock-ablation.v2")

    def test_summary_keeps_opponents_and_engagement_separate(self):
        cells = [
            {
                "opponent": "apex_v7",
                "status": "complete_pair",
                "score_delta": {"own": 5, "rival": 1, "margin": 4},
                "engaged": True,
            },
            {
                "opponent": "apex_v7",
                "status": "complete_pair",
                "score_delta": {"own": -1, "rival": 2, "margin": -3},
                "engaged": False,
            },
            {
                "opponent": "arlene_v14",
                "status": "incomplete_pair",
                "score_delta": None,
                "engaged": None,
            },
        ]
        value = paired.summarize(cells)
        self.assertEqual(value["apex_v7"]["complete_pairs"], 2)
        self.assertEqual(value["apex_v7"]["engaged"], 1)
        self.assertEqual(value["apex_v7"]["cold"], 1)
        self.assertEqual(value["arlene_v14"]["unknown_engagement"], 1)
        self.assertIsNone(value["arlene_v14"]["mean_margin_delta"])


if __name__ == "__main__":
    unittest.main()
