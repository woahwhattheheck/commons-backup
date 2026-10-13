# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name("p07_actor_binding_panel.py")
spec = importlib.util.spec_from_file_location("p07_actor_binding_panel_tested", MODULE)
assert spec is not None and spec.loader is not None
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _game(
    opponent: str = "arlene",
    seed: int = 7,
    seat: int = 0,
    *,
    action: str = "a",
    rows: int = 1,
    commands: int = 1,
    nonpass: int = 1,
):
    return {
        "opponent": opponent,
        "seed": seed,
        "candidate_seat": seat,
        "episode_steps": 720,
        "steps": 719,
        "candidate_action_count": 719,
        "candidate_action_sha256": _digest(action),
        "hand_overage_rows": rows,
        "hand_overage_commands": commands,
        "hand_overage_nonpass_commands": nonpass,
        "hand_shape_errors": [],
        "first_hand_overages": [] if rows == 0 else [{"step": 26}],
    }


def _paired_row(*, own=0.0, margin=0.0, base="W", cand="W"):
    return {
        "opponent": "arlene",
        "seed": 7,
        "candidate_seat": 0,
        "own_delta": own,
        "margin_delta": margin,
        "baseline_outcome": base,
        "candidate_outcome": cand,
    }


def _bound(*, base_commands=1, candidate_commands=0, own=0.0, margin=0.0):
    key = ("arlene", 7, 0)
    rows = [_paired_row(own=own, margin=margin)]
    baseline = {
        key: _game(
            action="base",
            rows=int(base_commands > 0),
            commands=base_commands,
            nonpass=base_commands,
        )
    }
    candidate = {
        key: _game(
            action="candidate",
            rows=int(candidate_commands > 0),
            commands=candidate_commands,
            nonpass=candidate_commands,
        )
    }
    return panel.bind_actor_metrics(rows, baseline, candidate)


class ActorBindingPanelTests(unittest.TestCase):
    def test_bind_metrics_records_exact_reduction(self):
        rows = _bound(base_commands=3, candidate_commands=0)
        self.assertEqual(rows[0]["hand_overage_commands_delta"], -3)
        self.assertTrue(rows[0]["actor_cardinality_improved"])
        self.assertFalse(rows[0]["actor_cardinality_regressed"])
        self.assertTrue(rows[0]["candidate_action_changed"])

    def test_duplicate_pair_rejects(self):
        key = ("arlene", 7, 0)
        raw = [_paired_row(), _paired_row()]
        with self.assertRaisesRegex(ValueError, "cardinality mismatch"):
            panel.bind_actor_metrics(raw, {key: _game()}, {key: _game(action="b")})

    def test_incomplete_action_receipt_rejects(self):
        key = ("arlene", 7, 0)
        candidate = _game(action="b", rows=0, commands=0, nonpass=0)
        candidate["candidate_action_count"] = 718
        with self.assertRaisesRegex(ValueError, "action count mismatch"):
            panel.bind_actor_metrics([_paired_row()], {key: _game()}, {key: candidate})

    def test_inconsistent_metrics_reject(self):
        key = ("arlene", 7, 0)
        candidate = _game(action="b", rows=2, commands=1, nonpass=1)
        with self.assertRaisesRegex(ValueError, "rows exceed commands"):
            panel.bind_actor_metrics([_paired_row()], {key: _game()}, {key: candidate})

    def test_parity_closure_extends_panel(self):
        rows = _bound(base_commands=1, candidate_commands=0)
        summary = panel.augment_summary(
            {"cells": 1, "mean_own_delta": 0.0, "mean_margin_delta": 0.0}, rows
        )
        verdict = panel.classify_verdict(rows, summary, {"arlene": summary})
        self.assertEqual(verdict["decision"], "ACTIVE_PARITY_EXTEND_PANEL")

    def test_strict_gain_advances_to_holdout(self):
        rows = _bound(base_commands=1, candidate_commands=0, own=4.0, margin=5.0)
        summary = panel.augment_summary(
            {"cells": 1, "mean_own_delta": 4.0, "mean_margin_delta": 5.0}, rows
        )
        verdict = panel.classify_verdict(rows, summary, {"arlene": summary})
        self.assertEqual(verdict["decision"], "ADVANCE_TO_DISJOINT_HOLDOUT")

    def test_score_regression_rejects(self):
        rows = _bound(base_commands=1, candidate_commands=0, own=-1.0, margin=-1.0)
        rows[0]["baseline_outcome"] = "W"
        rows[0]["candidate_outcome"] = "L"
        summary = panel.augment_summary(
            {"cells": 1, "mean_own_delta": -1.0, "mean_margin_delta": -1.0}, rows
        )
        verdict = panel.classify_verdict(rows, summary, {"arlene": summary})
        self.assertEqual(verdict["decision"], "ACTIVE_BUT_REJECT_SCORE_SAFETY")
        self.assertEqual(verdict["new_losses"], 1)

    def test_no_defect_witness_rejects(self):
        rows = _bound(base_commands=0, candidate_commands=0)
        summary = panel.augment_summary(
            {"cells": 1, "mean_own_delta": 0.0, "mean_margin_delta": 0.0}, rows
        )
        verdict = panel.classify_verdict(rows, summary, {"arlene": summary})
        self.assertEqual(verdict["decision"], "REJECT_NO_DEFECT_WITNESS")

    def test_cardinality_increase_rejects(self):
        rows = _bound(base_commands=1, candidate_commands=2)
        summary = panel.augment_summary(
            {"cells": 1, "mean_own_delta": 0.0, "mean_margin_delta": 0.0}, rows
        )
        verdict = panel.classify_verdict(rows, summary, {"arlene": summary})
        self.assertEqual(verdict["decision"], "REJECT_DORMANT_OR_UNBOUND")
        self.assertFalse(
            verdict["structural_checks"]["no_actor_cardinality_regression"]
        )

    def test_evaluator_instrumentation_is_exact_once_and_compiles(self):
        source = "\n".join(
            [
                "import hashlib",
                "",
                "def encoded(value):",
                "    return b'x'",
                "",
                "def play(cfg, state, candidate_seat):",
                "    actors, trace = [], hashlib.sha256()",
                "    result = {\"seed\": 1, \"candidate_seat\": candidate_seat, \"status\": \"failed\", \"scores\": None,",
                "              \"failure\": None, \"steps\": 0, \"episode_steps\": cfg.episodeSteps, \"daily_bank\": []}",
                "    try:",
                "        for step in range(1):",
                "            actions = []",
                "            for actor in actors:",
                "                response = {\"action\": {\"hands\": []}}",
                "                actions.append(response[\"action\"])",
                "            for seat in range(2):",
                "                state[seat].action = actions[seat]",
                "    except Exception:",
                "        pass",
                "    try:",
                "        pass",
                "    finally:",
                "        try:",
                "            trace.update(b'x')",
                "        except Exception:",
                "            pass",
                "        else:",
                "            result[\"trace_sha256\"] = trace.hexdigest()",
                "        if finalization_errors:",
                "            pass",
                "    return result",
                "",
            ]
        )
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "evaluate.py"
            path.write_text(source, encoding="utf-8")
            panel.instrument_evaluator(path)
            compiled = path.read_text(encoding="utf-8")
            compile(compiled, str(path), "exec")
            self.assertIn("hand_overage_commands", compiled)
            with self.assertRaisesRegex(RuntimeError, "seam changed"):
                panel.instrument_evaluator(path)


if __name__ == "__main__":
    unittest.main()
