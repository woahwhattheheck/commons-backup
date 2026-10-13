from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import regression_microscope as rm

N = rm.DEFAULT_EXPECTED_ACTION_COUNT


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def action(name: str, quantity: int = 1):
    return [{"type": name, "product": "WHEAT", "quantity": quantity}]


def cell(*, seed=1, seat=0, actions=None, own=100, rival=90, world="w", trace="t", engine="e"):
    actions = actions or [action("WAIT")] * N
    return {
        "opponent": "Arlene", "seed": seed, "seat": seat,
        "state": "complete", "phase": "finalize",
        "engine_sha256": h(engine), "opponent_sha256": h("arlene"),
        "tested_seat_actions": copy.deepcopy(actions),
        "tested_action_sha256": rm.action_sequence_digest(actions),
        "terminal": {
            "own_cash": own, "rival_cash": rival,
            "terminal_world_sha256": h(world), "full_trace_sha256": h(trace),
        },
    }


def version(label: str, cells):
    cells = list(cells)
    pairs = {(row["opponent"], row["seed"]) for row in cells}
    present = {(row["opponent"], row["seed"], row["seat"]) for row in cells}
    for opponent, seed in sorted(pairs):
        if (opponent, seed, 1) not in present:
            mirror = cell(seed=seed, seat=1, world=f"mirror-world-{seed}", trace=f"mirror-trace-{seed}")
            mirror["opponent"] = opponent
            cells.append(mirror)
    return {
        "identity": {
            "source_sha256": h(f"source:{label}"),
            "archive_sha256": h(f"archive:{label}"),
            "config_sha256": h(f"config:{label}"),
        },
        "cells": cells,
    }


def dataset(versions, *, status="PASS", labels=("v1", "v2", "v3")):
    first = versions[labels[0]]["cells"] if labels[0] in versions else next(iter(versions.values()))["cells"]
    expected = []
    seen = set()
    for row in first:
        key = (row["opponent"], row["seed"], row["seat"])
        if key not in seen:
            expected.append({"opponent": key[0], "seed": key[1], "seat": key[2]})
            seen.add(key)
    return {
        "schema": rm.SCHEMA,
        "expected_action_count": N,
        "expected_cells": expected,
        "upstream_causal_gate": {
            "tool": "SOL-AUDITOR paired-evidence causal gate",
            "schema": "titan-paired-evidence/v1",
            "status": status,
            "receipt_sha256": h("causal receipt"),
        },
        "three_way": list(labels),
        "versions": versions,
    }


def actions_with(step: int, name: str, quantity: int = 1):
    result = [action("WAIT")] * N
    result[step] = action(name, quantity)
    return result


