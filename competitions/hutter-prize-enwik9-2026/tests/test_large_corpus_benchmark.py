import hashlib
import tempfile
import unittest
from pathlib import Path

import large_corpus_benchmark as bench


class LargeCorpusHarnessTests(unittest.TestCase):
    def test_prefix_parser_accepts_material_increasing_sizes(self):
        self.assertEqual(bench.parse_prefixes("65536,262144"), (65536, 262144))

    def test_prefix_parser_rejects_fixture_sized_duplicate_or_descending_values(self):
        for bad in ("3560", "65536,65536", "262144,65536", "100000001"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bench.parse_prefixes(bad)

    def test_published_enwik8_identity_constants(self):
        self.assertEqual(bench.ENWIK8_URL, "https://www.mattmahoney.net/dc/enwik8.zip")
        self.assertEqual(bench.ENWIK8_BYTES, 100_000_000)
        self.assertEqual(bench.ENWIK8_MD5, "a1fa5ffddb56f4953e226637dabbb36a")
        self.assertEqual(bench.ENWIK8_SHA1, "57b8363b814821dc9d47aa4d41f58733519076b2")
        self.assertEqual(bench.DEFAULT_PREFIXES, (65_536, 262_144))

    def test_canonical_json_is_order_stable(self):
        self.assertEqual(bench.canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}')

    def test_digest_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x"
            path.write_bytes(b"abc")
            self.assertEqual(bench.digest_file(path), hashlib.sha256(b"abc").hexdigest())

    def test_source_accounting_counts_candidate_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mixerlab.py").write_bytes(b"12345")
            (root / "match_model.py").write_bytes(b"abcdefg")
            result = bench.source_accounting(root)
            self.assertEqual(result["baseline_program_source_bytes"], 5)
            self.assertEqual(result["candidate_program_source_bytes"], 12)
            self.assertIn("not official", result["rule"])

    def test_markdown_reports_archive_and_source_shape_totals(self):
        evidence = {
            "operation": "op",
            "corpus": {"url": "https://example.invalid/enwik8.zip", "full_corpus_md5": "m", "full_corpus_sha1": "s"},
            "source_accounting": {
                "rule": "source proxy",
                "baseline_program_source_bytes": 10,
                "candidate_program_source_bytes": 20,
            },
            "pairs": [{
                "input_bytes": 65536,
                "baseline": {"archive_bytes": 100, "codec_wall_seconds": 1.0, "peak_rss_bytes_linux": 1000},
                "candidate": {"archive_bytes": 70, "codec_wall_seconds": 2.0, "peak_rss_bytes_linux": 2000},
            }],
        }
        rendered = bench.render_markdown(evidence)
        self.assertIn("110", rendered)
        self.assertIn("90", rendered)
        self.assertIn("-20", rendered)


if __name__ == "__main__":
    unittest.main()