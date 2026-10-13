import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
FIXTURE = PKG/"fixtures"/"vault.synthetic.json"
SPEC = importlib.util.spec_from_file_location("vault", PKG/"compile_vault.py")
vault = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(vault)

def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))

def state_map(raw):
    artifact, internal, public, receipt = vault.compile_vault(raw)
    return {r["request_id"]: r["state"] for r in artifact["results"]}, artifact, internal, public, receipt

class ConsentVaultTests(unittest.TestCase):
    def test_fixture_states(self):
        states, _, _, public, receipt = state_map(fixture())
        self.assertEqual(states["REQ-PUBLIC"], "PUBLIC_CASE_STUDY_OK")
        self.assertEqual(states["REQ-REF"], "REFERENCE_OK")
        self.assertEqual(states["REQ-PAYMENT-INTERNAL"], "INTERNAL_ONLY")
        self.assertEqual(receipt["hold_permission"], 0)
        self.assertNotIn("evidence/private", public)

    def test_merge_never_mints_reference_permission(self):
        raw = fixture()
        raw["requests"][1]["permission_id"] = None
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-REF"], "INTERNAL_ONLY")

    def test_delivery_never_mints_case_study_permission(self):
        raw = fixture()
        raw["requests"][0]["permission_id"] = None
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "INTERNAL_ONLY")

    def test_payment_never_mints_case_study_permission(self):
        states, *_ = state_map(fixture())
        self.assertEqual(states["REQ-PAYMENT-INTERNAL"], "INTERNAL_ONLY")

    def test_expired_permission_holds(self):
        raw = fixture()
        raw["permissions"][0]["valid_through"] = "2026-09-16T00:00:00Z"
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "HOLD_PERMISSION")

    def test_revoked_permission_holds(self):
        raw = fixture()
        raw["permissions"][0]["revoked_at"] = "2026-09-16T16:00:00Z"
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "HOLD_PERMISSION")

    def test_future_grant_holds(self):
        raw = fixture()
        raw["permissions"][0]["granted_at"] = "2026-09-18T00:00:00Z"
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "HOLD_PERMISSION")

    def test_claim_drift_holds(self):
        raw = fixture()
        raw["requests"][0]["claim_text"] = "Delivered everything perfectly."
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "HOLD_PERMISSION")

    def test_category_drift_holds(self):
        raw = fixture()
        raw["requests"][0]["category"] = "SAVINGS"
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "HOLD_PERMISSION")

    def test_named_use_requires_permission(self):
        raw = fixture()
        raw["requests"][0]["named_use"] = True
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "HOLD_PERMISSION")

    def test_subject_mismatch_holds(self):
        raw = fixture()
        raw["requests"][0]["subject_id"] = "PROJECT-B"
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "HOLD_PERMISSION")

    def test_evidence_generation_drift_holds(self):
        raw = fixture()
        raw["evidence"][0]["generation"] = "delivery-v2"
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "HOLD_PERMISSION")

    def test_evidence_source_drift_holds(self):
        raw = fixture()
        raw["evidence"][0]["source_sha256"] = "a"*64
        states, *_ = state_map(raw)
        self.assertEqual(states["REQ-PUBLIC"], "HOLD_PERMISSION")

    def test_private_source_never_leaks_to_public_projection(self):
        raw = fixture()
        _, _, _, public, _ = state_map(raw)
        self.assertNotIn("permission-a", public)
        self.assertNotIn("EV-DELIVERY", public)
        self.assertNotIn("111111", public)
        self.assertNotIn("Synthetic Client Alpha", public)
        self.assertIn("An enterprise client", public)

    def test_named_reference_uses_permitted_public_name(self):
        _, _, _, public, _ = state_map(fixture())
        self.assertIn("Example Project", public)
        self.assertNotIn("Synthetic Open Project", public)

    def test_semantic_order_is_deterministic(self):
        a = fixture()
        b = copy.deepcopy(a)
        for key in ("counterparties","evidence","permissions","requests"):
            b[key].reverse()
        for p in b["permissions"]:
            p["modes"].reverse()
            p["categories"].reverse()
            p["exact_claims"].reverse()
            p["evidence_bindings"].reverse()
        self.assertEqual(vault.compile_vault(a), vault.compile_vault(b))

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"bad.json"
            p.write_text('{"schema":"x","schema":"y"}',encoding="utf-8")
            with self.assertRaises(vault.InputError):
                vault.load_strict(p)

    def test_nan_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"bad.json"
            p.write_text('{"x":NaN}',encoding="utf-8")
            with self.assertRaises(vault.InputError):
                vault.load_strict(p)

    def test_unsafe_path_rejected(self):
        raw=fixture()
        raw["evidence"][0]["source"]="../../secret"
        with self.assertRaises(vault.InputError):
            vault.compile_vault(raw)

    def test_url_userinfo_rejected(self):
        raw=fixture()
        raw["permissions"][1]["source"]="https://user:token@example.com/x"
        with self.assertRaises(vault.InputError):
            vault.compile_vault(raw)

    def test_bool_named_use_rejected(self):
        raw=fixture()
        raw["requests"][0]["named_use"]=1
        with self.assertRaises(vault.InputError):
            vault.compile_vault(raw)

    def test_compile_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); out=td/"out"
            self.assertEqual(vault.compile_to_dir(FIXTURE,out),0)
            self.assertEqual(vault.verify(FIXTURE,out/"artifact.json",out/"internal_packet.md",out/"public_projection.md",out/"receipt.json"),0)
            (out/"public_projection.md").write_text("tampered\n",encoding="utf-8")
            self.assertEqual(vault.verify(FIXTURE,out/"artifact.json",out/"internal_packet.md",out/"public_projection.md",out/"receipt.json"),1)

    def test_fail_on_hold_exit(self):
        raw=fixture()
        raw["permissions"][0]["revoked_at"]="2026-09-16T16:00:00Z"
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); inp=td/"in.json"; inp.write_text(json.dumps(raw),encoding="utf-8")
            self.assertEqual(vault.compile_to_dir(inp,td/"out",True),2)

    def test_optimized_python_cli(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); out=td/"out"
            c=subprocess.run([sys.executable,"-O",str(PKG/"compile_vault.py"),"compile","--input",str(FIXTURE),"--out-dir",str(out)],capture_output=True,text=True)
            self.assertEqual(c.returncode,0,c.stderr)
            v=subprocess.run([sys.executable,"-O",str(PKG/"compile_vault.py"),"verify","--input",str(FIXTURE),"--artifact",str(out/"artifact.json"),"--internal",str(out/"internal_packet.md"),"--public",str(out/"public_projection.md"),"--receipt",str(out/"receipt.json")],capture_output=True,text=True)
            self.assertEqual(v.returncode,0,v.stderr)
            self.assertIn("VERIFY_OK",v.stdout)

if __name__=="__main__":
    unittest.main()
