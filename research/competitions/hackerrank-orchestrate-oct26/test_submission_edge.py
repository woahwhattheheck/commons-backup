import json
import tempfile
import unittest
from pathlib import Path

import submission_edge as edge


class SubmissionEdgeTests(unittest.TestCase):
    def test_transcript_redacts_secrets_and_drops_private_records(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "chat.jsonl"
            dst = root / "clean.jsonl"
            src.write_text(
                json.dumps({"role": "user", "authorization": "Bearer abcdefghijklmnop", "text": "ok"}) + "\n"
                + json.dumps({"role": "assistant", "visibility": "private", "text": "internal"}) + "\n"
                + json.dumps({"role": "assistant", "text": "Bearer abcdefghijklmnop"}) + "\n",
                encoding="utf-8",
            )
            result = edge.sanitize_transcript(src, dst)
            self.assertEqual(result["kept"], 2)
            self.assertEqual(result["dropped_private"], 1)
            text = dst.read_text(encoding="utf-8")
            self.assertNotIn("abcdefghijklmnop", text)
            self.assertIn(edge.REDACTED, text)

    def test_validate_output_catches_duplicates_and_missing_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "out.csv"
            expected = root / "expected.txt"
            data.write_text("id,value\n1,a\n1,b\n", encoding="utf-8")
            expected.write_text("1\n2\n", encoding="utf-8")
            result = edge.validate_output(
                data, "csv", ["value"], "id", expected, None, False
            )
            self.assertFalse(result["ok"])
            self.assertTrue(any("duplicate ids" in item for item in result["errors"]))
            self.assertTrue(any("missing expected ids" in item for item in result["errors"]))

    def test_compare_is_order_independent_when_id_field_is_set(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "a.jsonl"
            b = root / "b.jsonl"
            a.write_text('{"id":"2","v":"b"}\n{"id":"1","v":"a"}\n', encoding="utf-8")
            b.write_text('{"v":"a","id":"1"}\n{"v":"b","id":"2"}\n', encoding="utf-8")
            result = edge.validate_output(a, "jsonl", [], "id", None, b, False)
            self.assertTrue(result["ok"])
            self.assertEqual(result["sha256_normalized"], result["compare_sha256_normalized"])

    def test_receipt_refuses_sensitive_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "result.txt"
            artifact.write_text("ok\n", encoding="utf-8")
            with self.assertRaises(edge.EdgeError):
                edge.build_receipt([artifact], ["api_key=nope"], None, None, None)


if __name__ == "__main__":
    unittest.main()
