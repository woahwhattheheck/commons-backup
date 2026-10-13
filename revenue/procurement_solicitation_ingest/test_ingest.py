from __future__ import annotations

import copy
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from revenue.procurement_solicitation_ingest.ingest import Error, compile_ingest, load, verify

ROOT = Path(__file__).parent
PACK = ROOT / "fixtures" / "synthetic_pack.json"


def raw(x):
    return (json.dumps(x, sort_keys=True, separators=(",", ":")) + "\n").encode()


class T(unittest.TestCase):
    def setUp(self):
        self.pb = PACK.read_bytes()
        self.p = json.loads(self.pb)

    def test_ready_selector_and_authority_false(self):
        o = compile_ingest(self.pb)
        sel = json.loads(o.selector)
        ready = json.loads(o.readiness)
        self.assertEqual("OWNER_REVIEW_READY", o.status)
        self.assertEqual("procurement-response-modules/solicitation/v1", sel["schema"])
        self.assertEqual("synthetic-public-sector-rfp", sel["solicitation_id"])
        self.assertEqual("2026-09-16T23:00:00Z", sel["generated_at"])
        self.assertEqual("2026-09-16T15:00:00Z", sel["observed_at"])
        kinds = {x["section_id"]: x["required"] for x in sel["requirements"]}
        self.assertTrue(kinds["section-01-corporate_capability"])
        self.assertTrue(kinds["section-03-cybersecurity"])
        self.assertTrue(kinds["section-04-accessibility"])
        self.assertFalse(kinds["section-06-sla_support"])
        cyber = next(x for x in sel["requirements"] if x["section_id"] == "section-03-cybersecurity")
        self.assertEqual(["fedramp", "public_sector"], cyber["required_tags"])
        self.assertTrue(all(v is False for v in ready["authority"].values()))
        self.assertEqual(1, ready["informational_requirement_count"])
        self.assertEqual(3, ready["blocking_requirement_count"])
        self.assertEqual("2026-10-08T17:00:00-07:00", ready["active_deadline"]["value"])

    def test_amendment_supersedes_lineage_text(self):
        active = json.loads(compile_ingest(self.pb).active)
        cyber = next(x for x in active["requirements"] if x["lineage_id"] == "req-cybersecurity")
        self.assertIn("FedRAMP", cyber["text"])
        self.assertEqual("amd-001", cyber["source_id"])
        self.assertEqual("dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd", cyber["source_sha256"])

    def test_secondary_cannot_create_or_supersede(self):
        active = json.loads(compile_ingest(self.pb).active)
        gaps = json.loads(compile_ingest(self.pb).gaps)
        ids = {x["lineage_id"] for x in active["requirements"]}
        self.assertIn("req-corporate-capability", ids)
        self.assertNotIn("req-pricing", ids)
        self.assertTrue(any(g["reason"] == "SECONDARY_SOURCE_CANNOT_CREATE_OR_SUPERSEDE" for g in gaps["gaps"]))
        self.assertNotEqual("2026-11-01T17:00:00-07:00", json.loads(compile_ingest(self.pb).readiness)["active_deadline"]["value"])

    def test_attachments_retained(self):
        active = json.loads(compile_ingest(self.pb).active)
        aids = {a["attachment_id"] for a in active["attachments"]}
        self.assertEqual({"att-rfp-body", "att-amend-1"}, aids)

    def test_unknown_source_target(self):
        p = copy.deepcopy(self.p)
        p["sources"][1]["supersedes_sources"] = ["nope"]
        self.assertRaisesRegex(Error, "unknown supersession target", compile_ingest, raw(p))

    def test_unknown_lineage_target(self):
        p = copy.deepcopy(self.p)
        p["sources"][1]["supersedes_lineages"] = ["nope"]
        self.assertRaisesRegex(Error, "unknown supersession target", compile_ingest, raw(p))

    def test_same_sequence_supersession(self):
        p = copy.deepcopy(self.p)
        p["sources"][1]["sequence"] = 1
        self.assertRaisesRegex(Error, "duplicate official sequence", compile_ingest, raw(p))

    def test_later_sequence_target_supersession(self):
        p = copy.deepcopy(self.p)
        p["sources"][0]["supersedes_sources"] = ["amd-001"]
        self.assertRaisesRegex(Error, "same/later-sequence supersession", compile_ingest, raw(p))

    def test_self_cycle(self):
        p = copy.deepcopy(self.p)
        p["sources"][1]["supersedes_sources"] = ["amd-001"]
        self.assertRaisesRegex(Error, "same/later-sequence supersession", compile_ingest, raw(p))

    def test_two_active_lineage_values(self):
        p = copy.deepcopy(self.p)
        p["sources"][1]["supersedes_lineages"] = []
        p["sources"][1]["deadline"]["supersedes_deadline"] = True
        self.assertRaisesRegex(Error, "two active values for lineage", compile_ingest, raw(p))

    def test_zero_deadline_hold(self):
        p = copy.deepcopy(self.p)
        p["sources"][0]["deadline"] = None
        p["sources"][1]["deadline"] = None
        p["sources"][1]["supersedes_lineages"] = ["req-cybersecurity"]
        o = compile_ingest(raw(p))
        self.assertEqual("HOLD", o.status)
        self.assertIn("ZERO_OR_MULTIPLE_ACTIVE_SUBMISSION_DEADLINES", json.loads(o.readiness)["hold_reasons"])

    def test_multiple_deadline_hold(self):
        p = copy.deepcopy(self.p)
        p["sources"][1]["deadline"]["supersedes_deadline"] = False
        o = compile_ingest(raw(p))
        self.assertEqual("HOLD", o.status)
        self.assertIn("ZERO_OR_MULTIPLE_ACTIVE_SUBMISSION_DEADLINES", json.loads(o.readiness)["hold_reasons"])

    def test_source_kill_removes_requirements(self):
        p = copy.deepcopy(self.p)
        p["sources"][1]["supersedes_sources"] = ["sol-001"]
        p["sources"][1]["supersedes_lineages"] = []
        o = compile_ingest(raw(p))
        active = json.loads(o.active)
        ids = {x["lineage_id"] for x in active["requirements"]}
        self.assertEqual({"req-cybersecurity"}, ids)
        self.assertEqual(["sol-001"], active["killed_sources"])

    def test_duplicate_json_key(self):
        self.assertRaisesRegex(Error, "duplicate JSON key", load, b'{"x":1,"x":2}')

    def test_bom(self):
        self.assertRaisesRegex(Error, "BOM", load, b"\xef\xbb\xbf{}")

    def test_float(self):
        self.assertRaisesRegex(Error, "non-integer", load, b'{"x":1.2}')

    def test_bool_sequence(self):
        p = copy.deepcopy(self.p)
        p["sources"][0]["sequence"] = True
        self.assertRaisesRegex(Error, "integer required", compile_ingest, raw(p))

    def test_future_source(self):
        p = copy.deepcopy(self.p)
        p["sources"][0]["captured_at"] = "2026-09-17T00:00:00-07:00"
        self.assertRaisesRegex(Error, "future source", compile_ingest, raw(p))

    def test_stale_source(self):
        p = copy.deepcopy(self.p)
        p["source_max_age_seconds"] = 1
        self.assertRaisesRegex(Error, "stale source", compile_ingest, raw(p))

    def test_ocr_guess_key_rejected(self):
        p = copy.deepcopy(self.p)
        p["sources"][0]["ocr_guess"] = True
        self.assertRaisesRegex(Error, "keys mismatch", compile_ingest, raw(p))

    def test_naive_timestamp_rejected(self):
        p = copy.deepcopy(self.p)
        p["evaluated_at"] = "2026-09-16T16:00:00"
        self.assertRaisesRegex(Error, "RFC3339-with-offset", compile_ingest, raw(p))

    def test_informational_not_blocking(self):
        gaps = json.loads(compile_ingest(self.pb).gaps)
        info = next(g for g in gaps["gaps"] if g["gap_id"] == "informational:req-sla-support")
        self.assertFalse(info["blocking"])
        man = next(g for g in gaps["gaps"] if g["gap_id"] == "human-evidence:req-corporate-capability")
        self.assertTrue(man["blocking"])

    def test_tamper_selector(self):
        o = compile_ingest(self.pb)
        s = json.loads(o.selector)
        s["authority"] = {"submission_authorized": True}
        self.assertRaisesRegex(
            Error,
            "selector mismatch",
            verify,
            self.pb,
            raw(s),
            o.active,
            o.gaps,
            o.markdown,
            o.readiness,
            o.receipt,
        )

    def test_tamper_receipt_authority(self):
        o = compile_ingest(self.pb)
        r = json.loads(o.receipt)
        r["authority"]["payment_authorized"] = True
        self.assertRaisesRegex(
            Error,
            "receipt mismatch",
            verify,
            self.pb,
            o.selector,
            o.active,
            o.gaps,
            o.markdown,
            o.readiness,
            raw(r),
        )

    def test_verify_roundtrip(self):
        o = compile_ingest(self.pb)
        v = verify(self.pb, o.selector, o.active, o.gaps, o.markdown, o.readiness, o.receipt)
        self.assertTrue(v["verified"])
        self.assertEqual("OWNER_REVIEW_READY", v["status"])

    def test_cli_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            base = [sys.executable, "-m", "revenue.procurement_solicitation_ingest.ingest"]
            a = subprocess.run(
                base + ["compile", "--pack", str(PACK), "--out-dir", d],
                cwd=ROOT.parents[1],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, a.returncode, a.stderr)
            b = subprocess.run(
                base
                + [
                    "verify",
                    "--pack",
                    str(PACK),
                    "--selector",
                    d + "/selector.json",
                    "--active-set",
                    d + "/active_set.json",
                    "--gaps",
                    d + "/gaps.json",
                    "--markdown",
                    d + "/gaps.md",
                    "--readiness",
                    d + "/readiness.json",
                    "--receipt",
                    d + "/receipt.json",
                ],
                cwd=ROOT.parents[1],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, b.returncode, b.stderr)
            self.assertIn('"verified": true', b.stdout)
            c = subprocess.run(
                base + ["compile", "--pack", str(PACK), "--out-dir", d],
                cwd=ROOT.parents[1],
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, c.returncode)
            self.assertIn("HOLD:", c.stderr)

    def test_fifo_compile_does_not_hang(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("platform has no mkfifo")
        with tempfile.TemporaryDirectory() as d:
            fifo = Path(d) / "pack.json"
            os.mkfifo(fifo, 0o600)
            self.assertTrue(stat.S_ISFIFO(os.stat(fifo).st_mode))
            base = [sys.executable, "-m", "revenue.procurement_solicitation_ingest.ingest"]
            a = subprocess.run(
                base + ["compile", "--pack", str(fifo), "--out-dir", d + "/out"],
                cwd=ROOT.parents[1],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(2, a.returncode, a.stderr)
            self.assertIn("not a regular file", a.stderr)


if __name__ == "__main__":
    unittest.main()
