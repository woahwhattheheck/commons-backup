from __future__ import annotations
import copy
import hashlib
import json
import unittest

from traceability import TraceabilityError, compile_assessment, verify_assessment, SCHEMA_SOURCE


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def doc(id_, lang, text, machine_readable=True):
    pages = [{"number": 1, "text": text if machine_readable else ""}]
    payload = {"id": id_, "language": lang, "machine_readable": machine_readable, "pages": pages}
    return payload, sha(pages[0]), sha(payload)


class TraceabilityTests(unittest.TestCase):
    def setUp(self):
        en, en_page, en_doc = doc("law-en", "en", "The authority shall publish an annual register.")
        fr, fr_page, fr_doc = doc("law-fr", "fr", "Le responsable doit publier un registre annuel.")
        es, es_page, es_doc = doc("law-es", "es", "La autoridad debe publicar un registro anual.")
        scan, _, _ = doc("scan-es", "es", "", machine_readable=False)
        self.docs = [en, fr, es]
        self.scan = scan
        self.meta = {
            "law-en": (en_page, en_doc),
            "law-fr": (fr_page, fr_doc),
            "law-es": (es_page, es_doc),
        }
        self.source = {
            "schema": SCHEMA_SOURCE,
            "framework": [
                {"id": "transparency", "label": "Transparency"},
                {"id": "oversight", "label": "Independent oversight"},
            ],
            "documents": copy.deepcopy(self.docs),
            "candidates": [],
        }

    def candidate(self, doc_id, quote, start=0, element="transparency"):
        page_sha, doc_sha = self.meta[doc_id]
        return {
            "element_id": element,
            "document_id": doc_id,
            "page": 1,
            "start": start,
            "end": start + len(quote),
            "quote": quote,
            "page_sha256": page_sha,
            "document_sha256": doc_sha,
        }

    def test_multilingual_verbatim_evidence_compiles_deterministically(self):
        self.source["candidates"] = [
            self.candidate("law-en", "The authority shall publish an annual register."),
            self.candidate("law-fr", "Le responsable doit publier un registre annuel."),
            self.candidate("law-es", "La autoridad debe publicar un registro anual."),
        ]
        first = compile_assessment(self.source)
        second = compile_assessment(copy.deepcopy(self.source))
        self.assertEqual(first, second)
        self.assertTrue(verify_assessment(self.source, first))
        by_id = {row["element_id"]: row for row in first["step3"]}
        self.assertEqual(by_id["transparency"]["status"], "IDENTIFIED_DRAFT")
        self.assertFalse(first["authority"]["legal_interpretation_authorized"])
        self.assertTrue(first["authority"]["human_review_required"])

    def test_paraphrase_is_rejected(self):
        bad = self.candidate("law-en", "The authority shall publish an annual register.")
        bad["quote"] = "The authority must publish an annual register."
        bad["end"] = bad["start"] + len(bad["quote"])
        self.source["candidates"] = [bad]
        with self.assertRaises(TraceabilityError):
            compile_assessment(self.source)

    def test_wrong_page_hash_rejected(self):
        bad = self.candidate("law-en", "The authority shall publish an annual register.")
        bad["page_sha256"] = "0" * 64
        self.source["candidates"] = [bad]
        with self.assertRaises(TraceabilityError):
            compile_assessment(self.source)

    def test_wrong_document_hash_rejected(self):
        bad = self.candidate("law-en", "The authority shall publish an annual register.")
        bad["document_sha256"] = "f" * 64
        self.source["candidates"] = [bad]
        with self.assertRaises(TraceabilityError):
            compile_assessment(self.source)

    def test_wrong_offsets_rejected(self):
        bad = self.candidate("law-en", "The authority shall publish an annual register.")
        bad["start"] = 1
        bad["end"] = 1 + len(bad["quote"])
        self.source["candidates"] = [bad]
        with self.assertRaises(TraceabilityError):
            compile_assessment(self.source)

    def test_duplicate_candidate_rejected(self):
        candidate = self.candidate("law-en", "The authority shall publish an annual register.")
        self.source["candidates"] = [candidate, copy.deepcopy(candidate)]
        with self.assertRaises(TraceabilityError):
            compile_assessment(self.source)

    def test_unreadable_scan_prevents_false_not_identified(self):
        self.source["documents"].append(copy.deepcopy(self.scan))
        assessment = compile_assessment(self.source)
        by_id = {row["element_id"]: row for row in assessment["step3"]}
        self.assertFalse(assessment["corpus_complete"])
        self.assertEqual(by_id["oversight"]["status"], "HOLD_INCOMPLETE_CORPUS")
        scan_receipt = [r for r in assessment["document_receipts"] if r["document_id"] == "scan-es"][0]
        self.assertEqual(scan_receipt["status"], "OCR_REQUIRED")

    def test_candidate_cannot_cite_unreadable_scan(self):
        self.source["documents"].append(copy.deepcopy(self.scan))
        self.source["candidates"] = [{
            "element_id": "transparency", "document_id": "scan-es", "page": 1,
            "start": 0, "end": 1, "quote": "x", "page_sha256": "0" * 64,
            "document_sha256": "0" * 64,
        }]
        with self.assertRaises(TraceabilityError):
            compile_assessment(self.source)

    def test_tampered_summary_fails_verification(self):
        assessment = compile_assessment(self.source)
        assessment["step3"][0]["status"] = "IDENTIFIED_DRAFT"
        self.assertFalse(verify_assessment(self.source, assessment))

    def test_unknown_element_rejected(self):
        bad = self.candidate("law-en", "The authority shall publish an annual register.", element="invented")
        self.source["candidates"] = [bad]
        with self.assertRaises(TraceabilityError):
            compile_assessment(self.source)

    def test_boolean_offset_rejected(self):
        bad = self.candidate("law-en", "The authority shall publish an annual register.")
        bad["start"] = False
        self.source["candidates"] = [bad]
        with self.assertRaises(TraceabilityError):
            compile_assessment(self.source)

    def test_unsupported_language_rejected(self):
        bad_doc = copy.deepcopy(self.source["documents"][0])
        bad_doc["id"] = "law-de"
        bad_doc["language"] = "de"
        self.source["documents"].append(bad_doc)
        with self.assertRaises(TraceabilityError):
            compile_assessment(self.source)


if __name__ == "__main__":
    unittest.main()
