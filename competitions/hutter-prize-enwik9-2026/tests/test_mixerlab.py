from __future__ import annotations

import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mixerlab
import readiness_gate


WIKI_SAMPLE = (b"<page>\n  <title>Compression</title>\n  <revision>\n    <text xml:space=\"preserve\">"
               b"[[Compression]] is {{useful}} &amp; reversible. http://example.test\n"
               b"</text>\n  </revision>\n</page>\n") * 20


class TransformTests(unittest.TestCase):
    def test_transform_roundtrip_hostiles(self):
        cases = [
            b"",
            bytes(range(256)),
            WIKI_SAMPLE,
            b"\xff\xff</text>\xff\n",
            "Málaga 東京 naïve résumé".encode("utf-8"),
        ]
        for data in cases:
            with self.subTest(length=len(data)):
                encoded = mixerlab.wiki_transform_encode(data)
                self.assertEqual(mixerlab.wiki_transform_decode(encoded), data)

    def test_transform_rejects_bad_escape(self):
        with self.assertRaises(ValueError):
            mixerlab.wiki_transform_decode(b"abc\xff")
        with self.assertRaises(ValueError):
            mixerlab.wiki_transform_decode(b"abc\xff\xfe")

    def test_transform_contracts_wiki_sample(self):
        encoded = mixerlab.wiki_transform_encode(WIKI_SAMPLE)
        self.assertLess(len(encoded), len(WIKI_SAMPLE))


class CodecTests(unittest.TestCase):
    def test_roundtrip_matrix(self):
        rng = random.Random(8128)
        cases = [
            b"",
            b"a",
            b"a" * 4096,
            WIKI_SAMPLE,
            bytes(rng.randrange(256) for _ in range(2048)),
            bytes(range(256)) * 8,
        ]
        for transform in (False, True):
            for data in cases:
                with self.subTest(transform=transform, length=len(data)):
                    archive = mixerlab.compress_bytes(data, use_transform=transform, table_bits=12)
                    self.assertEqual(mixerlab.decompress_bytes(archive), data)

    def test_archive_is_deterministic(self):
        a = mixerlab.compress_bytes(WIKI_SAMPLE, table_bits=12)
        b = mixerlab.compress_bytes(WIKI_SAMPLE, table_bits=12)
        self.assertEqual(a, b)

    def test_payload_corruption_fails_closed(self):
        archive = bytearray(mixerlab.compress_bytes(WIKI_SAMPLE, table_bits=12))
        _meta, payload = mixerlab._parse_archive(bytes(archive))
        self.assertGreater(len(payload), 2)
        offset = mixerlab._HEADER.size + (len(payload) // 2)
        archive[offset] ^= 0x40
        with self.assertRaisesRegex(ValueError, "payload SHA-256"):
            mixerlab.decompress_bytes(bytes(archive))

    def test_truncation_and_trailing_garbage_fail_closed(self):
        archive = mixerlab.compress_bytes(WIKI_SAMPLE, table_bits=12)
        with self.assertRaises(ValueError):
            mixerlab.decompress_bytes(archive[:-1])
        with self.assertRaises(ValueError):
            mixerlab.decompress_bytes(archive + b"x")

    def test_bounded_model_memory(self):
        model = mixerlab.BoundedContextMixer(12)
        before = model.table_bytes
        for value in range(10000):
            byte = value & 0xFF
            prefix = 0
            for bitpos in range(8):
                bit = (byte >> (7 - bitpos)) & 1
                _p1, indices = model.probability_one(bitpos, prefix)
                model.update(indices, bit)
                prefix = (prefix << 1) | bit
            model.push_byte(byte)
        self.assertEqual(model.table_bytes, before)
        self.assertEqual(model.size, 1 << 12)

    def test_program_accounting(self):
        self.assertEqual(mixerlab.program_accounted_bytes(100, combined_program_bytes=20), 120)
        self.assertEqual(mixerlab.program_accounted_bytes(100, compressor_bytes=20, decompressor_bytes=30), 180)
        with self.assertRaises(ValueError):
            mixerlab.program_accounted_bytes(100, combined_program_bytes=20, compressor_bytes=1, decompressor_bytes=1)


class ReceiptAndGateTests(unittest.TestCase):
    def test_benchmark_receipt_verifies_and_gate_blocks_fixture(self):
        receipt, archive = mixerlab.benchmark(WIKI_SAMPLE, table_bits=12, program_bytes=321)
        self.assertTrue(archive)
        mixerlab.verify_receipt(receipt)
        self.assertEqual(receipt["total_accounted_bytes"], len(archive) + 321)
        rules = json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))
        gate = readiness_gate.evaluate(receipt, rules)
        self.assertEqual(gate["status"], "BLOCKED")
        self.assertIn("evidence_class_not_official_enwik9_local", gate["reasons"])
        self.assertIn("official_enwik9_sha256_not_pinned", gate["reasons"])

    def test_receipt_tamper_rejected(self):
        receipt, _ = mixerlab.benchmark(b"abc" * 100, table_bits=12)
        receipt["archive_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "receipt SHA-256"):
            mixerlab.verify_receipt(receipt)

    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "in.bin"
            arc = root / "out.hml"
            dst = root / "out.bin"
            src.write_bytes(WIKI_SAMPLE)
            self.assertEqual(mixerlab.cli(["compress", str(src), str(arc), "--table-bits", "12"]), 0)
            self.assertEqual(mixerlab.cli(["decompress", str(arc), str(dst)]), 0)
            self.assertEqual(dst.read_bytes(), WIKI_SAMPLE)


if __name__ == "__main__":
    unittest.main()
