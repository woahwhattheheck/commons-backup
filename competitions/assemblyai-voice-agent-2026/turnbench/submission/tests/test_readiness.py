from __future__ import annotations
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import readiness as r

NOW = "2026-09-17T08:20:00Z"
ZERO = "0" * 64
ONE = "1" * 64
TWO = "2" * 64
THREE = "3" * 64
FOUR = "4" * 64
FIVE = "5" * 64


def ev(gate, observed="2026-09-17T08:00:00Z"):
    common = {
        "gate": gate,
        "project_id": r.PROJECT_ID,
        "event_id": r.EVENT_ID,
        "turnbench_source_commit": r.TURNBENCH_SOURCE_COMMIT,
        "observed_at": observed,
        "evidence_ref": f"receipt:{gate}:1",
        "evidence_sha256": ZERO,
    }
    if gate == "registration":
        return common | {
            "source_kind": "LABLAB_REGISTRATION_RECEIPT",
            "issuer": "lablab.ai",
            "facts": {"registration_state": "REGISTERED", "team_id": "team-123"},
        }
    if gate == "public_deployment":
        return common | {
            "source_kind": "PUBLIC_DEPLOYMENT_RECEIPT",
            "issuer": "vercel",
            "facts": {"deployment_state": "LIVE", "public_url": "https://example.invalid/turnbench", "deploy_sha256": ONE},
        }
    if gate == "live_assemblyai":
        return common | {
            "source_kind": "ASSEMBLYAI_LIVE_SESSION_RECEIPT",
            "issuer": "assemblyai.com",
            "facts": {"session_state": "COMPLETED", "turnbench_result": "PASS", "turnbench_receipt_sha256": TWO},
        }
    if gate == "presentation_assets":
        return common | {
            "source_kind": "OWNER_RETAINED_PRESENTATION_ASSETS",
            "issuer": "owner-retained",
            "facts": {
                "presentation_state": "READY",
                "narrative_sha256": THREE,
                "demo_script_sha256": FOUR,
                "demo_video_sha256": FIVE,
            },
        }
    raise AssertionError(gate)


def bundle(evidence=None):
    return {
        "project_id": r.PROJECT_ID,
        "event_id": r.EVENT_ID,
        "source_commit": r.TURNBENCH_SOURCE_COMMIT,
        "evaluation_at": NOW,
        "evidence": [] if evidence is None else evidence,
    }


