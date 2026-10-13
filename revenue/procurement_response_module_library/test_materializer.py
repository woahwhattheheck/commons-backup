import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from . import materializer as m
except ImportError:
    import materializer as m

SHA = "a" * 64

def record(**kw):
    v = {
        "record_id":"r1","evidence_id":"ev1","module_id":"mod1","claim_id":"cl1",
        "family":"corporate_capability","title":"Capability","claim_text":"Supported bounded capability.",
        "claim_kind":"CAPABILITY","source_kind":"APPROVED_CAPABILITY_FACT","source_ref":"receipt://cap/1",
        "source_sha256":SHA,"observed_at":"2026-09-16T20:00:00Z","expires_at":"2026-10-16T20:00:00Z",
        "owner_status":"APPROVED","evidence_state":"SUPPORTED","revision":1,
        "valid_from":"2026-09-01T00:00:00Z","valid_until":"2026-12-31T23:59:59Z",
        "applicability_tags":["general","public_sector"],
    }
    v.update(kw); return v

def source(*records):
    return {"schema":m.SOURCE_SCHEMA,"library_id":"materialized-demo","generated_at":"2026-09-16T22:40:00Z","evidence_max_age_seconds":31536000,"truth_boundary":m.TRUTH_BOUNDARY,"records":list(records or [record()])}

def raw(obj): return m.canon(obj)

