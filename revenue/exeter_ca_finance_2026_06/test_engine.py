from __future__ import annotations
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_PATH = HERE / "engine.py"
SPEC = importlib.util.spec_from_file_location("exeter_engine", ENGINE_PATH)
assert SPEC and SPEC.loader
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)

D = "a" * 64
E = "b" * 64
F = "c" * 64
G = "d" * 64
INPUT_SCHEMA = engine.INPUT_SCHEMA
REQUIRED_UAT = tuple(engine.REQUIRED_UAT)
SUBLEDGER_KEYS = tuple(engine.SUBLEDGER_KEYS)
CROSSWALK_KEYS = tuple(engine.CROSSWALK_KEYS)


def packet():
    controls = [
        {"id": f"gl-{name}", "source_cents": 1000, "target_cents": 1000, "approved_delta_cents": 0, "adjustment_sha256": None}
        for name in SUBLEDGER_KEYS
    ]
    controls.append({"id": "trial-balance", "source_cents": 10000, "target_cents": 10000, "approved_delta_cents": 0, "adjustment_sha256": None})
    return {
        "schema": INPUT_SCHEMA,
        "as_of_utc": "2026-09-18T08:00:00Z",
        "source_pin": {
            "ledger_sha256": D,
            "procurement_index_sha256": E,
            "rfp_sha256": F,
            "qa_addenda_sha256": G,
            "observed_at_utc": "2026-09-18T07:55:00Z",
            "qa_recheck_due_at_utc": "2026-09-18T07:00:00Z",
            "qa_addenda_state": "POSTED_AND_RETAINED",
        },
        "generation": {"source_sha256": D, "target_sha256": E},
        "crosswalks": {c: [{"source_id": f"{c}-s1", "target_id": f"{c}-t1"}] for c in CROSSWALK_KEYS},
        "control_totals": controls,
        "subledgers": {
            n: {
                "control_id": f"gl-{n}",
                "source_count": 2,
                "target_count": 2,
                "approved_count_delta": 0,
                "source_cents": 1000,
                "target_cents": 1000,
                "approved_amount_delta_cents": 0,
                "adjustment_sha256": None,
                "exceptions": [],
            }
            for n in SUBLEDGER_KEYS
        },
        "bank_reconciliation": {
            "statement_ending_cents": 10000,
            "statement_additions_cents": 500,
            "statement_deductions_cents": 250,
            "book_ending_cents": 10250,
            "book_additions_cents": 0,
            "book_deductions_cents": 0,
            "reconciled_cents": 10250,
        },
        "required_interfaces": ["BANK", "PAYMENTS"],
        "interfaces": [
            {"id": "BANK", "source": "erp", "target": "bank", "manifest_sha256": D, "status": "verified"},
            {"id": "PAYMENTS", "source": "cashiering", "target": "erp", "manifest_sha256": E, "status": "verified"},
        ],
        "uat": [{"id": x, "mandatory": True, "status": "pass", "evidence_sha256": D} for x in REQUIRED_UAT],
        "cutover": {"source_freeze_sha256": D, "rollback_receipt_sha256": E, "replay_receipt_sha256": F, "unresolved_exceptions": []},
    }


