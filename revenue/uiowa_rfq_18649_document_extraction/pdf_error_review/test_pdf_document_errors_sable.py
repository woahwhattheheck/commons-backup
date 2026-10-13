"""Independent PDF document-error acceptance cases for the existing extractor.

All documents are generated locally. This tests failure reporting and evidence
preservation, not exploitation, rendering fidelity, or production-system access.
Set EXTRACTOR_PATH to the exact candidate being exercised.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, NumberObject
except ImportError:
    PdfWriter = None

TARGET = Path(os.environ.get("EXTRACTOR_PATH", str(Path(__file__).resolve().parents[1] / "extract.py"))).resolve()
SPEC = importlib.util.spec_from_file_location("sable_pdf_target_" + hashlib.sha256(str(TARGET).encode()).hexdigest()[:12], TARGET)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def document(kind: str) -> bytes:
    """Make a small controlled document using the supported pypdf backend."""
    writer = PdfWriter()
    if kind != "empty":
        writer.add_blank_page(width=612, height=792)
    if kind == "missing_pages":
        del writer._root_object[NameObject("/Pages")]
    elif kind == "invalid_pages":
        writer._root_object[NameObject("/Pages")] = NumberObject(7)
    elif kind == "protected":
        writer.encrypt("fictional-test-password", algorithm="RC4-128")
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


@unittest.skipIf(PdfWriter is None, "PDF backend unavailable; install declared requirements to execute PDF cases")
class PdfDocumentErrors(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self, kind: str):
        source = self.root / (kind + ".pdf")
        source.write_bytes(document(kind))
        return source

    def cli(self, source: Path, output: Path | None = None):
        args = [sys.executable]
        if sys.flags.optimize:
            args.append("-O")
        for option in sys.warnoptions:
            args += ["-W", option]
        args += [str(TARGET), str(source)]
        if output is not None:
            args += ["-o", str(output)]
        return subprocess.run(args, capture_output=True, text=True, timeout=10)

    def error_result(self, kind: str):
        source = self.source(kind)
        before = source.read_bytes()
        proc = self.cli(source)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["schema"], "uiowa.document-extraction.v1")
        self.assertEqual(result["segments"], [])
        self.assertEqual(source.read_bytes(), before)
        return result

    def test_missing_pages_api_is_named_error(self):
        with self.assertRaisesRegex(MODULE.ExtractionError, "PDF_PAGE_TREE_FAILED:AttributeError"):
            MODULE.extract(self.source("missing_pages"))

    def test_invalid_pages_api_is_named_error(self):
        with self.assertRaisesRegex(MODULE.ExtractionError, "PDF_PAGE_TREE_FAILED:PdfReadError"):
            MODULE.extract(self.source("invalid_pages"))

    def test_missing_pages_cli_reports_json(self):
        self.assertIn("PDF_PAGE_TREE_FAILED", self.error_result("missing_pages")["error"])

    def test_invalid_pages_cli_reports_json(self):
        self.assertIn("PDF_PAGE_TREE_FAILED", self.error_result("invalid_pages")["error"])

    def test_bad_document_does_not_create_output(self):
        source = self.source("missing_pages")
        output = self.root / "not-created.json"
        proc = self.cli(source, output)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "error")
        self.assertFalse(output.exists())

    def test_bad_document_preserves_existing_report(self):
        source = self.source("invalid_pages")
        output = self.root / "retained.json"
        retained = b'{"retained":true}\r\n'
        output.write_bytes(retained)
        proc = self.cli(source, output)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "error")
        self.assertEqual(output.read_bytes(), retained)

    def test_bad_document_never_truncates_input_alias(self):
        source = self.source("missing_pages")
        before = source.read_bytes()
        proc = self.cli(source, source)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(json.loads(proc.stdout)["segments"], [])

    def test_late_page_enumeration_failure_has_no_partial_report(self):
        class Page:
            calls = 0
            def extract_text(self):
                self.calls += 1
                return "Uncommitted synthetic partial text"
        first = Page()
        class Reader:
            is_encrypted = False
            @property
            def pages(self):
                def pages():
                    yield first
                    raise ValueError("synthetic page enumeration failure")
                return pages()
        with patch("pypdf.PdfReader", return_value=Reader()):
            with self.assertRaisesRegex(MODULE.ExtractionError, "PDF_PAGE_TREE_FAILED:ValueError"):
                MODULE.extract(self.source("blank"))
        self.assertEqual(first.calls, 0, "Do not extract against incomplete page enumeration")

    def test_empty_document_has_explicit_no_pages_warning(self):
        source = self.source("empty")
        result = MODULE.extract(source)
        self.assertEqual(result["status"], "unreadable")
        self.assertEqual(result["segments"], [])
        self.assertIn("PDF_NO_PAGES", result["warnings"])
        self.assertEqual(result["document"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_blank_page_keeps_unreadable_page_locator(self):
        result = MODULE.extract(self.source("blank"))
        self.assertEqual(result["status"], "unreadable")
        self.assertEqual(result["segments"][0]["locator"], "page 1")
        self.assertEqual(result["segments"][0]["text"], "")

    def test_password_requirement_remains_distinct(self):
        result = self.error_result("protected")
        self.assertEqual(result["error"], "PDF_ENCRYPTED_PASSWORD_REQUIRED")

    def test_page_text_failure_retains_other_pages(self):
        class BrokenPage:
            def extract_text(self):
                raise ValueError("synthetic content failure")
        class GoodPage:
            def extract_text(self):
                return "Retained synthetic second-page text"
        class Reader:
            is_encrypted = False
            pages = [BrokenPage(), GoodPage()]
        with patch("pypdf.PdfReader", return_value=Reader()):
            result = MODULE.extract(self.source("blank"))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["segments"][0]["kind"], "unreadable")
        self.assertEqual(result["segments"][0]["locator"], "page 1")
        self.assertEqual(result["segments"][1]["text"], "Retained synthetic second-page text")
        self.assertEqual(result["segments"][1]["locator"], "page 2, block 1")
        self.assertIn("PDF_PAGES_WITHOUT_EXTRACTABLE_TEXT=1/2", result["warnings"])

    def test_page_enumeration_performed_once(self):
        class Page:
            def extract_text(self):
                return "Synthetic content"
        class Reader:
            is_encrypted = False
            count = 0
            @property
            def pages(self):
                self.count += 1
                if self.count > 1:
                    raise ValueError("do not reopen page traversal")
                return [Page()]
        reader = Reader()
        with patch("pypdf.PdfReader", return_value=reader):
            result = MODULE.extract(self.source("blank"))
        self.assertEqual(reader.count, 1)
        self.assertEqual(result["status"], "ok")

    def test_missing_backend_error_not_reclassified(self):
        with patch.dict(sys.modules, {"pypdf": None}):
            with self.assertRaisesRegex(MODULE.ExtractionError, "PDF_BACKEND_UNAVAILABLE"):
                MODULE.extract(self.source("blank"))

    def test_success_carries_snapshot_and_source_unchanged(self):
        source = self.source("blank")
        before = source.read_bytes()
        result = MODULE.extract(source)
        self.assertEqual(result["document"]["bytes"], len(before))
        self.assertEqual(result["document"]["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(source.read_bytes(), before)


class MissingBackendContract(unittest.TestCase):
    def test_missing_backend_has_named_error_without_loading_pdf(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "fictional.pdf"
            raw = b"%PDF-1.4\n% synthetic backend-absence test\n"
            source.write_bytes(raw)
            with patch.dict(sys.modules, {"pypdf": None}):
                with self.assertRaisesRegex(MODULE.ExtractionError, "PDF_BACKEND_UNAVAILABLE"):
                    MODULE.extract(source)
            self.assertEqual(source.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