class Tests(unittest.TestCase):
    def test_supported_generic_fact(self):
        cb, db, rb = m.compile_materializer(raw(source()))
        c = json.loads(cb); self.assertEqual(c["evidence"][0]["status"], "SUPPORTED")
        self.assertEqual(c["modules"][0]["owner_status"], "APPROVED")
        self.assertTrue(m.verify_materializer(raw(source()), cb, db, rb))

    def test_sensitive_claim_requires_exact_proof(self):
        cases = [
            ("CERTIFICATION","APPROVED_INTERNAL_RECEIPT","compliance_crosswalk"),
            ("REFERENCE","APPROVED_CAPABILITY_FACT","references_past_performance"),
            ("SLA","APPROVED_POLICY","sla_support"),
            ("SECURITY_CONTROL","APPROVED_POLICY","cybersecurity"),
        ]
        for kind, sk, family in cases:
            with self.subTest(kind=kind):
                c = json.loads(m.compile_materializer(raw(source(record(family=family, claim_kind=kind, source_kind=sk))))[0])
                self.assertEqual(c["evidence"][0]["status"], "PARTIAL")
                self.assertEqual(c["modules"][0]["owner_status"], "PENDING")
                self.assertIn("SENSITIVE_PROOF_REQUIRED", c["evidence"][0]["summary"])

    def test_sensitive_exact_proof_still_requires_specialized_authority(self):
        rows = [
            record(family="compliance_crosswalk", claim_kind="CERTIFICATION", source_kind="ISSUER_VERIFIED_CERTIFICATION"),
            record(family="references_past_performance", claim_kind="REFERENCE", source_kind="REFERENCE_PERMISSION_RECEIPT"),
            record(family="sla_support", claim_kind="SLA", source_kind="ACCEPTED_SLA_RECEIPT"),
            record(family="cybersecurity", claim_kind="SECURITY_CONTROL", source_kind="CONTROL_TEST_RECEIPT"),
        ]
        for row in rows:
            with self.subTest(kind=row["claim_kind"]):
                c = json.loads(m.compile_materializer(raw(source(row)))[0])
                self.assertEqual(c["evidence"][0]["status"], "PARTIAL")
                self.assertIn("SPECIALIZED_AUTHORITY_REQUIRED", c["evidence"][0]["summary"])

    def test_family_kind_alias_bypass_rejected(self):
        with self.assertRaises(m.Error):
            m.compile_materializer(raw(source(record(family="references_past_performance", claim_kind="CAPABILITY"))))

    def test_sensitive_language_in_generic_claim_holds(self):
        c=json.loads(m.compile_materializer(raw(source(record(claim_text="We are SOC 2 certified."))))[0])
        self.assertEqual(c["evidence"][0]["status"], "PARTIAL")
        self.assertIn("SENSITIVE_LANGUAGE_REQUIRES_SPECIALIZED_PROOF", c["evidence"][0]["summary"])

    def test_stale_beyond_catalog_max_age_rejected(self):
        s=source(record(observed_at="2025-01-01T00:00:00Z", expires_at="2027-01-01T00:00:00Z")); s["evidence_max_age_seconds"]=86400
        with self.assertRaises(m.Error): m.compile_materializer(raw(s))

    def test_synthetic_never_supports(self):
        c = json.loads(m.compile_materializer(raw(source(record(source_kind="SYNTHETIC_FIXTURE"))))[0])
        self.assertEqual(c["evidence"][0]["status"], "PARTIAL")
        self.assertIn("SYNTHETIC_ONLY", c["evidence"][0]["summary"])

    def test_pending_owner_holds(self):
        c = json.loads(m.compile_materializer(raw(source(record(owner_status="PENDING"))))[0])
        self.assertEqual(c["evidence"][0]["status"], "PARTIAL")

    def test_expired_holds(self):
        c = json.loads(m.compile_materializer(raw(source(record(expires_at="2026-09-16T22:39:59Z"))))[0])
        self.assertEqual(c["evidence"][0]["status"], "PARTIAL")
        self.assertIn("EXPIRED", c["evidence"][0]["summary"])

    def test_future_evidence_rejected(self):
        with self.assertRaises(m.Error): m.compile_materializer(raw(source(record(observed_at="2026-09-17T00:00:00Z", expires_at="2026-10-17T00:00:00Z"))))

    def test_duplicate_json_key_rejected(self):
        bad = b'{"schema":"x","schema":"y"}'
        with self.assertRaises(m.Error): m.load(bad)

    def test_float_nan_bool_revision_rejected(self):
        for bad in [b'{"x":1.5}', b'{"x":NaN}']:
            with self.assertRaises(m.Error): m.load(bad)
        x=source(); x["records"][0]["revision"]=True
        with self.assertRaises(m.Error): m.compile_materializer(raw(x))

    def test_lone_surrogate_rejected(self):
        bad=b'{"x":"\\ud800"}'
        with self.assertRaises(m.Error): m.load(bad)

    def test_unknown_family_rejected(self):
        with self.assertRaises(m.Error): m.compile_materializer(raw(source(record(family="unknown"))))

    def test_duplicate_id_rejected(self):
        r2=record(record_id="r2", module_id="mod2", claim_id="cl2")
        with self.assertRaises(m.Error): m.compile_materializer(raw(source(record(), r2)))

    def test_diff_added_changed_removed_deterministic(self):
        src=raw(source())
        cb, db, _=m.compile_materializer(src)
        d=json.loads(db); self.assertEqual(d["added_module_ids"],["mod1"])
        prev=json.loads(cb)
        changed=source(record(claim_text="Changed bounded capability."))
        _, db2, _=m.compile_materializer(raw(changed), raw(prev))
        d2=json.loads(db2); self.assertEqual(d2["changed_module_ids"],["mod1"]); self.assertEqual(d2["changed_evidence_ids"],[])
        removed=copy.deepcopy(prev); removed["modules"].append({**removed["modules"][0],"module_id":"old"})
        _, db3, _=m.compile_materializer(src, raw(removed)); self.assertEqual(json.loads(db3)["removed_module_ids"],["old"])

    def test_tamper_verify_false(self):
        sr=raw(source()); cb,db,rb=m.compile_materializer(sr)
        tampered=cb.replace(b"Supported bounded capability", b"Forged bounded capability")
        self.assertFalse(m.verify_materializer(sr,tampered,db,rb))

    def test_authority_all_false(self):
        rb=m.compile_materializer(raw(source()))[2]; a=json.loads(rb)["authority"]
        self.assertTrue(a); self.assertTrue(all(v is False for v in a.values()))

    def test_cli_roundtrip_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); src=p/"source.json"; src.write_bytes(raw(source()))
            out=p/"out"
            cmd=[sys.executable, m.__file__, "compile", "--source", str(src), "--out-dir", str(out)]
            q=subprocess.run(cmd,capture_output=True,text=True); self.assertEqual(q.returncode,0,q.stderr)
            v=subprocess.run([sys.executable,m.__file__,"verify","--source",str(src),"--catalog",str(out/"catalog.json"),"--diff",str(out/"diff.json"),"--receipt",str(out/"receipt.json")],capture_output=True,text=True)
            self.assertEqual(v.returncode,0,v.stderr); self.assertIn('"verified": true',v.stdout)
            again=subprocess.run(cmd,capture_output=True,text=True); self.assertEqual(again.returncode,2); self.assertIn("must not already exist",again.stderr)

if __name__ == "__main__": unittest.main()