class ReadinessTests(unittest.TestCase):
    def test_empty_current_state_holds_all_gates(self):
        out = r.compile_readiness(bundle())
        self.assertEqual(out["state"], "EXTERNAL_GATES_PENDING")
        self.assertEqual(len(out["blockers"]), 4)
        self.assertFalse(any(out["claims"][k] for k in (
            "registration_evidenced", "public_deployment_evidenced",
            "live_assemblyai_session_evidenced", "presentation_assets_evidenced")))
        self.assertFalse(out["claims"]["submitted"])
        self.assertFalse(out["authority"]["external_submission_authorized"])

    def test_exact_evidence_reaches_owner_actionability_only(self):
        out = r.compile_readiness(bundle([ev(g) for g in r.GATE_SPECS]))
        self.assertEqual(out["state"], "READY_FOR_OWNER_SUBMISSION_ACTION")
        self.assertEqual(out["blockers"], [])
        self.assertTrue(all(out["claims"][k] for k in (
            "registration_evidenced", "public_deployment_evidenced",
            "live_assemblyai_session_evidenced", "presentation_assets_evidenced")))
        self.assertFalse(out["claims"]["submitted"])
        self.assertFalse(out["authority"]["external_submission_authorized"])

    def test_missing_each_gate_holds(self):
        gates = list(r.GATE_SPECS)
        for missing in gates:
            rows = [ev(g) for g in gates if g != missing]
            out = r.compile_readiness(bundle(rows))
            self.assertIn(f"MISSING_{missing.upper()}", out["blockers"])

    def test_wrong_source_generation_rejected(self):
        b = bundle([ev("registration")])
        b["source_commit"] = "f" * 40
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(b)
        b = bundle([ev("registration")])
        b["evidence"][0]["turnbench_source_commit"] = "f" * 40
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(b)

    def test_cross_event_and_project_rejected(self):
        for field in ("project_id", "event_id"):
            b = bundle([ev("registration")])
            b["evidence"][0][field] = "other"
            with self.assertRaises(r.ReadinessError):
                r.compile_readiness(b)

    def test_self_authored_boolean_cannot_replace_evidence(self):
        b = bundle()
        b["registered"] = True
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(b)
        row = ev("registration")
        row["provider_authenticated"] = True
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(bundle([row]))

    def test_duplicate_gate_rejected(self):
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(bundle([ev("registration"), ev("registration")]))

    def test_wrong_evidence_class_or_issuer_rejected(self):
        row = ev("live_assemblyai")
        row["source_kind"] = "OWNER_SAYS_LIVE"
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(bundle([row]))
        row = ev("live_assemblyai")
        row["issuer"] = "self"
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(bundle([row]))

    def test_stale_live_session_holds_not_ready(self):
        rows = [ev(g) for g in r.GATE_SPECS]
        for row in rows:
            if row["gate"] == "live_assemblyai":
                row["observed_at"] = "2026-09-05T00:00:00Z"
        out = r.compile_readiness(bundle(rows))
        self.assertEqual(out["state"], "EXTERNAL_GATES_PENDING")
        self.assertIn("STALE_LIVE_ASSEMBLYAI", out["blockers"])

    def test_future_evidence_rejected(self):
        row = ev("registration", "2026-09-18T00:00:00Z")
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(bundle([row]))

    def test_bad_https_or_userinfo_rejected(self):
        row = ev("public_deployment")
        row["facts"]["public_url"] = "http://example.invalid"
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(bundle([row]))
        row = ev("public_deployment")
        row["facts"]["public_url"] = "https://user@example.invalid/path"
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(bundle([row]))

    def test_sha_must_be_lowercase_sha256(self):
        row = ev("registration")
        row["evidence_sha256"] = "A" * 64
        with self.assertRaises(r.ReadinessError):
            r.compile_readiness(bundle([row]))

    def test_receipt_exact_recompile(self):
        b = bundle([ev(g) for g in r.GATE_SPECS])
        receipt = r.compile_readiness(b)
        self.assertTrue(r.verify(b, receipt))
        forged = copy.deepcopy(receipt)
        forged["claims"]["submitted"] = True
        forged["receipt_sha256"] = r.sha256_obj({k: v for k, v in forged.items() if k != "receipt_sha256"})
        self.assertFalse(r.verify(b, forged))

    def test_evidence_reorder_is_canonical(self):
        gates = list(r.GATE_SPECS)
        a = r.compile_readiness(bundle([ev(g) for g in gates]))
        b = r.compile_readiness(bundle([ev(g) for g in reversed(gates)]))
        self.assertEqual(a, b)

    def test_duplicate_json_keys_rejected(self):
        raw = '{"project_id":"turnbench","project_id":"x"}'
        with self.assertRaises(r.ReadinessError):
            r.loads_strict(raw)

    def test_floats_and_nonfinite_rejected(self):
        for raw in ('{"x":1.5}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(r.ReadinessError):
                r.loads_strict(raw)

    def test_cli_create_exclusive_and_verify(self):
        b = bundle()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            bp, op = p/"bundle.json", p/"receipt.json"
            bp.write_bytes(r.canonical_bytes(b))
            run = subprocess.run([sys.executable, str(HERE/"readiness.py"), "compile", "--bundle", str(bp), "--out", str(op)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertIn("EXTERNAL_GATES_PENDING", run.stdout)
            run2 = subprocess.run([sys.executable, str(HERE/"readiness.py"), "verify", "--bundle", str(bp), "--receipt", str(op)], capture_output=True, text=True)
            self.assertEqual(run2.returncode, 0)
            self.assertIn("VERIFIED", run2.stdout)
            run3 = subprocess.run([sys.executable, str(HERE/"readiness.py"), "compile", "--bundle", str(bp), "--out", str(op)], capture_output=True, text=True)
            self.assertEqual(run3.returncode, 64)
            self.assertIn("HOLD", run3.stdout)


if __name__ == "__main__":
    unittest.main()
