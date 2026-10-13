"""Unicode scalar-value regressions for draft transport."""
import unittest

from . import bundle, examples


class UnicodeTests(unittest.TestCase):
    def test_unpaired_surrogates_are_structured_errors(self):
        for raw in (b'{"x":"\\ud800"}', b'{"\\udfff":1}',
                    b'{"nested":["\\udc00"]}'):
            with self.subTest(raw=raw):
                with self.assertRaises(bundle.BundleError) as error:
                    bundle.parse_object(raw, "input")
                self.assertEqual(error.exception.code, "JSON_INVALID")

    def test_paired_surrogates_and_supplementary_unicode_survive(self):
        raw = b'{"x":"\\ud83d\\ude00"}'
        self.assertEqual(bundle.parse_object(raw, "input")["x"], "😀")
        report, handoff = examples.synthetic_pair()
        handoff["cell_notes"][0]["analyst_note"] = "😀 supplementary text"
        bundle.verify_bundle(bundle.build_bundle(bundle.canonical(report),
                                                  bundle.canonical(handoff)))
