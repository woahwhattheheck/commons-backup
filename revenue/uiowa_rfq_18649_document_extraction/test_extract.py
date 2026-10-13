from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_sibling(stem):
    path = HERE / f"{stem}.py"
    name = "_uiowa032_existing_" + stem + "_" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extract = _load_sibling("extract")
make_synthetic_corpus = _load_sibling("make_synthetic_corpus")
HAS_PYPDF = importlib.util.find_spec("pypdf") is not None


class ExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._temporary.cleanup)
        cls.fixtures = Path(cls._temporary.name)
        make_synthetic_corpus.build_corpus(cls.fixtures)

    def test_text_preserves_heading_and_line_locators(self):
        result = extract.extract(self.fixtures / "sample.txt")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["document"]["type"], "plain_text")
        self.assertTrue(any(s["locator"] == "line 1" and s["kind"] == "heading" for s in result["segments"]))
        body = next(s for s in result["segments"] if "independent review" in s["text"])
        self.assertEqual(body["heading_path"], ["Software Development"])
        self.assertTrue(body["locator"].startswith("lines "))

    def test_docx_preserves_heading_context_and_linearizes_tables(self):
        result = extract.extract(self.fixtures / "sample.docx")
        self.assertEqual(result["status"], "partial")  # page-number limitation is explicit
        self.assertIn("DOCX_PAGE_NUMBERS_NOT_RELIABLE", result["warnings"][0])
        para = next(s for s in result["segments"] if "reversible deployment plan" in s["text"])
        self.assertEqual(para["heading_path"], ["Deployment Evidence"])
        table = next(s for s in result["segments"] if s["kind"] == "table")
        self.assertIn("Artifact | Locator", table["text"])
        self.assertEqual(table["locator"], "table 1")

    @unittest.skipUnless(HAS_PYPDF, "PDF backend absent; missing-backend contract tested separately")
    def test_pdf_uses_page_locators(self):
        result = extract.extract(self.fixtures / "sample.pdf")
        self.assertEqual(result["status"], "ok")
        page_one = next(s for s in result["segments"] if "page one" in s["text"])
        page_two = next(s for s in result["segments"] if "page two" in s["text"])
        self.assertTrue(page_one["locator"].startswith("page 1"))
        self.assertTrue(page_two["locator"].startswith("page 2"))

    @unittest.skipUnless(HAS_PYPDF, "PDF backend absent; missing-backend contract tested separately")
    def test_blank_pdf_reports_unreadable_or_partial_without_inventing_text(self):
        result = extract.extract(self.fixtures / "blank.pdf")
        self.assertIn(result["status"], {"partial", "unreadable"})
        self.assertTrue(any("PDF_PAGES_WITHOUT_EXTRACTABLE_TEXT" in w for w in result["warnings"]))
        self.assertTrue(any("PAGE_NO_EXTRACTABLE_TEXT" in " ".join(s["warnings"]) for s in result["segments"]))

    def test_cli_json_is_machine_readable(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "extract.py"), str(self.fixtures / "sample.txt")],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema"], "uiowa.document-extraction.v1")
        self.assertGreater(len(payload["segments"]), 0)

    def test_unsupported_extension_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.bin"
            p.write_bytes(b"x")
            with self.assertRaises(extract.ExtractionError):
                extract.extract(p)


if __name__ == "__main__":
    unittest.main()
