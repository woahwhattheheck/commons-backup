#!/usr/bin/env python3
"""Detect mid-word truncation and incomplete content-sized text groups.

OP5-CONTROL's original detector compares visible text with the retained desc.
Complete wrapped groups are now compared as a whole, so a line break in a long
identifier is not itself mistaken for lost content. The visible children must
also match the group's declared source; metadata alone is never a pass.
Native paragraph boundaries and empty paragraphs are preserved, and a declared
full-text group without source metadata is a finding rather than a skip.
Native full-text groups contain plain, direct text children, as emitted by
text_layout.text_block; unsupported structures are findings, not silent passes.

This checks XML text conservation, not pixels, CSS visibility, clipping,
font support, source authenticity or accessibility conformance. Invalid XML
and non-SVG input are errors, never evidence of complete text.

Paragraph/input composition and native-layout regressions: ZZ-Astra-Q7C4.
COPPERFINCH-82D6 retains the whole-group checker and renderer implementation.

    python3 check_rendered_text.py <dir-of-svgs>
"""
import glob
import html
import os
import re
import sys
import xml.etree.ElementTree as ET


def strip_markup(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _svg_tag(node, name):
    return node.tag in (name, "{http://www.w3.org/2000/svg}" + name)


def _native_layout_matches(source, lines):
    """Match complete paragraphs across consecutive native text rows.

    Joining all rows would miss a lost blank paragraph or merged paragraphs.
    Only the renderer's CRLF/CR newline normalization is permitted; other
    whitespace, order, case and characters must agree exactly.
    """
    index = 0
    paragraphs = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for paragraph in paragraphs:
        if not paragraph:
            if index >= len(lines) or lines[index] != "":
                return False
            index += 1
            continue
        consumed = 0
        while consumed < len(paragraph):
            if index >= len(lines):
                return False
            line = lines[index]
            if not line or not paragraph.startswith(line, consumed):
                return False
            consumed += len(line)
            index += 1
    return index == len(lines)


def truncated_texts(svg_source, min_len=12):
    """Report visible runs cut mid-word or missing their declared content."""
    root = ET.fromstring(svg_source)
    if not _svg_tag(root, "svg"):
        raise ValueError("document root must be SVG")
    desc = " ".join("".join(node.itertext()) for node in root.iter()
                    if _local(node.tag) == "desc").strip()
    found = []
    consumed = set()
    runs = []
    for node in root.iter():
        if node.get("data-text-layout") != "full":
            continue
        consumed.update(id(child) for child in node.iter() if _svg_tag(child, "text"))
        expected = node.get("data-source-text")
        if expected is None:
            found.append("FULL_TEXT missing data-source-text")
            continue
        children = list(node)
        if (not _svg_tag(node, "g") or (node.text or "").strip() or
                any(not _svg_tag(child, "text") or len(child) or
                    (child.tail or "").strip() for child in children)):
            found.append("FULL_TEXT unsupported native layout structure")
            continue
        lines = [child.text or "" for child in children]
        visible = "".join(lines)
        if not _native_layout_matches(expected, lines):
            found.append(visible.strip() or "<missing wrapped text>")
        else:
            # Preserve COPPERFINCH's check against desc even when shortened
            # metadata and shortened visible rows agree with one another.
            runs.append(visible.strip())
    for node in root.iter():
        if _local(node.tag) == "text" and id(node) not in consumed:
            runs.append("".join(node.itertext()).strip())
    for visible in runs:
        if len(visible) < min_len:
            continue
        at = desc.find(visible)
        if at == -1:
            continue
        nxt = desc[at + len(visible):at + len(visible) + 1]
        if nxt and nxt.isalnum():
            found.append(visible)
    return found


def main(argv):
    root = argv[1] if len(argv) > 1 else "."
    files = sorted(glob.glob(os.path.join(root, "*.svg")))
    if not files:
        print(f"no .svg files under {root}")
        return 2
    affected, total, invalid = 0, 0, 0
    for path in files:
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                cut = truncated_texts(fh.read())
        except (OSError, UnicodeError, ET.ParseError, ValueError) as exc:
            invalid += 1
            print(f"INVALID {os.path.basename(path)}: {exc}")
            continue
        if cut:
            affected += 1
            total += len(cut)
            print(f"TRUNCATED {os.path.basename(path)}  ({len(cut)})")
            for visible in cut:
                print(f"    ...{visible[-60:]!r}")
    print("-" * 70)
    print(f"files={len(files)}  affected={affected}  truncated-text-runs={total}  invalid={invalid}")
    return 2 if invalid else (1 if total else 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
