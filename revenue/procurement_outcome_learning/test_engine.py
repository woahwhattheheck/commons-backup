from __future__ import annotations

import copy
import hashlib
import json
import unittest

from revenue.procurement_outcome_learning import engine


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sample(status="LOST", text="The City decided to move forward with another vendor."):
    status_quote = "decided to move forward with another vendor" if status == "LOST" else None
    if status == "WON":
        text = "Your proposal has been selected for award."
        status_quote = "Your proposal has been selected for award"
    elif status == "NO_DECISION":
        text = "The RFP has been cancelled without award."
        status_quote = "RFP has been cancelled without award"
    elif status == "UNKNOWN":
        text = "Thank you for participating."
        status_quote = None
    return {
        "schema": engine.INPUT_SCHEMA,
        "truth_boundary": engine.TRUTH_BOUNDARY,
        "as_of": "2026-09-17T05:30:00Z",
        "opportunity": {
            "opportunity_id": "city-lims-1421",
            "buyer_key": "city-public-works",
            "proposal_sha256": "a" * 64,
            "submitted_at": "2026-09-04T12:00:00Z",
        },
        "evidence": [{
            "evidence_id": "decision-1",
            "opportunity_id": "city-lims-1421",
            "source_class": "BUYER_NOTICE",
            "observed_at": "2026-09-17T01:55:05Z",
            "source_sha256": sha(text),
            "redacted_text": text,
            "status": status,
            "status_quote": status_quote,
            "winner": None,
            "winner_quote": None,
            "reason": None,
            "reason_quote": None,
            "score": None,
            "score_quote": None,
        }],
        "internal_hypotheses": [],
    }


