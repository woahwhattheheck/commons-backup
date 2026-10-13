#!/usr/bin/env python3
"""Generate the two-page S139 method PDF from its reviewed Markdown source.

Cloud execution:
    python3 -B build_method_pdf.py S139-method.md /absolute/path/S139-method.pdf
Dependencies: reportlab. Render and visually inspect the resulting PDF separately.
The output must be new and its parent directory must already exist.
"""
import argparse
from html import escape
from io import BytesIO
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

PAGEBREAK = "<!-- PAGEBREAK -->"


def inline(text):
    """Convert only the small Markdown subset used by the reviewed source."""
    text = escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\((https://[^\s)]+)\)",
                  lambda m: '<link href="' + escape(m[2], quote=True) +
                  '" color="#174568">' + m[1] + "</link>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`([^`]+)`", r'<font name="Courier" size="9">\1</font>', text)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#B5B9BC"))
    canvas.setLineWidth(0.4)
    canvas.line(doc.leftMargin, 14 * mm, A4[0] - doc.rightMargin, 14 * mm)
    canvas.setFillColor(colors.HexColor("#555B60"))
    canvas.setFont("Helvetica", 8)
    canvas.drawString(doc.leftMargin, 10 * mm, "ROADEF 2026 - S139")
    canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, str(doc.page))
    canvas.restoreState()


class TwoPageDocument(SimpleDocTemplate):
    def afterPage(self):
        if self.page > 2:
            raise ValueError("Layout exceeded two pages; revise before delivery.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if not output.parent.is_dir():
        parser.error("Output parent directory must already exist.")
    if output.exists() or output == source:
        parser.error("Output must be a new file, separate from the source.")
    text = source.read_text(encoding="utf-8")
    if not text.isascii():
        parser.error("Source must use ASCII typography.")
    if text.count(PAGEBREAK) != 1:
        parser.error("Source must contain exactly one explicit page break.")
    blocks = [part.strip() for part in re.split(r"\n\s*\n", text.strip())]
    if not blocks or not blocks[0].startswith("# "):
        parser.error("Source must begin with one title.")
    if any(block.startswith("# ") for block in blocks[1:]):
        parser.error("Only one title is supported.")
    body = ParagraphStyle(
        "Body", fontName="Times-Roman", fontSize=10.7, leading=14.2,
        textColor=colors.HexColor("#202427"), alignment=TA_LEFT,
        spaceAfter=8, allowWidows=0, allowOrphans=0)
    title = ParagraphStyle(
        "Title", parent=body, fontName="Helvetica-Bold", fontSize=15,
        leading=19, spaceAfter=13, keepWithNext=True)
    references = ParagraphStyle(
        "References", parent=body, fontSize=9, leading=11.5, spaceAfter=0)
    story = []
    for block in blocks:
        if block == PAGEBREAK:
            story.append(PageBreak())
        elif block.startswith("# "):
            story.append(Paragraph(inline(block[2:]), title))
        else:
            style = references if block.startswith("**Sources.**") else body
            story.append(Paragraph(inline(" ".join(block.splitlines())), style))
    buffer = BytesIO()
    doc = TwoPageDocument(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=20 * mm,
        title="S139 - A portfolio for T-adaptive segment routing",
        author="TokenJunkieLabs contributors",
        subject="ROADEF 2026 method description", pageCompression=1)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    if doc.page != 2:
        raise ValueError("Expected two pages; inspect the source page break.")
    # Publish complete bytes only, without replacing any existing artifact.
    with output.open("xb") as stream:
        stream.write(buffer.getvalue())
    print(str(output))


if __name__ == "__main__":
    main()

