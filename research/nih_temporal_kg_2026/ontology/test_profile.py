from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from temporal_evidence import EvidenceEvent, Fact, TemporalEvidenceGraph
from ontology import profile


class OntologyProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fact_a = Fact.create(
            subject="gene:TP53",
            predicate="biolink:related_to",
            object="disease:Cancer",
            valid_from="2026-01-01T00:00:00Z",
            valid_to="2026-06-01T00:00:00Z",
            observed_at="2026-01-02T00:00:00Z",
            source_id="source-A",
            source_sha256="a" * 64,
            confidence=0.75,
        )
        self.fact_b = Fact.create(
            subject="gene:TP53",
            predicate="custom:status",
            object="reviewed",
            valid_from="2026-06-01T00:00:00Z",
            valid_to=None,
            observed_at="2026-06-02T00:00:00Z",
            source_id="source-B",
            source_sha256="b" * 64,
            confidence=1.0,
        )
        self.event = EvidenceEvent.create(
            action="supersede",
            target_fact_id=self.fact_a.fact_id,
            replacement_fact_id=self.fact_b.fact_id,
            observed_at="2026-06-03T00:00:00Z",
            source_id="correction-log",
            source_sha256="c" * 64,
        )
        graph = TemporalEvidenceGraph()
        graph.add_fact(self.fact_a)
        graph.add_fact(self.fact_b)
        graph.add_event(self.event)
        self.jsonl = graph.to_jsonl()
        self.nt = profile.export_jsonl_to_ntriples(self.jsonl)

    def assertRejects(self, nt: str) -> None:
        with self.assertRaises(profile.OntologyProfileError):
            profile.import_ntriples_to_jsonl(nt)

    def test_roundtrip_finite_open_and_events(self) -> None:
        self.assertEqual(profile.import_ntriples_to_jsonl(self.nt), self.jsonl)
        self.assertIn(profile.TIME_HAS_END, self.nt)
        self.assertIn(profile.TIME_IN_XSD_DATETIME, self.nt)
        self.assertIn(profile.PROV_WAS_DERIVED_FROM, self.nt)
        self.assertIn(profile.BIOLINK + "related_to", self.nt)
        self.assertIn(profile._predicate_iri("custom:status"), self.nt)
        self.assertIn(profile.P_REPLACEMENT, self.nt)

    def test_export_is_input_order_independent(self) -> None:
        lines = [line for line in self.jsonl.splitlines() if line]
        reversed_jsonl = "\n".join(reversed(lines)) + "\n"
        self.assertEqual(profile.export_jsonl_to_ntriples(reversed_jsonl), self.nt)

    def test_canonical_export_is_sorted_and_absolute(self) -> None:
        lines = self.nt.splitlines()
        self.assertEqual(lines, sorted(lines))
        self.assertTrue(all(line.startswith("<") for line in lines))
        self.assertNotIn("_:", self.nt)

    def test_project_vocabulary_has_no_commons_public_backlink(self) -> None:
        self.assertTrue(profile.PROFILE.startswith("urn:"))
        self.assertNotIn("woahwhattheheck.github.io/commons", self.nt)
        self.assertNotIn("github.com/woahwhattheheck/commons", self.nt)

    def test_duplicate_triple_rejected(self) -> None:
        first = self.nt.splitlines()[0]
        self.assertRejects(self.nt + first + "\n")

    def test_every_single_triple_deletion_fails_closed(self) -> None:
        lines = self.nt.splitlines()
        for index in range(len(lines)):
            with self.subTest(index=index, deleted=lines[index]):
                self.assertRejects("\n".join(lines[:index] + lines[index + 1:]) + "\n")

    def test_blank_node_rejected(self) -> None:
        line = self.nt.splitlines()[0]
        self.assertRejects("_:x " + line.split(" ", 1)[1] + "\n" + self.nt)

    def test_bad_escape_and_surrogate_rejected(self) -> None:
        self.assertRejects(self.nt.replace('"source-A"', '"source\\qA"', 1))
        self.assertRejects(self.nt.replace('"source-A"', '"source\\uD800A"', 1))

    def test_noncanonical_ntriples_lexical_forms_rejected(self) -> None:
        first, rest = self.nt.split("\n", 1)
        self.assertRejects(first.replace(" ", "  ", 1) + "\n" + rest)
        self.assertRejects(first.replace(" ", "\t", 1) + "\n" + rest)
        self.assertRejects(first + " \n" + rest)
        self.assertRejects("\n" + self.nt)
        self.assertRejects(self.nt.replace("\n", "\r\n"))
        self.assertRejects(self.nt.rstrip("\n"))

    def test_raw_control_character_in_iri_rejected(self) -> None:
        self.assertRejects(self.nt.replace("urn:nih-temporal-kg:source:", "urn:nih-temporal-kg:source:\x00", 1))

    def test_conflicting_functional_property_rejected(self) -> None:
        subject = profile._fact_iri(self.fact_a.fact_id)
        extra = profile._triple(subject, profile.P_SUBJECT, profile._obj_literal("different"))
        self.assertRejects(self.nt + extra + "\n")

    def test_unknown_profile_term_rejected(self) -> None:
        self.assertRejects(self.nt.replace(profile.P_SUBJECT, profile.PROFILE + "unknownField", 1))

    def test_noncanonical_datetime_and_decimal_rejected(self) -> None:
        self.assertIn(".000000Z", self.nt)
        self.assertRejects(self.nt.replace(".000000Z", "Z", 1))
        self.assertIn('"0.75"^^<' + profile.XSD_DECIMAL + '>', self.nt)
        self.assertRejects(self.nt.replace('"0.75"^^<' + profile.XSD_DECIMAL + '>', '"0.750"^^<' + profile.XSD_DECIMAL + '>', 1))

    def test_fact_digest_drift_rejected(self) -> None:
        old = profile._triple(
            profile._fact_iri(self.fact_a.fact_id),
            profile.P_FACT_ID,
            profile._obj_literal(self.fact_a.fact_id),
        )
        changed_id = "d" * 64
        new = profile._triple(
            profile._fact_iri(self.fact_a.fact_id),
            profile.P_FACT_ID,
            profile._obj_literal(changed_id),
        )
        self.assertIn(old, self.nt)
        self.assertRejects(self.nt.replace(old, new, 1))

    def test_source_alias_transplant_rejected(self) -> None:
        source = profile._source_iri(self.fact_a.source_id, self.fact_a.source_sha256)
        assertion = profile._triple(
            profile._fact_iri(self.fact_a.fact_id),
            profile.PROV_WAS_DERIVED_FROM,
            profile._obj_iri(source),
        )
        forged = source[:-1] + ("0" if source[-1] != "0" else "1")
        replacement = profile._triple(
            profile._fact_iri(self.fact_a.fact_id),
            profile.PROV_WAS_DERIVED_FROM,
            profile._obj_iri(forged),
        )
        self.assertIn(assertion, self.nt)
        self.assertRejects(self.nt.replace(assertion, replacement, 1))

    def test_interval_endpoint_loss_rejected_by_digest(self) -> None:
        fid = self.fact_a.fact_id
        interval = profile._interval_iri(fid)
        end = profile._instant_iri(fid, "end")
        kept = []
        for line in self.nt.splitlines():
            if line.startswith(f"<{interval}> <{profile.TIME_HAS_END}>"):
                continue
            if line.startswith(f"<{end}> "):
                continue
            kept.append(line)
        self.assertRejects("\n".join(kept) + "\n")

    def test_correction_target_and_replacement_mismatch_rejected(self) -> None:
        event_subject = profile._event_iri(self.event.event_id)
        target_line = profile._triple(
            event_subject, profile.P_TARGET, profile._obj_iri(profile._fact_iri(self.fact_a.fact_id))
        )
        wrong_target = profile._triple(
            event_subject, profile.P_TARGET, profile._obj_iri(profile._fact_iri(self.fact_b.fact_id))
        )
        self.assertIn(target_line, self.nt)
        self.assertRejects(self.nt.replace(target_line, wrong_target, 1))

        replacement_line = profile._triple(
            event_subject, profile.P_REPLACEMENT, profile._obj_iri(profile._fact_iri(self.fact_b.fact_id))
        )
        wrong_replacement = profile._triple(
            event_subject, profile.P_REPLACEMENT, profile._obj_iri(profile._fact_iri(self.fact_a.fact_id))
        )
        self.assertIn(replacement_line, self.nt)
        self.assertRejects(self.nt.replace(replacement_line, wrong_replacement, 1))

    def test_supersede_requires_replacement(self) -> None:
        eid = self.event.event_id
        line = profile._triple(
            profile._event_iri(eid),
            profile.P_REPLACEMENT,
            profile._obj_iri(profile._fact_iri(self.fact_b.fact_id)),
        )
        self.assertIn(line, self.nt)
        self.assertRejects(self.nt.replace(line + "\n", "", 1))

    def test_orphan_resource_rejected(self) -> None:
        orphan = profile._triple("urn:nih-temporal-kg:interval:" + "e" * 64, profile.RDF_TYPE, profile._obj_iri(profile.TIME_INTERVAL))
        self.assertRejects(self.nt + orphan + "\n")

    def test_receipt_rejects_noncanonical_triple_order(self) -> None:
        reordered = "\n".join(reversed(self.nt.splitlines())) + "\n"
        self.assertEqual(profile.import_ntriples_to_jsonl(reordered), self.jsonl)
        with self.assertRaises(profile.OntologyProfileError):
            profile.build_conformance_receipt(self.jsonl, reordered)
        canonical = profile.build_conformance_receipt(self.jsonl, self.nt)
        self.assertFalse(profile.verify_conformance_receipt(canonical, self.jsonl, reordered))

    def test_parent_implementation_path_transplant_rejected(self) -> None:
        original = profile._temporal_evidence_module.__file__
        try:
            profile._temporal_evidence_module.__file__ = __file__
            with self.assertRaises(profile.OntologyProfileError):
                profile._parent_implementation_sha256()
        finally:
            profile._temporal_evidence_module.__file__ = original

    def test_receipt_binds_exact_bytes_and_semantics(self) -> None:
        receipt = profile.build_conformance_receipt(self.jsonl, self.nt)
        self.assertTrue(receipt["roundtrip_match"])
        self.assertRegex(receipt["parent_temporal_evidence_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["parent_temporal_evidence_sha256"], profile._parent_implementation_sha256())
        self.assertTrue(profile.verify_conformance_receipt(receipt, self.jsonl, self.nt))
        self.assertFalse(profile.verify_conformance_receipt(receipt, self.jsonl + "\n", self.nt))
        tampered = self.nt.replace('"source-A"', '"source-X"', 1)
        self.assertFalse(profile.verify_conformance_receipt(receipt, self.jsonl, tampered))
        mutated = dict(receipt)
        mutated["fact_count"] += 1
        self.assertFalse(profile.verify_conformance_receipt(mutated, self.jsonl, self.nt))


    def test_public_verifier_generation_is_sealed_against_rebinding(self) -> None:
        receipt = profile.build_conformance_receipt(self.jsonl, self.nt)
        saved_verify = profile.verify_conformance_receipt
        saved_build = profile.build_conformance_receipt
        saved_export = profile.export_jsonl_to_ntriples

        names = (
            "build_conformance_receipt",
            "verify_conformance_receipt",
            "_sha256_text",
            "_profile_descriptor_sha256",
            "_implementation_sha256",
            "_parent_implementation_sha256",
            "export_jsonl_to_ntriples",
            "import_ntriples_to_jsonl",
            "_temporal_evidence_module",
            "TemporalEvidenceGraph",
            "json",
            "hashlib",
            "Path",
        )
        originals = {name: getattr(profile, name) for name in names}
        try:
            profile.build_conformance_receipt = lambda *_args, **_kwargs: {"forged": True}
            profile.verify_conformance_receipt = lambda *_args, **_kwargs: True
            profile._sha256_text = lambda *_args, **_kwargs: "0" * 64
            profile._profile_descriptor_sha256 = lambda: "1" * 64
            profile._implementation_sha256 = lambda: "2" * 64
            profile._parent_implementation_sha256 = lambda: "3" * 64
            profile.export_jsonl_to_ntriples = lambda *_args, **_kwargs: "forged\n"
            profile.import_ntriples_to_jsonl = lambda *_args, **_kwargs: self.jsonl
            profile._temporal_evidence_module = object()
            profile.TemporalEvidenceGraph = object
            profile.json = object()
            profile.hashlib = object()
            profile.Path = object

            self.assertEqual(saved_export(self.jsonl), self.nt)
            self.assertEqual(saved_build(self.jsonl, self.nt), receipt)
            self.assertTrue(saved_verify(receipt, self.jsonl, self.nt))
            self.assertFalse(saved_verify(receipt, self.jsonl + "\n", self.nt))
            tampered_nt = self.nt.replace('"source-A"', '"source-X"', 1)
            self.assertFalse(saved_verify(receipt, self.jsonl, tampered_nt))
        finally:
            for name, value in originals.items():
                setattr(profile, name, value)

    def test_retraction_roundtrip(self) -> None:
        graph = TemporalEvidenceGraph()
        graph.add_fact(self.fact_a)
        event = EvidenceEvent.create(
            action="retract",
            target_fact_id=self.fact_a.fact_id,
            observed_at="2026-06-04T00:00:00Z",
            source_id="retraction-log",
            source_sha256="f" * 64,
        )
        graph.add_event(event)
        text = graph.to_jsonl()
        nt = profile.export_jsonl_to_ntriples(text)
        self.assertNotIn(profile.P_REPLACEMENT, "\n".join(line for line in nt.splitlines() if profile._event_iri(event.event_id) in line))
        self.assertEqual(profile.import_ntriples_to_jsonl(nt), text)


if __name__ == "__main__":
    unittest.main()
