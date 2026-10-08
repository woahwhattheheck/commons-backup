"""Focused, offline tests of MOVA work-order preservation and Slack limits."""
import hashlib
import unittest

from chunk_slack import split_messages


class ChunkDeliveryTests(unittest.TestCase):
    def test_split_is_lossless_bounded_and_stable(self):
        original = "MOVA sprint\n" + "".join(f"PUBLISH | org/repo#{i} | $25 | provider://item{i}\n" for i in range(70))
        first = split_messages(original, 320)
        self.assertGreater(len(first), 1)
        self.assertEqual(first, split_messages(original, 320))
        restored = "".join(chunk["text"].split("\n", 1)[1] for chunk in first)
        self.assertEqual(original, restored)
        full_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
        for i, chunk in enumerate(first, 1):
            self.assertLessEqual(len(chunk["text"].encode("utf-8")), 320)
            self.assertIn(f"sha256:{full_hash} | part {i}/{len(first)}", chunk["text"])

    def test_unicode_counts_utf8_bytes_not_characters(self):
        source = "🧾 $25 payout 🔒\r\n" * 18
        parts = split_messages(source, 256)
        self.assertEqual(source, "".join(p["text"].split("\n", 1)[1] for p in parts))
        self.assertTrue(all(len(p["text"].encode("utf-8")) <= 256 for p in parts))

    def test_oversize_line_fails_instead_of_truncating(self):
        with self.assertRaisesRegex(ValueError, "indivisible"):
            split_messages("/claim #454 " + "a" * 500, 256)
        with self.assertRaises(ValueError):
            split_messages("", 256)


if __name__ == "__main__":
    unittest.main()
