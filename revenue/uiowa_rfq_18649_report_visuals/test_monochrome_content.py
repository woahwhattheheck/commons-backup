"""Export regressions: colour conversion must not rewrite evidence content."""
import unittest
import xml.etree.ElementTree as ET
from xml.parsers import expat

import contrast
import monochrome


def svg(body, attributes=""):
    return '<svg xmlns="http://www.w3.org/2000/svg" ' + attributes + '>' + body + '</svg>'


class MonochromeContentTests(unittest.TestCase):
    def test_visible_reference_and_description_keep_their_bytes(self):
        source = svg('<desc>Evidence #abc and #123456.</desc><text fill="#f00">Evidence #abc and #123456.</text>')
        result = monochrome.to_monochrome(source)
        self.assertEqual(result, source.replace('fill="#f00"', 'fill="#7F7F7F"'))

    def test_pattern_fragment_reference_is_not_a_colour(self):
        source = svg('<defs><pattern id="abc"><rect fill="#ff0000"/></pattern></defs><rect fill="url(#abc)"/>')
        result = monochrome.to_monochrome(source)
        self.assertIn('id="abc"', result)
        self.assertIn('fill="url(#abc)"', result)
        self.assertIn('fill="#7F7F7F"', result)

    def test_link_fragments_and_metadata_keep_their_bytes(self):
        source = svg('<a href="#abc"><text fill="#f00" data-source-text="#abc &amp; #abcdef" data-colour="#123456">#abcdef</text></a>')
        self.assertEqual(monochrome.to_monochrome(source),
                         source.replace('fill="#f00"', 'fill="#7F7F7F"'))

    def test_only_supported_paint_attributes_are_converted(self):
        source = svg('<rect fill="#f00" stroke="#00f" color="#0f0" stop-color="#123456" flood-color="#ABC" lighting-color="#12f" solid-color="#123abc"/>')
        result = monochrome.to_monochrome(source)
        self.assertTrue(monochrome.is_monochrome(result))
        self.assertFalse(monochrome.is_monochrome(source))
        ET.fromstring(result)

    def test_colour_listing_ignores_references_and_written_hex_strings(self):
        source = svg('<text fill="#111111">#abc</text><rect fill="url(#f00)" data-ref="#00ff00"/>')
        self.assertEqual(monochrome.colours_in(source), ['#111111'])
        self.assertTrue(monochrome.is_monochrome(source))

    def test_comments_are_not_parsed_as_live_paint(self):
        source = svg('<!-- <rect fill="#f00"/> --><text fill="#000000">#f00</text>')
        self.assertEqual(monochrome.to_monochrome(source), source)

    def test_cdata_is_not_rewritten_as_paint(self):
        source = svg('<text><![CDATA[Example <rect fill="#f00"/>]]></text>')
        self.assertEqual(monochrome.to_monochrome(source), source)

    def test_greater_than_inside_quoted_attribute_does_not_end_tag(self):
        source = svg('<text data-source-text="a > b and #abc" fill="#f00">a &gt; b</text>')
        self.assertEqual(monochrome.to_monochrome(source),
                         source.replace('fill="#f00"', 'fill="#7F7F7F"'))

    def test_unicode_byte_offsets_are_correct(self):
        source = svg('<text>情報 #abc café</text><text fill="#f00">完整记录</text>')
        self.assertEqual(monochrome.to_monochrome(source),
                         source.replace('fill="#f00"', 'fill="#7F7F7F"'))

    def test_unicode_attribute_names_are_not_matched_by_ascii_suffix(self):
        source = svg('<text 測fill="#f00" fill="#000000">#abc</text>')
        self.assertEqual(monochrome.to_monochrome(source), source)

    def test_entity_encoded_paint_and_reference_text_are_distinguished(self):
        source = svg('<text fill="&#35;f00">&#35;abc</text>')
        self.assertEqual(monochrome.to_monochrome(source),
                         source.replace('fill="&#35;f00"', 'fill="#7F7F7F"'))

    def test_single_quotes_whitespace_and_newlines_are_preserved(self):
        source = svg("\n<rect fill = '#f00'\n stroke=\"#00f\"/>\n")
        expected = source.replace("'#f00'", "'#7F7F7F'").replace('"#00f"', '"#4C4C4C"')
        self.assertEqual(monochrome.to_monochrome(source), expected)

    def test_named_black_white_and_no_paint_remain_monochrome(self):
        source = svg('<rect fill="black" stroke="white"/><g color="#222222"><text fill="currentColor">x</text></g><path fill="none" stroke="inherit"/>')
        self.assertTrue(monochrome.is_monochrome(monochrome.to_monochrome(source)))

    def test_unknown_named_colour_is_not_a_false_monochrome_pass(self):
        source = svg('<rect fill="red"/>')
        with self.assertRaises(monochrome.UnsupportedPaint):
            monochrome.to_monochrome(source)
        with self.assertRaises(monochrome.UnsupportedPaint):
            monochrome.is_monochrome(source)

    def test_inline_css_is_explicitly_unsupported(self):
        with self.assertRaises(monochrome.UnsupportedPaint):
            monochrome.to_monochrome(svg('<rect style="fill:#f00"/>'))

    def test_embedded_stylesheet_is_explicitly_unsupported(self):
        with self.assertRaises(monochrome.UnsupportedPaint):
            monochrome.to_monochrome(svg('<style>text{fill:#f00}</style><text>x</text>'))

    def test_external_stylesheet_is_explicitly_unsupported(self):
        with self.assertRaises(monochrome.UnsupportedPaint):
            monochrome.to_monochrome('<?xml-stylesheet href="styles.css"?>' + svg(''))

    def test_external_paint_is_not_silently_claimed_monochrome(self):
        with self.assertRaises(monochrome.UnsupportedPaint):
            monochrome.to_monochrome(svg('<rect fill="url(https://example.invalid/paint.svg#p)"/>'))

    def test_doctype_is_refused(self):
        with self.assertRaises(monochrome.UnsupportedPaint):
            monochrome.to_monochrome('<!DOCTYPE svg>' + svg(''))

    def test_malformed_or_non_svg_source_is_not_a_clean_pass(self):
        with self.assertRaises(expat.ExpatError):
            monochrome.to_monochrome('<svg>')
        with self.assertRaises(ValueError):
            monochrome.to_monochrome('<report/>')
        with self.assertRaises(TypeError):
            monochrome.to_monochrome(None)

    def test_repeated_conversion_is_deterministic_and_idempotent(self):
        source = svg('<rect fill="#08f"/><text stroke="#31a">#abc</text>')
        first = monochrome.to_monochrome(source)
        self.assertEqual(first, monochrome.to_monochrome(source))
        self.assertEqual(first, monochrome.to_monochrome(first))

    def test_luminance_calculation_remains_original(self):
        for colour in ('#123456', '#f00', '#00f', '#def', '#FFFFFF', '#000000'):
            source = svg('<rect fill="' + colour + '"/>')
            self.assertIn('fill="' + contrast.to_grayscale(colour) + '"',
                          monochrome.to_monochrome(source))

    def test_separation_report_stays_numerical_and_symmetric(self):
        fills = {'a': '#f00', 'b': '#0000ff', 'c': '#ffffff'}
        rows = monochrome.separation_report(fills)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r[2] for r in rows], sorted(r[2] for r in rows))
        for a, b, ratio in rows:
            self.assertEqual(ratio, contrast.grayscale_contrast(fills[a], fills[b]))


if __name__ == '__main__':
    unittest.main()
