from __future__ import annotations

import copy
import json
import unittest

from revenue.prospect_contact_capability_v2 import protocol as p

ANCHOR = "a" * 40
ANCHOR2 = "e" * 40
CLAIM_COMMIT = "b" * 40
TERMINAL_COMMIT = "c" * 40
CONTACTED_COMMIT = "d" * 40
REVEAL_COMMIT = "9" * 40
PREFLIGHT = "1" * 64
MESSAGE = "2" * 64


def claim_flow(target: str = "Lead.Person+Pilot@Example.com"):
    caps = []
    plan = p.prepare_claim(
        "email", target,
        claimant="Z-TEST", operation_id="OP-PAID-1",
        anchor_sha=ANCHOR, preflight_sha256=PREFLIGHT,
        retain_capability=caps.append,
    )
    intent = p.bind_claim_commit(plan, CLAIM_COMMIT)
    receipt = p.claim_receipt_from_readback(
        plan, intent,
        live_branch_sha=CLAIM_COMMIT,
        live_parent_sha=ANCHOR,
        live_metadata_json=plan["metadata_json"],
    )
    return plan, intent, receipt, caps[0]


def release_flow():
    claim_plan, claim_intent, claim_receipt, cap = claim_flow()
    terminal_plan = p.prepare_release_terminal(
        claim_receipt,
        capability=cap,
        live_claim_branch_sha=CLAIM_COMMIT,
        live_claim_parent_sha=ANCHOR,
        live_claim_metadata_json=claim_plan["metadata_json"],
        reason="No provider mutation occurred; route withdrawn",
    )
    terminal_intent = p.bind_terminal_commit(terminal_plan, TERMINAL_COMMIT)
    terminal_receipt = p.terminal_receipt_from_readback(
        terminal_plan, terminal_intent,
        live_branch_sha=TERMINAL_COMMIT,
        live_parent_sha=CLAIM_COMMIT,
        live_metadata_json=terminal_plan["metadata_json"],
    )
    reveal_plan = p.prepare_release_reveal(
        terminal_receipt,
        capability=cap,
        live_claim_branch_sha=CLAIM_COMMIT,
        live_claim_parent_sha=ANCHOR,
        live_claim_metadata_json=claim_plan["metadata_json"],
        live_terminal_branch_sha=TERMINAL_COMMIT,
        live_terminal_parent_sha=CLAIM_COMMIT,
        live_terminal_metadata_json=terminal_plan["metadata_json"],
    )
    reveal_intent = p.bind_release_reveal_commit(reveal_plan, REVEAL_COMMIT)
    reveal_receipt = p.release_reveal_receipt_from_readback(
        reveal_plan, reveal_intent,
        live_branch_sha=REVEAL_COMMIT,
        live_parent_sha=TERMINAL_COMMIT,
        live_metadata_json=reveal_plan["metadata_json"],
    )
    return claim_plan, claim_receipt, cap, terminal_plan, terminal_receipt, reveal_plan, reveal_receipt


def dispatch_flow():
    claim_plan, claim_intent, claim_receipt, cap = claim_flow()
    terminal_plan = p.prepare_dispatch_terminal(
        claim_receipt,
        capability=cap,
        live_claim_branch_sha=CLAIM_COMMIT,
        live_claim_parent_sha=ANCHOR,
        live_claim_metadata_json=claim_plan["metadata_json"],
        message_sha256=MESSAGE,
        channel="email",
        compensation_path="$2,500 paid discovery",
    )
    terminal_intent = p.bind_terminal_commit(terminal_plan, TERMINAL_COMMIT)
    terminal_receipt = p.terminal_receipt_from_readback(
        terminal_plan, terminal_intent,
        live_branch_sha=TERMINAL_COMMIT,
        live_parent_sha=CLAIM_COMMIT,
        live_metadata_json=terminal_plan["metadata_json"],
    )
    return claim_plan, claim_receipt, cap, terminal_plan, terminal_receipt


