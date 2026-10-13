"""Exercise the actual native layout -> monochrome -> checker handoff.

ZZ-Astra-Q7C4 contribution. Renderer, contrast arithmetic and monochrome
implementation remain unchanged and retain OP5-EMBER/COPPERFINCH credit.
These are synthetic text-conservation checks, not pixel/accessibility approval.
"""
from __future__ import annotations

import html
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import check_rendered_text as checker
import monochrome
import text_layout

TEXTS = (
    "",
    "\n",
    "Evidence #abc is retained.\nNot a rating.",
    "Alpha\n\nBeta",
    "Reference url(#abc) and fill='#123456' remain evidence.",
    '信息系统 e\u0301vidence & <scope> "A"',
    "EvidenceReferenceABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" * 2,
    " \t two  spaces\r\n \rvalue",
)
INKS = ("#abc", "#123456", "#D4357A", "#111111")
WIDTHS = (80, 120, 240)
PAINT = frozenset(("fill", "stroke", "color", "stop-color", "flood-color",
                   "lighting-color", "solid-color"))


def document(value, width=120, ink="#123456", namespace=True):
    block, _ = text_layout.text_block(10, 15, value, width, 10, ink)
    ns = ' xmlns="http://www.w3.org/2000/svg"' if namespace else ""
    return f'<svg{ns}><desc>{html.escape(value)}</desc>{block}</svg>'


def nonpaint_tree(source):
    """Independent semantic projection: ignore paint, retain other fields."""
    root = ET.fromstring(source)
    return [(node.tag, sorted((k, v) for k, v in node.attrib.items() if k not in PAINT),
             node.text, node.tail) for node in root.iter()]


def first_group(root):
    return next(node for node in root.iter() if node.get("data-text-layout") == "full")


class CheckerMonochromeInteropTests(unittest.TestCase):
    def test_192_native_text_colour_width_namespace_roundtrips(self):
        count = 0
        for value in TEXTS:
            for width in WIDTHS:
                for ink in INKS:
                    for namespace in (False, True):
                        with self.subTest(value=value, width=width, ink=ink, namespace=namespace):
                            original = document(value, width, ink, namespace)
                            output = monochrome.to_monochrome(original)
                            self.assertEqual(nonpaint_tree(output), nonpaint_tree(original))
                            self.assertEqual(checker.truncated_texts(original), [])
                            self.assertEqual(checker.truncated_texts(output), [])
                            self.assertTrue(monochrome.is_monochrome(output))
                            self.assertEqual(monochrome.to_monochrome(output), output)
                            count += 1
        self.assertEqual(count, 192)

    def test_colour_like_evidence_is_not_rewritten_with_paint(self):
        original = document("Reference #abc / #123456 / url(#abc).", ink="#abc")
        output = monochrome.to_monochrome(original)
        self.assertNotEqual(original, output)
        before, after = ET.fromstring(original), ET.fromstring(output)
        self.assertEqual(first_group(before).get("data-source-text"),
                         first_group(after).get("data-source-text"))
        self.assertEqual(list(before)[0].text, list(after)[0].text)
        self.assertEqual(checker.truncated_texts(output), [])

    def test_local_fragment_reference_is_not_a_paint_colour(self):
        original = document("Evidence #abc points to url(#abc).")
        original = original.replace("</svg>", '<defs><linearGradient id="abc">'
            '<stop stop-color="#ff3300"/></linearGradient></defs>'
            '<rect fill="url(#abc)" stroke="#123456"/></svg>')
        output = monochrome.to_monochrome(original)
        self.assertIn('id="abc"', output)
        self.assertIn('fill="url(#abc)"', output)
        self.assertEqual(nonpaint_tree(output), nonpaint_tree(original))
        self.assertEqual(checker.truncated_texts(output), [])

    def test_missing_metadata_remains_a_finding_after_conversion(self):
        root = ET.fromstring(document("Not a rating."))
        del first_group(root).attrib["data-source-text"]
        original = ET.tostring(root, encoding="unicode")
        output = monochrome.to_monochrome(original)
        self.assertEqual(checker.truncated_texts(original), checker.truncated_texts(output))
        self.assertTrue(checker.truncated_texts(output))

    def test_blank_paragraph_loss_remains_a_finding_after_conversion(self):
        root = ET.fromstring(document("Alpha\n\nBeta", width=240))
        group = first_group(root)
        group.remove(list(group)[1])
        original = ET.tostring(root, encoding="unicode")
        output = monochrome.to_monochrome(original)
        self.assertEqual(checker.truncated_texts(original), checker.truncated_texts(output))
        self.assertTrue(checker.truncated_texts(output))

    def test_qualifier_loss_remains_a_finding_after_conversion(self):
        root = ET.fromstring(document("Evidence available. Not a rating.", width=240))
        group = first_group(root)
        for child in list(group):
            group.remove(child)
        ET.SubElement(group, "text", {"fill": "#abc"}).text = "Evidence available."
        original = ET.tostring(root, encoding="unicode")
        output = monochrome.to_monochrome(original)
        self.assertEqual(checker.truncated_texts(original), checker.truncated_texts(output))
        self.assertTrue(checker.truncated_texts(output))

    def test_inline_css_refusal_is_not_a_clean_checker_pass(self):
        original = document("Not a rating.").replace("<svg ", '<svg style="fill:red" ', 1)
        with self.assertRaises(monochrome.UnsupportedPaint):
            monochrome.to_monochrome(original)

    def test_actual_cli_reports_later_monochrome_loss_after_bad_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad = root / "a-invalid.svg"
            bad.write_bytes(b"<svg>")
            good = monochrome.to_monochrome(document("Complete evidence #abc."))
            (root / "b-complete.svg").write_text(good, encoding="utf-8")
            loss_root = ET.fromstring(document("Alpha\n\nBeta"))
            group = first_group(loss_root)
            group.remove(list(group)[1])
            loss = monochrome.to_monochrome(ET.tostring(loss_root, encoding="unicode"))
            (root / "c-loss.svg").write_text(loss, encoding="utf-8")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            flags = ["-O"] if sys.flags.optimize else []
            result = subprocess.run([sys.executable, *flags, str(Path(checker.__file__)),
                                     str(root)], capture_output=True, text=True, timeout=10,
                                    check=False)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("INVALID a-invalid.svg", result.stdout)
            self.assertIn("TRUNCATED c-loss.svg", result.stdout)
            self.assertIn("files=3  affected=1", result.stdout)
            self.assertIn("invalid=1", result.stdout)
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
