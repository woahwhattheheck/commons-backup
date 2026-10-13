"""Regression closure for #12439 semantics missed by #12646 recovery."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import random
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "v4_composed_delta_reporter", HERE / "v31_delta_distribution_report.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load adjacent composed reporter")
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


def flat_row(seat=1, baseline=None, candidate=None):
    return {
        "opponent": "official",
        "seed": 99,
        "candidate_seat": seat,
        "baseline_scores": [90, 100] if baseline is None else baseline,
        "candidate_scores": [90, 120] if candidate is None else candidate,
    }


def explicit_row():
    return {
        "opponent": "official", "seed": 99, "candidate_seat": 1,
        "baseline": {"own": 100, "rival": 90},
        "candidate": {"own": 120, "rival": 90},
    }


class MissingChildCompositionTests(unittest.TestCase):
    def test_flat_seat_one_preserves_positive_candidate_margin(self):
        result = reporter.analyze([flat_row()])
        self.assertEqual(result["delta_m"]["mean"], 20.0)
        self.assertEqual(result["by_seat"]["1"]["mean_delta_m"], 20.0)

    def test_flat_seat_zero_is_not_reversed(self):
        result = reporter.analyze([flat_row(0, [100, 90], [120, 90])])
        self.assertEqual(result["delta_m"]["mean"], 20.0)

    def test_flat_seat_one_new_loss_is_not_laundered_into_win(self):
        result = reporter.analyze([flat_row(1, [90, 100], [90, 80])])
        self.assertEqual(result["delta_m"]["mean"], -20.0)
        self.assertEqual(result["outcomes"]["transitions"], {"W->L": 1})
        self.assertEqual(len(result["outcomes"]["new_losses"]), 1)
        self.assertTrue(reporter.policy_failures(result, require_no_new_losses=True))

    def test_flat_nested_and_explicit_aliases_can_agree_after_orientation(self):
        row = flat_row()
        row.update({
            "baseline": {"scores": [90, 100], "own": 100, "rival": 90},
            "candidate": {"scores": [90, 120], "own": 120, "rival": 90},
            "baseline_own": 100, "baseline_rival": 90,
            "candidate_own": 120, "candidate_rival": 90,
            "delta_m": 20,
        })
        before = deepcopy(row)
        result = reporter.analyze([row])
        self.assertEqual(result["delta_m"]["mean"], 20.0)
        self.assertEqual(result["delta_m"]["supplied_mismatch_count"], 0)
        self.assertEqual(row, before)

    def test_flat_alias_cannot_certify_reversed_explicit_pair(self):
        for arm in ("baseline", "candidate"):
            with self.subTest(arm=arm):
                row = flat_row()
                vector = row[arm + "_scores"]
                row[arm] = {"own": vector[0], "rival": vector[1]}
                with self.assertRaisesRegex(reporter.DataError, "conflicting .* score forms"):
                    reporter.analyze([row])

    def test_seeded_schema_equivalence_across_both_seats(self):
        rng = random.Random(1243912646)
        for case in range(128):
            base = [rng.randrange(-1000, 10000), rng.randrange(-1000, 10000)]
            cand = [rng.randrange(-1000, 10000), rng.randrange(-1000, 10000)]
            for seat in (0, 1):
                with self.subTest(case=case, seat=seat):
                    flat = flat_row(seat, base, cand)
                    nested = {key: value for key, value in flat.items() if not key.endswith("_scores")}
                    nested.update(baseline={"scores": base}, candidate={"scores": cand})
                    explicit = {key: value for key, value in nested.items() if key not in ("baseline", "candidate")}
                    explicit.update(
                        baseline={"own": base[seat], "rival": base[1 - seat]},
                        candidate={"own": cand[seat], "rival": cand[1 - seat]},
                    )
                    self.assertEqual(reporter.analyze([flat]), reporter.analyze([nested]))
                    self.assertEqual(reporter.analyze([flat]), reporter.analyze([explicit]))

    def test_duplicate_aliases_distinguish_json_scalar_types_recursively(self):
        for left, right in ((True, 1), (False, 0), (1, 1.0)):
            for key in ("results", "games", "matches"):
                with self.subTest(left_type=type(left).__name__, right_type=type(right).__name__, key=key):
                    a, b = explicit_row(), explicit_row()
                    a["metadata"] = {"nested": [{"value": left}]}
                    b["metadata"] = {"nested": [{"value": right}]}
                    with self.assertRaisesRegex(reporter.DataError, "conflicting evidence-container aliases"):
                        reporter.load_records({"cells": [a], key: [b]})

    def test_duplicate_aliases_reject_structural_and_value_drift(self):
        for other in ([1, 2], {"x": [1, 3]}, {"y": [1, 2]}, {"x": [1]}):
            with self.subTest(other=other):
                a, b = explicit_row(), explicit_row()
                a["metadata"], b["metadata"] = {"x": [1, 2]}, other
                with self.assertRaises(reporter.DataError):
                    reporter.load_records({"cells": [a], "results": [b]})

    def test_equal_distinct_container_copies_remain_supported_without_mutation(self):
        row = explicit_row()
        row["metadata"] = {"nested": [True, 1, 1.0, None, "1"]}
        document = {key: [deepcopy(row)] for key in ("cells", "results", "games", "matches")}
        before = deepcopy(document)
        result = reporter.analyze(reporter.load_records(document))
        self.assertEqual(result["delta_m"]["mean"], 20.0)
        self.assertEqual(document, before)

    def test_mixed_partial_and_malformed_arm_closure_is_preserved(self):
        for document in (
            {"baseline": []}, {"candidate": []}, {"baseline": {}, "candidate": []},
            {"baseline": [], "candidate": None},
            {"baseline": [], "candidate": [], "cells": [explicit_row()]},
            {"baseline": {}, "candidate": [], "cells": [explicit_row()]},
        ):
            with self.subTest(document=document):
                with self.assertRaises(reporter.DataError):
                    reporter.load_records(document)

    def test_flat_numeric_poison_still_fails_closed(self):
        for arm in ("baseline_scores", "candidate_scores"):
            for value in (True, "1", None, 10 ** 1000, float("nan"), float("inf")):
                with self.subTest(arm=arm, kind=type(value).__name__):
                    row = flat_row()
                    row[arm] = [90, value]
                    with self.assertRaises(reporter.DataError):
                        reporter.analyze([row])

    def test_cli_seat_orientation_preserves_policy_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            evidence = Path(td) / "evidence.json"
            evidence.write_text(json.dumps([flat_row()]), encoding="utf-8")
            for threshold, expected in (("19", 0), ("20", 0), ("21", 1)):
                with self.subTest(threshold=threshold):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        code = reporter.main([str(evidence), "--min-mean-delta", threshold])
                    self.assertEqual(code, expected)
                    self.assertEqual(json.loads(stdout.getvalue())["delta_m"]["mean"], 20.0)

    def test_cli_conflicting_types_emit_no_report_and_preserve_output(self):
        a, b = explicit_row(), explicit_row()
        a["metadata"], b["metadata"] = {"x": True}, {"x": 1}
        with tempfile.TemporaryDirectory() as td:
            evidence, output = Path(td) / "evidence.json", Path(td) / "report.json"
            evidence.write_text(json.dumps({"cells": [a], "results": [b]}), encoding="utf-8")
            output.write_text("unchanged", encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = reporter.main([str(evidence), "--output", str(output)])
            self.assertEqual(code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("DATA ERROR:", stderr.getvalue())
            self.assertEqual(output.read_text(encoding="utf-8"), "unchanged")


if __name__ == "__main__":
    unittest.main()
