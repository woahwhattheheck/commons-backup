from __future__ import annotations
import random
import unittest
import mixerlab
import match_model

WIKI_SAMPLE = (b"<page>\n  <title>Compression</title>\n  <revision>\n    <text xml:space=\"preserve\">"
               b"[[Compression]] is {{useful}} &amp; reversible. http://example.test\n"
               b"</text>\n  </revision>\n</page>\n") * 20

class MatchModelTests(unittest.TestCase):
    def test_roundtrip_hostile_matrix(self):
        rng = random.Random(0x5A17)
        cases = [
            b"", b"a", b"a" * 4096, WIKI_SAMPLE,
            bytes(rng.randrange(256) for _ in range(2048)),
            bytes(range(256)) * 8,
            (b"abcd" * 2000) + b"abce" + (b"abcd" * 2000),
        ]
        for transform in (False, True):
            for data in cases:
                with self.subTest(transform=transform, length=len(data)):
                    archive = match_model.compress_bytes(data, use_transform=transform,
                                                         table_bits=12, match_bits=12)
                    self.assertEqual(match_model.decompress_bytes(archive), data)

    def test_deterministic(self):
        a = match_model.compress_bytes(WIKI_SAMPLE, table_bits=12, match_bits=12)
        b = match_model.compress_bytes(WIKI_SAMPLE, table_bits=12, match_bits=12)
        self.assertEqual(a, b)

    def test_payload_corruption_and_truncation_fail_closed(self):
        archive = bytearray(match_model.compress_bytes(WIKI_SAMPLE, table_bits=12, match_bits=12))
        meta, payload = match_model._parse_archive(bytes(archive))
        self.assertGreater(len(payload), 2)
        archive[mixerlab._HEADER.size + len(payload) // 2] ^= 0x20
        with self.assertRaisesRegex(ValueError, "payload SHA-256"):
            match_model.decompress_bytes(bytes(archive))
        clean = match_model.compress_bytes(WIKI_SAMPLE, table_bits=12, match_bits=12)
        with self.assertRaises(ValueError):
            match_model.decompress_bytes(clean[:-1])
        with self.assertRaises(ValueError):
            match_model.decompress_bytes(clean + b"x")

    def test_fixed_memory_does_not_grow(self):
        model = match_model.FixedMatchPredictor(12)
        before = model.memory_bytes
        for i in range(100000):
            predicted, key, slot = model.predict()
            model.push((i * 17) & 0xFF, predicted, key, slot)
        self.assertEqual(model.memory_bytes, before)
        self.assertEqual(model.position, 100000)

    def test_exact_landed_fixture_beats_baseline_archive(self):
        result = match_model.paired_benchmark(WIKI_SAMPLE, table_bits=12, match_bits=12)
        self.assertTrue(result["archive_improved"], result)
        self.assertLess(result["candidate_archive_bytes"], result["baseline_archive_bytes"])
        self.assertEqual(result["input_sha256"], result["roundtrip_sha256"])
        self.assertFalse(result["official_enwik9_claim"])

    def test_no_false_improvement_requirement_on_noise(self):
        rng = random.Random(99173)
        data = bytes(rng.randrange(256) for _ in range(4096))
        archive = match_model.compress_bytes(data, use_transform=False,
                                             table_bits=12, match_bits=12)
        self.assertEqual(match_model.decompress_bytes(archive), data)

if __name__ == "__main__": unittest.main()
