from __future__ import annotations

import copy
import unittest

from .ledger import FunnelError, INPUT_SCHEMA, canonical_json, compile_funnel

AS_OF = "2026-09-13T10:10:00Z"


def _source(name: str, digest: str = "b" * 64) -> dict:
    return {
        "repository": "example/fixture",
        "commit": "1" * 40,
        "path": f"synthetic/{name}.json",
        "sha256": digest,
    }


def _payload() -> dict:
    return {
        "schema": INPUT_SCHEMA,
        "opportunities": [{
            "id": "opp-review",
            "family": "SERVICE",
            "offer": {"id": "offer-review", "version": "v1", "source": _source("offer")},
            "events": [{
                "id": "evt-traffic",
                "stage": "TRAFFIC",
                "observed_at": "2026-09-12T10:00:00Z",
                "evidence": _source("traffic"),
            }],
        }],
    }


class ReviewRegressionTests(unittest.TestCase):
    def test_identical_replay_preserves_packet_and_receipt_identity(self):
        once_input = _payload()
        replay_input = copy.deepcopy(once_input)
        replay_input["opportunities"][0]["events"].append(copy.deepcopy(replay_input["opportunities"][0]["events"][0]))
        once = compile_funnel(once_input, as_of=AS_OF)
        replay = compile_funnel(replay_input, as_of=AS_OF)
        self.assertEqual(canonical_json(once["packet"]), canonical_json(replay["packet"]))
        self.assertEqual(canonical_json(once["receipt"]), canonical_json(replay["receipt"]))

    def test_opaque_digest_is_not_scanned_as_phone_pii(self):
        value = _payload()
        value["opportunities"][0]["events"][0]["evidence"]["sha256"] = "1234567890" * 6 + "1234"
        out = compile_funnel(value, as_of=AS_OF)
        self.assertEqual(out["packet"]["state"], "FUNNEL_PACKET_READY_FOR_HUMAN_REVIEW")

    def test_secret_shaped_identifier_still_fails_closed(self):
        value = _payload()
        value["opportunities"][0]["offer"]["id"] = "sk_abcdefghijklmno"
        with self.assertRaises(FunnelError):
            compile_funnel(value, as_of=AS_OF)

    def test_one_source_cannot_mint_two_distinct_events_in_one_opportunity(self):
        value = _payload()
        traffic = value["opportunities"][0]["events"][0]
        value["opportunities"][0]["events"].append({
            "id": "evt-reply",
            "stage": "REPLY",
            "observed_at": "2026-09-12T11:00:00Z",
            "evidence": copy.deepcopy(traffic["evidence"]),
        })
        out = compile_funnel(value, as_of=AS_OF)
        row = out["packet"]["opportunities"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("EVIDENCE_REUSED_WITHIN_OPPORTUNITY", row["hold_reasons"])
        self.assertEqual(out["packet"]["metrics"]["eligible_opportunity_count"], 0)

    def test_case_variant_repository_cannot_mint_two_distinct_events(self):
        value = _payload()
        traffic = value["opportunities"][0]["events"][0]
        traffic["evidence"]["repository"] = "Example/Fixture"
        reply_source = copy.deepcopy(traffic["evidence"])
        reply_source["repository"] = "EXAMPLE/fixture"
        value["opportunities"][0]["events"].append({
            "id": "evt-reply",
            "stage": "REPLY",
            "observed_at": "2026-09-12T11:00:00Z",
            "evidence": reply_source,
        })
        out = compile_funnel(value, as_of=AS_OF)
        row = out["packet"]["opportunities"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("EVIDENCE_REUSED_WITHIN_OPPORTUNITY", row["hold_reasons"])
        self.assertEqual({event["evidence"]["repository"] for event in row["events"]}, {"example/fixture"})

    def test_case_variant_exact_event_replay_is_not_false_conflict(self):
        value = _payload()
        original = value["opportunities"][0]["events"][0]
        original["evidence"]["repository"] = "Example/Fixture"
        replay = copy.deepcopy(original)
        replay["evidence"]["repository"] = "EXAMPLE/fixture"
        value["opportunities"][0]["events"].append(replay)
        out = compile_funnel(value, as_of=AS_OF)
        row = out["packet"]["opportunities"][0]
        self.assertEqual(row["state"], "FUNNEL_PACKET_READY_FOR_HUMAN_REVIEW")
        self.assertEqual(len(row["events"]), 1)
        self.assertEqual(row["events"][0]["evidence"]["repository"], "example/fixture")

    def test_event_cannot_rebind_its_offer_definition_as_event_evidence(self):
        value = _payload()
        opp = value["opportunities"][0]
        opp["events"][0]["evidence"] = copy.deepcopy(opp["offer"]["source"])
        out = compile_funnel(value, as_of=AS_OF)
        row = out["packet"]["opportunities"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("EVIDENCE_ROLE_CONFLICT", row["hold_reasons"])

    def test_case_variant_repository_cannot_rebind_offer_as_event(self):
        value = _payload()
        opp = value["opportunities"][0]
        opp["offer"]["source"]["repository"] = "Example/Fixture"
        event_source = copy.deepcopy(opp["offer"]["source"])
        event_source["repository"] = "EXAMPLE/fixture"
        opp["events"][0]["evidence"] = event_source
        out = compile_funnel(value, as_of=AS_OF)
        row = out["packet"]["opportunities"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("EVIDENCE_ROLE_CONFLICT", row["hold_reasons"])

    def test_offer_source_reused_as_other_opportunity_event_holds_both(self):
        value = _payload()
        first = value["opportunities"][0]
        second = copy.deepcopy(first)
        second["id"] = "opp-second"
        second["offer"] = {
            "id": "offer-second",
            "version": "v1",
            "source": _source("offer-second", "c" * 64),
        }
        second["events"] = [{
            "id": "evt-second-traffic",
            "stage": "TRAFFIC",
            "observed_at": "2026-09-12T12:00:00Z",
            "evidence": copy.deepcopy(first["offer"]["source"]),
        }]
        value["opportunities"].append(second)
        out = compile_funnel(value, as_of=AS_OF)
        self.assertEqual(out["packet"]["metrics"]["held_opportunity_count"], 2)
        for row in out["packet"]["opportunities"]:
            self.assertIn("EVIDENCE_ROLE_CONFLICT", row["hold_reasons"])

    def test_case_variant_event_source_reused_across_opportunities_holds_both(self):
        value = _payload()
        first = value["opportunities"][0]
        first["events"][0]["evidence"]["repository"] = "Example/Fixture"
        second = copy.deepcopy(first)
        second["id"] = "opp-second"
        second["offer"] = {
            "id": "offer-second",
            "version": "v1",
            "source": _source("offer-second", "c" * 64),
        }
        second["events"] = [{
            "id": "evt-second-traffic",
            "stage": "TRAFFIC",
            "observed_at": "2026-09-12T12:00:00Z",
            "evidence": copy.deepcopy(first["events"][0]["evidence"]),
        }]
        second["events"][0]["evidence"]["repository"] = "EXAMPLE/fixture"
        value["opportunities"].append(second)
        out = compile_funnel(value, as_of=AS_OF)
        self.assertEqual(out["packet"]["metrics"]["held_opportunity_count"], 2)
        for row in out["packet"]["opportunities"]:
            self.assertIn("EVIDENCE_REUSED_ACROSS_OPPORTUNITIES", row["hold_reasons"])

    def test_same_logical_offer_version_cannot_change_immutable_source(self):
        value = _payload()
        first = value["opportunities"][0]
        second = copy.deepcopy(first)
        second["id"] = "opp-second"
        second["offer"]["source"] = _source("different-offer-definition", "d" * 64)
        second["events"] = [{
            "id": "evt-second-traffic",
            "stage": "TRAFFIC",
            "observed_at": "2026-09-12T12:00:00Z",
            "evidence": _source("second-traffic", "e" * 64),
        }]
        value["opportunities"].append(second)
        out = compile_funnel(value, as_of=AS_OF)
        self.assertEqual(out["packet"]["metrics"]["held_opportunity_count"], 2)
        for row in out["packet"]["opportunities"]:
            self.assertIn("OFFER_SOURCE_IDENTITY_CONFLICT", row["hold_reasons"])

    def test_same_logical_offer_version_may_reuse_same_definition(self):
        value = _payload()
        first = value["opportunities"][0]
        second = copy.deepcopy(first)
        second["id"] = "opp-second"
        second["events"] = [{
            "id": "evt-second-traffic",
            "stage": "TRAFFIC",
            "observed_at": "2026-09-12T12:00:00Z",
            "evidence": _source("second-traffic", "e" * 64),
        }]
        value["opportunities"].append(second)
        out = compile_funnel(value, as_of=AS_OF)
        self.assertEqual(out["packet"]["state"], "FUNNEL_PACKET_READY_FOR_HUMAN_REVIEW")
        self.assertEqual(out["packet"]["metrics"]["eligible_opportunity_count"], 2)

    def test_same_logical_offer_case_only_repository_drift_is_same_source(self):
        value = _payload()
        first = value["opportunities"][0]
        first["offer"]["source"]["repository"] = "Example/Fixture"
        second = copy.deepcopy(first)
        second["id"] = "opp-second"
        second["offer"]["source"]["repository"] = "EXAMPLE/fixture"
        second["events"] = [{
            "id": "evt-second-traffic",
            "stage": "TRAFFIC",
            "observed_at": "2026-09-12T12:00:00Z",
            "evidence": _source("second-traffic", "e" * 64),
        }]
        value["opportunities"].append(second)
        out = compile_funnel(value, as_of=AS_OF)
        self.assertEqual(out["packet"]["state"], "FUNNEL_PACKET_READY_FOR_HUMAN_REVIEW")
        self.assertEqual(out["packet"]["metrics"]["eligible_opportunity_count"], 2)
        self.assertNotIn(
            "OFFER_SOURCE_IDENTITY_CONFLICT",
            {reason for row in out["packet"]["opportunities"] for reason in row["hold_reasons"]},
        )
        self.assertEqual(
            {row["offer"]["source"]["repository"] for row in out["packet"]["opportunities"]},
            {"example/fixture"},
        )


if __name__ == "__main__":
    unittest.main()
