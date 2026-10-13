import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE / "quietbox_gate.py"


def row(opponent="mirror", seed=11, seat=0, rep=0, margin=0, **extra):
    data = {"opponent": opponent, "seed": seed, "seat": seat, "replicate": rep, "margin": margin, "status": "completed"}
    data.update(extra)
    return data


class QuietboxGateTests(unittest.TestCase):
    def run_gate(self, quiet_rows, loaded_rows, *args):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            q = td / "q.jsonl"
            l = td / "l.jsonl"
            out = td / "out.json"
            q.write_text("".join(json.dumps(r) + "\n" for r in quiet_rows), encoding="utf-8")
            l.write_text("".join(json.dumps(r) + "\n" for r in loaded_rows), encoding="utf-8")
            cp = subprocess.run(
                [sys.executable, str(TOOL), "--quiet", str(q), "--loaded", str(l), "--out", str(out), *args],
                text=True,
                capture_output=True,
            )
            report = json.loads(out.read_text()) if out.exists() else None
            return cp, report

    def test_stable_both_seats_certifies(self):
        q = [row(seat=0, margin=-6), row(seat=1, margin=6)]
        l = [row(seat=0, margin=-10), row(seat=1, margin=9)]
        cp, report = self.run_gate(q, l)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertTrue(report["certified"])
        self.assertEqual(report["aligned_pairs"], 2)

    def test_published_quiet_vs_loaded_scale_is_rejected(self):
        q = [row(seat=0, margin=-6), row(seat=1, margin=6)]
        l = [row(seat=0, margin=-561), row(seat=1, margin=561)]
        cp, report = self.run_gate(q, l)
        self.assertEqual(cp.returncode, 2)
        self.assertFalse(report["certified"])
        self.assertGreaterEqual(report["max_abs_drift"], 555)

    def test_missing_quiet_coordinate_is_rejected(self):
        q = [row(seat=0), row(seat=1)]
        l = [row(seat=0)]
        cp, report = self.run_gate(q, l, "--allow-one-seat")
        self.assertEqual(cp.returncode, 2)
        self.assertIn("misses 1 quiet coordinates", " ".join(report["failures"]))

    def test_loaded_may_be_superset_unless_exact_requested(self):
        q = [row(seat=0), row(seat=1)]
        l = q + [row(opponent="other", seat=0), row(opponent="other", seat=1)]
        cp, report = self.run_gate(q, l)
        self.assertEqual(cp.returncode, 0)
        self.assertEqual(report["extra_loaded_count"], 2)
        cp2, report2 = self.run_gate(q, l, "--exact-coverage")
        self.assertEqual(cp2.returncode, 2)
        self.assertFalse(report2["certified"])

    def test_fallback_fails_closed_before_comparison(self):
        q = [row(seat=0), row(seat=1)]
        l = [row(seat=0, fallback=True), row(seat=1)]
        cp, report = self.run_gate(q, l)
        self.assertEqual(cp.returncode, 3)
        self.assertIsNone(report)
        self.assertIn("fallback", cp.stderr.lower())

    def test_nonfinite_fails_closed(self):
        q = [row(seat=0), row(seat=1)]
        l = [row(seat=0, margin=float("nan")), row(seat=1)]
        cp, _ = self.run_gate(q, l)
        self.assertEqual(cp.returncode, 3)
        self.assertIn("not finite", cp.stderr.lower())

    def test_score_pair_margin_inference(self):
        def s(seat, own, rival):
            return {"opponent": "mirror", "seed": 11, "seat": seat, "own_score": own, "rival_score": rival, "status": "ok"}
        q = [s(0, 100, 100), s(1, 100, 100)]
        l = [s(0, 105, 100), s(1, 99, 100)]
        cp, report = self.run_gate(q, l)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(report["margin_sources_quiet"], {"own_score-rival_score": 2})

    def test_claimed_edge_tightens_noise_budget(self):
        q = [row(seat=0, margin=0), row(seat=1, margin=0)]
        l = [row(seat=0, margin=30), row(seat=1, margin=-30)]
        cp, report = self.run_gate(q, l, "--claimed-edge", "100", "--max-abs-drift", "100", "--max-mean-abs-drift", "100", "--max-mean-bias", "100")
        self.assertEqual(cp.returncode, 2)
        self.assertEqual(report["dynamic_claimed_edge_limit"], 25)

    def test_duplicate_coordinate_is_input_error(self):
        q = [row(seat=0), row(seat=0), row(seat=1)]
        l = [row(seat=0), row(seat=1)]
        cp, _ = self.run_gate(q, l)
        self.assertEqual(cp.returncode, 3)
        self.assertIn("duplicate coordinate", cp.stderr.lower())

    def test_explicit_nested_fields(self):
        q = [
            {"who": {"opp": "m", "seat": 0}, "rng": 1, "terminal": {"margin": 0}},
            {"who": {"opp": "m", "seat": 1}, "rng": 1, "terminal": {"margin": 0}},
        ]
        l = [
            {"who": {"opp": "m", "seat": 0}, "rng": 1, "terminal": {"margin": 1}},
            {"who": {"opp": "m", "seat": 1}, "rng": 1, "terminal": {"margin": -1}},
        ]
        cp, report = self.run_gate(q, l, "--key-fields", "who.opp,rng,who.seat", "--margin-field", "terminal.margin", "--seat-key-index", "2")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertTrue(report["certified"])


if __name__ == "__main__":
    unittest.main()
