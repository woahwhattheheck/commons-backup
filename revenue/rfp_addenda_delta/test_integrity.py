from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    from . import cli, engine as engine_module
    from .engine import compile_current, verify_report, markdown
    from .schema import DeltaError, canonical, loads_strict, normalize_generation
    from .test_helpers import decision_for, doc, generation, h, req
except ImportError:
    import cli, engine as engine_module
    from engine import compile_current, verify_report, markdown
    from schema import DeltaError, canonical, loads_strict, normalize_generation
    from test_helpers import decision_for, doc, generation, h, req


class DeltaIntegrityTests(unittest.TestCase):
    NOW = "2026-09-13T18:00:00Z"

    def report(self, old, new, decisions=None):
        with patch.object(engine_module, "_process_now", return_value=self.NOW):
            return compile_current(old, new, decisions or [])

    def test_requirement_on_secondary_source_rejected(self):
        bad = generation(documents=[doc(authority="OFFICIAL"), doc("mirror", role="ADDENDUM", authority="SECONDARY")],
                         requirements=[req(doc_id="mirror")])
        with self.assertRaises(DeltaError):
            normalize_generation(bad)

    def test_official_base_required(self):
        bad = generation(documents=[doc("mirror", role="ADDENDUM", authority="SECONDARY")])
        with self.assertRaises(DeltaError):
            normalize_generation(bad)

    def test_bool_not_string(self):
        bad = generation()
        bad["requirements"][0]["curable"] = 1
        with self.assertRaises(DeltaError):
            normalize_generation(bad)

    def test_unknown_generation_key_rejected(self):
        bad = generation()
        bad["extra"] = False
        with self.assertRaises(DeltaError):
            normalize_generation(bad)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(DeltaError):
            loads_strict('{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(DeltaError):
            loads_strict('{"a":NaN}')

    def test_url_credentials_rejected(self):
        bad = generation()
        bad["documents"][0]["url"] = "https://user:pass@buyer.example/rfp.pdf"
        with self.assertRaises(DeltaError):
            normalize_generation(bad)

    def test_noncanonical_time_rejected(self):
        bad = generation(captured="2026-09-13T12:00:00+00:00")
        with self.assertRaises(DeltaError):
            normalize_generation(bad)

    def test_order_invariant(self):
        old = generation(
            documents=[doc("add-1", role="ADDENDUM"), doc()],
            requirements=[req("R-002", doc_id="add-1", cls="INFORMATIONAL", response=None), req()],
        )
        new = generation(
            "g2", "2026-09-13T13:00:00Z",
            documents=[doc(), doc("add-1", role="ADDENDUM")],
            requirements=[req(), req("R-002", doc_id="add-1", cls="INFORMATIONAL", response=None)],
        )
        d = [decision_for(old)]
        a = self.report(old, new, d)
        old["documents"].reverse()
        old["requirements"].reverse()
        new["documents"].reverse()
        new["requirements"].reverse()
        b = self.report(old, new, d)
        self.assertEqual(canonical(a), canonical(b))

    def test_report_verifies_and_tamper_fails(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z")
        d = [decision_for(old)]
        report = self.report(old, new, d)
        with patch.object(engine_module, "_process_now", return_value=self.NOW):
            self.assertEqual(verify_report(old, new, d, report), (True, "ok"))
        forged = json.loads(canonical(report))
        forged["state"] = "REVIEW_REQUIRED"
        with patch.object(engine_module, "_process_now", return_value=self.NOW):
            self.assertFalse(verify_report(old, new, d, forged)[0])

    def test_reseal_tamper_still_fails_recompile(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z")
        d = [decision_for(old)]
        report = self.report(old, new, d)
        forged = json.loads(canonical(report))
        forged["state"] = "REVIEW_REQUIRED"
        unsigned = dict(forged)
        unsigned.pop("semantic_sha256")
        forged["semantic_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
        with patch.object(engine_module, "_process_now", return_value=self.NOW):
            self.assertEqual(verify_report(old, new, d, forged), (False, "report_recompile_mismatch"))

    def test_markdown_contains_authority_ceiling(self):
        old = generation()
        out = self.report(old, generation("g2", "2026-09-13T13:00:00Z"), [decision_for(old)])
        text = markdown(out)
        self.assertIn("Authority ceiling", text)
        self.assertIn("no buyer contact", text)

    def test_cli_compile_verify_and_no_overwrite(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z")
        decisions = [decision_for(old)]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, value in (("old.json", old), ("new.json", new), ("decisions.json", decisions)):
                (root / name).write_bytes(canonical(value))
            out_json, out_md = root / "report.json", root / "report.md"
            rc = cli.main([
                "compile", "--old", str(root/"old.json"), "--new", str(root/"new.json"),
                "--decisions", str(root/"decisions.json"), "--out-json", str(out_json),
                "--out-md", str(out_md),
            ])
            self.assertEqual(rc, 0)
            rc2 = cli.main([
                "verify", "--old", str(root/"old.json"), "--new", str(root/"new.json"),
                "--decisions", str(root/"decisions.json"), "--report", str(out_json),
            ])
            self.assertEqual(rc2, 0)
            rc3 = cli.main([
                "compile", "--old", str(root/"old.json"), "--new", str(root/"new.json"),
                "--decisions", str(root/"decisions.json"), "--out-json", str(out_json),
                "--out-md", str(root/"report2.md"),
            ])
            self.assertEqual(rc3, 2)

    def test_cli_preflights_both_outputs_before_publication(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z")
        decisions = [decision_for(old)]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, value in (("old.json", old), ("new.json", new), ("decisions.json", decisions)):
                (root / name).write_bytes(canonical(value))
            out_json, out_md = root / "report.json", root / "report.md"
            out_md.write_text("existing")
            rc = cli.main([
                "compile", "--old", str(root/"old.json"), "--new", str(root/"new.json"),
                "--decisions", str(root/"decisions.json"), "--out-json", str(out_json),
                "--out-md", str(out_md),
            ])
            self.assertEqual(rc, 2)
            self.assertFalse(out_json.exists())
            self.assertEqual(out_md.read_text(), "existing")

    def test_cli_rejects_same_output_path(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"old.json").write_bytes(canonical(old))
            (root/"new.json").write_bytes(canonical(new))
            out = root/"report.out"
            rc = cli.main([
                "compile", "--old", str(root/"old.json"), "--new", str(root/"new.json"),
                "--out-json", str(out), "--out-md", str(out),
            ])
            self.assertEqual(rc, 2)
            self.assertFalse(out.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_cli_refuses_symlink_output(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"old.json").write_bytes(canonical(old))
            (root/"new.json").write_bytes(canonical(new))
            target = root/"target.json"
            target.write_text("do-not-touch")
            link = root/"report.json"
            os.symlink(target, link)
            rc = cli.main([
                "compile", "--old", str(root/"old.json"), "--new", str(root/"new.json"),
                "--out-json", str(link), "--out-md", str(root/"report.md"),
            ])
            self.assertEqual(rc, 2)
            self.assertEqual(target.read_text(), "do-not-touch")

    def test_boolean_report_field_tamper_rejected(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z")
        report = self.report(old, new, [decision_for(old)])
        report["authority"]["buyer_contact"] = 0
        unsigned = dict(report)
        unsigned.pop("semantic_sha256")
        report["semantic_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
        with patch.object(engine_module, "_process_now", return_value=self.NOW):
            self.assertFalse(verify_report(old, new, [decision_for(old)], report)[0])


if __name__ == "__main__":
    unittest.main()
