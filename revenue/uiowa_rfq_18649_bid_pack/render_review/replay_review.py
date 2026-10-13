#!/usr/bin/env python3
"""Replay a byte-bound review of TOPAZ's synthetic bid-pack PDF.

This is an evidence replay, not the bid-pack assembler or a PDF accessibility
certifier. PyMuPDF supplies an independent reader/rasterizer. The original
visual inspection used Poppler; replays never inherit a visual-review verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

try:
    import pymupdf as pdf
except ImportError as exc:
    raise SystemExit("PyMuPDF is required for this independent PDF replay; it was not run.") from exc

REVIEWED_SHA256 = "b93f974d59c166f6f01897b73396d29ac3ad50000c8bf98b6b8bedac2cbb42ed"
REVIEWED_GIT_BLOB = "d0e35315a08158067b03af03402cac20eba7a4b7"
DEFAULT_PDF = Path(__file__).with_name("reviewed-proposal.pdf")
# One-based physical pages. Target strings identify the actual visible anchor,
# not merely a syntactically valid PDF destination on some page.
DESTINATIONS = {
    2: [(3, "1. Cover Letter"), (4, "2. Executive Summary"),
        (5, "3. Firm Qualifications"), (6, "4. Scope of Work and Methodology"),
        (7, "5. Staffing and Key Personnel"), (8, "6. Price Proposal"),
        (9, "7. Exceptions and Assumptions")],
    3: [(6, "4. Scope of Work and Methodology"), (8, "6. Price Proposal")],
    4: [(6, "4. Scope of Work and Methodology"),
        (7, "5. Staffing and Key Personnel"), (2, "ATT-FIN-01")],
    5: [(2, "ATT-REF-01"), (2, "ATT-QUAL-03")],
    6: [(7, "5. Staffing and Key Personnel"), (8, "6. Price Proposal")],
    7: [(2, "ATT-QUAL-03")],
    8: [(6, "4. Scope of Work and Methodology"), (2, "ATT-FIN-02"), (2, "ATT-FIN-01")],
    9: [(8, "6. Price Proposal")],
}
OUTLINES = [("Document Map", 2), ("Attachment Index", 2)] + [
    (target, page) for page, target in DESTINATIONS[2]
]


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def inspect_pdf(data: bytes) -> dict:
    """Return observations and bounded findings, never a visual approval.

    The expected content/navigation contract applies only to this nine-page
    review fixture. Other documents need their own review, not a forced pass.
    """
    sha = hashlib.sha256(data).hexdigest()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    findings: list[dict] = []

    def record(code: str, page: int | None, detail: str) -> None:
        findings.append({"code": code, "page": page, "detail": detail})

    with pdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Encrypted PDF cannot be inspected without its password.")
        if doc.page_count != 9:
            record("PAGE_COUNT", None, f"Expected 9 physical pages; found {doc.page_count}.")
        pages = []
        for number, page in enumerate(doc, 1):
            if tuple(page.rect) != (0.0, 0.0, 612.0, 792.0) or page.rotation:
                record("PAGE_GEOMETRY", number, "Expected unrotated US Letter geometry.")
            lines = [line for block in page.get_text("dict")["blocks"]
                     if "lines" in block for line in block["lines"]]
            # Font bounding boxes slightly overstate ink; allow 0.5pt rounding
            # at the declared body margins. This is not an overlap detector.
            for line in lines:
                text = "".join(span["text"] for span in line["spans"])
                box = pdf.Rect(line["bbox"])
                if (box.x0 < 71.5 or box.x1 > 540.5 or
                        box.y0 < 71.5 or box.y1 > 720.5):
                    record("TEXT_OUTSIDE_BODY", number, text)
            links = page.get_links()
            expected = DESTINATIONS.get(number, [])
            if len(links) != len(expected):
                record("LINK_COUNT", number, f"Expected {len(expected)}, found {len(links)}.")
            link_rows = []
            for index, link in enumerate(links):
                box = link["from"]
                intersecting = [line for line in lines
                                if pdf.Rect(line["bbox"]).intersects(box)]
                # A useful hit region must cover at least the center of its
                # visible label, not just have a valid /Rect syntax.
                # Use the center directly; keep overlap separate from coverage.
                covered = [line for line in intersecting if box.contains(
                    (pdf.Rect(line["bbox"]).tl + pdf.Rect(line["bbox"]).br) / 2)]
                if not covered:
                    record("LINK_WITHOUT_LABEL", number, f"Link {index + 1} misses label center.")
                if index < len(expected) and covered:
                    expected_page, anchor = expected[index]
                    source_text = compact(" ".join(
                        "".join(span["text"] for span in line["spans"]) for line in covered))
                    if number == 2:
                        wanted_label = anchor.partition(". ")[2]
                    elif anchor.startswith("ATT-"):
                        wanted_label = "-> " + anchor + ":"
                    else:
                        wanted_label = "-> " + {6: "S-SCOPE", 7: "S-STAFF", 8: "S-PRICE"}[expected_page] + ":"
                    if wanted_label not in source_text:
                        record("WRONG_VISIBLE_LABEL", number,
                               f"Link {index + 1}: expected label {wanted_label!r}, got {source_text!r}.")
                target_number = link.get("page", -1) + 1
                target_text = ""
                if link["kind"] != pdf.LINK_GOTO or not 1 <= target_number <= doc.page_count:
                    record("DESTINATION", number, f"Link {index + 1} has no usable internal page.")
                else:
                    point = link.get("to", pdf.Point(-1, -1))
                    target_page = doc[target_number - 1]
                    if not target_page.rect.contains(point):
                        record("DESTINATION_POSITION", number, f"Link {index + 1} lands off-page.")
                    target_text = compact(target_page.get_textbox(
                        pdf.Rect(72, point.y, 540, min(point.y + 30, 792))))
                    if index < len(expected):
                        expected_page, anchor = expected[index]
                        if target_number != expected_page or anchor not in target_text:
                            record("WRONG_VISIBLE_DESTINATION", number,
                                   f"Link {index + 1}: expected page {expected_page}, {anchor!r}; "
                                   f"got page {target_number}, {target_text!r}.")
                link_rows.append({"index": index + 1, "target_page": target_number,
                                  "target_text": target_text})
            pages.append({"page": number, "text_runs": sum(len(l["spans"]) for l in lines),
                          "links": link_rows, "text_sha256": hashlib.sha256(
                              page.get_text().encode()).hexdigest()})
        toc = [(title, number) for _level, title, number in doc.get_toc()]
        if toc != OUTLINES:
            record("OUTLINE", None, "Outline labels/order/physical pages differ from the reviewed sample.")
        if len(doc) >= 6:
            index_text = doc[1].get_text()
            for marker in ("SUBMISSION_INCOMPLETE", "UNKNOWN", "ATT-FIN-02",
                           "ATT-QUAL-02", "ATT-QUAL-03", "It is not zero and it is not a pass."):
                if marker not in index_text:
                    record("MISSING_INDEX_MARKER", 2, marker)
            if "S-APPENDIX-C" not in doc[5].get_text() or "UNRESOLVED" not in doc[5].get_text():
                record("MISSING_UNRESOLVED_MARKER", 6, "S-APPENDIX-C must remain explicitly unresolved.")
        if len(doc) and not all(word in doc[0].get_text() for word in ("FICTION", "NOT SUBMITTED")):
            record("MISSING_FICTION_OR_DRAFT", 1, "Synthetic draft labels must remain visible.")
        return {"schema": "uiowa136-render-replay/1", "bytes": len(data), "sha256": sha,
                "git_blob": blob, "matches_reviewed_bytes": sha == REVIEWED_SHA256,
                "reader": {"name": "PyMuPDF", "version": pdf.VersionBind},
                "page_count": doc.page_count, "link_count": sum(len(p["links"]) for p in pages),
                "outline_count": len(toc), "pages": pages, "findings": findings,
                "automated_observations": "PASS" if not findings else "FAIL",
                "visual_review": "NOT_PERFORMED_BY_THIS_REPLAY",
                "human_accessibility_review": "OUTSTANDING"}


def replay(source: Path, output: Path, dpi: int = 110) -> dict:
    """Create a new, standalone local inspection gallery without touching input."""
    if not 72 <= dpi <= 300:
        raise ValueError("Choose 72-300 DPI for this small review replay.")
    data = source.read_bytes()
    result = inspect_pdf(data)
    output.mkdir(parents=True, exist_ok=False)
    images = []
    with pdf.open(stream=data, filetype="pdf") as doc:
        for number, page in enumerate(doc, 1):
            name = f"page-{number:02d}.png"
            target = output / name
            page.get_pixmap(dpi=dpi, alpha=False).save(target)
            images.append({"page": number, "file": name,
                           "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    result["renders"] = images
    result["dpi"] = dpi
    (output / "observations.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    sections = "\n".join(f'<section><h2>Physical page {i["page"]}</h2>'
                         f'<img src="{i["file"]}" alt="Rendered physical page {i["page"]}; '
                         'review text and navigation using the PDF and observations file."></section>'
                         for i in images)
    (output / "index.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Fictional bid-pack render replay</title><style>body{max-width:1000px;margin:2em auto;'
        'font-family:system-ui}img{width:100%;height:auto}section{margin:3em 0}</style>'
        '<h1>Fictional bid-pack render replay</h1><p>These images have not been visually reviewed '
        'by this script. Automated observations are not human or AI visual approval.</p>'
        '<p>This is synthetic evidence, not a submitted proposal or an assertion of qualifications.</p>'
        f'<p>PDF SHA-256: <code>{result["sha256"]}</code></p>{sections}</html>', encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--out", type=Path, required=True, help="New output directory; existing paths are not overwritten.")
    parser.add_argument("--dpi", type=int, default=110)
    args = parser.parse_args(argv)
    try:
        report = replay(args.pdf, args.out, args.dpi)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Replay not completed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({k: report[k] for k in ("sha256", "page_count", "link_count",
                                            "automated_observations", "visual_review")}, indent=2))
    return 0 if report["matches_reviewed_bytes"] and not report["findings"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
