"""Native-layout integration regressions; no alternate renderer or model.

Credit: original layout is COPPERFINCH-82D6's published helper. This suite
and checker composition repair are ZZ-Astra-Q7C4's independent contribution.
"""
from __future__ import annotations

import copy
import html
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import check_rendered_text as checker
import text_layout as layout

SOURCE = "EvidenceReferenceABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def group(value=SOURCE, width=120):
    markup, _ = layout.text_block(10, 15, value, width, 10, "#111111")
    return ET.fromstring(markup)


def svg(node, source=SOURCE, namespace=False):
    ns = ' xmlns="http://www.w3.org/2000/svg"' if namespace else ''
    return (f'<svg{ns}><desc>{html.escape(source)}</desc>'
            f'{ET.tostring(node, encoding="unicode")}</svg>')


class FullLayoutConservationTests(unittest.TestCase):
    def test_native_complete_long_identifier_is_not_truncation(self):
        self.assertEqual(checker.truncated_texts(svg(group())), [])

    def test_native_complete_short_qualifier(self):
        self.assertEqual(checker.truncated_texts(svg(group("Not a rating."),
                                                    "Not a rating.")), [])

    def test_whole_word_tail_loss_is_detected(self):
        value = "Evidence available. Not a rating."
        node = group(value)
        for child in list(node):
            node.remove(child)
        ET.SubElement(node, "text").text = "Evidence available."
        self.assertTrue(checker.truncated_texts(svg(node, value)))

    def test_loss_shorter_than_legacy_minimum_is_detected(self):
        node = group("No rating", width=200)
        node[0].text = "No "
        self.assertTrue(checker.truncated_texts(svg(node, "No rating")))

    def test_complete_row_removal_is_detected(self):
        node = group()
        node.remove(node[-1])
        self.assertTrue(checker.truncated_texts(svg(node)))

    def test_duplicated_row_is_detected(self):
        node = group()
        node.append(copy.deepcopy(node[0]))
        self.assertTrue(checker.truncated_texts(svg(node)))

    def test_reordered_rows_are_detected(self):
        node = group()
        first = node[0]
        node.remove(first)
        node.append(first)
        self.assertTrue(checker.truncated_texts(svg(node)))

    def test_short_character_substitution_is_detected(self):
        node = group("UNKNOWN", width=200)
        node[0].text = "KNOWN"
        self.assertTrue(checker.truncated_texts(svg(node, "UNKNOWN")))

    def test_missing_source_metadata_fails_closed(self):
        node = group("Not a rating.", width=200)
        del node.attrib["data-source-text"]
        self.assertTrue(checker.truncated_texts(svg(node, "Not a rating.")))

    def test_empty_source_still_requires_native_empty_text_row(self):
        self.assertEqual(checker.truncated_texts(svg(group(""), "")), [])
        node = group("")
        node.remove(node[0])
        self.assertTrue(checker.truncated_texts(svg(node, "")))

    def test_blank_paragraph_removal_is_detected(self):
        value = "alpha\n\nbeta"
        node = group(value)
        self.assertEqual(checker.truncated_texts(svg(node, value)), [])
        node.remove(node[1])
        self.assertTrue(checker.truncated_texts(svg(node, value)))

    def test_merging_distinct_paragraphs_is_detected(self):
        value = "alpha\nbeta"
        node = group(value)
        node[0].text = "alphabeta"
        node.remove(node[1])
        self.assertTrue(checker.truncated_texts(svg(node, value)))

    def test_newline_normalization_spaces_and_tabs_preserved(self):
        value = "  alpha\r\n\r\nbeta\r\tvalue  "
        self.assertEqual(checker.truncated_texts(svg(group(value, 200), value)), [])

    def test_unicode_combining_and_escaped_symbols_preserved(self):
        value = '信息系统 e\u0301vidence <scope owner="A&B">  evidence  '
        self.assertEqual(checker.truncated_texts(svg(group(value, 200), value)), [])

    def test_default_svg_namespace_supported(self):
        self.assertEqual(checker.truncated_texts(svg(group(), namespace=True)), [])

    def test_explicit_svg_namespace_prefix_supported(self):
        root = ET.fromstring(svg(group()))
        for element in root.iter():
            element.tag = "{http://www.w3.org/2000/svg}" + element.tag
        self.assertEqual(checker.truncated_texts(ET.tostring(root, encoding="unicode")), [])

    def test_uncovered_legacy_truncation_is_not_hidden_by_valid_group(self):
        doc = svg(group()).replace('</svg>',
            '<text>EvidenceRefe</text></svg>')
        self.assertEqual(checker.truncated_texts(doc), ["EvidenceRefe"])

    def test_hidden_description_cannot_replace_visible_text(self):
        node = group("Not a rating.", width=200)
        node[0].text = ""
        ET.SubElement(node, "desc").text = "Not a rating."
        self.assertTrue(checker.truncated_texts(svg(node, "Not a rating.")))

    def test_nested_full_group_is_not_accepted_as_plain_native_layout(self):
        node = group()
        outer = ET.Element('g', {'data-text-layout': 'full', 'data-source-text': SOURCE})
        outer.append(node)
        self.assertTrue(checker.truncated_texts(svg(outer)))

    def test_non_native_nested_text_requires_explicit_review(self):
        node = group("Not a rating.", width=200)
        node[0].text = None
        ET.SubElement(node[0], "tspan").text = "Not a rating."
        self.assertTrue(checker.truncated_texts(svg(node, "Not a rating.")))

    def test_seeded_native_roundtrip_and_character_loss(self):
        rng = random.Random(1635307)
        alphabet = "ABefgh0123456789  <>;&\t界\u0301"
        for index in range(400):
            value = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 200)))
            node = group(value, width=rng.randrange(8, 25)*10)
            with self.subTest(index=index):
                self.assertEqual(checker.truncated_texts(svg(node, value)), [])
                changed = next(child for child in reversed(list(node)) if child.text)
                changed.text = changed.text[:-1]
                self.assertTrue(checker.truncated_texts(svg(node, value)))


