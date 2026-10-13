# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

import paired


class PairedTest(unittest.TestCase):
    def test_score_triplet_binds_tested_seat(self):
        game = {"status": "complete", "steps": 719, "scores": [100, 75]}
        self.assertEqual(
            paired.score_triplet(game, 0),
            {"own": 100.0, "rival": 75.0, "margin": 25.0},
        )
        self.assertEqual(
            paired.score_triplet(game, 1),
            {"own": 75.0, "rival": 100.0, "margin": -25.0},
        )

    def test_score_triplet_rejects_incomplete_or_bool(self):
        self.assertIsNone(paired.score_triplet(
            {"status": "complete", "steps": 718, "scores": [1, 2]}, 0
        ))
        self.assertIsNone(paired.score_triplet(
            {"status": "complete", "steps": 719, "scores": [True, 2]}, 0
        ))

    def test_summarize_keeps_own_rival_margin_and_interaction(self):
        def cell(opponent, values):
            control = {"own": 100.0, "rival": 90.0, "margin": 10.0}
            metrics = {"control": control, "v31_reference": control, **values}
            return {
                "opponent": opponent,
                "metrics": metrics,
                "deltas_vs_control": {
                    arm: paired._delta(metrics[arm], control)
                    for arm in paired.RUN_ARMS if arm != "control"
                },
            }

        rows = [cell("apex_v7", {
            "min_v31": {"own": 105.0, "rival": 90.0, "margin": 15.0},
            "no_reorder": {"own": 102.0, "rival": 89.0, "margin": 13.0},
            "funding_pair_v31": {"own": 110.0, "rival": 88.0, "margin": 22.0},
        })]
        summary = paired.summarize(rows)
        self.assertEqual(summary["complete_cells"], 1)
        self.assertEqual(
            summary["arms_vs_v4_control"]["min_v31"]["mean_own_delta"], 5.0
        )
        self.assertEqual(summary["interaction"]["mean_margin_delta"], 4.0)

    def test_parse_csv_requires_distinct_values(self):
        self.assertEqual(paired.parse_csv_ints("1,2"), [1, 2])
        with self.assertRaisesRegex(ValueError, "distinct"):
            paired.parse_csv_ints("1,1")

    def test_capture_archive_single_read_and_hash(self):
        payload = b"archive"
        expected = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "archive.tar.gz"
            path.write_bytes(payload)
            captured = paired.capture_archive(path, expected, "fixture")
            path.write_bytes(b"poison")
            self.assertEqual(captured, payload)

    def test_capture_archive_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "archive.tar.gz"
            target.write_bytes(b"x")
            link = root / "link.tar.gz"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "ordinary file"):
                paired.capture_archive(
                    link, hashlib.sha256(b"x").hexdigest(), "fixture"
                )

    def test_capture_git_blob(self):
        raw = b"print('ok')\n"
        expected = paired.git_blob_bytes(raw)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "helper.py"
            path.write_bytes(raw)
            self.assertEqual(paired.capture_git_blob(path, expected), raw)

    def test_capture_sha256_survives_source_swap_after_auth(self):
        raw = b"VALUE = 7\n"
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td) / "evaluator.py"
            origin.write_bytes(raw)
            captured = paired.capture_sha256(origin, expected)
            origin.write_bytes(b"VALUE = 99\n")
            module = paired.load_captured(captured, origin, "funding_swap_captured")
            self.assertEqual(module.VALUE, 7)
            self.assertNotEqual(origin.read_bytes(), captured)

    def test_capture_sha256_survives_source_delete_after_auth(self):
        raw = b"VALUE = 11\n"
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td) / "pack.py"
            origin.write_bytes(raw)
            captured = paired.capture_sha256(origin, expected)
            origin.unlink()
            module = paired.load_captured(captured, origin, "funding_delete_captured")
            self.assertEqual(module.VALUE, 11)
            self.assertFalse(origin.exists())

    def test_capture_sha256_rejects_symlink(self):
        raw = b"VALUE = 13\n"
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "bridge.py"
            target.write_bytes(raw)
            link = root / "bridge-link.py"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "ordinary file"):
                paired.capture_sha256(link, expected)

    def test_private_loader_uses_authenticated_capture_not_visible_origin(self):
        raw = b"VALUE = 23\n"
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            visible = root / "public-evidence-loader.py"
            visible.write_bytes(raw)
            captured = paired.capture_sha256(visible, expected)
            visible.write_bytes(b"VALUE = 101\n")
            private = root / "private-runtime" / "evaluate.py"
            self.assertEqual(
                paired.write_private_runtime_bytes(captured, private, expected), private
            )
            self.assertEqual(private.read_bytes(), raw)
            self.assertNotEqual(private.read_bytes(), visible.read_bytes())

    def test_private_loader_rejects_wrong_captured_digest(self):
        raw = b"VALUE = 23\n"
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            private = Path(td) / "private-runtime" / "evaluate.py"
            with self.assertRaisesRegex(
                ValueError, "Private runtime bytes do not match authenticated SHA256"
            ):
                paired.write_private_runtime_bytes(b"VALUE = 24\n", private, expected)
            self.assertFalse(private.exists())

    def test_public_opponent_evidence_poison_cannot_change_private_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            private = root / "private"
            public = root / "output"
            private.mkdir()
            public.mkdir()
            private_opponent = private / "opponents" / "apex_v7"
            private_opponent.mkdir(parents=True)
            private_adapter = private_opponent / "adapter.py"
            private_adapter.write_bytes(b"PRIVATE-OPPONENT\n")
            public_opponent = paired.copy_evidence_tree(
                private_opponent, public / "opponents" / "apex_v7"
            )
            public_adapter = public_opponent / "adapter.py"
            public_adapter.write_bytes(b"POISON\n")
            self.assertEqual(private_adapter.read_bytes(), b"PRIVATE-OPPONENT\n")
            self.assertEqual(
                paired.assert_private_execution_path(private_adapter, private, public),
                private_adapter.resolve(),
            )
            with self.assertRaisesRegex(ValueError, "caller-visible output"):
                paired.assert_private_execution_path(public_adapter, private, public)

    def test_public_candidate_evidence_poison_cannot_change_private_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            private = root / "private"
            public = root / "output"
            private.mkdir()
            public.mkdir()
            candidate = private / "games" / "cell-arm"
            payload = candidate / "payload"
            payload.mkdir(parents=True)
            private_adapter = candidate / "adapter.py"
            private_main = payload / "main.py"
            private_adapter.write_bytes(b"PRIVATE-ADAPTER\n")
            private_main.write_bytes(b"PRIVATE-MAIN\n")
            public_candidate = paired.copy_evidence_tree(
                candidate, public / "candidate-evidence" / "cell-arm"
            )
            (public_candidate / "adapter.py").write_bytes(b"POISON-ADAPTER\n")
            (public_candidate / "payload" / "main.py").write_bytes(b"POISON-MAIN\n")
            self.assertEqual(private_adapter.read_bytes(), b"PRIVATE-ADAPTER\n")
            self.assertEqual(private_main.read_bytes(), b"PRIVATE-MAIN\n")
            self.assertEqual(
                paired.assert_private_execution_path(private_adapter, private, public),
                private_adapter.resolve(),
            )
            self.assertEqual(
                paired.assert_private_execution_path(private_main, private, public),
                private_main.resolve(),
            )
            with self.assertRaisesRegex(ValueError, "caller-visible output"):
                paired.assert_private_execution_path(
                    public_candidate / "adapter.py", private, public
                )

    def test_execution_guard_rejects_path_outside_private_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            private = root / "private"
            public = root / "output"
            external = root / "external.py"
            private.mkdir()
            public.mkdir()
            external.write_text("x\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escaped private runtime"):
                paired.assert_private_execution_path(external, private, public)


if __name__ == "__main__":
    unittest.main()
