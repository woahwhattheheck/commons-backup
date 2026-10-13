from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cli import build_parser
from .engine import (
    DealEconomicsError,
    canonical_json,
    compile_report,
    parse_strict_json,
    read_json_file,
    render_markdown,
    verify_current,
    verify_historical,
    write_exclusive,
)

NOW = "2026-09-13T21:30:00Z"
OBS = "2026-09-13T20:30:00Z"
START = "2026-09-15T00:00:00Z"
END = "2026-09-25T00:00:00Z"


def packet() -> dict:
    return {
        "schema": "commons.service-deal-economics.input/v1",
        "policy": {
            "policy_id": "owner-policy", "generation": 1, "currency": "USD",
            "minimum_gross_margin_bps": 3000, "risk_reserve_bps": 1000,
            "snapshot_max_age_hours": 24, "quote_validity_hours": 72,
            "source_ref": "policy-source", "source_sha256": "1" * 64, "observed_at": OBS,
        },
        "deal": {
            "deal_id": "deal-1", "scope_id": "scope-v1", "scope_revision": 1,
            "currency": "USD", "target_price_cents": 700000,
            "delivery_start": START, "delivery_end": END,
            "source_ref": "deal-source", "source_sha256": "2" * 64, "observed_at": OBS,
            "items": [
                {"item_id": "implementation", "planned_minutes": 600, "internal_rate_cents_per_hour": 12000,
                 "external_cost_cents": 30000, "source_ref": "cost-impl", "source_sha256": "3" * 64, "observed_at": OBS},
                {"item_id": "acceptance", "planned_minutes": 900, "internal_rate_cents_per_hour": 10000,
                 "external_cost_cents": 50000, "source_ref": "cost-accept", "source_sha256": "4" * 64, "observed_at": OBS},
            ],
        },
        "capacity": {
            "snapshot_id": "capacity-v1", "window_start": START, "window_end": END,
            "total_minutes": 3000, "reserved_minutes": 1000,
            "source_ref": "capacity-source", "source_sha256": "5" * 64, "observed_at": OBS,
        },
    }


