from __future__ import annotations

import copy
import unittest

from revenue.human_reply_workshare_kit.core import (
    COMMERCIAL_STATE,
    WorkshareError,
    compile_offer,
    pack_catalog,
    render_receipt_json,
    strict_json_loads,
)


def base_record(pack_id: str = "FINANCIAL_EVIDENCE_RECONCILIATION"):
    amounts = {
        "DATA_MIGRATION_ACCEPTANCE": (3_000_000, 15),
        "RESPONSIBLE_AI_EVALUATION": (2_400_000, 15),
        "FINANCIAL_EVIDENCE_RECONCILIATION": (1_250_000, 10),
    }
    amount, duration = amounts[pack_id]
    return {
        "schema": "human-reply-paid-workshare/v1",
        "offer_id": "example-001",
        "pack_id": pack_id,
        "counterparty_label": "Example Prime",
        "opportunity_label": "Example bounded workshare",
        "commercial_state": "PROPOSED_NOT_ACCEPTED",
        "offer": {
            "amount_minor": amount,
            "currency": "USD",
            "decimals": 2,
            "duration_business_days": duration,
        },
        "scope": {
            "one_line": "One legal entity, one closed period, buyer-supplied retained evidence only.",
            "input_bounds": [
                "one legal entity",
                "one closed period",
                "one currency",
            ],
        },
        "evidence_state": {
            "buyer_accepted": False,
            "customer_relationship": False,
            "contract_signed": False,
            "invoice_issued": False,
            "payment_settled": False,
            "booked_revenue": False,
            "recognized_revenue": False,
        },
    }


class HumanReplyWorkshareKitTests(unittest.TestCase):
    def test_all_three_packs_compile(self):
        for pack_id in pack_catalog():
            with self.subTest(pack_id=pack_id):
                compiled = compile_offer(base_record(pack_id))
                self.assertIn(COMMERCIAL_STATE, compiled.markdown)
                self.assertEqual(compiled.normalized["pack_id"], pack_id)

    def test_markdown_contains_role_first_truth_boundaries(self):
        md = compile_offer(base_record()).markdown
        self.assertIn("qualification/workshare proposal only", md)
        self.assertIn("Authority retained by buyer / prime", md)
        self.assertIn("no acceptance, contract, invoice, payment, or revenue is asserted", md)
        self.assertIn("do not silently roll old terms forward", md)

    def test_amount_below_pack_floor_fails(self):
        row = base_record()
        row["offer"]["amount_minor"] = 100
        with self.assertRaisesRegex(WorkshareError, "out of range"):
            compile_offer(row)

    def test_amount_above_pack_ceiling_fails(self):
        row = base_record()
        row["offer"]["amount_minor"] = 9_999_999
        with self.assertRaisesRegex(WorkshareError, "out of range"):
            compile_offer(row)

    def test_duration_bounds_fail_closed(self):
        row = base_record()
        row["offer"]["duration_business_days"] = 99
        with self.assertRaisesRegex(WorkshareError, "out of range"):
            compile_offer(row)

    def test_bool_is_not_integer(self):
        row = base_record()
        row["offer"]["amount_minor"] = True
        with self.assertRaisesRegex(WorkshareError, "must be an integer"):
            compile_offer(row)

    def test_usd_native_terms_only(self):
        row = base_record()
        row["offer"]["currency"] = "EUR"
        with self.assertRaisesRegex(WorkshareError, "must be USD"):
            compile_offer(row)

    def test_commercial_state_is_hard_false(self):
        row = base_record()
        row["commercial_state"] = "ACCEPTED"
        with self.assertRaisesRegex(WorkshareError, "PROPOSED_NOT_ACCEPTED"):
            compile_offer(row)

    def test_any_positive_evidence_claim_is_rejected(self):
        for key in base_record()["evidence_state"]:
            row = base_record()
            row["evidence_state"][key] = True
            with self.subTest(key=key):
                with self.assertRaisesRegex(WorkshareError, "outside this qualification"):
                    compile_offer(row)

    def test_unsupported_scope_claims_are_rejected(self):
        phrases = [
            "Buyer accepted this scope yesterday.",
            "We have been awarded the work.",
            "Award secured for this program.",
            "Payment received for the pilot.",
            "This is booked revenue.",
            "This is recognized revenue.",
            "Existing customer requested the change.",
            "Guaranteed savings of ten percent.",
        ]
        for phrase in phrases:
            row = base_record()
            row["scope"]["one_line"] = phrase
            with self.subTest(phrase=phrase):
                with self.assertRaisesRegex(WorkshareError, "unsupported"):
                    compile_offer(row)

    def test_acceptance_evidence_phrase_is_allowed(self):
        row = base_record("DATA_MIGRATION_ACCEPTANCE")
        row["scope"]["one_line"] = "Legacy-to-target reconciliation and acceptance evidence for one frozen migration batch."
        self.assertIn("acceptance evidence", compile_offer(row).markdown)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(WorkshareError, "duplicate key"):
            strict_json_loads('{"x":1,"x":2}')

    def test_float_json_rejected(self):
        with self.assertRaisesRegex(WorkshareError, "floats are not allowed"):
            strict_json_loads('{"x":1.5}')

    def test_newline_in_label_rejected(self):
        row = base_record()
        row["counterparty_label"] = "Example\nPrime"
        with self.assertRaisesRegex(WorkshareError, "one line"):
            compile_offer(row)

    def test_blank_after_strip_values_are_rejected(self):
        row = base_record()
        row["counterparty_label"] = "   "
        with self.assertRaisesRegex(WorkshareError, "must not be blank"):
            compile_offer(row)

        row = base_record()
        row["scope"]["one_line"] = "   "
        with self.assertRaisesRegex(WorkshareError, "must not be blank"):
            compile_offer(row)

        row = base_record()
        row["scope"]["input_bounds"] = ["one entity", "   "]
        with self.assertRaisesRegex(WorkshareError, "must not be blank"):
            compile_offer(row)

    def test_input_bounds_cardinality_is_bounded(self):
        row = base_record()
        row["scope"]["input_bounds"] = [f"item {i}" for i in range(9)]
        with self.assertRaisesRegex(WorkshareError, "1..8"):
            compile_offer(row)

    def test_extra_keys_rejected(self):
        row = base_record()
        row["accepted"] = True
        with self.assertRaisesRegex(WorkshareError, "keys mismatch"):
            compile_offer(row)

    def test_receipt_is_deterministic(self):
        a = compile_offer(base_record())
        b = compile_offer(copy.deepcopy(base_record()))
        self.assertEqual(a.receipt_sha256, b.receipt_sha256)
        self.assertEqual(a.markdown, b.markdown)
        self.assertEqual(render_receipt_json(a), render_receipt_json(b))

    def test_scope_change_changes_receipt(self):
        a = compile_offer(base_record())
        row = base_record()
        row["scope"]["one_line"] = "One entity, one other frozen closed period, retained exports only."
        b = compile_offer(row)
        self.assertNotEqual(a.receipt_sha256, b.receipt_sha256)

    def test_milestones_are_monotonic_and_end_at_duration(self):
        md = compile_offer(base_record()).markdown
        self.assertIn("Day 2: Boundary + acceptance lock", md)
        self.assertIn("Day 7: Deterministic draft evidence pack", md)
        self.assertIn("Day 10: Final acceptance handoff", md)

    def test_offer_revision_warning_present(self):
        md = compile_offer(base_record()).markdown
        for word in ("scope", "price", "deadline", "currency", "acceptance"):
            self.assertIn(word, md.lower())


if __name__ == "__main__":
    unittest.main()
