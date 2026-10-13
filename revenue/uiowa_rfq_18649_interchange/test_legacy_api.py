from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from transport import (
    TransportError,
    from_rows,
    project_docx,
    project_pdf,
    read_csv,
    read_xlsx,
    to_rows,
    write_csv,
    write_xlsx,
)

HERE = Path(__file__).resolve().parent
CLI = HERE / "cli.py"


def seeded_doc(rng: random.Random) -> dict:
    def leaf() -> object:
        kind = rng.choice(["int", "float", "bool", "null", "str", "empty"])
        if kind == "int":
            return rng.randint(-10_000, 10_000)
        if kind == "float":
            return rng.choice([0.0, 1.5, -2.25, 3.14159])
        if kind == "bool":
            return rng.choice([True, False])
        if kind == "null":
            return None
        if kind == "empty":
            return ""
        return rng.choice(["café", "公式", "ok\nline", "=SUM(A1:A2)", "id-Ω-009", "ctrl:\u0007"])

    def node(depth: int) -> object:
        if depth <= 0:
            return leaf()
        if rng.random() < 0.5:
            return {f"k{rng.randint(0, 20)}": node(depth - 1) for _ in range(rng.randint(1, 4))}
        return [node(depth - 1) for _ in range(rng.randint(1, 4))]

    return {
        "schema": "synthetic.assessment.envelope.v1",
        "authority": "none",
        "payload": node(3),
        "notes": "multiline\nnote with 日本語 and formula-like =1+1",
        "locator": "https://example.invalid/evidence/" + "x" * 80,
        "empty_field": "",
        "missing_sibling_present": True,
        "score_not_elevated": None,
    }


class TransportTests(unittest.TestCase):
    def test_scalar_roundtrip(self):
        doc = {"i": 7, "f": 1.25, "b": False, "n": None, "s": "", "t": "hi"}
        self.assertEqual(from_rows(to_rows(doc)), doc)

    def test_nested_and_array(self):
        doc = {"a": [{"x": 1}, {"x": 2}], "u": "ユニコード"}
        self.assertEqual(from_rows(to_rows(doc)), doc)

    def test_seeded_nested_documents(self):
        for seed in range(150):
            doc = seeded_doc(random.Random(seed))
            self.assertEqual(from_rows(to_rows(doc)), doc, msg=f"seed {seed}")

    def test_csv_roundtrip_unicode_formula_large(self):
        doc = {
            "note": "line1\nline2",
            "formula": "=SUM(A1:A2)",
            "big": "Z" * 20000,
            "ctrl": "a\tb",
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.csv"
            write_csv(doc, path)
            self.assertEqual(read_csv(path), doc)

    def test_xlsx_roundtrip(self):
        doc = {"id": "RFQ-18649", "ok": True, "n": None, "empty": ""}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.xlsx"
            write_xlsx(doc, path)
            self.assertEqual(read_xlsx(path), doc)

    def test_duplicate_keys_last_json_wins_on_load(self):
        raw = '{"a": 1, "a": 2}'
        doc = json.loads(raw)
        self.assertEqual(doc["a"], 2)
        self.assertEqual(from_rows(to_rows(doc)), {"a": 2})

    def test_structural_corruption(self):
        with self.assertRaises(TransportError):
            from_rows([{"pointer": "no-slash", "type": "string", "value": "x", "presence": "present"}])

    def test_cli_roundtrip(self):
        doc = {"k": "v", "n": 3}
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            csv_path = Path(td) / "out.csv"
            back = Path(td) / "back.json"
            src.write_text(json.dumps(doc), encoding="utf-8")
            subprocess.check_call([sys.executable, str(CLI), "json-to-csv", str(src), str(csv_path)])
            subprocess.check_call([sys.executable, str(CLI), "csv-to-json", str(csv_path), str(back)])
            self.assertEqual(json.loads(back.read_text(encoding="utf-8")), doc)

    def test_docx_projection_does_not_elevate(self):
        import zipfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "s.docx"
            document_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Synthetic evidence note</w:t></w:r></w:p></w:body>"
                "</w:document>"
            )
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", document_xml)
            proj = project_docx(path)
            self.assertEqual(proj["authority"], "none")
            self.assertEqual(proj["assessment"], "not_elevated")
            self.assertIn("Synthetic evidence note", proj["paragraphs"])

    def test_pdf_projection_unknown_text(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "s.pdf"
            path.write_bytes(b"%PDF-1.1\n%\xff\n1 0 obj<<>>endobj\ntrailer<<>>\n")
            proj = project_pdf(path)
            self.assertEqual(proj["status"], "unknown_text")
            self.assertEqual(proj["text"], "")
            self.assertEqual(proj["authority"], "none")


if __name__ == "__main__":
    unittest.main()
