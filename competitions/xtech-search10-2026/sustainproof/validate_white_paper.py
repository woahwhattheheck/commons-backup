"""Mechanical checks for the xTech|Search 10 draft carrier.

This cannot prove pagination in the sponsor's mandatory template. It verifies that
our draft is intentionally split into three bounded source sections and preserves
all rubric/evidence warnings before a human transfers it into the official template.
"""
from __future__ import annotations

import re
from pathlib import Path

REQUIRED_TAGS = {
    "[INTRODUCTION-5]",
    "[TECHNICAL-40]",
    "[ARMY-BENEFITS-25]",
    "[COMMERCIAL-25]",
    "[PROPOSAL-QUALITY-5]",
}
PAGE_RE = re.compile(r"^<!-- PAGE ([123])/3 -->$", re.MULTILINE)
OWNER_MARKER = "OWNER EVIDENCE REQUIRED"


class DraftError(ValueError):
    pass


def validate_text(text: str) -> dict[str, int]:
    pages = PAGE_RE.findall(text)
    if pages != ["1", "2", "3"]:
        raise DraftError("draft must contain exactly PAGE 1/3, PAGE 2/3, PAGE 3/3 markers in order")
    missing = sorted(tag for tag in REQUIRED_TAGS if tag not in text)
    if missing:
        raise DraftError(f"missing rubric tags: {missing}")
    if OWNER_MARKER not in text:
        raise DraftError("owner-evidence marker missing")
    if "submissionAuthorized=false" not in text:
        raise DraftError("submission authority ceiling missing")
    chunks = PAGE_RE.split(text)
    # split layout: preamble, num, page, num, page, num, page
    page_texts = [chunks[2], chunks[4], chunks[6]]
    counts: list[int] = []
    for idx, page in enumerate(page_texts, start=1):
        words = re.findall(r"\b[\w’'-]+\b", page)
        if not 180 <= len(words) <= 750:
            raise DraftError(f"page {idx} word count out of bounded drafting range: {len(words)}")
        counts.append(len(words))
    return {"page1Words": counts[0], "page2Words": counts[1], "page3Words": counts[2], "totalWords": sum(counts)}


def validate_file(path: str | Path) -> dict[str, int]:
    return validate_text(Path(path).read_text(encoding="utf-8"))
