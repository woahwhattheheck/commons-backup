import copy
import json
import tempfile
import unittest
from pathlib import Path

import cash_realization_ledger as crl


def claim_digest(claim):
    return crl._sha256(claim)


def packet():
    claim = {
        "id": "claim-lily-267",
        "kind": "BOUNTY",
        "counterparty_ref": "counterparty-lily",
        "currency": "USD",
        "reference_amount_minor": 9000,
        "created_at": "2026-09-06T12:00:00Z",
        "source_ref": "github://issue/267",
        "source_sha256": "1" * 64,
    }
    award = {
        "id": "ev-award",
        "claim_id": claim["id"],
        "claim_sha256": claim_digest(claim),
        "kind": "AWARD_EVIDENCE",
        "occurred_at": "2026-09-06T13:00:00Z",
        "evidence_id": "e-award",
        "amount_minor": 9000,
    }
    return {
        "schema_version": 2,
        "portfolio": {"name": "Synthetic Funded Work"},
        "claims": [claim],
        "events": [award],
        "evidence": [
            {
                "id": "e-award",
                "status": "verified",
                "authority": "sponsor_evidence",
                "captured_at": "2026-09-06T13:01:00Z",
                "reference": "synthetic://sponsor/award",
                "sha256": "2" * 64,
                "event_sha256": crl.event_sha256(award),
            }
        ],
    }


def add_event(
    p,
    *,
    event_id,
    kind,
    time,
    evidence_id,
    authority,
    amount=9000,
    status="verified",
    claim_index=0,
    reference=None,
    source_sha=None,
):
    claim = p["claims"][claim_index]
    event = {
        "id": event_id,
        "claim_id": claim["id"],
        "claim_sha256": claim_digest(claim),
        "kind": kind,
        "occurred_at": time,
        "evidence_id": evidence_id,
        **({"amount_minor": amount} if kind != "OPPORTUNITY_RECORDED" else {}),
    }
    p["events"].append(event)
    proof_index = len(p["evidence"]) + 3
    digest_digit = format(proof_index, "x")[-1]
    p["evidence"].append(
        {
            "id": evidence_id,
            "status": status,
            "authority": authority,
            "captured_at": time,
            "reference": reference or f"synthetic://evidence/{evidence_id}",
            "sha256": source_sha or digest_digit * 64,
            "event_sha256": crl.event_sha256(event),
        }
    )
    return event


def second_claim(p):
    claim = copy.deepcopy(p["claims"][0])
    claim.update(
        {
            "id": "claim-second",
            "counterparty_ref": "counterparty-second",
            "source_ref": "github://issue/other",
            "source_sha256": "a" * 64,
        }
    )
    p["claims"].append(claim)
    return claim


