import copy
import json
import tempfile
import unittest
from pathlib import Path

from engine import EvidenceError, canonical_bytes, cli, compile_packet, decisions_csv, digest, loads_strict, summary_markdown, verify_result

HERE = Path(__file__).resolve().parent
FIXTURE = json.loads((HERE / "fixture.json").read_text())
AS_OF = "2026-09-13T10:45:00Z"


def po_packet(amounts, *, po_total="1000.00", po_id="PO-CUM-001"):
    """Build a small valid packet whose rows all reference one open PO."""
    p = copy.deepcopy(FIXTURE)
    vendor = copy.deepcopy(FIXTURE["vendors"][0])
    po = copy.deepcopy(FIXTURE["purchase_orders"][0])
    po.update({"po_id": po_id, "vendor_id": vendor["vendor_id"], "total": po_total})
    p["vendors"] = [vendor]
    p["purchase_orders"] = [po]
    p["invoices"] = []
    for index, amount in enumerate(amounts, start=1):
        inv = copy.deepcopy(FIXTURE["invoices"][0])
        inv.update(
            {
                "invoice_id": f"CUM-{index:03d}",
                "vendor_id": vendor["vendor_id"],
                "po_id": po_id,
                "amount": amount,
                "invoice_date": f"2026-08-{10 + index:02d}",
                "due_date": f"2026-09-{10 + index:02d}",
                "source_ref": f"cumulative-source-{index}",
                "snapshot_sha256": f"{index:x}" * 64,
            }
        )
        p["invoices"].append(inv)
    return p