class ExeterAcceptanceTests(unittest.TestCase):
    def test_01_complete_packet_ready_and_deterministic(self):
        p = packet(); a = engine.evaluate(p); b = engine.evaluate(copy.deepcopy(p))
        self.assertEqual(a, b); self.assertTrue(a["ready"])
        self.assertEqual(a["authority"], "EVIDENCE_ONLY_NO_BUYER_OR_PRODUCTION_ACCEPTANCE")
        for k in ("buyer_acceptance_authorized", "production_posting_authorized", "bank_action_authorized", "payment_authorized", "revenue_recognized"):
            self.assertIs(a[k], False)

    def test_02_unknown_top_level_field_fails_closed(self):
        p = packet(); p["surprise"] = True
        with self.assertRaisesRegex(engine.PacketError, "OBJECT_KEYS_INVALID"): engine.evaluate(p)

    def test_03_invalid_generation_digest_fails(self):
        p = packet(); p["generation"]["source_sha256"] = "ABC"
        with self.assertRaisesRegex(engine.PacketError, "SHA256_INVALID"): engine.evaluate(p)

    def test_04_duplicate_source_mapping_fails(self):
        p = packet(); p["crosswalks"]["accounts"].append(copy.deepcopy(p["crosswalks"]["accounts"][0]))
        with self.assertRaisesRegex(engine.PacketError, "DUPLICATE_SOURCE_ID"): engine.evaluate(p)

    def test_05_control_total_cent_mismatch_holds(self):
        p = packet(); p["control_totals"][-1]["target_cents"] += 1
        self.assertIn("CONTROL_TOTAL_DELTA_MISMATCH", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_06_boolean_cannot_masquerade_as_money(self):
        p = packet(); p["control_totals"][0]["source_cents"] = True
        with self.assertRaisesRegex(engine.PacketError, "TYPE_INTEGER_REQUIRED"): engine.evaluate(p)

    def test_07_unexplained_subledger_count_drift_holds(self):
        p = packet(); p["subledgers"]["ap"]["target_count"] = 3
        self.assertIn("SUBLEDGER_COUNT_DELTA_MISMATCH", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_08_nonzero_approved_adjustment_without_digest_holds(self):
        p = packet(); row = p["subledgers"]["ar"]; row["target_count"] = 3; row["approved_count_delta"] = 1
        self.assertIn("ADJUSTMENT_EVIDENCE_MISSING", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_09_evidenced_approved_adjustment_can_reconcile_when_gl_matches(self):
        p = packet(); row = p["subledgers"]["payroll"]; row["target_count"] = 3; row["approved_count_delta"] = 1; row["target_cents"] = 1250; row["approved_amount_delta_cents"] = 250; row["adjustment_sha256"] = F
        control = next(c for c in p["control_totals"] if c["id"] == "gl-payroll"); control["target_cents"] = 1250; control["approved_delta_cents"] = 250; control["adjustment_sha256"] = F
        self.assertTrue(engine.evaluate(p)["ready"])

    def test_10_open_subledger_exception_holds(self):
        p = packet(); p["subledgers"]["utility"]["exceptions"] = ["utility-row-7"]
        self.assertIn("SUBLEDGER_EXCEPTION_OPEN", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_11_bank_statement_or_book_terminal_mismatch_holds(self):
        p = packet(); p["bank_reconciliation"]["statement_additions_cents"] += 1; p["bank_reconciliation"]["book_deductions_cents"] += 2
        codes = {x["code"] for x in engine.evaluate(p)["exceptions"]}; self.assertIn("BANK_STATEMENT_RECON_MISMATCH", codes); self.assertIn("BANK_BOOK_RECON_MISMATCH", codes)

    def test_12_missing_required_interface_holds(self):
        p = packet(); p["interfaces"] = [x for x in p["interfaces"] if x["id"] != "BANK"]
        self.assertIn("REQUIRED_INTERFACE_MISSING", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_13_unverified_interface_holds(self):
        p = packet(); p["interfaces"][0]["status"] = "pending"
        self.assertIn("INTERFACE_NOT_VERIFIED", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_14_missing_required_uat_case_holds(self):
        p = packet(); p["uat"] = [x for x in p["uat"] if x["id"] != "PAYROLL"]
        self.assertIn("REQUIRED_UAT_MISSING", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_15_failed_mandatory_uat_holds(self):
        p = packet(); p["uat"][0]["status"] = "fail"
        self.assertIn("MANDATORY_UAT_NOT_PASS", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_16_unresolved_cutover_exception_holds(self):
        p = packet(); p["cutover"]["unresolved_exceptions"] = ["C-17"]
        self.assertIn("CUTOVER_EXCEPTION_OPEN", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_17_invalid_cutover_receipt_digest_fails(self):
        p = packet(); p["cutover"]["rollback_receipt_sha256"] = "bad"
        with self.assertRaisesRegex(engine.PacketError, "SHA256_INVALID"): engine.evaluate(p)

    def test_18_cli_emits_0_ready_2_hold_and_64_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ready = root / "ready.json"; hold = root / "hold.json"; invalid = root / "invalid.json"
            ready.write_text(json.dumps(packet()), encoding="utf-8")
            p = packet(); p["cutover"]["unresolved_exceptions"] = ["open"]; hold.write_text(json.dumps(p), encoding="utf-8")
            invalid.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            a = subprocess.run([sys.executable, str(ENGINE_PATH), str(ready)], text=True, capture_output=True)
            b = subprocess.run([sys.executable, str(ENGINE_PATH), str(hold)], text=True, capture_output=True)
            c = subprocess.run([sys.executable, str(ENGINE_PATH), str(invalid)], text=True, capture_output=True)
            self.assertEqual(a.returncode, 0, a.stderr); self.assertEqual(b.returncode, 2, b.stderr); self.assertEqual(c.returncode, 64); self.assertIn("DUPLICATE_JSON_KEY", c.stderr)

    def test_19_exception_ids_and_order_are_stable(self):
        p = packet(); p["control_totals"][-1]["target_cents"] += 1; p["cutover"]["unresolved_exceptions"] = ["z", "a"]
        a = engine.evaluate(p); b = engine.evaluate(copy.deepcopy(p)); self.assertEqual(a["exceptions"], b["exceptions"]); self.assertEqual(a["exception_count"], 3)

    def test_20_zero_delta_cannot_carry_adjustment_digest(self):
        p = packet(); p["subledgers"]["cashiering"]["adjustment_sha256"] = D
        self.assertIn("UNNEEDED_ADJUSTMENT_EVIDENCE", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_21_required_uat_cannot_be_demoted_to_optional(self):
        p = packet(); p["uat"][0]["mandatory"] = False
        self.assertIn("REQUIRED_UAT_NOT_MANDATORY", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_22_source_pin_stale_holds(self):
        p = packet(); p["source_pin"]["observed_at_utc"] = "2026-09-15T07:55:00Z"
        self.assertIn("SOURCE_PIN_STALE", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_23_expected_qa_without_current_resolution_holds(self):
        p = packet(); p["source_pin"]["qa_addenda_state"] = "OFFICIAL_PAGE_RECHECKED_NO_POSTING"; p["source_pin"]["qa_addenda_sha256"] = None
        self.assertIn("QA_PUBLICATION_UNRESOLVED", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_24_posted_qa_requires_digest(self):
        p = packet(); p["source_pin"]["qa_addenda_sha256"] = None
        self.assertIn("QA_ADDENDA_DIGEST_MISSING", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_25_no_qa_confirmed_requires_evidence_digest(self):
        p = packet(); p["source_pin"]["qa_addenda_state"] = "NO_QA_ADDENDA_REQUIRED_CONFIRMED"; p["source_pin"]["qa_addenda_sha256"] = None
        self.assertIn("QA_NO_ADDENDA_CONFIRMATION_MISSING", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_26_subledger_gl_control_linkage_mismatch_holds(self):
        p = packet(); next(c for c in p["control_totals"] if c["id"] == "gl-ap")["target_cents"] = 999
        codes = {x["code"] for x in engine.evaluate(p)["exceptions"]}; self.assertIn("SUBLEDGER_TARGET_GL_MISMATCH", codes)

    def test_27_missing_subledger_gl_control_holds(self):
        p = packet(); p["subledgers"]["ap"]["control_id"] = "no-such-control"
        self.assertIn("SUBLEDGER_CONTROL_MISSING", {x["code"] for x in engine.evaluate(p)["exceptions"]})

    def test_28_one_control_cannot_cover_two_subledgers(self):
        p = packet(); p["subledgers"]["ar"]["control_id"] = p["subledgers"]["ap"]["control_id"]
        with self.assertRaisesRegex(engine.PacketError, "SUBLEDGER_CONTROL_ID_REUSED"): engine.evaluate(p)

    def test_29_bank_adjustment_magnitudes_must_be_nonnegative(self):
        p = packet(); p["bank_reconciliation"]["statement_deductions_cents"] = -1
        with self.assertRaisesRegex(engine.PacketError, "INTEGER_RANGE_INVALID"): engine.evaluate(p)

    def test_30_exported_policy_mutation_and_rebinding_cannot_widen_semantics(self):
        p = packet(); baseline = engine.evaluate(p)
        engine.AUTHORITY = "BUYER_ACCEPTED"
        engine.REQUIRED_UAT = ()
        engine.SUBLEDGER_KEYS = ()
        engine.CROSSWALK_KEYS = ()
        engine.TOP_KEYS = set()
        engine.MAX_SOURCE_AGE_SECONDS = 10**18
        engine.INPUT_SCHEMA = "attacker"
        result = engine.evaluate(copy.deepcopy(p))
        self.assertEqual(result, baseline)
        self.assertIs(result["buyer_acceptance_authorized"], False)
        self.assertIs(result["payment_authorized"], False)
        self.assertIs(result["revenue_recognized"], False)

    def test_31_rebinding_public_evaluate_does_not_change_verifier_generation(self):
        p = packet(); report = engine.evaluate(p); original_verify = engine.verify_report; original_evaluate = engine.evaluate
        try:
            engine.evaluate = lambda _: {"ready": True, "authority": "BUYER_ACCEPTED"}
            self.assertTrue(original_verify(report, p))
            forged = dict(report); forged["buyer_acceptance_authorized"] = True
            self.assertFalse(original_verify(forged, p))
        finally:
            engine.evaluate = original_evaluate

    def test_32_verify_report_rejects_semantic_tamper(self):
        p = packet(); report = engine.evaluate(p); self.assertTrue(engine.verify_report(report, p))
        report["packet_sha256"] = "0" * 64; self.assertFalse(engine.verify_report(report, p))

    def test_33_real_python_O_runs_full_suite(self):
        if not __debug__: return
        proc = subprocess.run([sys.executable, "-O", str(Path(__file__))], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
