from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import acqatlas

FIXTURE = ROOT / "fixtures" / "synthetic_procurements.jsonl"

class AcqAtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = acqatlas.load_documents(FIXTURE)

    def test_tokenization_is_normalized(self):
        self.assertEqual(acqatlas.tokenize("The ZERO_TRUST services for 123.5 endpoints"), ["zero-trust", "<num>", "endpoints"])

    def test_duplicate_doc_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate doc_id"):
            acqatlas.analyze([self.docs[0], self.docs[0]])

    def test_deterministic_analysis(self):
        a = acqatlas.analyze(self.docs)
        b = acqatlas.analyze(list(reversed(self.docs)))
        self.assertEqual(a["analysis_sha256"], b["analysis_sha256"])
        self.assertEqual(a, b)
        acqatlas.verify_analysis(a)

    def test_analysis_tamper_rejected(self):
        value = acqatlas.analyze(self.docs)
        value["document_count"] += 1
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            acqatlas.verify_analysis(value)

    def test_clusters_separate_major_domains(self):
        value = acqatlas.analyze(self.docs)
        actual = {frozenset(c["members"]) for c in value["clusters"]}
        expected = {
            frozenset(f"{domain}-{i:02d}" for i in range(1, 5))
            for domain in ("cloud", "cyber", "data", "flight", "training")
        }
        # This catches both under-clustering (the original cloud singleton bug)
        # and cross-domain graph bridges.
        self.assertEqual(actual, expected)

    def test_fixture_similarity_has_threshold_margin(self):
        _vectors, similarities, _counts = acqatlas.build_similarity(self.docs)
        by_id = {d.doc_id: d for d in self.docs}
        cross = []
        for (a, b), score in similarities.items():
            if a.split("-", 1)[0] != b.split("-", 1)[0]:
                cross.append(score)
        self.assertLess(max(cross), 0.10)
        # The calibrated 0.18 threshold therefore has a substantial fixture
        # margin over the strongest cross-domain edge (~0.091).
        self.assertGreater(0.18, max(cross) * 1.9)

    def test_leave_one_out_has_useful_signal(self):
        value = acqatlas.validate_leave_one_out(self.docs, top_k=5)
        self.assertGreaterEqual(value["top1_accuracy"], 0.75)
        self.assertGreaterEqual(value["top5_recall"], 0.95)

    def test_benchmark_proves_repeatability(self):
        receipt = acqatlas.benchmark(self.docs, repeats=4)
        self.assertTrue(receipt["deterministic"])
        self.assertEqual(len(set(receipt["analysis_hashes"])), 1)
        self.assertEqual(receipt["network_calls"], 0)
        self.assertEqual(receipt["llm_tokens"], 0)
        self.assertEqual(receipt["document_manifest_sha256"], acqatlas.document_manifest_sha256(self.docs))
        acqatlas.verify_benchmark_receipt(receipt)

    def test_benchmark_receipt_tamper_rejected(self):
        receipt = acqatlas.benchmark(self.docs, repeats=2)
        receipt["elapsed_seconds_total"] += 1
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            acqatlas.verify_benchmark_receipt(receipt)

    def test_manifest_is_input_order_independent(self):
        self.assertEqual(
            acqatlas.document_manifest_sha256(self.docs),
            acqatlas.document_manifest_sha256(list(reversed(self.docs))),
        )

    def test_html_escapes_titles(self):
        docs = [acqatlas.Document("x", "<script>x</script>", "cloud identity zero trust", "V")]
        value = acqatlas.analyze(docs)
        rendered = acqatlas.render_html(value, docs)
        self.assertNotIn("<script>x</script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_loader_rejects_bad_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text('{"doc_id":"x"}\nnot-json\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                acqatlas.load_documents(path)

    def test_cli_roundtrip_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "analysis.json"
            html = Path(tmp) / "analysis.html"
            rc = acqatlas.cli(["analyze", str(FIXTURE), "--output", str(out), "--html", str(html)])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            self.assertTrue(html.exists())
            self.assertEqual(acqatlas.cli(["verify-analysis", str(out)]), 0)

if __name__ == "__main__":
    unittest.main()
