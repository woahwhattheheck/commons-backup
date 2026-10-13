"""The old mid-word check must understand complete multi-line visible text."""
import html
import tempfile
import unittest
from pathlib import Path

import check_rendered_text as checker
import text_layout as layout


def document(source, markup):
    return '<svg xmlns="http://www.w3.org/2000/svg"><desc>' + html.escape(source) + '</desc>' + markup + '</svg>'


class WrappedCheckerTests(unittest.TestCase):
    def test_long_identifier_can_span_several_lines(self):
        source = "EvidenceReference" * 20
        markup, _ = layout.text_block(0, 0, source, 140, 10, "#111111")
        self.assertEqual(checker.truncated_texts(document(source, markup)), [])

    def test_missing_last_line_is_not_hidden_by_metadata(self):
        source = "The original evidence explanation must remain complete."
        markup, _ = layout.text_block(0, 0, source, 160, 10, "#111111")
        start = markup.rfind("<text")
        damaged = markup[:start] + "</g>"
        self.assertTrue(checker.truncated_texts(document(source, damaged)))

    def test_blank_wrapped_group_is_not_a_pass(self):
        source = "Full source present only in an attribute."
        markup = '<g data-text-layout="full" data-source-text="' + source + '"></g>'
        self.assertEqual(checker.truncated_texts(document(source, markup)),
                         ["<missing wrapped text>"])

    def test_forged_short_source_still_gets_original_desc_check(self):
        source = "The practice is applied consistently across the group."
        shortened = "The practice is applied consist"
        markup, _ = layout.text_block(0, 0, shortened, 160, 10, "#111111")
        self.assertEqual(checker.truncated_texts(document(source, markup)), [shortened])

    def test_xml_entities_compare_as_actual_characters(self):
        source = 'Written evidence includes <scope> & "quoted" constraints.'
        markup, _ = layout.text_block(0, 0, source, 160, 10, "#111111")
        self.assertEqual(checker.truncated_texts(document(source, markup)), [])

    def test_malformed_svg_returns_invalid_not_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "invalid.svg").write_text("<svg>", encoding="utf-8")
            self.assertEqual(checker.main(["checker", tmp]), 2)


if __name__ == "__main__":
    unittest.main()