class ThreeWayRegressionMicroscopeTests(unittest.TestCase):
    def test_localises_v2_harm_v3_repair_and_signature(self):
        v1 = [action("WAIT")] * N
        v2 = actions_with(2, "BUY_PRODUCT", 3)
        v3 = actions_with(2, "SELL", 2)
        report = rm.build_report(dataset({
            "v1": version("v1", [cell(actions=v1, own=100, rival=90, world="1", trace="1")]),
            "v2": version("v2", [cell(actions=v2, own=80, rival=95, world="2", trace="2")]),
            "v3": version("v3", [cell(actions=v3, own=110, rival=90, world="3", trace="3")]),
        }))
        key = "Arlene|seed=1|seat=0"
        out = report["attribution"]
        self.assertEqual(out["v2_regression_cells"], [key])
        self.assertEqual(out["v3_repaired_to_v1_cells"], [key])
        self.assertEqual(out["v3_unrepaired_v2_regressions"], [])
        self.assertIn("step=2", out["v2_harmful_first_divergence_clusters"][0]["signature"])
        self.assertIn("BUY_PRODUCT", out["v2_harmful_first_divergence_clusters"][0]["signature"])

    def test_unrepaired_and_new_v3_regressions_remain_separate(self):
        wait = [action("WAIT")] * N
        report = rm.build_report(dataset({
            "v1": version("v1", [cell(seed=1, actions=wait, own=100, world="a1", trace="a1"), cell(seed=2, actions=wait, own=100, world="a2", trace="a2")]),
            "v2": version("v2", [cell(seed=1, actions=actions_with(0, "BUY_PRODUCT"), own=80, world="b1", trace="b1"), cell(seed=2, actions=actions_with(1, "SELL"), own=110, world="b2", trace="b2")]),
            "v3": version("v3", [cell(seed=1, actions=actions_with(0, "BUY_PRODUCT", 2), own=90, world="c1", trace="c1"), cell(seed=2, actions=actions_with(1, "BUY_PRODUCT"), own=90, world="c2", trace="c2")]),
        }))
        out = report["attribution"]
        self.assertEqual(out["v3_unrepaired_v2_regressions"], ["Arlene|seed=1|seat=0"])
        self.assertEqual(out["v3_new_regression_cells"], ["Arlene|seed=2|seat=0"])

    def test_upstream_causal_pass_and_receipt_are_mandatory(self):
        versions = {label: version(label, [cell()]) for label in ("v1", "v2", "v3")}
        with self.assertRaisesRegex(rm.MicroscopeError, "must be PASS"):
            rm.build_report(dataset(versions, status="HOLD"))
        report = rm.build_report(dataset(versions))
        self.assertEqual(report["upstream_causal_gate"]["receipt_sha256"], h("causal receipt"))

    def test_action_identical_world_score_or_trace_drift_is_invalid(self):
        wait = [action("WAIT")] * N
        report = rm.build_report(dataset({
            "v1": version("v1", [cell(actions=wait, own=100, world="a", trace="a")]),
            "v2": version("v2", [cell(actions=wait, own=120, world="b", trace="b")]),
            "v3": version("v3", [cell(actions=wait, own=100, world="a", trace="a")]),
        }))
        row = report["comparisons"]["v1->v2"]["cells"][0]
        self.assertEqual(row["classification"], "invalid_confounded")
        self.assertIn("action_identical_own_cash_drift", row["defense_in_depth_issues"])
        self.assertIn("action_identical_full_trace_drift", row["defense_in_depth_issues"])
        self.assertEqual(report["comparisons"]["v1->v2"]["summary"]["diagnostic_status"], "INVALID_EVIDENCE")

    def test_own_down_rival_down_more_is_regression_not_gain(self):
        wait = [action("WAIT")] * N
        changed = actions_with(1, "SELL")
        report = rm.build_report(dataset({
            "v1": version("v1", [cell(actions=wait, own=100, rival=100, world="a", trace="a")]),
            "v2": version("v2", [cell(actions=changed, own=90, rival=50, world="b", trace="b")]),
            "v3": version("v3", [cell(actions=wait, own=100, rival=100, world="a", trace="a")]),
        }))
        row = report["comparisons"]["v1->v2"]["cells"][0]
        self.assertEqual(row["classification"], "objective_conflict")
        self.assertEqual(row["delta"]["own_cash"], -10)
        self.assertEqual(report["comparisons"]["v1->v2"]["summary"]["diagnostic_status"], "REGRESSION_PRESENT")

    def test_action_change_requires_full_trace_change(self):
        wait = [action("WAIT")] * N
        report = rm.build_report(dataset({
            "v1": version("v1", [cell(actions=wait, world="a", trace="same")]),
            "v2": version("v2", [cell(actions=actions_with(4, "SELL"), world="b", trace="same")]),
            "v3": version("v3", [cell(actions=wait, world="a", trace="same")]),
        }))
        issues = report["comparisons"]["v1->v2"]["cells"][0]["defense_in_depth_issues"]
        self.assertIn("action_changed_but_full_trace_identical", issues)

    def test_exact_action_cardinality_and_digest_are_enforced(self):
        bad_count = cell(actions=[action("WAIT")] * (N - 1))
        versions = {"v1": version("v1", [bad_count]), "v2": version("v2", [cell()]), "v3": version("v3", [cell()])}
        with self.assertRaisesRegex(rm.MicroscopeError, f"exactly {N} returned actions"):
            rm.build_report(dataset(versions))
        bad_digest = cell()
        bad_digest["tested_action_sha256"] = h("wrong")
        versions["v1"] = version("v1", [bad_digest])
        with self.assertRaisesRegex(rm.MicroscopeError, "does not match"):
            rm.build_report(dataset(versions))

    def test_grid_duplicate_and_version_label_closure(self):
        with self.assertRaisesRegex(rm.MicroscopeError, "grid mismatch"):
            rm.build_report(dataset({
                "v1": version("v1", [cell(seed=1), cell(seed=2)]),
                "v2": version("v2", [cell(seed=1)]),
                "v3": version("v3", [cell(seed=1), cell(seed=2)]),
            }))
        duplicate = cell()
        with self.assertRaisesRegex(rm.MicroscopeError, "duplicate cell"):
            rm.build_report(dataset({
                "v1": version("v1", [duplicate, copy.deepcopy(duplicate)]),
                "v2": version("v2", [cell()]), "v3": version("v3", [cell()]),
            }))
        with self.assertRaisesRegex(rm.MicroscopeError, "must equal the three_way labels"):
            rm.build_report(dataset({
                "v1": version("v1", [cell()]), "v2": version("v2", [cell()]), "other": version("other", [cell()]),
            }))

    def test_engine_identity_mismatch_is_invalid(self):
        wait = [action("WAIT")] * N
        report = rm.build_report(dataset({
            "v1": version("v1", [cell(actions=wait, engine="a", trace="a")]),
            "v2": version("v2", [cell(actions=actions_with(2, "SELL"), engine="b", trace="b")]),
            "v3": version("v3", [cell(actions=wait, engine="a", trace="a")]),
        }))
        row = report["comparisons"]["v1->v2"]["cells"][0]
        self.assertEqual(row["classification"], "invalid_confounded")
        self.assertIn("engine_sha256_mismatch", row["defense_in_depth_issues"])

    def test_action_identical_v2_to_v3_cannot_be_reported_as_repair(self):
        a = [action("WAIT")] * N
        b = actions_with(2, "BUY_PRODUCT")
        report = rm.build_report(dataset({
            "v1": version("v1", [cell(actions=a, own=100, world="a", trace="a")]),
            "v2": version("v2", [cell(actions=b, own=80, world="b", trace="b")]),
            "v3": version("v3", [cell(actions=b, own=110, world="c", trace="c")]),
        }))
        key = "Arlene|seed=1|seat=0"
        self.assertEqual(report["comparisons"]["v2->v3"]["cells"][0]["classification"], "invalid_confounded")
        self.assertNotIn(key, report["attribution"]["v3_repaired_to_v1_cells"])
        self.assertIn(key, report["attribution"]["v3_unrepaired_v2_regressions"])

    def test_wrapped_action_step_and_seat_continuity_are_checked(self):
        wrapped = [
            {"step": index, "tested_seat": 0, "action": action("WAIT")}
            for index in range(N)
        ]
        bad_step = cell(actions=wrapped)
        bad_step["tested_seat_actions"][7]["step"] = 8
        versions = {"v1": version("v1", [bad_step]), "v2": version("v2", [cell()]), "v3": version("v3", [cell()])}
        with self.assertRaisesRegex(rm.MicroscopeError, "step must equal 7"):
            rm.build_report(dataset(versions))
        bad_seat = cell(actions=wrapped)
        bad_seat["tested_seat_actions"][7]["tested_seat"] = 1
        versions["v1"] = version("v1", [bad_seat])
        with self.assertRaisesRegex(rm.MicroscopeError, "must equal cell seat 0"):
            rm.build_report(dataset(versions))

    def test_production_action_count_and_two_seat_grid_are_fixed(self):
        versions = {label: version(label, [cell()]) for label in ("v1", "v2", "v3")}
        raw = dataset(versions)
        raw["expected_action_count"] = 5
        with self.assertRaisesRegex(rm.MicroscopeError, "must equal 719"):
            rm.build_report(raw)
        raw = dataset(versions)
        raw["expected_cells"] = [item for item in raw["expected_cells"] if item["seat"] == 0]
        with self.assertRaisesRegex(rm.MicroscopeError, "both seats"):
            rm.build_report(raw)

    def test_cli_emits_self_hashed_machine_and_human_receipts_only(self):
        wait = [action("WAIT")] * N
        raw = dataset({
            "v1": version("v1", [cell(actions=wait, own=100, world="a", trace="a")]),
            "v2": version("v2", [cell(actions=actions_with(0, "BUY_PRODUCT"), own=90, world="b", trace="b")]),
            "v3": version("v3", [cell(actions=actions_with(0, "SELL", 2), own=101, world="c", trace="c")]),
        })
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, machine, human = root / "in.json", root / "out.json", root / "out.md"
            source.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(rm.main([str(source), "--json-out", str(machine), "--markdown-out", str(human)]), 0)
            report = json.loads(machine.read_text())
            self.assertEqual(report["attribution"]["v3_repaired_to_v1_cells"], ["Arlene|seed=1|seat=0"])
            self.assertEqual(len(report["report_sha256"]), 64)
            self.assertIn("Diagnostic only", human.read_text())
            self.assertNotIn("ADVANCE", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
