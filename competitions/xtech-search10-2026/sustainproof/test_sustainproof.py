from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from sustainproof import ContractError, VERSION, compile_handoff, event_sha256, parse_json_strict

AS_OF = datetime(2026, 9, 14, 4, 0, tzinfo=timezone.utc)
H = lambda ch: ch * 64


def event(event_id: str, *, stream="wo", subject="WO-1", generation=1, previous=None,
          kind="WORK_ORDER", state="OPEN", quantity=0, part=None,
          observed="2026-09-14T03:00:00Z", evidence=None):
    return {
        "eventId": event_id,
        "streamRef": stream,
        "subjectRef": subject,
        "generation": generation,
        "previousEventSha256": previous,
        "kind": kind,
        "state": state,
        "quantity": quantity,
        "partRef": part,
        "observedAt": observed,
        "evidenceSha256": evidence or H("a"),
    }


def doc(*events):
    return {"version": VERSION, "maxAgeHours": 24, "events": list(events)}


class SustainProofTests(unittest.TestCase):
    def test_waiting_part_available_is_ready(self):
        w = event("w1", state="WAITING_PART", part="P-1")
        p = event("p1", stream="parts-a", subject="P-1", kind="PARTS", state="AVAILABLE", quantity=2, evidence=H("b"))
        out = compile_handoff(doc(w, p), as_of=AS_OF)
        self.assertEqual(out["overallState"], "READY_FOR_HUMAN_HANDOFF")
        self.assertEqual(out["handoffs"][0]["state"], "READY_FOR_HUMAN_HANDOFF")
        self.assertFalse(any(out["authority"].values()))
        self.assertEqual(out["mode"], "HISTORICAL_INTEGRITY_ONLY")

    def test_missing_part_holds(self):
        out = compile_handoff(doc(event("w1", state="WAITING_PART", part="P-1")), as_of=AS_OF)
        self.assertEqual(out["handoffs"][0]["reasons"], ["PART_STATE_MISSING"])
        self.assertEqual(out["overallState"], "HOLD_FOR_HUMAN_REVIEW")

    def test_reserved_part_holds(self):
        w = event("w1", state="WAITING_PART", part="P-1")
        p = event("p1", stream="parts", subject="P-1", kind="PARTS", state="RESERVED", quantity=1)
        out = compile_handoff(doc(w, p), as_of=AS_OF)
        self.assertIn("PART_NOT_AVAILABLE", out["handoffs"][0]["reasons"])

    def test_inspection_hold_blocks_handoff(self):
        w = event("w1", state="READY_FOR_MAINTENANCE")
        i = event("i1", stream="inspection", subject="WO-1", kind="INSPECTION", state="HOLD", evidence=H("c"))
        out = compile_handoff(doc(w, i), as_of=AS_OF)
        self.assertIn("INSPECTION_HOLD", out["handoffs"][0]["reasons"])

    def test_same_work_order_subject_across_streams_is_global_hold(self):
        w1 = event("w1", stream="site-a", subject="WO-1", state="OPEN")
        w2 = event("w2", stream="site-b", subject="WO-1", state="OPEN", evidence=H("b"))
        out = compile_handoff(doc(w1, w2), as_of=AS_OF)
        self.assertIn("WORK_ORDER_SUBJECT_AMBIGUOUS:WO-1", out["chainReasons"])
        self.assertEqual(out["overallState"], "HOLD_FOR_HUMAN_REVIEW")

    def test_multiple_part_authorities_hold_instead_of_sort_selecting(self):
        w = event("w1", state="WAITING_PART", part="P-1")
        p1 = event("p1", stream="parts-a", subject="P-1", kind="PARTS", state="AVAILABLE", quantity=1)
        p2 = event("p2", stream="parts-b", subject="P-1", kind="PARTS", state="AVAILABLE", quantity=9, evidence=H("b"))
        out = compile_handoff(doc(w, p1, p2), as_of=AS_OF)
        self.assertIn("PART_AUTHORITY_AMBIGUOUS", out["handoffs"][0]["reasons"])

    def test_multiple_inspection_authorities_hold(self):
        w = event("w1", state="READY_FOR_MAINTENANCE")
        i1 = event("i1", stream="inspection-a", subject="WO-1", kind="INSPECTION", state="PASS")
        i2 = event("i2", stream="inspection-b", subject="WO-1", kind="INSPECTION", state="PASS", evidence=H("b"))
        out = compile_handoff(doc(w, i1, i2), as_of=AS_OF)
        self.assertIn("INSPECTION_AUTHORITY_AMBIGUOUS", out["handoffs"][0]["reasons"])

    def test_exact_duplicate_event_id_collapses(self):
        w = event("w1")
        one = compile_handoff(doc(w), as_of=AS_OF)
        two = compile_handoff(doc(w, deepcopy(w)), as_of=AS_OF)
        self.assertEqual(one["handoffs"], two["handoffs"])

    def test_changed_event_id_fails_closed(self):
        a = event("w1")
        b = deepcopy(a)
        b["state"] = "CLOSED"
        with self.assertRaisesRegex(ContractError, "EVENT_ID_DRIFT"):
            compile_handoff(doc(a, b), as_of=AS_OF)

    def test_generation_chain_and_input_order_are_deterministic(self):
        a = event("w1", state="OPEN")
        b = event("w2", generation=2, previous=event_sha256(a), state="READY_FOR_MAINTENANCE", observed="2026-09-14T03:10:00Z", evidence=H("b"))
        x = compile_handoff(doc(a, b), as_of=AS_OF)
        y = compile_handoff(doc(b, a), as_of=AS_OF)
        self.assertEqual(x, y)
        self.assertEqual(x["handoffs"][0]["sourceGeneration"], 2)

    def test_generation_gap_is_global_hold(self):
        b = event("w2", generation=2, previous=H("d"), state="READY_FOR_MAINTENANCE")
        out = compile_handoff(doc(b), as_of=AS_OF)
        self.assertIn("GENERATION_GAP:wo:WO-1", out["chainReasons"])
        self.assertIn("NO_WORK_ORDERS", out["chainReasons"])

    def test_generation_fork_is_global_hold(self):
        a = event("w1")
        b = event("w2", state="CLOSED", evidence=H("b"))
        out = compile_handoff(doc(a, b), as_of=AS_OF)
        self.assertIn("GENERATION_FORK:wo:WO-1:1", out["chainReasons"])

    def test_bad_previous_digest_holds(self):
        a = event("w1")
        b = event("w2", generation=2, previous=H("f"), observed="2026-09-14T03:05:00Z")
        out = compile_handoff(doc(a, b), as_of=AS_OF)
        self.assertIn("CHAIN_LINK_INVALID:wo:WO-1:2", out["chainReasons"])

    def test_chronology_rewind_holds(self):
        a = event("w1", observed="2026-09-14T03:10:00Z")
        b = event("w2", generation=2, previous=event_sha256(a), observed="2026-09-14T03:00:00Z")
        out = compile_handoff(doc(a, b), as_of=AS_OF)
        self.assertIn("CHRONOLOGY_REWIND:wo:WO-1:2", out["chainReasons"])

    def test_future_event_holds(self):
        out = compile_handoff(doc(event("w1", observed="2026-09-14T04:01:00Z")), as_of=AS_OF)
        self.assertIn("FUTURE_EVENT:wo:WO-1:1", out["chainReasons"])

    def test_stale_latest_chain_holds(self):
        out = compile_handoff(doc(event("w1", observed="2026-09-12T00:00:00Z")), as_of=AS_OF)
        self.assertIn("STALE_CHAIN:wo:WO-1", out["chainReasons"])

    def test_work_order_part_ref_only_when_waiting(self):
        with self.assertRaisesRegex(ContractError, "PART_REF_ONLY_WHEN_WAITING_PART"):
            compile_handoff(doc(event("w1", state="OPEN", part="P-1")), as_of=AS_OF)

    def test_part_state_quantity_semantics_are_exact(self):
        with self.assertRaisesRegex(ContractError, "PART_QUANTITY_STATE_MISMATCH"):
            compile_handoff(doc(event("p1", stream="parts", subject="P-1", kind="PARTS", state="AVAILABLE", quantity=0)), as_of=AS_OF)
        with self.assertRaisesRegex(ContractError, "PART_QUANTITY_STATE_MISMATCH"):
            compile_handoff(doc(event("p2", stream="parts", subject="P-2", kind="PARTS", state="OUT_OF_STOCK", quantity=1)), as_of=AS_OF)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite(self):
        with self.assertRaisesRegex(ContractError, "JSON_DUPLICATE_KEY"):
            parse_json_strict('{"a":1,"a":2}')
        with self.assertRaisesRegex(ContractError, "JSON_NONFINITE"):
            parse_json_strict('{"a":NaN}')


if __name__ == "__main__":
    unittest.main()