class IdentityTests(unittest.TestCase):
    def test_email_normalization_is_casefolded(self):
        a = p.normalize_target("email", "Lead.Person@Example.COM")
        b = p.normalize_target("email", "lead.person@example.com")
        self.assertEqual(a["key_sha256"], b["key_sha256"])

    def test_raw_target_is_not_in_plan(self):
        raw = "Secret.Lead@Example.com"
        plan, _, _, cap = claim_flow(raw)
        text = json.dumps(plan, sort_keys=True)
        self.assertNotIn(raw.casefold(), text.casefold())
        self.assertNotIn(cap, text)

    def test_same_contact_same_branch_despite_claimant_and_anchor(self):
        caps1, caps2 = [], []
        one = p.prepare_claim("email", "lead@example.com", claimant="Z-A", operation_id="OP-A", anchor_sha="a"*40, preflight_sha256="1"*64, retain_capability=caps1.append)
        two = p.prepare_claim("email", "LEAD@example.com", claimant="Z-B", operation_id="OP-B", anchor_sha="b"*40, preflight_sha256="2"*64, retain_capability=caps2.append)
        self.assertEqual(one["branch_name"], two["branch_name"])
        self.assertNotEqual(one["metadata_sha256"], two["metadata_sha256"])

    def test_different_contact_different_branch(self):
        c1, c2 = [], []
        one = p.prepare_claim("email", "a@example.com", claimant="Z-A", operation_id="OP-A", anchor_sha=ANCHOR, preflight_sha256=PREFLIGHT, retain_capability=c1.append)
        two = p.prepare_claim("email", "b@example.com", claimant="Z-A", operation_id="OP-A", anchor_sha=ANCHOR, preflight_sha256=PREFLIGHT, retain_capability=c2.append)
        self.assertNotEqual(one["branch_name"], two["branch_name"])


class ClaimTests(unittest.TestCase):
    def test_claim_exact_readback_and_possession(self):
        plan, _, receipt, cap = claim_flow()
        self.assertTrue(p.verify_claim_possession(receipt, capability=cap, live_branch_sha=CLAIM_COMMIT, live_parent_sha=ANCHOR, live_metadata_json=plan["metadata_json"]))

    def test_copied_public_claim_wrong_secret_fails(self):
        plan, _, receipt, _ = claim_flow()
        with self.assertRaises(p.CustodyError):
            p.verify_claim_possession(receipt, capability="f"*64, live_branch_sha=CLAIM_COMMIT, live_parent_sha=ANCHOR, live_metadata_json=plan["metadata_json"])

    def test_moved_claim_head_fails(self):
        plan, _, receipt, cap = claim_flow()
        with self.assertRaises(p.CustodyError):
            p.verify_claim_possession(receipt, capability=cap, live_branch_sha="f"*40, live_parent_sha=ANCHOR, live_metadata_json=plan["metadata_json"])

    def test_wrong_claim_parent_fails(self):
        plan, _, receipt, cap = claim_flow()
        with self.assertRaises(p.CustodyError):
            p.verify_claim_possession(receipt, capability=cap, live_branch_sha=CLAIM_COMMIT, live_parent_sha="f"*40, live_metadata_json=plan["metadata_json"])

    def test_claim_metadata_tamper_fails(self):
        plan, _, receipt, cap = claim_flow()
        with self.assertRaises(p.CustodyError):
            p.verify_claim_possession(receipt, capability=cap, live_branch_sha=CLAIM_COMMIT, live_parent_sha=ANCHOR, live_metadata_json=plan["metadata_json"] + " ")

    def test_retention_failure_prevents_plan(self):
        def boom(_: str):
            raise RuntimeError("private store unavailable")
        with self.assertRaises(p.CustodyError):
            p.prepare_claim("email", "lead@example.com", claimant="Z-A", operation_id="OP-A", anchor_sha=ANCHOR, preflight_sha256=PREFLIGHT, retain_capability=boom)


