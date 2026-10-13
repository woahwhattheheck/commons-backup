"""Exercise the actual SQLite core, PDF converter and HTTP application."""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import shutil
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import create_server
from study import Conflict, MAX_CARDS, Workspace, extract_pages, generate_cards, normalized

NOTES = b"# Systems\n\nLatency: the elapsed time between a request and its response.\nThroughput: the number of completed operations per unit of time.\n\fFeedback: information used to adjust the next behavior of a system.\n"


def text_pdf() -> bytes:
    """A real, original two-page PDF fixture; no PDF library required."""
    texts = [b"Latency: the elapsed time between a request and its response.",
             b"Throughput: the number of completed operations per unit of time."]
    streams = [b"BT /F1 12 Tf 48 720 Td (" + text + b") Tj ET" for text in texts]
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>",
               b"<< /Length " + str(len(streams[0])).encode() + b" >>\nstream\n" + streams[0] + b"\nendstream",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>",
               b"<< /Length " + str(len(streams[1])).encode() + b" >>\nstream\n" + streams[1] + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


class ExtractionTests(unittest.TestCase):
    def test_notes_page_line_and_exact_quote(self):
        kind, pages = extract_pages(NOTES, "systems.md")
        cards = generate_cards(pages)
        self.assertEqual(kind, "text")
        latency = next(c for c in cards if c["answer"] == "Latency")
        feedback = next(c for c in cards if c["answer"] == "Feedback")
        self.assertEqual((latency["page"], latency["line_start"]), (1, 3))
        self.assertEqual(latency["quote"], pages[0].splitlines()[2])
        self.assertEqual((feedback["page"], feedback["line_start"]), (2, 1))

    def test_unicode_and_line_endings(self):
        kind, pages = extract_pages("\ufeffCafé: a place where prepared beverages are served.\r\n".encode(), "notes.txt")
        self.assertEqual(generate_cards(pages)[0]["answer"], "Café")
        self.assertNotIn("\r", pages[0])
        self.assertEqual(normalized("ＣＡＦÉ!"), normalized("café"))

    def test_cloze_is_a_literal_source_sentence(self):
        line = "Measurements collected over several intervals help describe changing behavior."
        card = generate_cards([line])[0]
        self.assertEqual(card["kind"], "cloze")
        self.assertIn(card["answer"], line)
        self.assertEqual(card["quote"], line)
        self.assertIn("[ … ]", card["prompt"])

    def test_duplicates_and_maximum(self):
        line = "Term: this describes the original source material."
        self.assertEqual(len(generate_cards([line + "\n" + line])), 1)
        many = "\n".join(f"Term {i}: this describes unique original material {i}." for i in range(MAX_CARDS + 50))
        self.assertEqual(len(generate_cards([many])), MAX_CARDS)

    def test_empty_binary_and_unsupported_file(self):
        for raw, name in [(b"", "a.txt"), (b"\0", "a.txt"), (b"\xff", "a.txt"), (b"notes", "a.exe"), (b"hello", "a.pdf")]:
            with self.subTest(name=name, raw=raw), self.assertRaises(ValueError):
                extract_pages(raw, name)

    def test_no_generated_cards_is_explicit(self):
        self.assertEqual(generate_cards(["# Only a heading\nshort"]), [])

    @unittest.skipUnless(shutil.which("pdftotext"), "Poppler pdftotext is not installed")
    def test_real_pdf_extraction_and_page_references(self):
        kind, pages = extract_pages(text_pdf(), "chapter.pdf")
        self.assertEqual(kind, "pdf")
        self.assertEqual(len(pages), 2)
        cards = generate_cards(pages)
        self.assertEqual({c["answer"]: c["page"] for c in cards}, {"Latency": 1, "Throughput": 2})

    @unittest.skipUnless(shutil.which("pdftotext"), "Poppler pdftotext is not installed")
    def test_malformed_pdf_has_readable_failure(self):
        with self.assertRaisesRegex(ValueError, "extraction did not succeed"):
            extract_pages(b"%PDF-1.4\nnot a PDF body", "bad.pdf")


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nested" / "workspace.sqlite3"
        self.w = Workspace(self.path)
        self.document_id = self.w.import_document(NOTES, "notes.md", "Systems")["id"]
        self.card = next(c for c in self.w.cards(self.document_id) if c["answer"] == "Latency")

    def answer(self, answer="Latency", operation="r1", now=1000, revision=1):
        return self.w.review(self.card["id"], answer, operation, revision, now)

    def edits(self, **changes):
        result = {key: self.card[key] for key in ["prompt", "answer", "aliases", "explanation", "revision"]}
        result.update(changes)
        return result

    def test_source_hash_and_original_bytes(self):
        self.assertEqual(self.document_id, hashlib.sha256(NOTES).hexdigest())
        self.assertEqual(self.w.document(self.document_id, original=True)["original"], NOTES)
        self.assertNotIn("original", self.w.document(self.document_id))

    def test_repeat_import_preserves_keys_and_progress(self):
        updated = self.w.edit_card(self.card["id"], self.edits(answer="Delay", aliases=["Latency"]))
        self.answer("Delay", revision=updated["revision"])
        repeated = self.w.import_document(NOTES, "renamed.md", "Renamed")
        self.assertTrue(repeated["duplicate"])
        current = next(c for c in self.w.cards(self.document_id) if c["id"] == self.card["id"])
        self.assertEqual((current["answer"], current["attempts"], current["revision"]), ("Delay", 1, 2))
        self.assertEqual(self.w.document(self.document_id)["title"], "Systems")

    def test_mismatch_feedback_is_source_bound(self):
        result = self.answer("Throughput")
        self.assertFalse(result["correct"])
        self.assertEqual(result["quote"], self.card["quote"])
        self.assertEqual(result["answer"], "Latency")
        self.assertIn("editable key", result["feedback"])
        self.assertIn("#p1-l3", result["source_url"])
        self.assertEqual(result["due_at"], 1600)

    def test_normalized_key_and_alias(self):
        updated = self.w.edit_card(self.card["id"], self.edits(aliases=["response delay"]))
        self.assertTrue(self.answer(" RESPONSE, DELAY! ", revision=updated["revision"])["correct"])

    def test_schedule_1_3_6_days_and_lapse(self):
        for i, days in enumerate([1, 3, 6], 1):
            result = self.answer(operation=f"good{i}", now=i * 1_000_000)
            self.assertEqual(result["interval_days"], days)
            self.assertEqual(result["due_at"], i * 1_000_000 + days * 86400)
        result = self.answer("not this", "lapse", now=4_000_000)
        self.assertEqual(result["interval_days"], 0)
        self.assertEqual(result["due_at"], 4_000_600)
        self.assertEqual(self.answer(operation="after-lapse")["interval_days"], 1)

    def test_due_boundary_and_progress_counts(self):
        result = self.answer()
        self.assertNotIn(self.card["id"], [c["id"] for c in self.w.cards(self.document_id, True, result["due_at"] - 1)])
        self.assertIn(self.card["id"], [c["id"] for c in self.w.cards(self.document_id, True, result["due_at"])])
        document = self.w.documents(now=1001)[0]
        self.assertEqual((document["attempts"], document["due"]), (1, 2))

    def test_retry_after_database_reopen_is_counted_once(self):
        result = self.answer()
        self.w = Workspace(self.path)
        self.assertEqual(result, self.answer(now=2000))
        data = self.w.export(self.document_id)
        self.assertEqual(len(data["reviews"]), 1)
        self.assertEqual(sum(c["attempts"] for c in data["cards"]), 1)

    def test_concurrent_retry_is_counted_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.answer(now=1000), range(16)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(len(self.w.export(self.document_id)["reviews"]), 1)

    def test_concurrent_import_does_not_duplicate_cards(self):
        raw = b"New term: another original definition for this chapter."
        with ThreadPoolExecutor(max_workers=4) as pool:
            imports = list(pool.map(lambda _: self.w.import_document(raw, "new.txt"), range(8)))
        self.assertEqual(sum(not x["duplicate"] for x in imports), 1)
        self.assertEqual(len(self.w.cards(imports[0]["id"])), 1)

    def test_reused_operation_with_different_answer_conflicts(self):
        self.answer()
        with self.assertRaises(Conflict):
            self.answer("other")
        self.assertEqual(len(self.w.export(self.document_id)["reviews"]), 1)

    def test_edit_revision_and_stale_answer_conflict(self):
        self.w.edit_card(self.card["id"], self.edits())
        with self.assertRaises(Conflict):
            self.w.edit_card(self.card["id"], self.edits())
        with self.assertRaises(Conflict):
            self.answer()

    def test_edit_preserves_history_but_reschedules(self):
        self.answer()
        card = self.w.edit_card(self.card["id"], self.edits(explanation="Refer to the latency definition on page 1."))
        self.assertEqual((card["attempts"], card["due_at"], card["revision"]), (1, 0, 2))
        self.assertEqual(card["quote"], self.card["quote"])
        self.assertEqual(len(self.w.export(self.document_id)["reviews"]), 1)

    def test_invalid_editor_values_do_not_mutate(self):
        for changes in [{"answer": "!"}, {"aliases": ["---"]}, {"aliases": "text"}, {"revision": True}, {"prompt": ""}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.w.edit_card(self.card["id"], self.edits(**changes))
        self.assertEqual(self.w.cards(self.document_id), Workspace(self.path).cards(self.document_id))
        self.assertEqual(next(c for c in self.w.cards(self.document_id) if c["id"] == self.card["id"])["revision"], 1)

    def test_zero_card_document_is_saved_with_notice(self):
        imported = self.w.import_document(b"# Short notes", "short.md")
        self.assertEqual(imported["cards"], 0)
        self.assertIn("No practice cards", imported["notice"])
        self.assertEqual(self.w.document(imported["id"])["pages"], ["# Short notes"])

    def test_export_contains_source_cards_and_review_state(self):
        self.answer()
        exported = self.w.export(self.document_id)
        self.assertEqual(exported["format"], "hive-study-export-v1")
        self.assertEqual(exported["document"]["pages"], NOTES.decode().split("\f"))
        self.assertEqual(exported["reviews"][0]["result"]["answer"], "Latency")
        json.dumps(exported)

    def test_delete_cascades_without_deleting_other_document(self):
        other = self.w.import_document(b"Distinct: a different chapter that remains in the workspace.", "other.txt")["id"]
        self.answer()
        self.w.delete_document(self.document_id)
        with self.assertRaises(KeyError):
            self.w.document(self.document_id)
        with self.w.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
        self.assertEqual(self.w.documents()[0]["id"], other)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.workspace = Workspace(Path(cls.temp.name) / "http.sqlite3")
        cls.server = create_server("127.0.0.1", 0, cls.workspace)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=5)
        cls.temp.cleanup()

    def request(self, path, method="GET", payload=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            body = json.dumps(payload).encode() if payload is not None else raw
            conn.request(method, path, body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def import_notes(self):
        status, _, data = self.request("/api/import", "POST", {"filename": "source.md", "data": base64.b64encode(NOTES).decode()})
        self.assertEqual(status, 200)
        return json.loads(data)["id"]

    def test_capabilities_and_response_headers(self):
        for path in ["/api/capabilities", "/api/documents"]:
            status, headers, raw = self.request(path)
            self.assertEqual(status, 200)
            self.assertTrue(raw)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertIn("'self'", headers["Content-Security-Policy"])

    def test_actual_http_roundtrip_retry_and_export(self):
        document_id = self.import_notes()
        status, _, raw = self.request(f"/api/documents/{document_id}/cards")
        self.assertEqual(status, 200)
        card = json.loads(raw)["cards"][0]
        payload = {"card_id": card["id"], "answer": card["answer"], "request_id": "http-review", "revision": card["revision"]}
        first = self.request("/api/review", "POST", payload)
        second = self.request("/api/review", "POST", payload)
        self.assertEqual(first[0], 200)
        self.assertEqual(first[2], second[2])
        status, headers, exported = self.request(f"/api/documents/{document_id}/export")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(len(json.loads(exported)["reviews"]), 1)
        status, _, original = self.request(f"/original/{document_id}")
        self.assertEqual(original, NOTES)

    def test_source_is_escaped_with_stable_anchors(self):
        raw = b'<script>alert("source")</script>\nKey: original source text used for this practice question.'
        status, _, result = self.request("/api/import", "POST", {"filename": "x.txt", "title": "<b>title</b>", "data": base64.b64encode(raw).decode()})
        self.assertEqual(status, 200)
        document_id = json.loads(result)["id"]
        status, _, page = self.request(f"/source/{document_id}")
        self.assertEqual(status, 200)
        self.assertNotIn(b"<script>", page)
        self.assertIn(b"&lt;script&gt;", page)
        self.assertIn(b'id="p1-l2"', page)
        self.assertIn(b"&lt;b&gt;title&lt;/b&gt;", page)

    def test_bad_payload_and_missing_routes(self):
        for path, body in [("/api/import", b"null"), ("/api/import", b"[1]"), ("/api/import", b"{bad"), ("/api/import", b'{"data":"%"}')]:
            status, _, raw = self.request(path, "POST", raw=body)
            self.assertEqual(status, 400)
            self.assertIn("message", json.loads(raw))
        self.assertEqual(self.request("/api/documents/missing")[0], 404)
        self.assertEqual(self.request("/missing")[0], 404)

    @unittest.skipUnless(shutil.which("pdftotext"), "Poppler pdftotext is not installed")
    def test_pdf_via_real_http_import(self):
        raw = text_pdf()
        status, _, result = self.request("/api/import", "POST", {"filename": "chapter.pdf", "data": base64.b64encode(raw).decode()})
        self.assertEqual(status, 200)
        document_id = json.loads(result)["id"]
        status, headers, downloaded = self.request(f"/original/{document_id}")
        self.assertEqual((status, downloaded), (200, raw))
        self.assertEqual(headers["Content-Type"], "application/pdf")


if __name__ == "__main__":
    unittest.main(verbosity=2)
