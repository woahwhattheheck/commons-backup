# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import ablation


FROZEN = b"""from selected_sell_core import optimize_lot, joint_plan_metrics, shared_slot_ledger\n\ndef f(best, pairs, ledger):\n    for pair in pairs:\n        metrics=joint_plan_metrics([entry[2] for entry in pair])\n        if ledger is None or metrics is None or metrics['worst_relative_gain']<=0:continue\n        best=('joint', pair)\n    return best\n"""
CORE = b"def joint_plan_metrics(infos):\n    return {'worst_relative_gain': 1}\n"


def members():
    return {"main.py": b"def agent(*a): return None\n", "frozen_selected.py": FROZEN,
            "selected_sell_core.py": CORE, "other.py": b"unchanged\n"}


def execute_synthetic_function(raw: bytes, metric_value=9):
    """Execute only the tiny pair-selection function, not its synthetic imports."""
    text = raw.decode("utf-8")
    body = text[text.index("def f"):]
    namespace = {"joint_plan_metrics": lambda _infos: {"worst_relative_gain": metric_value}}
    exec(compile(body, "<synthetic-e05-witness>", "exec"), namespace)
    return namespace["f"]


class AblationTest(unittest.TestCase):
    def test_changes_only_frozen_selected(self):
        base = members()
        cand, receipt = ablation.ablate_joint_sell(base)
        self.assertEqual(set(cand), set(base))
        self.assertEqual(cand["main.py"], base["main.py"])
        self.assertEqual(cand["selected_sell_core.py"], base["selected_sell_core.py"])
        self.assertEqual(cand["other.py"], base["other.py"])
        self.assertNotEqual(cand["frozen_selected.py"], base["frozen_selected.py"])
        self.assertNotIn(b"metrics=joint_plan_metrics", cand["frozen_selected.py"])
        self.assertIn(b"metrics=None  # evidence-only E05 joint-pair ablation", cand["frozen_selected.py"])
        self.assertIn(b"if ledger is None or metrics is None", cand["frozen_selected.py"])
        self.assertEqual(receipt["changed_members"], ["frozen_selected.py"])

    def test_reachable_joint_candidate_falls_back_to_incumbent_single_plan(self):
        base = members()
        cand, _receipt = ablation.ablate_joint_sell(base)
        pair = (("p1", "plan1", {"gain": 4}), ("p2", "plan2", {"gain": 5}))
        incumbent = ("single", "p1")
        self.assertEqual(execute_synthetic_function(base["frozen_selected.py"])(incumbent, [pair], object()),
                         ("joint", pair))
        self.assertEqual(execute_synthetic_function(cand["frozen_selected.py"])(incumbent, [pair], object()),
                         incumbent)

    def test_source_drift_fails_closed(self):
        base = members()
        base["frozen_selected.py"] = base["frozen_selected.py"].replace(
            b"joint_plan_metrics([entry[2] for entry in pair])", b"joint_plan_metrics(pair)"
        )
        with self.assertRaisesRegex(ValueError, "callsite drifted"):
            ablation.ablate_joint_sell(base)

    def test_duplicate_callsite_fails_closed(self):
        base = members()
        base["frozen_selected.py"] += b"metrics=joint_plan_metrics([entry[2] for entry in pair])\n"
        with self.assertRaisesRegex(ValueError, "callsite drifted"):
            ablation.ablate_joint_sell(base)

    def test_missing_provider_fails_closed(self):
        base = members()
        base["selected_sell_core.py"] = b"pass\n"
        with self.assertRaisesRegex(ValueError, "provider drifted"):
            ablation.ablate_joint_sell(base)

    def test_capture_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.tar.gz"
            real.write_bytes(b"x")
            link = root / "link.tar.gz"
            link.symlink_to(real)
            with self.assertRaisesRegex(ValueError, "ordinary file"):
                ablation.capture_exact_archive(link)

    def test_capture_authenticates_single_read_bytes(self):
        payload = b"submitted-v4-fixture"
        expected = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "v4.tar.gz"
            path.write_bytes(payload)
            with mock.patch.object(ablation, "BASELINE_SHA256", expected):
                captured = ablation.capture_exact_archive(path)
                path.write_bytes(b"poison-after-auth")
                self.assertEqual(captured, payload)
                self.assertNotEqual(captured, path.read_bytes())

    def test_capture_rejects_wrong_sha(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "v4.tar.gz"
            path.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "not exact submitted V4"):
                ablation.capture_exact_archive(path)


if __name__ == "__main__":
    unittest.main()
