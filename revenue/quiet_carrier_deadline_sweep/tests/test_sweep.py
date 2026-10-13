import copy
import json
import pathlib
import subprocess
import sys
import unittest

from revenue.quiet_carrier_deadline_sweep.sweep import SweepError, compile_sweep, render_markdown

HERE = pathlib.Path(__file__).resolve().parents[1]
FIX = HERE / "candidates.json"

def payload():
    return json.loads(FIX.read_text())

class SweepTests(unittest.TestCase):
    def test_impo_ranks_first_and_snoco_second(self):
        out = compile_sweep(payload())
        self.assertEqual([x["id"] for x in out["ranked_actionability"]], ["IMPO-MTP2055-2026", "SNOCO-RFP-26-0791BC"])
        self.assertEqual([x["rank"] for x in out["ranked_actionability"]], [1,2])

    def test_active_usac_is_excluded(self):
        out = compile_sweep(payload())
        row = next(x for x in out["excluded"] if x["id"] == "USAC-IT-26-139")
        self.assertIn("CURRENT_OWNER_AFTER_SEP16", row["excluded_reasons"])

    def test_deadline_exclusions(self):
        out = compile_sweep(payload())
        for cid in ("TTUHSC-739-SL3821039", "WRI-OPEN-TIMBER-PORTAL", "ALCORN-RFP-5588"):
            row = next(x for x in out["excluded"] if x["id"] == cid)
            self.assertIn("DEADLINE_OUTSIDE_SEP23_OCT15", row["excluded_reasons"])

    def test_external_authority_always_false(self):
        out = compile_sweep(payload())
        self.assertIs(out["external_action_authorized"], False)
        self.assertTrue(out["ranked_actionability"])
        for row in out["ranked_actionability"]:
            self.assertIs(row["external_action_authorized"], False)

    def test_sent_candidate_excluded(self):
        p = payload(); p["candidates"][0]["sent"] = True
        row = next(x for x in compile_sweep(p)["excluded"] if x["id"] == "IMPO-MTP2055-2026")
        self.assertIn("SENT_EXISTS", row["excluded_reasons"])

    def test_dnr_candidate_excluded(self):
        p = payload(); p["candidates"][0]["dnr"] = True
        row = next(x for x in compile_sweep(p)["excluded"] if x["id"] == "IMPO-MTP2055-2026")
        self.assertIn("DNR_EXISTS", row["excluded_reasons"])

    def test_non_hold_excluded(self):
        p = payload(); p["candidates"][0]["terminal_state"] = "READY"
        row = next(x for x in compile_sweep(p)["excluded"] if x["id"] == "IMPO-MTP2055-2026")
        self.assertIn("TERMINAL_STATE_NOT_HOLD", row["excluded_reasons"])

    def test_outside_merge_window_excluded(self):
        p = payload(); p["candidates"][0]["merged_at"] = "2026-09-16T00:00:00Z"
        row = next(x for x in compile_sweep(p)["excluded"] if x["id"] == "IMPO-MTP2055-2026")
        self.assertIn("MERGE_OUTSIDE_SEP1_15_WINDOW", row["excluded_reasons"])

    def test_past_deadline_excluded(self):
        p = payload(); p["as_of"] = "2026-10-07T00:00:00-04:00"
        row = next(x for x in compile_sweep(p)["excluded"] if x["id"] == "IMPO-MTP2055-2026")
        self.assertIn("DEADLINE_NOT_OPEN", row["excluded_reasons"])

    def test_duplicate_ids_fail(self):
        p = payload(); p["candidates"].append(copy.deepcopy(p["candidates"][0]))
        with self.assertRaises(SweepError): compile_sweep(p)

    def test_bool_smuggling_value_fails(self):
        p = payload(); p["candidates"][0]["value_path_minor"] = True
        with self.assertRaises(SweepError): compile_sweep(p)

    def test_naive_timestamp_fails(self):
        p = payload(); p["as_of"] = "2026-09-17T05:46:40"
        with self.assertRaises(SweepError): compile_sweep(p)

    def test_bad_source_state_fails(self):
        p = payload(); p["candidates"][0]["source_state"] = "MAGIC"
        with self.assertRaises(SweepError): compile_sweep(p)

    def test_deterministic_digest(self):
        a = compile_sweep(payload()); b = compile_sweep(payload())
        self.assertEqual(a,b)
        self.assertRegex(a["input_digest_sha256"], r"^[0-9a-f]{64}$")

    def test_markdown_contains_required_columns(self):
        text = render_markdown(compile_sweep(payload()))
        for label in ("Deadline (UTC)", "Value path", "One blocker", "Owner-only step", "Executable next action"):
            self.assertIn(label, text)
        self.assertIn("IMPO-MTP2055-2026", text)
        self.assertIn("USAC-IT-26-139", text)

    def test_cli_json(self):
        proc = subprocess.run([sys.executable, "-m", "revenue.quiet_carrier_deadline_sweep.sweep", str(FIX)], cwd=HERE.parents[1], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["ranked_actionability"][0]["id"], "IMPO-MTP2055-2026")

if __name__ == "__main__": unittest.main()