class DealEconomicsTests(unittest.TestCase):
    def test_ready_economics_exact(self):
        report = compile_report(packet(), NOW)
        self.assertEqual(report["disposition"], "READY_FOR_OWNER_QUOTE_REVIEW")
        self.assertEqual(report["economics"]["labor_cost_cents"], 270000)
        self.assertEqual(report["economics"]["external_cost_cents"], 80000)
        self.assertEqual(report["economics"]["direct_cost_cents"], 350000)
        self.assertEqual(report["economics"]["risk_reserve_cents"], 35000)
        self.assertEqual(report["economics"]["loaded_delivery_cost_cents"], 385000)
        self.assertEqual(report["economics"]["minimum_price_cents"], 550000)
        self.assertEqual(report["economics"]["modeled_margin_bps_at_target"], 4500)
        self.assertEqual(report["capacity"]["proposed_demand_minutes"], 1500)
        self.assertEqual(report["capacity"]["available_minutes"], 2000)
        self.assertFalse(report["capacity"]["reservation_created"])
        self.assertTrue(all(value is False for value in report["authority"].values()))

    def test_exact_margin_floor_passes(self):
        p = packet(); p["deal"]["target_price_cents"] = 550000
        report = compile_report(p, NOW)
        self.assertEqual(report["disposition"], "READY_FOR_OWNER_QUOTE_REVIEW")
        self.assertEqual(report["economics"]["modeled_margin_bps_at_target"], 3000)

    def test_one_cent_below_floor_holds(self):
        p = packet(); p["deal"]["target_price_cents"] = 549999
        report = compile_report(p, NOW)
        self.assertEqual(report["disposition"], "HOLD_MARGIN")
        self.assertIn("TARGET_PRICE_BELOW_MARGIN_FLOOR", report["reasons"])

    def test_labor_rounds_up(self):
        p = packet(); p["deal"]["items"] = [{
            "item_id": "minute", "planned_minutes": 1, "internal_rate_cents_per_hour": 1,
            "external_cost_cents": 0, "source_ref": "minute-cost", "source_sha256": "6" * 64, "observed_at": OBS,
        }]
        p["policy"]["minimum_gross_margin_bps"] = 0
        p["policy"]["risk_reserve_bps"] = 0
        p["deal"]["target_price_cents"] = 1
        self.assertEqual(compile_report(p, NOW)["economics"]["labor_cost_cents"], 1)

    def test_capacity_exact_boundary_passes(self):
        p = packet(); p["capacity"]["total_minutes"] = 2500
        report = compile_report(p, NOW)
        self.assertEqual(report["capacity"]["available_minutes"], 1500)
        self.assertEqual(report["disposition"], "READY_FOR_OWNER_QUOTE_REVIEW")

    def test_capacity_one_minute_short_holds(self):
        p = packet(); p["capacity"]["total_minutes"] = 2499
        report = compile_report(p, NOW)
        self.assertEqual(report["capacity"]["shortfall_minutes"], 1)
        self.assertEqual(report["disposition"], "HOLD_CAPACITY")

    def test_margin_and_capacity_hold(self):
        p = packet(); p["deal"]["target_price_cents"] = 1; p["capacity"]["total_minutes"] = 1000
        report = compile_report(p, NOW)
        self.assertEqual(report["disposition"], "HOLD_MARGIN_AND_CAPACITY")

    def test_stale_evidence_holds_before_margin(self):
        p = packet(); old = "2026-09-12T20:29:59Z"
        p["capacity"]["observed_at"] = old
        report = compile_report(p, NOW)
        self.assertEqual(report["disposition"], "HOLD_EVIDENCE")
        self.assertIn("STALE_EVIDENCE:CAPACITY", report["reasons"])

    def test_future_evidence_holds(self):
        p = packet(); p["deal"]["items"][0]["observed_at"] = "2026-09-13T21:30:01Z"
        report = compile_report(p, NOW)
        self.assertEqual(report["disposition"], "HOLD_EVIDENCE")
        self.assertIn("FUTURE_EVIDENCE:ITEM:implementation", report["reasons"])

    def test_delivery_started_holds(self):
        report = compile_report(packet(), "2026-09-15T00:00:00Z")
        self.assertEqual(report["disposition"], "HOLD_EVIDENCE")
        self.assertIn("DELIVERY_WINDOW_ALREADY_STARTED", report["reasons"])

    def test_currency_mismatch_holds(self):
        p = packet(); p["deal"]["currency"] = "EUR"
        report = compile_report(p, NOW)
        self.assertEqual(report["disposition"], "HOLD_EVIDENCE")
        self.assertIn("CURRENCY_MISMATCH", report["reasons"])

    def test_capacity_window_transplant_holds(self):
        p = packet(); p["capacity"]["window_end"] = "2026-09-24T00:00:00Z"
        report = compile_report(p, NOW)
        self.assertEqual(report["disposition"], "HOLD_EVIDENCE")
        self.assertIn("CAPACITY_WINDOW_MISMATCH", report["reasons"])

    def test_capacity_overdraw_holds(self):
        p = packet(); p["capacity"]["reserved_minutes"] = 3001
        report = compile_report(p, NOW)
        self.assertEqual(report["disposition"], "HOLD_EVIDENCE")
        self.assertIn("CAPACITY_OVERDRAWN", report["reasons"])

    def test_duplicate_item_id_rejected(self):
        p = packet(); p["deal"]["items"].append(copy.deepcopy(p["deal"]["items"][0]))
        with self.assertRaisesRegex(DealEconomicsError, "duplicate item_id"):
            compile_report(p, NOW)

    def test_bool_is_not_integer(self):
        p = packet(); p["deal"]["target_price_cents"] = True
        with self.assertRaisesRegex(DealEconomicsError, "must be an integer"):
            compile_report(p, NOW)

    def test_float_is_not_integer(self):
        p = packet(); p["capacity"]["total_minutes"] = 3000.0
        with self.assertRaisesRegex(DealEconomicsError, "must be an integer"):
            compile_report(p, NOW)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(DealEconomicsError, "duplicate JSON key"):
            parse_strict_json('{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(DealEconomicsError, "non-finite"):
            parse_strict_json('{"x":NaN}')

    def test_unknown_key_rejected(self):
        p = packet(); p["deal"]["surprise"] = 1
        with self.assertRaisesRegex(DealEconomicsError, "keys mismatch"):
            compile_report(p, NOW)

    def test_noncanonical_timestamp_rejected(self):
        p = packet(); p["deal"]["observed_at"] = "2026-09-13T20:30:00+00:00"
        with self.assertRaisesRegex(DealEconomicsError, "canonical"):
            compile_report(p, NOW)

    def test_malformed_digest_rejected(self):
        p = packet(); p["capacity"]["source_sha256"] = "ABC"
        with self.assertRaisesRegex(DealEconomicsError, "SHA-256"):
            compile_report(p, NOW)

    def test_input_order_invariance(self):
        a = packet(); b = packet(); b["deal"]["items"] = list(reversed(b["deal"]["items"]))
        ra = compile_report(a, NOW); rb = compile_report(b, NOW)
        self.assertEqual(ra["receipt_sha256"], rb["receipt_sha256"])
        self.assertEqual(canonical_json(ra), canonical_json(rb))

    def test_risk_reserve_changes_floor(self):
        p = packet(); p["policy"]["risk_reserve_bps"] = 2000
        report = compile_report(p, NOW)
        self.assertEqual(report["economics"]["risk_reserve_cents"], 70000)
        self.assertEqual(report["economics"]["loaded_delivery_cost_cents"], 420000)
        self.assertEqual(report["economics"]["minimum_price_cents"], 600000)

    def test_historical_verification_and_tamper(self):
        p = packet(); report = compile_report(p, NOW)
        self.assertTrue(verify_historical(p, report))
        bad = copy.deepcopy(report); bad["economics"]["minimum_price_cents"] += 1
        self.assertFalse(verify_historical(p, bad))

    def test_input_tamper_breaks_historical_verification(self):
        p = packet(); report = compile_report(p, NOW)
        p["deal"]["target_price_cents"] += 1
        self.assertFalse(verify_historical(p, report))

    def test_current_verification(self):
        p = packet(); report = compile_report(p, NOW)
        result = verify_current(p, report, "2026-09-13T21:31:00Z")
        self.assertEqual(result["state"], "CURRENT_VERIFIED")
        self.assertTrue(result["historical_receipt_valid"])

    def test_future_receipt_not_current(self):
        p = packet(); report = compile_report(p, NOW)
        result = verify_current(p, report, "2026-09-13T21:29:59Z")
        self.assertEqual(result["state"], "FUTURE_RECEIPT")

    def test_current_verification_ages_out(self):
        p = packet(); report = compile_report(p, NOW)
        result = verify_current(p, report, "2026-09-14T21:31:00Z")
        self.assertEqual(result["state"], "STALE_OR_DRIFTED")

    def test_markdown_has_no_false_authority(self):
        text = render_markdown(compile_report(packet(), NOW))
        self.assertIn("does not send or commit a quote", text)
        self.assertIn("READY_FOR_OWNER_QUOTE_REVIEW", text)

    def test_cli_exposes_no_as_of_option(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["compile", "a", "b", "--as-of", NOW])

    def test_create_exclusive_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            write_exclusive(path, "first")
            with self.assertRaisesRegex(DealEconomicsError, "already exists"):
                write_exclusive(path, "second")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_output_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"; target.write_text("keep", encoding="utf-8")
            link = Path(tmp) / "out"; os.symlink(target, link)
            with self.assertRaisesRegex(DealEconomicsError, "symlink"):
                write_exclusive(link, "replace")
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and hasattr(os, "symlink"), "O_NOFOLLOW unavailable")
    def test_input_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "input.json"; target.write_text(json.dumps(packet()), encoding="utf-8")
            link = Path(tmp) / "link.json"; os.symlink(target, link)
            with self.assertRaisesRegex(DealEconomicsError, "cannot open input safely"):
                read_json_file(link)

    def test_read_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"; path.write_text(json.dumps(packet()), encoding="utf-8")
            self.assertEqual(read_json_file(path)["deal"]["deal_id"], "deal-1")

    def test_quote_validity_capped_at_delivery_start(self):
        p = packet(); p["policy"]["quote_validity_hours"] = 1000
        report = compile_report(p, NOW)
        self.assertEqual(report["quote_valid_until"], START)

    def test_authority_never_promoted_by_ready_state(self):
        report = compile_report(packet(), NOW)
        self.assertEqual(report["disposition"], "READY_FOR_OWNER_QUOTE_REVIEW")
        self.assertFalse(report["authority"]["quote_sent_or_committed"])
        self.assertFalse(report["authority"]["capacity_reserved"])
        self.assertFalse(report["authority"]["revenue_booked_or_recognized"])


if __name__ == "__main__":
    unittest.main()