class EngineTests(unittest.TestCase):
    def test_control_fixture_exact_counts(self):
        result = compile_packet(FIXTURE, as_of=AS_OF)
        self.assertEqual(result["manifest"]["counts"], {"total": 12, "ready": 7, "hold": 5})
        holds = {r["invoice_id"]: r["reasons"] for r in result["queue"]}
        self.assertEqual(set(holds), {"INV-003", "INV-005", "INV-007", "INV-009", "INV-011"})
        self.assertIn("PO_MISSING", holds["INV-003"])
        self.assertIn("VENDOR_INACTIVE", holds["INV-005"])
        self.assertIn("INVOICE_EXCEEDS_PO", holds["INV-007"])
        self.assertIn("INVOICE_PREDATES_PO", holds["INV-009"])
        self.assertIn("DUE_DATE_PRECEDES_INVOICE", holds["INV-011"])

    def test_replay_byte_identical(self):
        a = compile_packet(FIXTURE, as_of=AS_OF)
        b = compile_packet(copy.deepcopy(FIXTURE), as_of=AS_OF)
        self.assertEqual(canonical_bytes(a), canonical_bytes(b))
        self.assertEqual(decisions_csv(a), decisions_csv(b))
        self.assertEqual(summary_markdown(a), summary_markdown(b))

    def test_verify_round_trip(self):
        result = compile_packet(FIXTURE, as_of=AS_OF)
        self.assertTrue(verify_result(FIXTURE, result, as_of=AS_OF))

    def test_tampered_decision_fails_verify(self):
        result = compile_packet(FIXTURE, as_of=AS_OF)
        result["decisions"][0]["state"] = "HOLD"
        with self.assertRaises(EvidenceError):
            verify_result(FIXTURE, result, as_of=AS_OF)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(EvidenceError, "duplicate JSON key"):
            loads_strict('{"schema_version":"x","schema_version":"y"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(EvidenceError):
            loads_strict('{"x": NaN}')

    def test_unknown_root_field_rejected(self):
        p = copy.deepcopy(FIXTURE); p["surprise"] = True
        with self.assertRaisesRegex(EvidenceError, "unknown fields"):
            compile_packet(p, as_of=AS_OF)

    def test_duplicate_invoice_id_rejected(self):
        p = copy.deepcopy(FIXTURE); p["invoices"].append(copy.deepcopy(p["invoices"][0]))
        with self.assertRaisesRegex(EvidenceError, "duplicate invoice_id"):
            compile_packet(p, as_of=AS_OF)

    def test_semantic_duplicate_holds_both(self):
        p = copy.deepcopy(FIXTURE)
        extra = copy.deepcopy(p["invoices"][0]); extra["invoice_id"] = "INV-099"; extra["snapshot_sha256"] = "f" * 64
        p["invoices"].append(extra)
        r = compile_packet(p, as_of=AS_OF)
        states = {x["invoice_id"]: x for x in r["decisions"]}
        self.assertIn("DUPLICATE_INVOICE_EVIDENCE", states["INV-001"]["reasons"])
        self.assertIn("DUPLICATE_INVOICE_EVIDENCE", states["INV-099"]["reasons"])

    def test_cumulative_po_overrun_holds_every_otherwise_ready_invoice(self):
        p = po_packet(["700.00", "700.00"], po_total="1000.00")
        r = compile_packet(p, as_of=AS_OF)
        self.assertEqual(r["manifest"]["counts"], {"total": 2, "ready": 0, "hold": 2})
        for row in r["decisions"]:
            self.assertEqual(row["state"], "HOLD")
            self.assertEqual(row["reasons"], ["PO_CUMULATIVE_AMOUNT_EXCEEDED"])

    def test_cumulative_po_exact_boundary_remains_ready(self):
        r = compile_packet(po_packet(["500.00", "500.00"], po_total="1000.00"), as_of=AS_OF)
        self.assertEqual(r["manifest"]["counts"], {"total": 2, "ready": 2, "hold": 0})
        self.assertTrue(all(row["reasons"] == [] for row in r["decisions"]))

    def test_cumulative_three_invoice_overrun_holds_all_candidates(self):
        r = compile_packet(po_packet(["350.00", "350.00", "350.00"], po_total="1000.00"), as_of=AS_OF)
        self.assertEqual(r["manifest"]["counts"], {"total": 3, "ready": 0, "hold": 3})
        self.assertTrue(
            all("PO_CUMULATIVE_AMOUNT_EXCEEDED" in row["reasons"] for row in r["decisions"])
        )

    def test_cumulative_exposure_isolated_by_po(self):
        p = po_packet(["600.00", "600.00"], po_total="1000.00", po_id="PO-CUM-A")
        second_po = copy.deepcopy(p["purchase_orders"][0])
        second_po.update({"po_id": "PO-CUM-B", "total": "1000.00", "snapshot_sha256": "b" * 64})
        p["purchase_orders"].append(second_po)
        third = copy.deepcopy(p["invoices"][0])
        third.update(
            {
                "invoice_id": "CUM-B-001",
                "po_id": "PO-CUM-B",
                "amount": "900.00",
                "source_ref": "second-po-source",
                "invoice_date": "2026-08-20",
                "due_date": "2026-09-20",
                "snapshot_sha256": "c" * 64,
            }
        )
        p["invoices"].append(third)
        rows = {row["invoice_id"]: row for row in compile_packet(p, as_of=AS_OF)["decisions"]}
        self.assertEqual(rows["CUM-001"]["reasons"], ["PO_CUMULATIVE_AMOUNT_EXCEEDED"])
        self.assertEqual(rows["CUM-002"]["reasons"], ["PO_CUMULATIVE_AMOUNT_EXCEEDED"])
        self.assertEqual(rows["CUM-B-001"]["state"], "READY")
        self.assertEqual(rows["CUM-B-001"]["reasons"], [])

    def test_row_level_overrun_does_not_consume_candidate_ready_exposure(self):
        p = po_packet(["700.00", "1200.00"], po_total="1000.00")
        rows = {row["invoice_id"]: row for row in compile_packet(p, as_of=AS_OF)["decisions"]}
        self.assertEqual(rows["CUM-001"]["state"], "READY")
        self.assertEqual(rows["CUM-001"]["reasons"], [])
        self.assertEqual(rows["CUM-002"]["state"], "HOLD")
        self.assertEqual(rows["CUM-002"]["reasons"], ["INVOICE_EXCEEDS_PO"])

    def test_semantic_duplicate_does_not_double_count_candidate_exposure(self):
        p = po_packet(["600.00", "400.00"], po_total="1000.00")
        duplicate = copy.deepcopy(p["invoices"][0])
        duplicate["invoice_id"] = "CUM-099"
        duplicate["snapshot_sha256"] = "f" * 64
        p["invoices"].append(duplicate)
        rows = {row["invoice_id"]: row for row in compile_packet(p, as_of=AS_OF)["decisions"]}
        self.assertEqual(rows["CUM-001"]["reasons"], ["DUPLICATE_INVOICE_EVIDENCE"])
        self.assertEqual(rows["CUM-099"]["reasons"], ["DUPLICATE_INVOICE_EVIDENCE"])
        self.assertEqual(rows["CUM-002"]["state"], "READY")
        self.assertEqual(rows["CUM-002"]["reasons"], [])

    def test_cumulative_decisions_are_invariant_to_invoice_input_order(self):
        p = po_packet(["700.00", "700.00"], po_total="1000.00")
        forward = compile_packet(copy.deepcopy(p), as_of=AS_OF)
        p["invoices"].reverse()
        reversed_result = compile_packet(p, as_of=AS_OF)
        self.assertEqual(forward["decisions"], reversed_result["decisions"])
        self.assertEqual(forward["manifest"]["decisions_sha256"], reversed_result["manifest"]["decisions_sha256"])
        self.assertNotEqual(forward["manifest"]["packet_sha256"], reversed_result["manifest"]["packet_sha256"])

    def test_vendor_missing_holds(self):
        p = copy.deepcopy(FIXTURE); p["invoices"][0]["vendor_id"] = "V-NOPE"
        r = compile_packet(p, as_of=AS_OF)
        row = next(x for x in r["decisions"] if x["invoice_id"] == "INV-001")
        self.assertIn("VENDOR_MISSING", row["reasons"])

    def test_po_vendor_mismatch_holds(self):
        p = copy.deepcopy(FIXTURE); p["purchase_orders"][0]["vendor_id"] = "V-002"
        r = compile_packet(p, as_of=AS_OF)
        row = next(x for x in r["decisions"] if x["invoice_id"] == "INV-001")
        self.assertIn("PO_VENDOR_MISMATCH", row["reasons"])

    def test_po_currency_mismatch_rejected_at_boundary(self):
        p = copy.deepcopy(FIXTURE); p["purchase_orders"][0]["currency"] = "EUR"
        with self.assertRaisesRegex(EvidenceError, "unsupported currency"):
            compile_packet(p, as_of=AS_OF)

    def test_amount_requires_string(self):
        p = copy.deepcopy(FIXTURE); p["invoices"][0]["amount"] = 1000.00
        with self.assertRaisesRegex(EvidenceError, "expected string"):
            compile_packet(p, as_of=AS_OF)

    def test_amount_requires_two_decimals(self):
        p = copy.deepcopy(FIXTURE); p["invoices"][0]["amount"] = "1000"
        with self.assertRaisesRegex(EvidenceError, "two decimal"):
            compile_packet(p, as_of=AS_OF)

    def test_negative_amount_rejected(self):
        p = copy.deepcopy(FIXTURE); p["invoices"][0]["amount"] = "-1.00"
        with self.assertRaisesRegex(EvidenceError, "nonnegative"):
            compile_packet(p, as_of=AS_OF)

    def test_bad_digest_rejected(self):
        p = copy.deepcopy(FIXTURE); p["invoices"][0]["snapshot_sha256"] = "A" * 64
        with self.assertRaisesRegex(EvidenceError, "lowercase sha256"):
            compile_packet(p, as_of=AS_OF)

    def test_future_capture_rejected(self):
        p = copy.deepcopy(FIXTURE); p["captured_at"] = "2026-09-13T10:46:00Z"
        with self.assertRaisesRegex(EvidenceError, "future evidence"):
            compile_packet(p, as_of=AS_OF)

    def test_stale_capture_rejected(self):
        p = copy.deepcopy(FIXTURE); p["captured_at"] = "2026-01-01T00:00:00Z"
        with self.assertRaisesRegex(EvidenceError, "stale evidence"):
            compile_packet(p, as_of=AS_OF)

    def test_noncanonical_instant_rejected(self):
        p = copy.deepcopy(FIXTURE); p["captured_at"] = "2026-09-13T10:40:00.000Z"
        with self.assertRaisesRegex(EvidenceError, "canonical seconds"):
            compile_packet(p, as_of=AS_OF)

    def test_due_before_invoice_holds_not_rejects_packet(self):
        result = compile_packet(FIXTURE, as_of=AS_OF)
        row = next(x for x in result["decisions"] if x["invoice_id"] == "INV-011")
        self.assertEqual(row["state"], "HOLD")
        self.assertEqual(row["reasons"], ["DUE_DATE_PRECEDES_INVOICE"])

    def test_authority_ceiling_all_false_except_read_only(self):
        a = compile_packet(FIXTURE, as_of=AS_OF)["manifest"]["authority"]
        self.assertTrue(a.pop("read_only"))
        self.assertTrue(all(v is False for v in a.values()))

    def test_manifest_digest_self_verifies(self):
        r = compile_packet(FIXTURE, as_of=AS_OF)
        m = r["manifest"]
        core = {k: v for k, v in m.items() if k != "manifest_sha256"}
        self.assertEqual(m["manifest_sha256"], digest(core))

    def test_csv_is_stable_and_has_13_lines(self):
        text = decisions_csv(compile_packet(FIXTURE, as_of=AS_OF))
        self.assertEqual(len(text.splitlines()), 13)
        self.assertTrue(text.startswith("invoice_id,state,reasons"))

    def test_markdown_contains_authority_warning(self):
        md = summary_markdown(compile_packet(FIXTURE, as_of=AS_OF))
        self.assertIn("cannot approve an invoice", md)
        self.assertIn("READY: **7**", md)
        self.assertIn("HOLD: **5**", md)

    def test_cli_compile_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "packet.json"
            src.write_text(json.dumps(FIXTURE), encoding="utf-8")
            out = td / "out"
            self.assertEqual(cli(["compile", str(src), "--as-of", AS_OF, "--out-dir", str(out)]), 0)
            self.assertTrue((out / "result.json").exists())
            self.assertTrue((out / "decisions.csv").exists())
            self.assertTrue((out / "receipt.md").exists())
            self.assertEqual(cli(["verify", str(src), str(out / "result.json"), "--as-of", AS_OF]), 0)

    def test_cli_refuses_tampered_result(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "packet.json"; src.write_text(json.dumps(FIXTURE), encoding="utf-8")
            result = compile_packet(FIXTURE, as_of=AS_OF); result["manifest"]["counts"]["ready"] = 99
            rp = td / "result.json"; rp.write_text(json.dumps(result), encoding="utf-8")
            self.assertEqual(cli(["verify", str(src), str(rp), "--as-of", AS_OF]), 2)


if __name__ == "__main__":
    unittest.main()