class CashRealizationLedgerTests(unittest.TestCase):
    def test_award_is_not_cash(self):
        out = crl.compile_ledger(packet())
        row = out["claims"][0]
        self.assertEqual(row["state"], "AWARDED")
        self.assertEqual(row["net_received_minor"], 0)
        self.assertFalse(out["summary"]["accounting_revenue_recognized"])
        self.assertTrue(out["summary"]["evidence_bound_to_exact_event"])

    def test_invoice_and_pending_are_not_cash(self):
        p = packet()
        add_event(p, event_id="ev-request", kind="REQUESTED_OR_INVOICED_EVIDENCE", time="2026-09-07T12:00:00Z", evidence_id="e-request", authority="internal_record")
        add_event(p, event_id="ev-pending", kind="PAYMENT_PENDING_EVIDENCE", time="2026-09-07T13:00:00Z", evidence_id="e-pending", authority="payment_provider_evidence")
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "PAYMENT_PENDING")
        self.assertEqual(row["net_received_minor"], 0)

    def test_wrong_authority_cannot_mint_cash(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="owner_approved")
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("ev-cash:AUTHORITY_MISMATCH", row["blockers"])
        self.assertEqual(row["net_received_minor"], 0)

    def test_full_receipt_requires_payment_or_bank_authority(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="payment_provider_evidence")
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "RECEIVED")
        self.assertEqual(row["net_received_minor"], 9000)

    def test_partial_receipt(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=4000)
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "PARTIALLY_RECEIVED")
        self.assertEqual(row["outstanding_reference_minor"], 5000)

    def test_reversal_knocks_state_back(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record")
        add_event(p, event_id="ev-rev", kind="PAYMENT_REVERSED_EVIDENCE", time="2026-09-09T12:00:00Z", evidence_id="e-rev", authority="bank_record", amount=2500)
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "REVERSED")
        self.assertEqual(row["net_received_minor"], 6500)

    def test_reversal_cannot_exceed_prior_receipt(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=2000)
        add_event(p, event_id="ev-rev", kind="PAYMENT_REVERSED_EVIDENCE", time="2026-09-09T12:00:00Z", evidence_id="e-rev", authority="bank_record", amount=2500)
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("ev-rev:REVERSAL_EXCEEDS_RECEIVED", row["blockers"])

    def test_reconciliation_requires_owner_and_exact_net(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=4000)
        add_event(p, event_id="ev-rec", kind="RECONCILED_EVIDENCE", time="2026-09-08T13:00:00Z", evidence_id="e-rec", authority="owner_approved", amount=4000)
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "RECONCILED")
        p2 = copy.deepcopy(p)
        p2["events"][-1]["amount_minor"] = 3999
        with self.assertRaisesRegex(ValueError, "event digest mismatch"):
            crl.compile_ledger(p2)

    def test_new_cash_after_reconciliation_makes_old_reconcile_stale(self):
        p = packet()
        add_event(p, event_id="ev-cash1", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash1", authority="bank_record", amount=4000)
        add_event(p, event_id="ev-rec", kind="RECONCILED_EVIDENCE", time="2026-09-08T13:00:00Z", evidence_id="e-rec", authority="owner_approved", amount=4000)
        add_event(p, event_id="ev-cash2", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-09T12:00:00Z", evidence_id="e-cash2", authority="bank_record", amount=5000)
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("ev-rec:STALE_RECONCILIATION", row["blockers"])

    def test_cumulative_receipt_above_reference_holds(self):
        p = packet()
        add_event(p, event_id="ev-cash1", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash1", authority="bank_record", amount=6000)
        add_event(p, event_id="ev-cash2", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-09T12:00:00Z", evidence_id="e-cash2", authority="bank_record", amount=4000)
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("ev-cash2:CUMULATIVE_RECEIPT_EXCEEDS_REFERENCE", row["blockers"])

    def test_pending_or_rejected_evidence_cannot_advance(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", status="pending")
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("ev-cash:EVIDENCE_NOT_VERIFIED", row["blockers"])

    def test_event_claim_digest_transplant_rejected(self):
        p = packet()
        p["events"][0]["claim_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "claim digest mismatch"):
            crl.compile_ledger(p)

    def test_chronology_capture_before_event_holds(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record")
        p["evidence"][-1]["captured_at"] = "2026-09-08T11:59:59Z"
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("ev-cash:CHRONOLOGY_HOLD", row["blockers"])

    def test_bool_and_float_money_rejected(self):
        for bad in (True, 90.0):
            p = packet()
            p["claims"][0]["reference_amount_minor"] = bad
            with self.assertRaisesRegex(ValueError, "integer minor-unit"):
                crl.compile_ledger(p)

    def test_multicurrency_partition_no_cross_total(self):
        p = packet()
        eur_claim = copy.deepcopy(p["claims"][0])
        eur_claim.update({"id": "claim-eur", "currency": "EUR", "reference_amount_minor": 5000, "source_sha256": "a" * 64})
        p["claims"].append(eur_claim)
        add_event(p, event_id="ev-usd-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-usd-cash", authority="bank_record", amount=9000)
        out = crl.compile_ledger(p)
        self.assertEqual(set(out["summary"]["currency_buckets"]), {"EUR", "USD"})
        self.assertTrue(out["summary"]["cross_currency_total_prohibited"])

    def test_semantic_duplicate_with_distinct_proofs_holds(self):
        p = packet()
        add_event(p, event_id="ev-cash-a", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash-a", authority="bank_record", amount=4500)
        add_event(p, event_id="ev-cash-b", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash-b", authority="bank_record", amount=4500)
        row = crl.compile_ledger(p)["claims"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("ev-cash-b:DUPLICATE_SEMANTIC_EVENT", row["blockers"])
        self.assertEqual(row["gross_received_minor"], 4500)

    def test_deterministic_order_and_verifier(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record")
        first = crl.compile_ledger(p)
        q = copy.deepcopy(p)
        q["events"] = list(reversed(q["events"]))
        q["evidence"] = list(reversed(q["evidence"]))
        second = crl.compile_ledger(q)
        self.assertEqual(first, second)
        self.assertTrue(crl.verify_ledger(p, first)[0])
        tampered = copy.deepcopy(first)
        tampered["claims"][0]["state"] = "RECONCILED"
        self.assertFalse(crl.verify_ledger(p, tampered)[0])

    def test_cli_strict_duplicate_json_key_and_create_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp = root / "in.json"
            out = root / "out.json"
            inp.write_text(json.dumps(packet()), encoding="utf-8")
            self.assertEqual(crl.main(["compile", "--input", str(inp), "--json-out", str(out)]), 0)
            with self.assertRaises(FileExistsError):
                crl.main(["compile", "--input", str(inp), "--json-out", str(out)])
            dup = root / "dup.json"
            dup.write_text('{"schema_version":2,"schema_version":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                crl._load_json_strict(dup)

    def test_cli_round_trip_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp, out, md, csvp = root / "in.json", root / "out.json", root / "out.md", root / "out.csv"
            inp.write_text(json.dumps(packet()), encoding="utf-8")
            self.assertEqual(crl.main(["compile", "--input", str(inp), "--json-out", str(out), "--markdown-out", str(md), "--csv-out", str(csvp)]), 0)
            self.assertEqual(crl.main(["verify", "--input", str(inp), "--ledger", str(out)]), 0)
            loaded = json.loads(out.read_text(encoding="utf-8"))
            loaded["claims"][0]["state"] = "RECONCILED"
            out2 = root / "tampered.json"
            out2.write_text(json.dumps(loaded), encoding="utf-8")
            self.assertEqual(crl.main(["verify", "--input", str(inp), "--ledger", str(out2)]), 3)

    def test_fail_on_hold_exit_code_and_csv(self):
        p = packet()
        add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="owner_approved")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp, out, csvp = root / "in.json", root / "out.json", root / "out.csv"
            inp.write_text(json.dumps(p), encoding="utf-8")
            self.assertEqual(crl.main(["compile", "--input", str(inp), "--json-out", str(out), "--csv-out", str(csvp), "--fail-on-hold"]), 2)
            self.assertIn("claim_id,claim_kind,currency", csvp.read_text(encoding="utf-8"))

    def test_legacy_v1_unbound_packet_fails_closed(self):
        p = packet()
        p["schema_version"] = 1
        for proof in p["evidence"]:
            proof.pop("event_sha256")
        with self.assertRaisesRegex(ValueError, "legacy v1 evidence is not event-bound"):
            crl.compile_ledger(p)

    def test_same_evidence_id_cannot_authorize_two_events(self):
        p = packet()
        add_event(p, event_id="ev-cash-a", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=4000)
        second = copy.deepcopy(p["events"][-1])
        second.update({"id": "ev-cash-b", "occurred_at": "2026-09-08T12:30:00Z", "amount_minor": 5000})
        p["events"].append(second)
        with self.assertRaisesRegex(ValueError, "referenced by multiple events"):
            crl.compile_ledger(p)

    def test_cloned_external_source_identity_under_new_id_rejected(self):
        p = packet()
        add_event(p, event_id="ev-cash-a", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash-a", authority="bank_record", amount=4000, reference="bank://statement/tx-1", source_sha="b" * 64)
        add_event(p, event_id="ev-cash-b", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T13:00:00Z", evidence_id="e-cash-b", authority="bank_record", amount=5000, reference="bank://same-bytes/different-label", source_sha="b" * 64)
        with self.assertRaisesRegex(ValueError, "source identity reused"):
            crl.compile_ledger(p)

    def test_proof_cannot_be_transplanted_to_second_claim(self):
        p = packet()
        second_claim(p)
        event = add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=4000)
        event["claim_id"] = p["claims"][1]["id"]
        event["claim_sha256"] = claim_digest(p["claims"][1])
        with self.assertRaisesRegex(ValueError, "event digest mismatch"):
            crl.compile_ledger(p)

    def test_amount_mutation_under_same_proof_rejected(self):
        p = packet()
        event = add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=4000)
        event["amount_minor"] = 5000
        with self.assertRaisesRegex(ValueError, "event digest mismatch"):
            crl.compile_ledger(p)

    def test_kind_mutation_under_same_proof_rejected(self):
        p = packet()
        event = add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=4000)
        event["kind"] = "PAYMENT_REVERSED_EVIDENCE"
        with self.assertRaisesRegex(ValueError, "event digest mismatch"):
            crl.compile_ledger(p)

    def test_time_mutation_under_same_proof_rejected(self):
        p = packet()
        event = add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=4000)
        event["occurred_at"] = "2026-09-08T12:01:00Z"
        with self.assertRaisesRegex(ValueError, "event digest mismatch"):
            crl.compile_ledger(p)

    def test_event_id_mutation_under_same_proof_rejected(self):
        p = packet()
        event = add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=4000)
        event["id"] = "ev-cash-relabelled"
        with self.assertRaisesRegex(ValueError, "event digest mismatch"):
            crl.compile_ledger(p)

    def test_evidence_registry_exposes_exact_event_binding(self):
        p = packet()
        event = add_event(p, event_id="ev-cash", kind="PAYMENT_RECEIVED_EVIDENCE", time="2026-09-08T12:00:00Z", evidence_id="e-cash", authority="bank_record", amount=4000)
        out = crl.compile_ledger(p)
        proof = next(row for row in out["evidence_registry"] if row["id"] == "e-cash")
        self.assertEqual(proof["event_sha256"], crl.event_sha256(event))


    def test_unreferenced_evidence_rejected(self):
        p = packet()
        p["evidence"].append({
            "id": "e-unused", "status": "verified", "authority": "bank_record",
            "captured_at": "2026-09-08T12:00:00Z", "reference": "bank://unused",
            "sha256": "c" * 64, "event_sha256": "d" * 64,
        })
        with self.assertRaisesRegex(ValueError, "not referenced by any event"):
            crl.compile_ledger(p)

    def test_unknown_event_binding_field_is_strict(self):
        p = packet()
        p["evidence"][0]["event_digest"] = p["evidence"][0]["event_sha256"]
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            crl.compile_ledger(p)


if __name__ == "__main__":
    unittest.main()