class TerminalTests(unittest.TestCase):
    def test_release_and_dispatch_contend_on_same_terminal_branch(self):
        claim_plan, _, claim_receipt, cap = claim_flow()
        release = p.prepare_release_terminal(claim_receipt, capability=cap, live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"], reason="No send")
        dispatch = p.prepare_dispatch_terminal(claim_receipt, capability=cap, live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"], message_sha256=MESSAGE, channel="email", compensation_path="$2500 paid pilot")
        self.assertEqual(release["terminal_branch_name"], dispatch["terminal_branch_name"])
        self.assertNotEqual(release["metadata_sha256"], dispatch["metadata_sha256"])

    def test_release_terminal_keeps_active_capability_private_until_live_reveal(self):
        _, _, cap, terminal_plan, terminal_receipt, reveal_plan, reveal_receipt = release_flow()
        self.assertNotIn(cap, json.dumps(terminal_plan, sort_keys=True))
        self.assertNotIn(cap, json.dumps(terminal_receipt, sort_keys=True))
        self.assertEqual(reveal_plan["retired_capability"], cap)
        self.assertEqual(reveal_receipt["retired_capability"], cap)
        self.assertEqual(p.capability_commitment(cap), reveal_receipt["claim_capability_sha256"])

    def test_dispatch_does_not_disclose_capability(self):
        _, _, cap, plan, receipt = dispatch_flow()
        self.assertNotIn(cap, json.dumps(plan, sort_keys=True))
        self.assertNotIn(cap, json.dumps(receipt, sort_keys=True))

    def test_dispatch_possession_checks_claim_and_terminal_live_state(self):
        claim_plan, _, cap, terminal_plan, receipt = dispatch_flow()
        self.assertTrue(p.verify_dispatch_possession(
            receipt, capability=cap,
            live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"],
            live_terminal_branch_sha=TERMINAL_COMMIT, live_terminal_parent_sha=CLAIM_COMMIT, live_terminal_metadata_json=terminal_plan["metadata_json"],
        ))

    def test_dispatch_wrong_secret_fails(self):
        claim_plan, _, _, terminal_plan, receipt = dispatch_flow()
        with self.assertRaises(p.CustodyError):
            p.verify_dispatch_possession(
                receipt, capability="f"*64,
                live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"],
                live_terminal_branch_sha=TERMINAL_COMMIT, live_terminal_parent_sha=CLAIM_COMMIT, live_terminal_metadata_json=terminal_plan["metadata_json"],
            )

    def test_dispatch_forged_claim_readback_fails(self):
        claim_plan, _, cap, terminal_plan, receipt = dispatch_flow()
        with self.assertRaises(p.CustodyError):
            p.verify_dispatch_possession(
                receipt, capability=cap,
                live_claim_branch_sha="f"*40, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"],
                live_terminal_branch_sha=TERMINAL_COMMIT, live_terminal_parent_sha=CLAIM_COMMIT, live_terminal_metadata_json=terminal_plan["metadata_json"],
            )

    def test_zero_compensation_fails(self):
        claim_plan, _, claim_receipt, cap = claim_flow()
        with self.assertRaises(p.CustodyError):
            p.prepare_dispatch_terminal(claim_receipt, capability=cap, live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"], message_sha256=MESSAGE, channel="email", compensation_path="$0 bounty")

    def test_unpaid_compensation_fails(self):
        claim_plan, _, claim_receipt, cap = claim_flow()
        with self.assertRaises(p.CustodyError):
            p.prepare_dispatch_terminal(claim_receipt, capability=cap, live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"], message_sha256=MESSAGE, channel="email", compensation_path="unpaid volunteer pilot")

    def test_positive_amount_accepted(self):
        _, _, _, plan, _ = dispatch_flow()
        self.assertEqual(plan["compensation_category"], "priced_service")


class ReleaseChainTests(unittest.TestCase):
    def _next_claim(self, *, claim_plan, terminal_plan, reveal_plan, reveal_receipt,
                    claim_sha=CLAIM_COMMIT, terminal_sha=TERMINAL_COMMIT, reveal_sha=REVEAL_COMMIT):
        caps = []
        plan = p.prepare_claim(
            "email", "lead.person+pilot@example.com",
            claimant="Z-NEXT", operation_id="OP-NEXT",
            anchor_sha=ANCHOR2, preflight_sha256="3"*64,
            retain_capability=caps.append,
            prior_release_reveal_receipt=reveal_receipt,
            live_prior_claim_branch_sha=claim_sha,
            live_prior_claim_parent_sha=ANCHOR,
            live_prior_claim_metadata_json=claim_plan["metadata_json"],
            live_prior_terminal_branch_sha=terminal_sha,
            live_prior_terminal_parent_sha=CLAIM_COMMIT,
            live_prior_terminal_metadata_json=terminal_plan["metadata_json"],
            live_prior_reveal_branch_sha=reveal_sha,
            live_prior_reveal_parent_sha=TERMINAL_COMMIT,
            live_prior_reveal_metadata_json=reveal_plan["metadata_json"],
        )
        return plan, caps[0]

    def test_release_reopens_exact_next_generation(self):
        claim_plan, _, _, terminal_plan, _, reveal_plan, reveal = release_flow()
        next_plan, _ = self._next_claim(
            claim_plan=claim_plan, terminal_plan=terminal_plan,
            reveal_plan=reveal_plan, reveal_receipt=reveal,
        )
        self.assertEqual(next_plan["generation"], 2)
        self.assertNotEqual(next_plan["branch_name"], claim_plan["branch_name"])
        self.assertEqual(next_plan["prior_release_reveal_receipt_sha256"], reveal["receipt_sha256"])

    def test_dispatch_cannot_reopen(self):
        claim_plan, _, _, terminal_plan, dispatch = dispatch_flow()
        with self.assertRaises(p.CustodyError):
            p.prepare_claim(
                "email", "lead.person+pilot@example.com",
                claimant="Z-NEXT", operation_id="OP-NEXT", anchor_sha=ANCHOR2, preflight_sha256="3"*64,
                retain_capability=lambda _: None,
                prior_release_reveal_receipt=dispatch,
                live_prior_claim_branch_sha=CLAIM_COMMIT, live_prior_claim_parent_sha=ANCHOR, live_prior_claim_metadata_json=claim_plan["metadata_json"],
                live_prior_terminal_branch_sha=TERMINAL_COMMIT, live_prior_terminal_parent_sha=CLAIM_COMMIT, live_prior_terminal_metadata_json=terminal_plan["metadata_json"],
                live_prior_reveal_branch_sha=REVEAL_COMMIT, live_prior_reveal_parent_sha=TERMINAL_COMMIT, live_prior_reveal_metadata_json="{}\n",
            )

    def test_stale_prior_claim_readback_blocks_reopen(self):
        claim_plan, _, _, terminal_plan, _, reveal_plan, reveal = release_flow()
        with self.assertRaises(p.CustodyError):
            self._next_claim(claim_plan=claim_plan, terminal_plan=terminal_plan, reveal_plan=reveal_plan, reveal_receipt=reveal, claim_sha="f"*40)

    def test_stale_prior_terminal_readback_blocks_reopen(self):
        claim_plan, _, _, terminal_plan, _, reveal_plan, reveal = release_flow()
        with self.assertRaises(p.CustodyError):
            self._next_claim(claim_plan=claim_plan, terminal_plan=terminal_plan, reveal_plan=reveal_plan, reveal_receipt=reveal, terminal_sha="f"*40)

    def test_stale_prior_reveal_readback_blocks_reopen(self):
        claim_plan, _, _, terminal_plan, _, reveal_plan, reveal = release_flow()
        with self.assertRaises(p.CustodyError):
            self._next_claim(claim_plan=claim_plan, terminal_plan=terminal_plan, reveal_plan=reveal_plan, reveal_receipt=reveal, reveal_sha="f"*40)

    def test_reveal_receipt_retired_secret_tamper_fails(self):
        _, _, _, _, _, _, reveal = release_flow()
        bad = copy.deepcopy(reveal)
        bad["retired_capability"] = "f"*64
        material = dict(bad); material.pop("receipt_sha256")
        bad["receipt_sha256"] = p._digest(material)
        with self.assertRaises(p.CustodyError):
            p.verify_release_reveal_receipt(bad)

    def test_release_reveal_requires_live_terminal_before_secret_disclosure(self):
        claim_plan, _, cap, terminal_plan, release, _, _ = release_flow()
        with self.assertRaises(p.CustodyError):
            p.prepare_release_reveal(
                release, capability=cap,
                live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"],
                live_terminal_branch_sha="f"*40, live_terminal_parent_sha=CLAIM_COMMIT, live_terminal_metadata_json=terminal_plan["metadata_json"],
            )

    def test_reveal_parent_mismatch_fails(self):
        _, _, _, _, _, reveal_plan, _ = release_flow()
        intent = p.bind_release_reveal_commit(reveal_plan, REVEAL_COMMIT)
        with self.assertRaises(p.CustodyError):
            p.release_reveal_receipt_from_readback(
                reveal_plan, intent,
                live_branch_sha=REVEAL_COMMIT,
                live_parent_sha="f"*40,
                live_metadata_json=reveal_plan["metadata_json"],
            )

    def test_wrong_secret_cannot_prepare_release_reveal(self):
        claim_plan, _, _, terminal_plan, release, _, _ = release_flow()
        with self.assertRaises(p.CustodyError):
            p.prepare_release_reveal(
                release, capability="f"*64,
                live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"],
                live_terminal_branch_sha=TERMINAL_COMMIT, live_terminal_parent_sha=CLAIM_COMMIT, live_terminal_metadata_json=terminal_plan["metadata_json"],
            )


class ContactedTests(unittest.TestCase):
    def test_contacted_binds_provider_digest_not_plaintext(self):
        claim_plan, _, cap, terminal_plan, dispatch = dispatch_flow()
        provider = "gmail-message-id:abc123 accepted"
        plan = p.prepare_contacted(
            dispatch,
            capability=cap,
            live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"],
            live_terminal_branch_sha=TERMINAL_COMMIT, live_terminal_parent_sha=CLAIM_COMMIT, live_terminal_metadata_json=terminal_plan["metadata_json"],
            provider_receipt=provider,
        )
        self.assertNotIn(provider, json.dumps(plan, sort_keys=True))
        intent = p.bind_contacted_commit(plan, CONTACTED_COMMIT)
        receipt = p.contacted_receipt_from_readback(plan, intent, live_branch_sha=CONTACTED_COMMIT, live_parent_sha=TERMINAL_COMMIT, live_metadata_json=plan["metadata_json"])
        self.assertEqual(p.verify_contacted_receipt(receipt)["state"], "CONTACTED")

    def test_release_cannot_be_finalized_contacted(self):
        claim_plan, _, cap, terminal_plan, release, _, _ = release_flow()
        with self.assertRaises(p.CustodyError):
            p.prepare_contacted(
                release,
                capability=cap,
                live_claim_branch_sha=CLAIM_COMMIT, live_claim_parent_sha=ANCHOR, live_claim_metadata_json=claim_plan["metadata_json"],
                live_terminal_branch_sha=TERMINAL_COMMIT, live_terminal_parent_sha=CLAIM_COMMIT, live_terminal_metadata_json=terminal_plan["metadata_json"],
                provider_receipt="accepted",
            )


class AuthorityCeilingTests(unittest.TestCase):
    def test_every_receipt_keeps_authority_false(self):
        _, _, claim, _ = claim_flow()
        _, _, _, terminal_plan, release, reveal_plan, reveal = release_flow()
        _, _, _, dispatch_plan, dispatch = dispatch_flow()
        docs = [claim, release, reveal, terminal_plan, reveal_plan, dispatch, dispatch_plan]
        for doc in docs:
            self.assertIs(doc["external_send_authorized"], False)
            self.assertIs(doc["provider_send_completed"], False)
            self.assertIs(doc["payment_or_revenue_inferred"], False)

    def test_resealed_unknown_authority_field_is_rejected(self):
        _, _, claim, _ = claim_flow()
        forged = copy.deepcopy(claim)
        forged["approved"] = True
        material = dict(forged); material.pop("receipt_sha256")
        forged["receipt_sha256"] = p._digest(material)
        with self.assertRaises(p.CustodyError):
            p.verify_claim_receipt(forged)

    def test_resealed_reveal_still_requires_live_readback(self):
        claim_plan, _, _, terminal_plan, _, reveal_plan, reveal = release_flow()
        forged = copy.deepcopy(reveal)
        forged["reveal_commit_sha"] = "f"*40
        material = dict(forged); material.pop("receipt_sha256")
        forged["receipt_sha256"] = p._digest(material)
        with self.assertRaises(p.CustodyError):
            p.prepare_claim(
                "email", "lead.person+pilot@example.com",
                claimant="Z-NEXT", operation_id="OP-NEXT", anchor_sha=ANCHOR2, preflight_sha256="3"*64,
                retain_capability=lambda _: None,
                prior_release_reveal_receipt=forged,
                live_prior_claim_branch_sha=CLAIM_COMMIT, live_prior_claim_parent_sha=ANCHOR, live_prior_claim_metadata_json=claim_plan["metadata_json"],
                live_prior_terminal_branch_sha=TERMINAL_COMMIT, live_prior_terminal_parent_sha=CLAIM_COMMIT, live_prior_terminal_metadata_json=terminal_plan["metadata_json"],
                live_prior_reveal_branch_sha=REVEAL_COMMIT, live_prior_reveal_parent_sha=TERMINAL_COMMIT, live_prior_reveal_metadata_json=reveal_plan["metadata_json"],
            )


if __name__ == "__main__":
    unittest.main()