class XMLAndCLITests(unittest.TestCase):
    def test_different_xml_entity_spellings_compare_as_same_text(self):
        doc = ('<svg><desc>The A &amp; B evidence is consistently verified.</desc>'
               '<text>The A &#38; B evidence is consist</text></svg>')
        self.assertEqual(checker.truncated_texts(doc),
                         ['The A & B evidence is consist'])

    def test_xml_comments_do_not_supply_visible_text(self):
        doc = ('<svg><desc>The practice is applied consistently.</desc>'
               '<!-- <text>The practice is applied consist</text> --></svg>')
        self.assertEqual(checker.truncated_texts(doc), [])

    def test_malformed_xml_raises_instead_of_passing(self):
        with self.assertRaises(ET.ParseError):
            checker.truncated_texts('<svg><text>broken')

    def test_non_svg_document_raises_instead_of_passing(self):
        with self.assertRaises(ValueError):
            checker.truncated_texts('<html><body>not an SVG</body></html>')

    def test_foreign_namespace_svg_raises(self):
        with self.assertRaises(ValueError):
            checker.truncated_texts('<svg xmlns="urn:not-svg"/>')

    def run_cli(self, directory):
        flags = ['-O'] if sys.flags.optimize else []
        return subprocess.run([sys.executable, *flags, str(Path(checker.__file__)),
                               str(directory)], capture_output=True, text=True,
                              timeout=10, check=False)

    def test_cli_valid_complete_document_returns_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'good.svg').write_text(svg(group()), encoding='utf-8')
            result = self.run_cli(directory)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_cli_detected_text_loss_returns_one(self):
        with tempfile.TemporaryDirectory() as directory:
            node = group('Not a rating.', 200)
            node[0].text = 'Not a '
            (Path(directory)/'loss.svg').write_text(svg(node, 'Not a rating.'), encoding='utf-8')
            result = self.run_cli(directory)
            self.assertEqual(result.returncode, 1, result.stdout+result.stderr)

    def test_cli_malformed_document_returns_two_and_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'a-broken.svg').write_text('<svg><text>broken', encoding='utf-8')
            (Path(directory)/'b-good.svg').write_text(svg(group()), encoding='utf-8')
            result = self.run_cli(directory)
            self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
            self.assertIn('a-broken.svg', result.stdout)
            self.assertIn('files=2', result.stdout)
            self.assertNotIn('Traceback', result.stderr)

    def test_cli_invalid_utf8_returns_two(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'bad.svg').write_bytes(b'<svg>\xff</svg>')
            result = self.run_cli(directory)
            self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
            self.assertIn('bad.svg', result.stdout)
            self.assertNotIn('Traceback', result.stderr)

    def test_cli_empty_directory_returns_two(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.run_cli(directory).returncode, 2)


if __name__ == '__main__':
    unittest.main()