class OutcomeLearningTests(unittest.TestCase):
    def test_loss_is_source_bound_without_invented_reason(self):
        request = sample("LOST")
        packet = json.loads(engine.compile_packet(raw(request)))
        self.assertEqual("LOST", packet["outcome"]["status"])
        self.assertFalse(packet["outcome"]["winner"]["known"])
        self.assertFalse(packet["outcome"]["reason"]["known"])
        self.assertFalse(packet["outcome"]["score"]["known"])
        self.assertTrue(all(value is False for value in packet["authority"].values()))
        self.assertEqual("SOURCE_BOUND_FACTS_ONLY__HYPOTHESES_NEVER_PROMOTED", packet["learning_rule"])

    def test_supported_won_and_no_decision_quotes_compile(self):
        for status in ("WON", "NO_DECISION"):
            with self.subTest(status=status):
                packet = json.loads(engine.compile_packet(raw(sample(status))))
                self.assertEqual(status, packet["outcome"]["status"])

    def test_weak_quote_cannot_mint_loss_or_win(self):
        request = sample("LOST", text="Thank you for participating.")
        row = request["evidence"][0]
        row["status_quote"] = "Thank you for participating."
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

        request = sample("WON")
        row = request["evidence"][0]
        row["redacted_text"] = "Your proposal is a finalist."
        row["source_sha256"] = sha(row["redacted_text"])
        row["status_quote"] = "Your proposal is a finalist."
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

    def test_reason_winner_and_score_must_be_exact_source_quotes(self):
        text = "Another vendor was selected. Winner: Example Labs. Reason: lower evaluated cost. Score 91/100."
        request = sample("LOST", text=text)
        row = request["evidence"][0]
        row["status_quote"] = "Another vendor was selected"
        row["winner"] = row["winner_quote"] = "Example Labs"
        row["reason"] = row["reason_quote"] = "lower evaluated cost"
        row["score"] = row["score_quote"] = "91/100"
        packet = json.loads(engine.compile_packet(raw(request)))
        self.assertEqual("Example Labs", packet["outcome"]["winner"]["value"])
        self.assertEqual("lower evaluated cost", packet["outcome"]["reason"]["value"])
        self.assertEqual("91/100", packet["outcome"]["score"]["value"])

        for field, quote_field, forged in (
            ("winner", "winner_quote", "Invented Vendor"),
            ("reason", "reason_quote", "invented rationale"),
            ("score", "score_quote", "99/100"),
        ):
            bad = copy.deepcopy(request)
            bad["evidence"][0][field] = forged
            bad["evidence"][0][quote_field] = forged
            with self.subTest(field=field), self.assertRaises(engine.OutcomeError):
                engine.compile_packet(raw(bad))

    def test_wrong_opportunity_and_time_boundaries_fail_closed(self):
        request = sample()
        request["evidence"][0]["opportunity_id"] = "other-opportunity"
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

        request = sample()
        request["evidence"][0]["observed_at"] = "2026-09-01T00:00:00Z"
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

        request = sample()
        request["evidence"][0]["observed_at"] = "2026-09-18T00:00:00Z"
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

    def test_source_digest_must_bind_redacted_text(self):
        request = sample()
        request["evidence"][0]["source_sha256"] = "b" * 64
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

    def test_duplicate_and_reminted_evidence_fail_closed(self):
        request = sample()
        duplicate = copy.deepcopy(request["evidence"][0])
        duplicate["evidence_id"] = "decision-2"
        request["evidence"].append(duplicate)
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

        request = sample()
        duplicate = copy.deepcopy(request["evidence"][0])
        duplicate["evidence_id"] = "decision-2"
        duplicate["redacted_text"] += " Additional harmless sentence."
        duplicate["source_sha256"] = sha(duplicate["redacted_text"])
        request["evidence"].append(duplicate)
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

    def test_contradictory_terminal_outcomes_fail_closed(self):
        request = sample("LOST")
        won = sample("WON")["evidence"][0]
        won["evidence_id"] = "decision-2"
        request["evidence"].append(won)
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

    def test_private_contact_and_locator_material_is_forbidden_everywhere(self):
        bad_values = (
            "Contact person at person@example.test",
            "Call 406-555-0199 for details",
            "See https://example.test/decision",
        )
        for text in bad_values:
            request = sample()
            row = request["evidence"][0]
            row["redacted_text"] = text + " The City decided to move forward with another vendor."
            row["source_sha256"] = sha(row["redacted_text"])
            with self.subTest(text=text), self.assertRaises(engine.OutcomeError):
                engine.compile_packet(raw(request))

        request = sample()
        request["internal_hypotheses"] = [{
            "hypothesis_id": "h1",
            "statement": "Ask person@example.test what happened",
            "test": "wait for public evidence",
        }]
        with self.assertRaises(engine.OutcomeError):
            engine.compile_packet(raw(request))

    def test_internal_hypotheses_are_explicitly_not_buyer_facts(self):
        request = sample()
        request["internal_hypotheses"] = [{
            "hypothesis_id": "h1",
            "statement": "Maybe integration proof was weak",
            "test": "compare future scored criteria if published",
        }]
        packet = json.loads(engine.compile_packet(raw(request)))
        hypothesis = packet["internal_hypotheses"][0]
        self.assertEqual("INTERNAL_HYPOTHESIS_NOT_BUYER_FACT", hypothesis["classification"])
        self.assertFalse(packet["outcome"]["reason"]["known"])

    def test_unknown_without_terminal_evidence_stays_unknown(self):
        packet = json.loads(engine.compile_packet(raw(sample("UNKNOWN"))))
        self.assertEqual("UNKNOWN", packet["outcome"]["status"])
        self.assertEqual([], packet["outcome"]["evidence_ids"])

    def test_verify_rejects_packet_tamper(self):
        request = sample()
        request_bytes = raw(request)
        packet = engine.compile_packet(request_bytes)
        self.assertTrue(engine.verify_packet(request_bytes, packet))
        tampered = json.loads(packet)
        tampered["outcome"]["status"] = "WON"
        with self.assertRaises(engine.OutcomeError):
            engine.verify_packet(request_bytes, engine.canon(tampered))

    def test_portfolio_counts_outcomes_without_inventing_causes(self):
        lost = engine.compile_packet(raw(sample("LOST")))
        won_request = sample("WON")
        won_request["opportunity"]["opportunity_id"] = "other-opportunity"
        won_request["opportunity"]["buyer_key"] = "other-buyer"
        won_request["opportunity"]["proposal_sha256"] = "b" * 64
        won_request["evidence"][0]["opportunity_id"] = "other-opportunity"
        won = engine.compile_packet(raw(won_request))
        portfolio = json.loads(engine.compile_portfolio([lost, won]))
        self.assertEqual(1, portfolio["counts"]["LOST"])
        self.assertEqual(1, portfolio["counts"]["WON"])
        self.assertEqual("OUTCOME_COUNTS_ARE_FACTS__CAUSES_REQUIRE_SOURCE_BOUND_REASON_EVIDENCE", portfolio["learning_rule"])
        lost_row = next(row for row in portfolio["opportunities"] if row["status"] == "LOST")
        self.assertFalse(lost_row["reason_known"])

    def test_portfolio_rejects_duplicate_opportunity_and_authority_tamper(self):
        packet = engine.compile_packet(raw(sample("LOST")))
        with self.assertRaises(engine.OutcomeError):
            engine.compile_portfolio([packet, packet])
        tampered = json.loads(packet)
        tampered["authority"]["revenue_established"] = True
        with self.assertRaises(engine.OutcomeError):
            engine.compile_portfolio([engine.canon(tampered)])


if __name__ == "__main__":
    unittest.main()
