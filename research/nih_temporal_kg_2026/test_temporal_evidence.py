import copy
import json
import unittest

from temporal_evidence import (
    EvidenceEvent,
    Fact,
    TemporalEvidenceError,
    TemporalEvidenceGraph,
    canonical_json,
    digest_json,
    strict_json_loads,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def fact(**overrides):
    base = dict(
        subject="A",
        predicate="rel",
        object="B",
        valid_from="2026-01-01T00:00:00Z",
        valid_to="2027-01-01T00:00:00Z",
        observed_at="2026-01-02T00:00:00Z",
        source_id="source-a",
        source_sha256=SHA_A,
        confidence=1.0,
    )
    base.update(overrides)
    return Fact.create(**base)


class FactContractTests(unittest.TestCase):
    def test_fact_id_is_canonical_across_timezone_offsets(self):
        a = fact(observed_at="2026-01-02T00:00:00Z")
        b = fact(observed_at="2026-01-01T19:00:00-05:00")
        self.assertEqual(a.fact_id, b.fact_id)
        self.assertEqual(a, b)

    def test_half_open_validity_interval(self):
        item = fact()
        graph = TemporalEvidenceGraph()
        graph.add_fact(item)
        self.assertEqual(1, len(graph.active_facts(valid_at="2026-01-01T00:00:00Z", known_at="2026-01-03T00:00:00Z")))
        self.assertEqual(0, len(graph.active_facts(valid_at="2027-01-01T00:00:00Z", known_at="2027-01-02T00:00:00Z")))

    def test_open_ended_validity(self):
        graph = TemporalEvidenceGraph()
        graph.add_fact(fact(valid_to=None))
        self.assertEqual(1, len(graph.active_facts(valid_at="2099-01-01T00:00:00Z", known_at="2099-01-01T00:00:00Z")))

    def test_invalid_interval_rejected(self):
        with self.assertRaises(TemporalEvidenceError):
            fact(valid_to="2026-01-01T00:00:00Z")

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(TemporalEvidenceError):
            fact(observed_at="2026-01-02T00:00:00")

    def test_bad_source_digest_rejected(self):
        with self.assertRaises(TemporalEvidenceError):
            fact(source_sha256="abc")

    def test_confidence_must_be_finite_and_bounded(self):
        for bad in (-0.1, 1.1, float("inf"), float("nan"), True):
            with self.subTest(bad=bad):
                with self.assertRaises(TemporalEvidenceError):
                    fact(confidence=bad)

    def test_record_with_tampered_fact_id_rejected(self):
        record = fact().canonical_record()
        record["fact_id"] = SHA_C
        with self.assertRaises(TemporalEvidenceError):
            Fact.from_record(record)


class BitemporalTests(unittest.TestCase):
    def test_future_observation_never_leaks_into_historical_knowledge_query(self):
        graph = TemporalEvidenceGraph()
        graph.add_fact(fact(observed_at="2026-06-01T00:00:00Z"))
        before = graph.active_facts(valid_at="2026-03-01T00:00:00Z", known_at="2026-05-31T23:59:59Z")
        after = graph.active_facts(valid_at="2026-03-01T00:00:00Z", known_at="2026-06-01T00:00:00Z")
        self.assertEqual((), before)
        self.assertEqual(1, len(after))

    def test_late_retraction_changes_only_later_knowledge_state(self):
        graph = TemporalEvidenceGraph()
        target = fact()
        graph.add_fact(target)
        graph.retract(target.fact_id, observed_at="2026-06-01T00:00:00Z", source_id="retract", source_sha256=SHA_B)
        old_view = graph.active_facts(valid_at="2026-03-01T00:00:00Z", known_at="2026-05-01T00:00:00Z")
        new_view = graph.active_facts(valid_at="2026-03-01T00:00:00Z", known_at="2026-07-01T00:00:00Z")
        self.assertEqual([target.fact_id], [f.fact_id for f in old_view])
        self.assertEqual((), new_view)

    def test_event_cannot_predate_target_observation(self):
        graph = TemporalEvidenceGraph()
        target = fact(observed_at="2026-06-01T00:00:00Z")
        graph.add_fact(target)
        with self.assertRaises(TemporalEvidenceError):
            graph.retract(target.fact_id, observed_at="2026-05-01T00:00:00Z", source_id="r", source_sha256=SHA_B)

    def test_supersession_is_append_only_and_knowledge_sensitive(self):
        graph = TemporalEvidenceGraph()
        old = fact(object="old", observed_at="2026-01-02T00:00:00Z")
        new = fact(object="new", observed_at="2026-04-01T00:00:00Z", source_id="source-b", source_sha256=SHA_B)
        graph.add_fact(old)
        graph.add_fact(new)
        graph.supersede(old.fact_id, new.fact_id, observed_at="2026-04-01T00:00:00Z", source_id="sup", source_sha256=SHA_C)
        before = graph.active_facts(valid_at="2026-03-01T00:00:00Z", known_at="2026-03-15T00:00:00Z")
        after = graph.active_facts(valid_at="2026-05-01T00:00:00Z", known_at="2026-05-01T00:00:00Z")
        self.assertEqual(["old"], [f.object for f in before])
        self.assertEqual(["new"], [f.object for f in after])
        self.assertEqual(2, len(graph.facts))
        self.assertEqual(1, len(graph.events))

    def test_supersession_cannot_reference_future_observation(self):
        graph = TemporalEvidenceGraph()
        old = fact(object="old")
        new = fact(object="new", observed_at="2026-07-01T00:00:00Z", source_id="source-b", source_sha256=SHA_B)
        graph.add_fact(old)
        graph.add_fact(new)
        event = EvidenceEvent.create(
            action="supersede", target_fact_id=old.fact_id, replacement_fact_id=new.fact_id,
            observed_at="2026-06-01T00:00:00Z", source_id="sup", source_sha256=SHA_C,
        )
        with self.assertRaises(TemporalEvidenceError):
            graph.add_event(event)

    def test_confidence_filter(self):
        graph = TemporalEvidenceGraph()
        graph.add_fact(fact(object="low", confidence=0.49))
        graph.add_fact(fact(object="high", confidence=0.9, source_id="source-b", source_sha256=SHA_B))
        result = graph.active_facts(valid_at="2026-02-01T00:00:00Z", known_at="2026-02-01T00:00:00Z", min_confidence=0.5)
        self.assertEqual(["high"], [f.object for f in result])


class PathReasoningTests(unittest.TestCase):
    def setUp(self):
        self.graph = TemporalEvidenceGraph()

    def add_edge(self, subject, object, start, end, observed="2026-01-01T00:00:00Z", predicate="leads_to", confidence=1.0, source=SHA_A):
        self.graph.add_fact(fact(
            subject=subject, predicate=predicate, object=object,
            valid_from=start, valid_to=end, observed_at=observed,
            source_id=f"src-{subject}-{object}", source_sha256=source, confidence=confidence,
        ))

    def test_time_respecting_path_advances_monotonically(self):
        self.add_edge("A", "B", "2026-01-01T00:00:00Z", "2026-01-10T00:00:00Z")
        self.add_edge("B", "C", "2026-01-05T00:00:00Z", "2026-01-20T00:00:00Z", source=SHA_B)
        path = self.graph.time_respecting_path(
            "A", "C", earliest="2026-01-02T00:00:00Z", latest="2026-01-15T00:00:00Z",
            known_at="2026-02-01T00:00:00Z",
        )
        self.assertIsNotNone(path)
        self.assertEqual(["B", "C"], [edge.object for edge, _ in path])
        times = [when.isoformat() for _, when in path]
        self.assertEqual("2026-01-02T00:00:00+00:00", times[0])
        self.assertEqual("2026-01-05T00:00:00+00:00", times[1])

    def test_temporally_impossible_reverse_chain_is_rejected(self):
        self.add_edge("A", "B", "2026-01-10T00:00:00Z", "2026-01-20T00:00:00Z")
        self.add_edge("B", "C", "2026-01-01T00:00:00Z", "2026-01-05T00:00:00Z", source=SHA_B)
        path = self.graph.time_respecting_path(
            "A", "C", earliest="2026-01-01T00:00:00Z", latest="2026-01-30T00:00:00Z",
            known_at="2026-02-01T00:00:00Z",
        )
        self.assertIsNone(path)

    def test_future_observed_edge_is_not_available_to_path(self):
        self.add_edge("A", "B", "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z", observed="2026-06-01T00:00:00Z")
        self.assertIsNone(self.graph.time_respecting_path(
            "A", "B", earliest="2026-02-01T00:00:00Z", latest="2026-03-01T00:00:00Z",
            known_at="2026-05-01T00:00:00Z",
        ))

    def test_retracted_edge_is_not_available_to_path_after_retraction_known(self):
        edge = fact(subject="A", predicate="leads_to", object="B", valid_from="2026-01-01T00:00:00Z", valid_to=None)
        self.graph.add_fact(edge)
        self.graph.retract(edge.fact_id, observed_at="2026-04-01T00:00:00Z", source_id="r", source_sha256=SHA_B)
        before = self.graph.time_respecting_path("A", "B", earliest="2026-02-01T00:00:00Z", latest="2026-03-01T00:00:00Z", known_at="2026-03-01T00:00:00Z")
        after = self.graph.time_respecting_path("A", "B", earliest="2026-02-01T00:00:00Z", latest="2026-03-01T00:00:00Z", known_at="2026-05-01T00:00:00Z")
        self.assertIsNotNone(before)
        self.assertIsNone(after)

    def test_predicate_filter_and_max_hops(self):
        self.add_edge("A", "B", "2026-01-01T00:00:00Z", None, predicate="allowed")
        self.add_edge("B", "C", "2026-01-01T00:00:00Z", None, predicate="blocked", source=SHA_B)
        self.assertIsNone(self.graph.time_respecting_path(
            "A", "C", earliest="2026-01-01T00:00:00Z", latest="2026-02-01T00:00:00Z",
            known_at="2026-02-01T00:00:00Z", predicates=["allowed"],
        ))
        self.assertIsNone(self.graph.time_respecting_path(
            "A", "C", earliest="2026-01-01T00:00:00Z", latest="2026-02-01T00:00:00Z",
            known_at="2026-02-01T00:00:00Z", max_hops=1,
        ))

    def test_zero_hop_identity_path(self):
        path = self.graph.time_respecting_path(
            "A", "A", earliest="2026-01-01T00:00:00Z", latest="2026-01-02T00:00:00Z",
            known_at="2026-01-02T00:00:00Z",
        )
        self.assertEqual((), path)


class ReceiptTests(unittest.TestCase):
    def test_snapshot_receipt_is_deterministic_across_insertion_order(self):
        a = fact(object="B")
        b = fact(object="C", source_id="source-b", source_sha256=SHA_B)
        left = TemporalEvidenceGraph()
        right = TemporalEvidenceGraph()
        left.add_fact(a)
        left.add_fact(b)
        right.add_fact(b)
        right.add_fact(a)
        one = left.snapshot_receipt(valid_at="2026-02-01T00:00:00Z", known_at="2026-02-01T00:00:00Z")
        two = right.snapshot_receipt(valid_at="2026-02-01T00:00:00Z", known_at="2026-02-01T00:00:00Z")
        self.assertEqual(one, two)
        self.assertTrue(TemporalEvidenceGraph.verify_snapshot_receipt(one))

    def test_snapshot_receipt_tamper_is_detected(self):
        graph = TemporalEvidenceGraph()
        graph.add_fact(fact())
        receipt = graph.snapshot_receipt(valid_at="2026-02-01T00:00:00Z", known_at="2026-02-01T00:00:00Z")
        tampered = copy.deepcopy(receipt)
        tampered["facts"][0]["object"] = "EVIL"
        self.assertFalse(TemporalEvidenceGraph.verify_snapshot_receipt(tampered))

    def test_path_receipt_tamper_and_nonmonotonic_hop_are_detected(self):
        graph = TemporalEvidenceGraph()
        graph.add_fact(fact(subject="A", object="B", valid_to=None))
        graph.add_fact(fact(subject="B", object="C", valid_from="2026-02-01T00:00:00Z", valid_to=None, source_id="b", source_sha256=SHA_B))
        receipt = graph.path_receipt(
            "A", "C", earliest="2026-01-15T00:00:00Z", latest="2026-03-01T00:00:00Z",
            known_at="2026-03-01T00:00:00Z",
        )
        self.assertTrue(TemporalEvidenceGraph.verify_path_receipt(receipt))
        tampered = copy.deepcopy(receipt)
        tampered["hops"][1]["hop_time"] = "2026-01-01T00:00:00.000000Z"
        tampered_payload = {k: v for k, v in tampered.items() if k != "receipt_sha256"}
        tampered["receipt_sha256"] = digest_json(tampered_payload)
        self.assertFalse(TemporalEvidenceGraph.verify_path_receipt(tampered))

    def test_failed_path_receipt_verifies_as_explicit_negative_result(self):
        graph = TemporalEvidenceGraph()
        receipt = graph.path_receipt(
            "A", "Z", earliest="2026-01-01T00:00:00Z", latest="2026-02-01T00:00:00Z",
            known_at="2026-02-01T00:00:00Z",
        )
        self.assertFalse(receipt["found"])
        self.assertIsNone(receipt["hops"])
        self.assertTrue(TemporalEvidenceGraph.verify_path_receipt(receipt))


class StrictIOTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(TemporalEvidenceError):
            strict_json_loads('{"kind":"fact","kind":"event"}')

    def test_nonfinite_json_numbers_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                with self.assertRaises(TemporalEvidenceError):
                    strict_json_loads('{"x":' + value + '}')

    def test_jsonl_roundtrip_preserves_graph_and_events(self):
        graph = TemporalEvidenceGraph()
        old = fact(object="old")
        new = fact(object="new", observed_at="2026-03-01T00:00:00Z", source_id="b", source_sha256=SHA_B)
        graph.add_fact(old)
        graph.add_fact(new)
        graph.supersede(old.fact_id, new.fact_id, observed_at="2026-03-02T00:00:00Z", source_id="sup", source_sha256=SHA_C)
        encoded = graph.to_jsonl()
        decoded = TemporalEvidenceGraph.from_jsonl(encoded)
        self.assertEqual(graph.facts, decoded.facts)
        self.assertEqual(graph.events, decoded.events)
        self.assertEqual(encoded, decoded.to_jsonl())

    def test_jsonl_rejects_unknown_fields(self):
        record = {"kind": "fact", **fact().canonical_record(), "surprise": 1}
        with self.assertRaises(TemporalEvidenceError):
            TemporalEvidenceGraph.from_jsonl(json.dumps(record))

    def test_event_before_fact_in_jsonl_is_allowed_but_still_validated(self):
        graph = TemporalEvidenceGraph()
        target = fact()
        graph.add_fact(target)
        event = EvidenceEvent.create(
            action="retract", target_fact_id=target.fact_id,
            observed_at="2026-03-01T00:00:00Z", source_id="r", source_sha256=SHA_B,
        )
        lines = [
            canonical_json({"kind": "event", **event.canonical_record()}),
            canonical_json({"kind": "fact", **target.canonical_record()}),
        ]
        decoded = TemporalEvidenceGraph.from_jsonl("\n".join(lines))
        self.assertEqual(1, len(decoded.events))
        self.assertEqual(0, len(decoded.active_facts(valid_at="2026-02-01T00:00:00Z", known_at="2026-04-01T00:00:00Z")))

    def test_canonical_json_is_stable(self):
        one = canonical_json({"b": 2, "a": [3, 1]})
        two = canonical_json({"a": [3, 1], "b": 2})
        self.assertEqual('{"a":[3,1],"b":2}', one)
        self.assertEqual(one, two)
        self.assertEqual(digest_json({"a": 1}), digest_json({"a": 1}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
