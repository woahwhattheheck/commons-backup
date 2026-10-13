"""Regression tests for complete, content-sized SVG text (standard library)."""
import math
import random
import unittest
import xml.etree.ElementTree as ET

import text_layout as layout


class TextLayoutTests(unittest.TestCase):
    def test_empty_text_has_one_line(self):
        self.assertEqual(layout.wrap_text("", 100, 10), ("",))

    def test_word_boundary_wrap_retains_spaces(self):
        text = "The practice is applied consistently across the entire group."
        lines = layout.wrap_text(text, 160, 10)
        self.assertEqual("".join(lines), text)
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(len(line) <= 16 for line in lines))

    def test_no_eighty_character_title_limit(self):
        text = "A complete roadmap title containing every necessary qualifier " * 6
        self.assertEqual("".join(layout.wrap_text(text, 220, 11.5)), text)

    def test_unbroken_identifiers_keep_all_characters(self):
        text = "EvidenceReference" * 100
        self.assertEqual("".join(layout.wrap_text(text, 120, 10)), text)

    def test_newlines_and_blank_paragraphs_are_actual_rows(self):
        self.assertEqual(layout.wrap_text("alpha\r\n\r\nbeta", 100, 10),
                         ("alpha", "", "beta"))

    def test_wide_characters_respect_cell_budget(self):
        text = "信息系统" * 12
        lines = layout.wrap_text(text, 100, 10)
        self.assertEqual("".join(lines), text)
        self.assertTrue(all(sum(layout._units(c) for c in line) <= 10 for line in lines))

    def test_combining_marks_are_not_discarded(self):
        text = "e\u0301vidence " * 18
        self.assertEqual("".join(layout.wrap_text(text, 100, 10)), text)

    def test_xml_escaping_does_not_change_text(self):
        text = '<scope owner="A&B"> complete \'quoted\' value'
        markup, _ = layout.text_block(2, 3, text, 160, 10, "#111111")
        root = ET.fromstring(markup)
        self.assertEqual(root.attrib["data-source-text"], text)
        self.assertEqual("".join(node.text or "" for node in root), text)
        self.assertIsNone(root.find("scope"))

    def test_original_newline_attribute_survives_xml(self):
        text = "alpha\nbeta\tvalue"
        markup, _ = layout.text_block(2, 3, text, 180, 10, "#111111")
        root = ET.fromstring(markup)
        self.assertEqual(root.attrib["data-source-text"], text)
        self.assertEqual("".join(node.text or "" for node in root), "alphabeta\tvalue")

    def test_height_matches_last_line_plus_descender_room(self):
        text = "A long explanation " * 12
        markup, bottom = layout.text_block(4, 7, text, 150, 10, "#111111")
        root = ET.fromstring(markup)
        expected = 7 + len(root) * 14
        self.assertEqual(bottom, expected)
        self.assertEqual(layout.text_height(text, 150, 10), bottom - 7)
        self.assertLess(float(root[-1].attrib["y"]), bottom)

    def test_repeated_render_is_byte_deterministic(self):
        args = (4, 7, "Evidence unavailable, not a zero rating.", 150, 10, "#111111")
        self.assertEqual(layout.text_block(*args), layout.text_block(*args))

    def test_invalid_dimensions_fail_explicitly(self):
        for value in (0, -1, float("inf"), float("nan"), True, "100", None):
            with self.subTest(value=value):
                with self.assertRaises((ValueError, TypeError)):
                    layout.wrap_text("text", value, 10)
                with self.assertRaises((ValueError, TypeError)):
                    layout.wrap_text("text", 100, value)

    def test_too_narrow_column_fails_instead_of_truncating(self):
        with self.assertRaises(ValueError):
            layout.wrap_text("text", 5, 10)
        with self.assertRaises(ValueError):
            layout.wrap_text("界", 10, 10)

    def test_non_text_is_not_silently_coerced(self):
        for value in (None, 42, False, ["text"]):
            with self.assertRaises(TypeError):
                layout.wrap_text(value, 100, 10)

    def test_seeded_text_roundtrip(self):
        randomizer = random.Random(826)
        alphabet = "ABCdefghijk  -:/0123456789<&>"
        for _ in range(200):
            text = "".join(randomizer.choice(alphabet) for _ in range(randomizer.randrange(1, 400)))
            lines = layout.wrap_text(text, randomizer.randrange(5, 30) * 10, 10)
            self.assertEqual("".join(lines), text)


if __name__ == "__main__":
    unittest.main()
