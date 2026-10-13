from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from . import cli
from .engine import (
    InputError,
    PILOT_MAX_INVOICES,
    PILOT_PRICE_USD_MINOR,
    canonical_bytes,
    compile_report,
    loads_strict,
    render_markdown,
    verify_report,
)

HERE = Path(__file__).resolve().parent


def packet():
    return loads_strict((HERE / "example.json").read_text(encoding="utf-8"))


def sha(ch: str) -> str:
    return ch * 64


def invoice(report, invoice_id: str):
    return next(row for row in report["invoices"] if row["invoice_id"] == invoice_id)


class ARLeakageTests(unittest.TestCase):
    def test_synthetic_acceptance_states_and_totals(self):
        report = compile_report(packet())
        states = {row["invoice_id"]: row["status"] for row in report["invoices"]}
        self.assertEqual(
            states,
            {
                "inv-conflict": "CONFLICT",
                "inv-disputed": "DISPUTED_HOLD",
                "inv-open": "OPEN",
                "inv-overdue": "PARTIAL_OVERDUE",
                "inv-paid": "PAID",
                "inv-partial": "PARTIAL",
                "inv-partial-overdue": "PARTIAL_OVERDUE",
                "inv-void": "VOID",
            },
        )
        summary = report["summary"]
        self.assertEqual(
            summary["known_outstanding_minor"],
            10000 + 15000 + 25000 + 30000 + 50000,
        )
        self.assertEqual(summary["recovery_candidate_minor"], 25000 + 30000)
        self.assertEqual(summary["disputed_outstanding_minor"], 50000)
        self.assertEqual(summary["unapplied_payment_minor"], 12500)
        self.assertEqual(summary["conflict_count"], 1)

    def test_order_invariant(self):
        candidate = packet()
        expected = canonical_bytes(compile_report(candidate))
        for key in ("invoices", "payments", "credits", "disputes"):
            candidate[key].reverse()
        self.assertEqual(canonical_bytes(compile_report(candidate)), expected)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(InputError):
            loads_strict('{"schema":"x","schema":"y"}')

    def test_nonfinite_rejected(self):
        with self.assertRaises(InputError):
            loads_strict('{"x":NaN}')

    def test_bool_never_amount(self):
        candidate = packet()
        candidate["invoices"][0]["amount_minor"] = True
        with self.assertRaises(InputError):
            compile_report(candidate)

    def test_unknown_root_field_rejected(self):
        candidate = packet()
        candidate["owner_says_ready"] = True
        with self.assertRaises(InputError):
            compile_report(candidate)

    def test_email_like_account_id_rejected(self):
        candidate = packet()
        candidate["invoices"][0]["account_id"] = "person@example.com"
        with self.assertRaises(InputError):
            compile_report(candidate)

    def test_evidence_replay_rejected(self):
        candidate = packet()
        candidate["payments"][1]["evidence_sha256"] = candidate["payments"][0][
            "evidence_sha256"
        ]
        with self.assertRaises(InputError):
            compile_report(candidate)

    def test_cross_account_payment_conflicts_invoice(self):
        candidate = packet()
        candidate["payments"][0]["account_id"] = "acct-other"
        report = compile_report(candidate)
        self.assertEqual(invoice(report, "inv-partial")["status"], "CONFLICT")
        self.assertIn(
            "PAYMENT_ACCOUNT_MISMATCH",
            {row["code"] for row in report["integrity_conflicts"]},
        )

    def test_cross_currency_payment_conflicts_invoice(self):
        candidate = packet()
        candidate["payments"][0]["currency"] = "EUR"
        report = compile_report(candidate)
        self.assertEqual(invoice(report, "inv-partial")["status"], "CONFLICT")

    def test_unknown_invoice_payment_is_conflict_not_allocation(self):
        candidate = packet()
        candidate["payments"][0]["invoice_id"] = "inv-missing"
        report = compile_report(candidate)
        self.assertIn(
            "PAYMENT_UNKNOWN_INVOICE",
            {row["code"] for row in report["integrity_conflicts"]},
        )
        self.assertEqual(invoice(report, "inv-partial")["applied_payment_minor"], 0)

    def test_future_payment_conflicts_target(self):
        candidate = packet()
        candidate["payments"][0]["observed_at"] = "2026-09-15T00:00:00Z"
        report = compile_report(candidate)
        self.assertEqual(invoice(report, "inv-partial")["status"], "CONFLICT")

    def test_overapplication_conflict(self):
        report = compile_report(packet())
        row = invoice(report, "inv-conflict")
        self.assertEqual(row["status"], "CONFLICT")
        self.assertEqual(row["balance_minor"], 0)

    def test_void_invoice_allocation_conflict(self):
        candidate = packet()
        candidate["payments"].append(
            {
                "payment_id": "pay-void",
                "account_id": "acct-g",
                "invoice_id": "inv-void",
                "amount_minor": 1,
                "currency": "USD",
                "observed_at": "2026-09-10T00:00:00Z",
                "evidence_sha256": sha("0"),
            }
        )
        report = compile_report(candidate)
        self.assertEqual(invoice(report, "inv-void")["status"], "CONFLICT")

    def test_unapplied_not_guessed(self):
        report = compile_report(packet())
        self.assertEqual(report["unapplied_payments"][0]["payment_id"], "pay-unapplied")
        self.assertEqual(
            report["unapplied_payments"][0]["review"],
            "RECONCILE_UNAPPLIED_PAYMENT",
        )

    def test_open_dispute_holds_recovery(self):
        report = compile_report(packet())
        row = invoice(report, "inv-disputed")
        self.assertEqual(row["status"], "DISPUTED_HOLD")
        self.assertNotEqual(row["balance_minor"], 0)

    def test_resolved_dispute_releases_hold(self):
        candidate = packet()
        candidate["disputes"].append(
            {
                "event_id": "disp-resolved",
                "dispute_id": "case-1",
                "account_id": "acct-e",
                "invoice_id": "inv-disputed",
                "state": "RESOLVED",
                "observed_at": "2026-09-03T12:00:00Z",
                "evidence_sha256": sha("0"),
            }
        )
        report = compile_report(candidate)
        self.assertEqual(invoice(report, "inv-disputed")["status"], "OVERDUE")

    def test_same_time_dispute_fork_conflicts(self):
        candidate = packet()
        candidate["disputes"].append(
            {
                "event_id": "disp-fork",
                "dispute_id": "case-1",
                "account_id": "acct-e",
                "invoice_id": "inv-disputed",
                "state": "RESOLVED",
                "observed_at": "2026-09-02T12:00:00Z",
                "evidence_sha256": sha("0"),
            }
        )
        report = compile_report(candidate)
        self.assertEqual(invoice(report, "inv-disputed")["status"], "CONFLICT")

    def test_grace_boundary(self):
        candidate = packet()
        candidate["analysis_date"] = "2026-09-02"
        candidate["grace_days"] = 2
        report = compile_report(candidate)
        self.assertEqual(invoice(report, "inv-overdue")["status"], "PARTIAL")

    def test_exact_grace_plus_one_is_overdue(self):
        candidate = packet()
        candidate["analysis_date"] = "2026-09-03"
        candidate["grace_days"] = 2
        report = compile_report(candidate)
        self.assertEqual(invoice(report, "inv-overdue")["status"], "PARTIAL_OVERDUE")

    def test_paid_invoice(self):
        report = compile_report(packet())
        row = invoice(report, "inv-paid")
        self.assertEqual(row["status"], "PAID")
        self.assertEqual(row["balance_minor"], 0)

    def test_report_tamper_fails_verify(self):
        candidate = packet()
        report = compile_report(candidate)
        report["summary"]["recovery_candidate_minor"] += 1
        self.assertFalse(verify_report(candidate, report))

    def test_source_change_fails_verify(self):
        candidate = packet()
        report = compile_report(candidate)
        candidate["analysis_date"] = "2026-09-13"
        self.assertFalse(verify_report(candidate, report))

    def test_exact_report_verifies(self):
        candidate = packet()
        report = compile_report(candidate)
        self.assertTrue(verify_report(candidate, report))

    def test_authority_always_false(self):
        report = compile_report(packet())
        self.assertTrue(report["authority"])
        self.assertTrue(all(value is False for value in report["authority"].values()))

    def test_commercial_reference_is_not_acceptance(self):
        report = compile_report(packet())
        self.assertEqual(
            report["commercial_reference"]["pilot_price_usd_minor"],
            PILOT_PRICE_USD_MINOR,
        )
        self.assertEqual(
            report["commercial_reference"]["pilot_max_invoices"],
            PILOT_MAX_INVOICES,
        )
        self.assertEqual(
            report["commercial_reference"]["state"], "REFERENCE_NOT_ACCEPTED"
        )

    def test_markdown_preserves_truth_boundary(self):
        text = render_markdown(compile_report(packet()))
        self.assertIn("not legal debt", text)
        self.assertIn("$2,500 fixed diagnostic", text)
        self.assertNotIn("customer_contact_authorized: true", text.lower())

    def test_too_many_invoices_rejected(self):
        candidate = packet()
        base = candidate["invoices"][0]
        candidate["invoices"] = []
        for index in range(PILOT_MAX_INVOICES + 1):
            row = dict(base)
            row["invoice_id"] = f"i{index}"
            row["evidence_sha256"] = f"{index:064x}"
            candidate["invoices"].append(row)
        with self.assertRaises(InputError):
            compile_report(candidate)

    def test_cli_compile_verify_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "in.json"
            out = root / "report.json"
            markdown = root / "report.md"
            inp.write_bytes((HERE / "example.json").read_bytes())
            self.assertEqual(
                cli.main(
                    [
                        "compile",
                        "--input",
                        str(inp),
                        "--report",
                        str(out),
                        "--markdown",
                        str(markdown),
                    ]
                ),
                0,
            )
            self.assertEqual(
                cli.main(["verify", "--input", str(inp), "--report", str(out)]),
                0,
            )
            self.assertEqual(
                cli.main(
                    [
                        "compile",
                        "--input",
                        str(inp),
                        "--report",
                        str(out),
                        "--markdown",
                        str(markdown),
                    ]
                ),
                2,
            )

    def test_cli_input_symlink_refused_where_supported(self):
        import os

        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.json"
            link = root / "link.json"
            real.write_bytes((HERE / "example.json").read_bytes())
            link.symlink_to(real)
            self.assertEqual(
                cli.main(
                    [
                        "compile",
                        "--input",
                        str(link),
                        "--report",
                        str(root / "r.json"),
                        "--markdown",
                        str(root / "r.md"),
                    ]
                ),
                2,
            )

    def test_receipt_is_64_lower_hex(self):
        self.assertRegex(
            compile_report(packet())["receipt_sha256"], r"^[0-9a-f]{64}$"
        )

    # Post-merge repair hostiles.

    def test_v1_rejects_non_usd_packet_currency(self):
        candidate = packet()
        candidate["currency"] = "JPY"
        for row in candidate["payments"] + candidate["credits"]:
            row["currency"] = "JPY"
        with self.assertRaisesRegex(InputError, "v1 supports USD"):
            compile_report(candidate)

    def test_future_invoice_is_conflict_and_contributes_zero_normal_economics(self):
        candidate = packet()
        baseline = compile_report(candidate)["summary"]
        candidate["invoices"].append(
            {
                "invoice_id": "inv-future",
                "account_id": "acct-future",
                "issue_date": "2026-09-15",
                "due_date": "2026-10-01",
                "amount_minor": 12345,
                "state": "OPEN",
                "evidence_sha256": sha("0"),
            }
        )
        report = compile_report(candidate)
        row = invoice(report, "inv-future")
        self.assertEqual(row["status"], "CONFLICT")
        self.assertEqual(row["balance_minor"], 0)
        self.assertIn(
            "INVOICE_AFTER_ANALYSIS_DATE",
            {item["code"] for item in report["integrity_conflicts"]},
        )
        for field in (
            "billed_minor",
            "applied_payment_minor",
            "applied_credit_minor",
            "known_outstanding_minor",
            "recovery_candidate_minor",
            "disputed_outstanding_minor",
        ):
            self.assertEqual(report["summary"][field], baseline[field])
        self.assertEqual(
            report["summary"]["conflicted_face_value_minor"],
            baseline["conflicted_face_value_minor"] + 12345,
        )

    def test_payment_before_invoice_conflicts_without_application(self):
        candidate = packet()
        candidate["payments"][0]["observed_at"] = "2026-08-31T23:59:59Z"
        report = compile_report(candidate)
        row = invoice(report, "inv-partial")
        self.assertEqual(row["status"], "CONFLICT")
        self.assertEqual(row["applied_payment_minor"], 0)
        self.assertIn(
            "PAYMENT_BEFORE_INVOICE",
            {item["code"] for item in report["integrity_conflicts"]},
        )

    def test_credit_before_invoice_conflicts_without_application(self):
        candidate = packet()
        candidate["credits"][0]["observed_at"] = "2026-07-31T23:59:59Z"
        report = compile_report(candidate)
        row = invoice(report, "inv-overdue")
        self.assertEqual(row["status"], "CONFLICT")
        self.assertEqual(row["applied_credit_minor"], 0)
        self.assertIn(
            "CREDIT_BEFORE_INVOICE",
            {item["code"] for item in report["integrity_conflicts"]},
        )

    def test_dispute_before_invoice_conflicts_without_hold(self):
        candidate = packet()
        candidate["disputes"][0]["observed_at"] = "2026-07-31T23:59:59Z"
        report = compile_report(candidate)
        row = invoice(report, "inv-disputed")
        self.assertEqual(row["status"], "CONFLICT")
        self.assertFalse(row["open_dispute"])
        self.assertIn(
            "DISPUTE_BEFORE_INVOICE",
            {item["code"] for item in report["integrity_conflicts"]},
        )

    def test_event_on_invoice_issue_date_is_admissible(self):
        candidate = packet()
        candidate["payments"][0]["observed_at"] = "2026-09-01T00:00:00Z"
        report = compile_report(candidate)
        row = invoice(report, "inv-partial")
        self.assertEqual(row["status"], "PARTIAL")
        self.assertEqual(row["applied_payment_minor"], 5000)
        self.assertNotIn(
            "PAYMENT_BEFORE_INVOICE",
            {item["code"] for item in report["integrity_conflicts"]},
        )

    def test_markdown_renders_integrity_conflict_queue(self):
        markdown = render_markdown(compile_report(packet()))
        self.assertIn("## Integrity conflicts", markdown)
        self.assertIn("INVOICE_OVER_APPLIED", markdown)
        self.assertIn("inv-conflict", markdown)

    def test_renderer_rejects_unsupported_currency_even_on_resealed_report(self):
        report = compile_report(packet())
        report["currency"] = "JPY"
        with self.assertRaisesRegex(InputError, "unsupported"):
            render_markdown(report)


if __name__ == "__main__":
    unittest.main()
