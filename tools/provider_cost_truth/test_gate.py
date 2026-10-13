from __future__ import annotations
from copy import deepcopy
import json
import unittest
from tools.provider_cost_truth import engine, evaluator, gate, trusted_sources
from tools.provider_cost_truth._test_support import NOW,event,request,snapshot


class ProviderCostTruthTests(unittest.TestCase):
    def evaluate(self, snap, *, trusted_events=()):
        trusted = frozenset(
            evaluator._provider_evidence_fingerprint(item) for item in trusted_events
        )
        manifest_sha = trusted_sources._manifest_digest(trusted)

        def current_events(rows, now):
            return evaluator._current_provider_events(rows, now, _trusted=trusted)

        # Private explicit-time evaluator only: this helper cannot mint a current
        # receipt. Supported compile_current() always uses the source manifest.
        return evaluator._evaluate_snapshot(
            snap,
            NOW,
            _current_events=current_events,
            _manifest_sha=manifest_sha,
        )

    def test_raw_provider_authenticated_label_cannot_mint_zero(self):
        row = event("a-zero")
        result = self.evaluate(snapshot([row]))
        self.assertEqual(result["state"], "COST_UNKNOWN")
        self.assertFalse(result["free_only_satisfied"])
        self.assertIn(
            "IGNORED_UNTRUSTED_PROVIDER_EVIDENCE:a-zero", result["reasons"]
        )

    def test_exact_model_zero_allows_free_only_advisory_only_when_manifest_trusted(self):
        row = event("a-zero")
        result = self.evaluate(snapshot([row]), trusted_events=[row])
        self.assertEqual(result["state"], "ZERO_COST_VERIFIED")
        self.assertTrue(result["free_only_satisfied"])
        self.assertFalse(result["provider_session_authorized"])
        self.assertFalse(result["spend_authorized"])
        self.assertEqual(
            result["trusted_provider_evidence_manifest_sha256"],
            trusted_sources._manifest_digest(
                frozenset({evaluator._provider_evidence_fingerprint(row)})
            ),
        )

    def test_account_charge_does_not_become_model_price(self):
        row = event("b-paid",scope="ACCOUNT",kind="CHARGE_PAID",amount=2160)
        result = self.evaluate(snapshot([row]), trusted_events=[row])
        self.assertEqual(result["state"], "FREE_UNPROVEN_ACCOUNT_BILLING_PRESENT")
        self.assertFalse(result["free_only_satisfied"])
        self.assertEqual(result["controlling_event_ids"], [])
        self.assertEqual(result["account_billing_event_ids"], ["b-paid"])

    def test_exact_model_charge_is_billable_verified(self):
        row = event("c-paid",kind="CHARGE_PAID",amount=2160)
        result = self.evaluate(snapshot([row]), trusted_events=[row])
        self.assertEqual(result["state"], "BILLABLE_VERIFIED")
        self.assertFalse(result["free_only_satisfied"])

    def test_failed_exact_charge_is_nonzero_billing_evidence(self):
        row = event("d-fail",kind="CHARGE_FAILED",amount=2160)
        self.assertEqual(
            self.evaluate(snapshot([row]), trusted_events=[row])["state"],
            "BILLABLE_VERIFIED",
        )

    def test_session_evidence_cannot_transfer(self):
        row = event("e-sess",scope="SESSION",session_id="session-A")
        result = self.evaluate(
            snapshot([row],request(session_id="session-B")), trusted_events=[row]
        )
        self.assertEqual(result["state"], "COST_UNKNOWN")

    def test_later_paid_supersedes_older_zero(self):
        old=event("a-old",event_at="2026-09-17T18:00:00Z",observed_at="2026-09-17T18:01:00Z")
        new=event("b-new",kind="CHARGE_PAID",amount=100,event_at="2026-09-17T18:40:00Z",observed_at="2026-09-17T18:41:00Z")
        result=self.evaluate(snapshot([old,new]),trusted_events=[old,new])
        self.assertEqual(result["state"],"BILLABLE_VERIFIED")
        self.assertEqual(result["controlling_event_ids"],["b-new"])

    def test_same_generation_zero_and_paid_is_contradictory(self):
        zero=event("a-zero")
        paid=event("b-paid",kind="CHARGE_PAID",amount=100,valid_until=None)
        self.assertEqual(
            self.evaluate(snapshot([zero,paid]),trusted_events=[zero,paid])["state"],
            "CONTRADICTORY",
        )

    def test_stale_and_future_zero_hold(self):
        stale=event("a-stale",event_at="2026-09-01T18:30:00Z",observed_at="2026-09-01T18:31:00Z",valid_until="2026-10-01T18:30:00Z")
        result=self.evaluate(snapshot([stale]),trusted_events=[stale])
        self.assertEqual(result["state"],"COST_UNKNOWN")
        self.assertIn("IGNORED_STALE_EVIDENCE:a-stale",result["reasons"])
        future=event("a-future",event_at="2026-09-17T19:01:00Z",observed_at="2026-09-17T19:01:00Z",valid_until="2026-09-18T19:01:00Z")
        result=self.evaluate(snapshot([future]),trusted_events=[future])
        self.assertEqual(result["state"],"COST_UNKNOWN")
        self.assertIn("IGNORED_FUTURE_EVIDENCE:a-future",result["reasons"])

    def test_marketing_free_claim_cannot_mint_zero(self):
        claim=event("a-marketing",authority="MARKETING_MATERIAL")
        result=self.evaluate(snapshot([claim]))
        self.assertEqual(result["state"],"COST_UNKNOWN")
        self.assertIn("IGNORED_NON_PROVIDER_AUTHORITY:a-marketing",result["reasons"])

    def test_marketing_free_plus_trusted_account_charge_is_free_unproven(self):
        claim=event("a-marketing",authority="MARKETING_MATERIAL")
        paid=event("b-paid",scope="ACCOUNT",kind="CHARGE_PAID",amount=2160)
        self.assertEqual(
            self.evaluate(snapshot([claim,paid]),trusted_events=[paid])["state"],
            "FREE_UNPROVEN_ACCOUNT_BILLING_PRESENT",
        )

    def test_source_digest_drift_cannot_reuse_trust(self):
        trusted=event("a-zero")
        drifted=deepcopy(trusted);drifted["source_sha256"]="b"*64
        result=self.evaluate(snapshot([drifted]),trusted_events=[trusted])
        self.assertEqual(result["state"],"COST_UNKNOWN")
        self.assertIn("IGNORED_UNTRUSTED_PROVIDER_EVIDENCE:a-zero",result["reasons"])

    def test_source_ref_hash_transplant_cannot_reuse_trust(self):
        trusted=event("a-zero")
        transplant=event("b-zero")
        transplant["source_ref"]=trusted["source_ref"]
        transplant["source_sha256"]=trusted["source_sha256"]
        result=self.evaluate(snapshot([transplant]),trusted_events=[trusted])
        self.assertEqual(result["state"],"COST_UNKNOWN")
        self.assertIn("IGNORED_UNTRUSTED_PROVIDER_EVIDENCE:b-zero",result["reasons"])

    def test_duplicate_event_and_json_keys_rejected(self):
        with self.assertRaisesRegex(gate.GateError,"duplicate evidence event_id"):
            self.evaluate(snapshot([event("a-dupe"),event("a-dupe")]))
        with self.assertRaisesRegex(gate.GateError,"duplicate JSON key"):
            gate.loads_strict_json('{"a":1,"a":2}')

    def test_nonfinite_bool_hash_scope_and_identity_rejected(self):
        with self.assertRaisesRegex(gate.GateError,"non-finite"):
            gate.loads_strict_json('{"x":NaN}')
        bad=event("a-bool");bad["amount_minor"]=False
        with self.assertRaisesRegex(gate.GateError,"non-negative integer"):
            self.evaluate(snapshot([bad]))
        bad=event("a-hash");bad["source_sha256"]="ABC"
        with self.assertRaisesRegex(gate.GateError,"lowercase SHA-256"):
            self.evaluate(snapshot([bad]))
        bad=event("a-scope",scope="SESSION",session_id="s");bad["model"]=None
        with self.assertRaisesRegex(gate.GateError,"SESSION scope"):
            self.evaluate(snapshot([bad]))
        bad=event("a-x");bad["account_id"]="other-account"
        with self.assertRaisesRegex(gate.GateError,"transplant"):
            self.evaluate(snapshot([bad]))

    def test_current_receipt_raw_snapshot_is_non_authorizing_and_replay_bound(self):
        snap=snapshot([event("a-zero")])
        receipt=gate.compile_current(snap)
        self.assertEqual(receipt["state"],"COST_UNKNOWN")
        self.assertFalse(receipt["free_only_satisfied"])
        self.assertIn("IGNORED_UNTRUSTED_PROVIDER_EVIDENCE:a-zero",receipt["reasons"])
        self.assertTrue(gate.verify_receipt(snap,receipt))
        bad=deepcopy(receipt);bad["state"]="ZERO_COST_VERIFIED"
        with self.assertRaises(gate.GateError):
            gate.verify_receipt(snap,bad)
        changed=snapshot([event("a-zero"),event("b-paid",scope="ACCOUNT",kind="CHARGE_PAID",amount=10)])
        with self.assertRaisesRegex(gate.GateError,"semantic replay mismatch|snapshot_sha256"):
            gate.verify_receipt(changed,receipt)

    def test_permutation_determinism_with_test_trust_generation(self):
        a=event("a-zero")
        b=event("b-billing",scope="ACCOUNT",kind="CHARGE_PAID",amount=2160,event_at="2026-09-17T18:20:00Z",observed_at="2026-09-17T18:21:00Z")
        self.assertEqual(
            self.evaluate(snapshot([a,b]),trusted_events=[a,b]),
            self.evaluate(snapshot([b,a]),trusted_events=[a,b]),
        )

    def test_validate_snapshot_canonicalizes_evidence_after_duplicate_rejection(self):
        a=event("a-zero")
        b=event("b-billing",scope="ACCOUNT",kind="CHARGE_PAID",amount=2160,event_at="2026-09-17T18:20:00Z",observed_at="2026-09-17T18:21:00Z")
        forward=gate.validate_snapshot(snapshot([b,a]))
        reverse=gate.validate_snapshot(snapshot([a,b]))
        self.assertIsInstance(forward, dict)
        self.assertEqual(forward, reverse)
        self.assertEqual([row["event_id"] for row in forward["evidence"]], ["a-zero", "b-billing"])
        self.assertEqual(
            self.evaluate(snapshot([a,b]),trusted_events=[a,b])["snapshot_sha256"],
            self.evaluate(snapshot([b,a]),trusted_events=[a,b])["snapshot_sha256"],
        )
        with self.assertRaisesRegex(gate.GateError, "duplicate evidence event_id"):
            gate.validate_snapshot(snapshot([a, b, a]))

    def test_strict_roundtrip_loader(self):
        snap=snapshot([event("a-zero")])
        loaded=gate.loads_strict_json(json.dumps(snap,separators=(",",":")))
        self.assertEqual(gate.validate_snapshot(loaded),snap)


if __name__=="__main__":unittest.main()
