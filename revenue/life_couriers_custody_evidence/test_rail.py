from __future__ import annotations

import copy
import json
import unittest

from acceptance import build_shipment, run_acceptance
from rail import EvidenceRail, verify_receipt


class EvidenceRailTests(unittest.TestCase):
    def rail_for(self, events):
        rail = EvidenceRail()
        rail.ingest_many(events)
        return rail

    def test_clean_shipment_ready(self):
        rail = self.rail_for(build_shipment("S1", 0))
        state = rail.shipment_state("S1")
        self.assertEqual("READY_FOR_HANDOFF", state.status)
        self.assertEqual(3, state.leg_count)
        self.assertEqual((), state.holds)

    def test_exact_retry_collapses(self):
        events = build_shipment("S2", 1000)
        rail = EvidenceRail()
        results = rail.ingest_many(events)
        self.assertEqual(1, sum(result.status == "DUPLICATE" for result in results))
        self.assertEqual("READY_FOR_HANDOFF", rail.shipment_state("S2").status)

    def test_same_event_id_changed_payload_holds_and_is_order_invariant(self):
        events = build_shipment("S3", 2000)
        original = next(event for event in events if event["event_id"].endswith("L1:temp1"))
        changed = copy.deepcopy(original)
        changed["payload"]["temp_c"] = 6.25
        a = self.rail_for(events + [changed])
        b = self.rail_for([changed] + list(reversed(events)))
        self.assertEqual("HOLD", a.shipment_state("S3").status)
        self.assertTrue(any(h["code"] == "EVENT_ID_CONFLICT" for h in a.shipment_state("S3").holds))
        self.assertEqual(a.manifest_bytes(), b.manifest_bytes())
        self.assertEqual(a.receipt(), b.receipt())

    def test_input_order_does_not_change_manifest(self):
        events = build_shipment("S4", 3000, reconciled_unknown=True)
        a = self.rail_for(events)
        b = self.rail_for(reversed(events))
        self.assertEqual(a.manifest_bytes(), b.manifest_bytes())
        self.assertEqual("READY_FOR_HANDOFF", b.shipment_state("S4").status)

    def test_source_lineage_ambiguity_holds(self):
        rail = self.rail_for(build_shipment("S5", 4000, fault="source_ambiguity"))
        state = rail.shipment_state("S5")
        self.assertEqual("HOLD", state.status)
        self.assertTrue(any(h["code"] == "SOURCE_LINEAGE_AMBIGUOUS" for h in state.holds))

    def test_missing_temperature_holds(self):
        rail = self.rail_for(build_shipment("S6", 5000, fault="missing_temp"))
        state = rail.shipment_state("S6")
        self.assertTrue(any(h["code"] == "MISSING_TEMPERATURE_EVIDENCE" for h in state.holds))

    def test_temperature_excursion_holds(self):
        rail = self.rail_for(build_shipment("S7", 6000, fault="excursion"))
        state = rail.shipment_state("S7")
        self.assertTrue(any(h["code"] == "TEMPERATURE_EXCURSION" for h in state.holds))

    def test_unknown_effect_requires_reconciliation(self):
        unresolved = self.rail_for(build_shipment("S8", 7000, fault="unknown_effect"))
        self.assertIn("FX-1", unresolved.shipment_state("S8").unresolved_effects)
        self.assertEqual("HOLD", unresolved.shipment_state("S8").status)
        resolved = self.rail_for(build_shipment("S9", 8000, reconciled_unknown=True))
        self.assertEqual((), resolved.shipment_state("S9").unresolved_effects)
        self.assertEqual("READY_FOR_HANDOFF", resolved.shipment_state("S9").status)

    def test_open_exception_holds_close(self):
        rail = self.rail_for(build_shipment("S10", 9000, fault="open_exception"))
        state = rail.shipment_state("S10")
        self.assertIn("EX-1", state.unresolved_exceptions)
        self.assertTrue(any(h["code"] == "UNRESOLVED_EXCEPTION" for h in state.holds))

    def test_wrong_custody_party_holds(self):
        events = build_shipment("S11", 10000)
        event = next(event for event in events if event["event_id"].endswith("L2:receive"))
        event["payload"]["party"] = "wrong-party"
        rail = self.rail_for(events)
        self.assertTrue(any(h["code"] == "RECEIPT_PARTY_MISMATCH" for h in rail.shipment_state("S11").holds))

    def test_evidence_after_close_holds(self):
        events = build_shipment("S12", 11000)
        close = next(event for event in events if event["event_type"] == "shipment_closed")
        close["occurred_at"] = 11050
        rail = self.rail_for(events)
        self.assertTrue(any(h["code"] == "EVIDENCE_AFTER_CLOSE" for h in rail.shipment_state("S12").holds))

    def test_receipt_verifies_and_tamper_fails(self):
        rail = self.rail_for(build_shipment("S13", 12000))
        manifest = rail.manifest_bytes()
        receipt = rail.receipt()
        self.assertTrue(verify_receipt(manifest, receipt))
        parsed = json.loads(manifest)
        parsed["shipments"][0]["status"] = "HOLD"
        tampered = json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode()
        self.assertFalse(verify_receipt(tampered, receipt))

    def test_payload_schema_is_fail_closed(self):
        event = build_shipment("S14", 13000)[0]
        event["payload"]["undeclared"] = True
        with self.assertRaises(ValueError):
            EvidenceRail().ingest(event)

    def test_nonfinite_temperature_rejected(self):
        event = next(event for event in build_shipment("S15", 14000) if event["event_type"] == "temperature_sample")
        event["payload"]["temp_c"] = float("nan")
        with self.assertRaises(ValueError):
            EvidenceRail().ingest(event)

    def test_acceptance_fixture(self):
        metrics = run_acceptance()
        self.assertEqual(120, metrics["shipments"])
        self.assertEqual(100, metrics["ready"])
        self.assertEqual(20, metrics["hold"])
        self.assertEqual(120, metrics["duplicate_retries"])
        self.assertTrue(metrics["receipt_valid"])


if __name__ == "__main__":
    unittest.main()
