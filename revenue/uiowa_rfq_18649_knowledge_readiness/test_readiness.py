"""Executable acceptance for UIOWA-073; no network or external dependencies."""
import contextlib
import copy
import csv
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import readiness as r
from demo import snapshots, run


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.before, self.after = snapshots()

    def query(self, report, query_id):
        return next(q for q in report["queries"] if q["query_id"] == query_id)

    def test_before_after_expected_fact_counts(self):
        before, after = r.assess(self.before), r.assess(self.after)
        self.assertEqual([q["supported_facts"]["numerator"] for q in before["queries"]], [0, 0, 0, 1, 1])
        self.assertEqual([q["supported_facts"]["numerator"] for q in after["queries"]], [1, 2, 1, 2, 1])
        self.assertEqual(len(before["conflicts"]), 1)
        self.assertEqual(after["conflicts"], [])

    def test_conflict_outside_top_k_is_not_hidden(self):
        packet = copy.deepcopy(self.before)
        packet["queries"][0]["top_k"] = 1
        result = r.assess(packet)["queries"][0]
        self.assertEqual(len(result["retrieved"]), 1)
        self.assertEqual(result["required_facts"][0]["state"], "conflicting")
        self.assertEqual(len(result["required_facts"][0]["corpus_support"]["sources"]), 2)

    def test_freshness_does_not_adjudicate_contradictions(self):
        self.before["documents"][1]["reviewed_on"] = "2020-01-01"
        self.assertEqual(r.assess(self.before)["queries"][0]["required_facts"][0]["state"], "conflicting")

    def test_explicit_supersession_resolves_not_latest_date(self):
        self.before["documents"][1]["status"] = "superseded"
        self.before["queries"][0]["relevant_document_ids"] = ["ESS-RETRY"]
        result = r.assess(self.before)["queries"][0]
        self.assertEqual(result["required_facts"][0]["state"], "supported_by_current_record")
        self.assertNotIn("ESS-OLD", [d["document_id"] for d in result["retrieved"]])

    def test_retrieval_vocabulary_repair_is_measured(self):
        before = self.query(r.assess(self.before), "Q-RIS-VOCABULARY")
        after = self.query(r.assess(self.after), "Q-RIS-VOCABULARY")
        self.assertEqual(before["retrieved"], [])
        self.assertEqual(before["required_facts"][0]["state"], "retrieval_gap")
        self.assertEqual(before["retrieval_metrics"]["precision"], {"numerator": 0, "denominator": 0, "value": None})
        self.assertEqual(before["retrieval_metrics"]["recall"]["value"], 0.0)
        self.assertEqual(after["retrieved"][0]["document_id"], "RIS-IMPORT")
        self.assertEqual(after["retrieval_metrics"]["recall"]["value"], 1.0)

    def test_missing_fact_is_not_retrieval_gap(self):
        q = self.query(r.assess(self.before), "Q-IAM-MISSING")
        self.assertEqual(q["required_facts"][1]["state"], "missing")
        self.assertEqual(q["required_facts"][1]["corpus_support"]["sources"], [])

    def test_unknown_judgments_not_perfect_scores(self):
        q = self.query(r.assess(self.after), "Q-IAM-UNKNOWN-JUDGMENT")
        self.assertEqual(q["retrieval_metrics"], {"judgment_status": "unknown", "precision": None, "recall": None})

    def test_empty_gold_has_undefined_recall(self):
        self.after["queries"][0]["relevant_document_ids"] = []
        m = r.assess(self.after)["queries"][0]["retrieval_metrics"]
        self.assertEqual(m["precision"]["value"], 0.0)
        self.assertIsNone(m["recall"]["value"])

    def test_source_metadata_missing_is_explicit(self):
        report = r.assess(self.before)
        health = next(d for d in report["sources"] if d["document_id"] == "RIS-BUDGET")
        self.assertEqual(set(health["issues"]), {"unknown_owner", "unknown_source_locator", "unknown_access_semantics", "unknown_freshness"})
        q = self.query(report, "Q-RIS-METADATA")
        self.assertEqual(q["required_facts"][0]["state"], "support_needs_preparation")

    def test_access_metadata_does_not_filter_retrieval(self):
        packet = copy.deepcopy(self.after)
        docs = packet["documents"]
        original = r.retrieve(docs, packet["queries"][0])
        docs[0]["access_semantics"] = None
        self.assertEqual(r.retrieve(docs, packet["queries"][0]), original)
        self.assertIn("unknown_access_semantics", r.assess(packet)["sources"][0]["issues"])

    def test_review_boundary_dates_and_unknowns(self):
        d = self.after["documents"][0]
        d["reviewed_on"] = "2026-08-20"
        self.assertEqual(r.source_health(d, date(2026, 9, 19))["freshness"], "current_within_declared_interval")
        d["reviewed_on"] = "2026-08-19"
        self.assertEqual(r.source_health(d, date(2026, 9, 19))["freshness"], "stale")
        d["reviewed_on"] = "2026-09-20"
        self.assertEqual(r.source_health(d, date(2026, 9, 19))["freshness"], "future_review_date")
        d["reviewed_on"] = "2026-09-19"
        self.assertEqual(r.source_health(d, date(2026, 9, 19))["freshness"], "review_after_capture")
        d["review_interval_days"] = None
        self.assertEqual(r.source_health(d, date(2026, 9, 19))["freshness"], "unknown")

    def test_future_capture_cannot_count_current_support(self):
        self.after["documents"][0]["captured_on"] = "2026-09-20"
        q = r.assess(self.after)["queries"][0]
        self.assertEqual(q["required_facts"][0]["state"], "support_needs_preparation")

    def test_retired_documents_not_preparation_work(self):
        subjects = [i["subject"] for i in r.assess(self.after)["preparation_backlog"]]
        self.assertNotIn("ESS-OLD", subjects)
        self.assertNotIn("IAM-ARCHIVE", subjects)

    def test_group_and_scope_do_not_collide(self):
        self.before["documents"][1]["group"] = "RIS"
        self.before["queries"][0]["relevant_document_ids"] = ["ESS-RETRY"]
        self.assertEqual(r.assess(self.before)["conflicts"], [])
        before, _ = snapshots()
        before["documents"][1]["assertions"][0]["scope"] = "registration-different-service"
        self.assertEqual(r.assess(before)["conflicts"], [])

    def test_digest_mismatch_rejected(self):
        self.before["documents"][0]["content"] += "changed"
        with self.assertRaisesRegex(r.DataError, "digest mismatch"):
            r.assess(self.before)

    def test_quote_and_line_locator_binding(self):
        self.before["documents"][0]["assertions"][0]["quote"] = "Invented unsupported text"
        with self.assertRaisesRegex(r.DataError, "quote does not match"):
            r.assess(self.before)
        before, _ = snapshots()
        before["documents"][0]["assertions"][0]["end_line"] = 999
        with self.assertRaisesRegex(r.DataError, "outside source"):
            r.assess(before)

    def test_duplicate_document_query_and_relevance_ids(self):
        for key in ("documents", "queries"):
            packet = copy.deepcopy(self.before)
            packet[key].append(copy.deepcopy(packet[key][0]))
            with self.subTest(key=key), self.assertRaises(r.DataError):
                r.assess(packet)
        self.before["queries"][0]["relevant_document_ids"].append("ESS-RETRY")
        with self.assertRaisesRegex(r.DataError, "duplicate relevance"):
            r.assess(self.before)

    def test_gold_scope_and_existence_checked(self):
        for value in (["MISSING"], ["IAM-RECOVERY"], ["IAM-ARCHIVE"]):
            self.before["queries"][0]["relevant_document_ids"] = value
            with self.subTest(value=value), self.assertRaises(r.DataError):
                r.assess(self.before)

    def test_bad_shapes_and_booleans_not_integer(self):
        for field, value in (("group", []), ("status", {}), ("review_interval_days", True), ("reviewed_on", "20260919")):
            packet = copy.deepcopy(self.before)
            packet["documents"][0][field] = value
            with self.subTest(field=field), self.assertRaises(r.DataError):
                r.assess(packet)
        self.before["queries"][0]["top_k"] = True
        with self.assertRaises(r.DataError):
            r.assess(self.before)

    def test_duplicate_keys_nonfinite_invalid_json(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "packet.json"
            for value in ('{"id":1,"id":2}', '{"id":NaN}', '{"id":Infinity}', '[] garbage'):
                p.write_text(value)
                with self.subTest(value=value), self.assertRaises(r.DataError):
                    r.load(p)

    def test_unicode_and_tie_order(self):
        self.assertEqual(r.tokens("CAFÉ ＲＥＴＲＹ retry"), ["café", "retry", "retry"])
        doc = copy.deepcopy(self.after["documents"][0])
        duplicate = copy.deepcopy(doc)
        duplicate["id"] = "AAA"
        hits = r.retrieve([doc, duplicate], self.after["queries"][0])
        self.assertEqual([d["document_id"] for d in hits], ["AAA", "ESS-RETRY"])

    def test_metric_denominators_are_unique_returned_documents(self):
        q = r.assess(self.before)["queries"][0]
        ids = [d["document_id"] for d in q["retrieved"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(q["retrieval_metrics"]["precision"]["denominator"], len(ids))
        self.assertEqual(q["retrieval_metrics"]["recall"]["denominator"], 2)

    def test_inputs_not_mutated_and_results_deterministic(self):
        original = copy.deepcopy(self.before)
        a = r.assess(self.before)
        b = r.assess(self.before)
        self.assertEqual(a, b)
        self.assertEqual(self.before, original)
        self.assertEqual(r.render(a), r.render(b))

    def test_csv_display_encoding_preserves_canonical_json(self):
        for value in ("=SUM(1,2)", "  +cmd", "@name", "-123", "\ttext"):
            self.assertEqual(r.csv_text(value), "'" + value)
        self.assertEqual(r.csv_text(None), "UNKNOWN")
        report = r.assess(self.before)
        report["preparation_backlog"][0]["owner"] = "=synthetic formula-shaped text"
        with tempfile.TemporaryDirectory() as td:
            r.write_outputs(report, Path(td))
            reread = r.load(Path(td) / "report.json")
            self.assertEqual(reread, report)
            with (Path(td) / "preparation.csv").open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(rows[0]["owner"].startswith("'="))

    def test_end_to_end_portable_rehearsal_and_cli(self):
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(io.StringIO()):
            base = Path(td)
            run(base / "demo")
            for side in ("before", "after"):
                packet = r.load(base / "demo" / side / "collection.json")
                for doc in packet["documents"]:
                    actual = (base / "demo" / side / "documents" / f"{doc['id']}.md").read_text()
                    self.assertEqual(r.digest(actual), doc["sha256"])
                rc = r.main([str(base / "demo" / side / "collection.json"), "--out", str(base / side)])
                self.assertEqual(rc, 0)
                self.assertEqual((base / side / "report.json").read_bytes(), (base / "demo" / side / "report.json").read_bytes())
            self.assertTrue((base / "demo" / "comparison.md").exists())

    def test_empty_token_document_does_not_break_retrieval(self):
        doc = copy.deepcopy(self.after["documents"][0])
        doc.update(id="ESS-EMPTY-TOKENS", title="the and", content="--- !!!\n", assertions=[])
        doc["sha256"] = r.digest(doc["content"])
        self.after["documents"].append(doc)
        result = r.assess(self.after)["queries"][0]
        self.assertNotIn(doc["id"], [x["document_id"] for x in result["retrieved"]])
        self.assertEqual(result["supported_facts"]["numerator"], 1)

    def test_missing_relevance_key_is_unknown_not_a_crash(self):
        del self.before["queries"][0]["relevant_document_ids"]
        result = r.assess(self.before)["queries"][0]["retrieval_metrics"]
        self.assertEqual(result["judgment_status"], "unknown")
        self.assertIsNone(result["precision"])

    def test_overflowing_json_number_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "number.json"
            path.write_text('{"value":1e400}')
            with self.assertRaises(r.DataError):
                r.load(path)

    def test_unpaired_unicode_surrogate_is_a_contract_error(self):
        self.before["documents"][0]["title"] = "\ud800"
        with self.assertRaises(r.DataError):
            r.assess(self.before)

    def test_bad_input_cli_returns_two_without_report(self):
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stderr(io.StringIO()):
            p = Path(td) / "bad.json"
            p.write_text("{}")
            self.assertEqual(r.main([str(p), "--out", str(Path(td) / "out")]), 2)
            self.assertFalse((Path(td) / "out").exists())


if __name__ == "__main__":
    unittest.main()
