from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from revenue.swarmops_dossier.acceptance import fixture
from revenue.swarmops_dossier.cli import main as cli_main
from revenue.swarmops_dossier.engine import (
    DossierError, _compile_at, compile_dossier, render_markdown, strict_json_loads, verify_dossier,
)

AS_OF = "2026-09-13T14:00:00Z"
PORTFOLIO = "commons-swarmops-public-demo"


def h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def commercial(state="PAID", kind="PAYMENT_RECEIPT", sid="payment-1", sha=None):
    return {
        "capability_id": "commercial-event", "source_id": sid, "source_kind": kind,
        "source_ref": "retained:receipt1", "source_sha256": sha or h("pay"), "observed_state": state,
        "observed_at": "2026-09-13T13:05:00Z", "freshness_seconds": 86400,
        "prospect_class": "PROSPECT_SAFE", "required": False,
        "claim": "An independently retained commercial receipt exists for one event.",
    }


def authority(row, *, portfolio_id=PORTFOLIO, **overrides):
    out = {
        "portfolio_id": portfolio_id,
        **{
            key: row[key]
            for key in (
                "capability_id",
                "source_kind",
                "source_ref",
                "source_sha256",
                "observed_state",
                "observed_at",
                "freshness_seconds",
                "prospect_class",
                "required",
                "claim",
            )
        },
    }
    out.update(overrides)
    return out


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.packet, self.policy = fixture()

    def compile(self, trusted=None):
        return compile_dossier(self.packet, self.policy, AS_OF, trusted)

    def test_mixed_acceptance_truth(self):
        out = self.compile()
        self.assertEqual(out["schema"], "commons.swarmops-dossier-output/v4")
        self.assertEqual(out["evaluation_mode"], "HISTORICAL_REPLAY")
        self.assertEqual(out["status"], "HISTORICAL_READY")
        self.assertEqual(out["summary"]["DEMONSTRATED"], 2)
        self.assertEqual(out["summary"]["LIMITED"], 2)
        self.assertEqual(out["external_truth"], {"buyer_accepted": False, "paid": False, "revenue_recognized": False})

    def test_queued_ci_never_demonstrated(self):
        self.assertEqual(next(r for r in self.compile()["evidence"] if r["capability_id"] == "hosted-ci")["classification"], "LIMITED")

    def test_sent_never_accepted(self):
        self.assertFalse(self.compile()["external_truth"]["buyer_accepted"])

    def test_provider_cannot_claim_paid(self):
        self.packet["evidence"][3]["observed_state"] = "PAID"
        with self.assertRaises(DossierError):
            self.compile()

    def test_fabricated_payment_receipt_without_trust_never_mints_paid(self):
        row = commercial()
        self.packet["evidence"].append(row)
        out = self.compile()
        self.assertFalse(out["external_truth"]["paid"])
        self.assertIn("UNTRUSTED_COMMERCIAL_RECEIPT", next(r for r in out["evidence"] if r["source_id"] == row["source_id"])["reasons"])

    def test_payment_requires_independent_typed_authority(self):
        row = commercial()
        self.packet["evidence"].append(row)
        out = self.compile({row["source_id"]: authority(row)})
        self.assertTrue(out["external_truth"]["paid"])
        self.assertEqual(next(r for r in out["evidence"] if r["source_id"] == row["source_id"])["classification"], "DEMONSTRATED")

    def test_wrong_payment_digest_is_limited(self):
        row = commercial()
        self.packet["evidence"].append(row)
        out = self.compile({row["source_id"]: authority(row, source_sha256=h("wrong"))})
        self.assertFalse(out["external_truth"]["paid"])
        self.assertIn("COMMERCIAL_RECEIPT_DIGEST_MISMATCH", next(r for r in out["evidence"] if r["source_id"] == row["source_id"])["reasons"])

    def test_buyer_acceptance_requires_exact_typed_authority(self):
        row = commercial("BUYER_ACCEPTED", "BUYER_RECEIPT", "buyer-1", h("buyer"))
        self.packet["evidence"].append(row)
        self.assertFalse(self.compile()["external_truth"]["buyer_accepted"])
        self.assertTrue(self.compile({row["source_id"]: authority(row)})["external_truth"]["buyer_accepted"])

    def test_revenue_recognition_requires_exact_typed_authority(self):
        row = commercial("REVENUE_RECOGNIZED", "ACCOUNTING_RECEIPT", "acct-1", h("acct"))
        self.packet["evidence"].append(row)
        self.assertFalse(self.compile()["external_truth"]["revenue_recognized"])
        self.assertTrue(self.compile({row["source_id"]: authority(row)})["external_truth"]["revenue_recognized"])

    def test_commercial_state_wrong_kind_fails(self):
        self.packet["evidence"].append(commercial("BUYER_ACCEPTED", "PROVIDER_RECEIPT", "buyer-1", h("buyer")))
        with self.assertRaises(DossierError):
            self.compile()

    def test_incoherent_trusted_authority_fails_closed(self):
        row = commercial()
        self.packet["evidence"].append(row)
        forged = authority(row, source_kind="BUYER_RECEIPT")
        with self.assertRaises(DossierError):
            self.compile({row["source_id"]: forged})

    def test_payment_authority_cannot_be_relabelled_buyer_acceptance(self):
        trusted_row = commercial()
        forged = commercial("BUYER_ACCEPTED", "BUYER_RECEIPT", trusted_row["source_id"], trusted_row["source_sha256"])
        self.packet["evidence"].append(forged)
        out = self.compile({trusted_row["source_id"]: authority(trusted_row)})
        projected = next(r for r in out["evidence"] if r["source_id"] == trusted_row["source_id"])
        self.assertEqual(projected["classification"], "LIMITED")
        self.assertIn("COMMERCIAL_RECEIPT_KIND_MISMATCH", projected["reasons"])
        self.assertIn("COMMERCIAL_RECEIPT_STATE_MISMATCH", projected["reasons"])
        self.assertFalse(out["external_truth"]["buyer_accepted"])
        self.assertFalse(out["external_truth"]["paid"])

    def test_payment_authority_cannot_be_relabelled_revenue(self):
        trusted_row = commercial()
        forged = commercial("REVENUE_RECOGNIZED", "ACCOUNTING_RECEIPT", trusted_row["source_id"], trusted_row["source_sha256"])
        self.packet["evidence"].append(forged)
        out = self.compile({trusted_row["source_id"]: authority(trusted_row)})
        projected = next(r for r in out["evidence"] if r["source_id"] == trusted_row["source_id"])
        self.assertEqual(projected["classification"], "LIMITED")
        self.assertIn("COMMERCIAL_RECEIPT_KIND_MISMATCH", projected["reasons"])
        self.assertIn("COMMERCIAL_RECEIPT_STATE_MISMATCH", projected["reasons"])
        self.assertFalse(out["external_truth"]["revenue_recognized"])

    def test_buyer_and_accounting_authority_cannot_cross_roles(self):
        cases = [
            (commercial("BUYER_ACCEPTED", "BUYER_RECEIPT", "buyer-1", h("buyer")), "PAID", "PAYMENT_RECEIPT", "paid"),
            (commercial("REVENUE_RECOGNIZED", "ACCOUNTING_RECEIPT", "acct-1", h("acct")), "BUYER_ACCEPTED", "BUYER_RECEIPT", "buyer_accepted"),
        ]
        for trusted_row, forged_state, forged_kind, truth_key in cases:
            packet, policy = fixture()
            forged = commercial(forged_state, forged_kind, trusted_row["source_id"], trusted_row["source_sha256"])
            packet["evidence"].append(forged)
            out = compile_dossier(packet, policy, AS_OF, {trusted_row["source_id"]: authority(trusted_row)})
            projected = next(r for r in out["evidence"] if r["source_id"] == trusted_row["source_id"])
            self.assertEqual(projected["classification"], "LIMITED")
            self.assertFalse(out["external_truth"][truth_key])

    def test_trusted_receipt_cannot_move_between_capabilities(self):
        trusted_row = commercial()
        forged = copy.deepcopy(trusted_row)
        forged["capability_id"] = "different-commercial-event"
        self.packet["evidence"].append(forged)
        out = self.compile({trusted_row["source_id"]: authority(trusted_row)})
        projected = next(r for r in out["evidence"] if r["source_id"] == trusted_row["source_id"])
        self.assertIn("COMMERCIAL_RECEIPT_CAPABILITY_MISMATCH", projected["reasons"])
        self.assertFalse(out["external_truth"]["paid"])

    def test_trusted_receipt_cannot_move_between_portfolios(self):
        row = commercial()
        self.packet["evidence"].append(row)
        trusted = {row["source_id"]: authority(row)}
        self.packet["portfolio_id"] = "different-portfolio"
        out = self.compile(trusted)
        projected = next(r for r in out["evidence"] if r["source_id"] == row["source_id"])
        self.assertIn("COMMERCIAL_RECEIPT_PORTFOLIO_MISMATCH", projected["reasons"])
        self.assertFalse(out["external_truth"]["paid"])

    def test_trusted_receipt_cannot_change_source_ref(self):
        trusted_row = commercial()
        forged = copy.deepcopy(trusted_row)
        forged["source_ref"] = "retained:different-receipt"
        self.packet["evidence"].append(forged)
        out = self.compile({trusted_row["source_id"]: authority(trusted_row)})
        projected = next(r for r in out["evidence"] if r["source_id"] == trusted_row["source_id"])
        self.assertIn("COMMERCIAL_RECEIPT_REF_MISMATCH", projected["reasons"])
        self.assertFalse(out["external_truth"]["paid"])

    def test_trusted_receipt_cannot_refresh_observed_time(self):
        trusted_row = commercial()
        forged = copy.deepcopy(trusted_row)
        forged["observed_at"] = "2026-09-13T13:06:00Z"
        self.packet["evidence"].append(forged)
        out = self.compile({trusted_row["source_id"]: authority(trusted_row)})
        projected = next(r for r in out["evidence"] if r["source_id"] == trusted_row["source_id"])
        self.assertIn("COMMERCIAL_RECEIPT_OBSERVED_AT_MISMATCH", projected["reasons"])
        self.assertFalse(out["external_truth"]["paid"])

    def test_trusted_receipt_cannot_extend_freshness(self):
        trusted_row = commercial()
        forged = copy.deepcopy(trusted_row)
        forged["freshness_seconds"] = 172800
        self.packet["evidence"].append(forged)
        out = self.compile({trusted_row["source_id"]: authority(trusted_row)})
        projected = next(r for r in out["evidence"] if r["source_id"] == trusted_row["source_id"])
        self.assertIn("COMMERCIAL_RECEIPT_FRESHNESS_MISMATCH", projected["reasons"])
        self.assertFalse(out["external_truth"]["paid"])

    def test_internal_trusted_receipt_cannot_be_released_to_prospect(self):
        trusted_row = commercial()
        trusted_row["prospect_class"] = "INTERNAL_ONLY"
        forged = copy.deepcopy(trusted_row)
        forged["prospect_class"] = "PROSPECT_SAFE"
        self.packet["evidence"].append(forged)
        out = self.compile({trusted_row["source_id"]: authority(trusted_row)})
        projected = next(r for r in out["evidence"] if r["source_id"] == trusted_row["source_id"])
        self.assertIn("COMMERCIAL_RECEIPT_PROSPECT_CLASS_MISMATCH", projected["reasons"])
        self.assertFalse(out["external_truth"]["paid"])

    def test_trusted_receipt_cannot_change_claim_or_required_semantics(self):
        trusted_row = commercial()
        forged = copy.deepcopy(trusted_row)
        forged["claim"] = "A different prospect claim is asserted from the same retained receipt."
        forged["required"] = True
        self.packet["evidence"].append(forged)
        out = self.compile({trusted_row["source_id"]: authority(trusted_row)})
        projected = next(r for r in out["evidence"] if r["source_id"] == trusted_row["source_id"])
        self.assertIn("COMMERCIAL_RECEIPT_CLAIM_MISMATCH", projected["reasons"])
        self.assertIn("COMMERCIAL_RECEIPT_REQUIRED_MISMATCH", projected["reasons"])
        self.assertFalse(out["external_truth"]["paid"])

    def test_unused_trusted_receipt_fails(self):
        row = commercial(sid="not-present")
        with self.assertRaises(DossierError):
            self.compile({row["source_id"]: authority(row)})

    def test_malformed_trusted_receipt_fails(self):
        with self.assertRaises(DossierError):
            self.compile({"payment-1": "0" * 64})

    def test_trust_map_is_bound_into_receipt_and_verifier(self):
        row = commercial()
        self.packet["evidence"].append(row)
        trusted = {row["source_id"]: authority(row)}
        out = self.compile(trusted)
        self.assertIn("trusted_commercial_receipts_sha256", out)
        self.assertTrue(verify_dossier(self.packet, self.policy, AS_OF, out, trusted))
        self.assertFalse(verify_dossier(self.packet, self.policy, AS_OF, out, {}))
        substituted = {row["source_id"]: authority(row, capability_id="different-commercial-event")}
        self.assertFalse(verify_dossier(self.packet, self.policy, AS_OF, out, substituted))

    def test_future_required_holds(self):
        self.packet["evidence"][0]["observed_at"] = "2026-09-13T15:00:00Z"
        core = _compile_at(self.packet, self.policy, AS_OF)
        self.assertEqual(core["status"], "HOLD")
        row = next(item for item in core["evidence"] if item["source_id"] == "merge-receipt-1")
        self.assertIn("FUTURE_EVIDENCE", row["reasons"])
        with self.assertRaises(DossierError):
            self.compile()

    def test_stale_required_holds(self):
        self.packet["evidence"][0]["observed_at"] = "2026-09-10T00:00:00Z"
        self.packet["evidence"][0]["freshness_seconds"] = 60
        self.assertEqual(self.compile()["status"], "HISTORICAL_HOLD")

    def test_internal_required_holds_and_is_not_projected(self):
        self.packet["evidence"][0]["prospect_class"] = "INTERNAL_ONLY"
        out = self.compile()
        self.assertEqual(out["status"], "HISTORICAL_HOLD")
        self.assertFalse(any(r["source_id"] == "merge-receipt-1" for r in out["evidence"]))

    def test_owner_approval_required_holds(self):
        self.packet["evidence"][0]["prospect_class"] = "OWNER_APPROVAL_REQUIRED"
        self.assertEqual(self.compile()["status"], "HISTORICAL_HOLD")

    def test_changed_duplicate_source_fails(self):
        dup = copy.deepcopy(self.packet["evidence"][0])
        dup["claim"] = "Changed bytes"
        self.packet["evidence"].append(dup)
        with self.assertRaises(DossierError):
            self.compile()

    def test_exact_duplicate_cap_source_fails(self):
        self.packet["evidence"].append(copy.deepcopy(self.packet["evidence"][0]))
        with self.assertRaises(DossierError):
            self.compile()

    def test_bad_hash_time_bool_fail(self):
        for key, val in [("source_sha256", "0" * 63), ("observed_at", "2026-09-13 13:00:00"), ("freshness_seconds", True)]:
            packet = copy.deepcopy(self.packet)
            packet["evidence"][0][key] = val
            with self.assertRaises(DossierError):
                compile_dossier(packet, self.policy, AS_OF)

    def test_unsafe_prospect_text_fails(self):
        self.packet["evidence"][0]["claim"] = "claim=value-not-prospect-safe"
        with self.assertRaises(DossierError):
            self.compile()

    def test_unknown_is_not_demonstrated(self):
        self.packet["evidence"].append({
            "capability_id": "future-capability",
            "source_id": "u1",
            "source_kind": "TEST_RECEIPT",
            "source_ref": "receipt:u1",
            "source_sha256": h("u"),
            "observed_state": "UNVERIFIED",
            "observed_at": "2026-09-13T13:05:00Z",
            "freshness_seconds": 86400,
            "prospect_class": "PUBLIC",
            "required": False,
            "claim": "This dossier lane remains unverified.",
        })
        out = self.compile()
        row = next(r for r in out["evidence"] if r["source_id"] == "u1")
        self.assertEqual(row["classification"], "UNKNOWN")

    def test_duplicate_json_keys_and_nonfinite_fail(self):
        with self.assertRaises(DossierError):
            strict_json_loads('{"a":1,"a":2}')
        with self.assertRaises(DossierError):
            strict_json_loads('{"a":NaN}')

    def test_order_invariant(self):
        a = self.compile()
        self.packet["evidence"].reverse()
        self.assertEqual(a, self.compile())

    def test_markdown_deterministic(self):
        out = self.compile()
        self.assertEqual(render_markdown(out), render_markdown(out))
        self.assertIn("Buyer accepted: false", render_markdown(out))

    def test_verifier_tamper(self):
        out = self.compile()
        self.assertTrue(verify_dossier(self.packet, self.policy, AS_OF, out))
        out["summary"]["DEMONSTRATED"] += 1
        self.assertFalse(verify_dossier(self.packet, self.policy, AS_OF, out))

    def test_missing_required_and_unknown(self):
        self.policy["required_capabilities"].append("not-present")
        self.assertEqual(self.compile()["status"], "HISTORICAL_HOLD")

    def test_cli_cannot_self_mint_paid_and_rejects_trust_flag(self):
        row = commercial()
        self.packet["evidence"].append(row)
        trusted = {row["source_id"]: authority(row)}
        with tempfile.TemporaryDirectory() as td:
            packet = Path(td, "packet.json"); policy = Path(td, "policy.json"); trust = Path(td, "trust.json")
            out = Path(td, "out.json"); md = Path(td, "out.md")
            packet.write_text(json.dumps(self.packet)); policy.write_text(json.dumps(self.policy)); trust.write_text(json.dumps(trusted))
            self.assertEqual(cli_main(["replay", str(packet), str(policy), "--as-of", AS_OF, "--json-out", str(out), "--markdown-out", str(md)]), 0)
            self.assertFalse(json.loads(out.read_text())["external_truth"]["paid"])
            with self.assertRaises(SystemExit):
                cli_main(["replay", str(packet), str(policy), "--as-of", AS_OF, "--trusted-commercial-receipts", str(trust), "--json-out", str(Path(td, "evil.json")), "--markdown-out", str(Path(td, "evil.md"))])

    def test_cli_cannot_verify_programmatic_paid_truth(self):
        row = commercial()
        self.packet["evidence"].append(row)
        paid = compile_dossier(self.packet, self.policy, AS_OF, {row["source_id"]: authority(row)})
        self.assertTrue(paid["external_truth"]["paid"])
        with tempfile.TemporaryDirectory() as td:
            packet = Path(td, "packet.json"); policy = Path(td, "policy.json"); candidate = Path(td, "paid.json")
            packet.write_text(json.dumps(self.packet)); policy.write_text(json.dumps(self.policy)); candidate.write_text(json.dumps(paid))
            self.assertEqual(cli_main(["verify-replay", str(packet), str(policy), str(candidate), "--as-of", AS_OF]), 3)

    def test_cli_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            packet = Path(td, "packet.json"); policy = Path(td, "policy.json"); out = Path(td, "out.json"); md = Path(td, "out.md")
            packet.write_text(json.dumps(self.packet)); policy.write_text(json.dumps(self.policy))
            self.assertEqual(cli_main(["replay", str(packet), str(policy), "--as-of", AS_OF, "--json-out", str(out), "--markdown-out", str(md)]), 0)
            self.assertEqual(cli_main(["replay", str(packet), str(policy), "--as-of", AS_OF, "--json-out", str(out), "--markdown-out", str(Path(td, "other.md"))]), 4)

    def test_cli_rejects_symlink_input(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td, "real.json"); target.write_text("{}")
            link = Path(td, "link.json"); os.symlink(target, link)
            self.assertEqual(cli_main(["verify", str(link), str(target), str(target)]), 4)


if __name__ == "__main__":
    unittest.main()
