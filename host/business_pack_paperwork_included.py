#!/usr/bin/env python3
"""Factory paperwork homework: filled Do X lines, not doing the filing.

SCOUT hub 1788328090.862799: "paperwork included" is true only with a
filled checklist. This helper measures the factory sheet's Do X homework
(official portals and templates). Instance Status may stay OWNER_UNSET
until the buyer files. Not legal advice. Not a Commons gate.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_PAPERWORK_INCLUDED.json"
DEFAULT_SHEET = ROOT / "packs" / "_template" / "paperwork.md"
REQUIRED = ("registration", "ein", "sales_tax", "license", "insurance", "contract")
EMPTY_MARKERS = {"", "OWNER_UNSET", "HOLD_COUNSEL", "TODO", "TBD"}
HEADING_KEYS = (
    ("sales tax", "sales_tax"),
    ("license", "license"),
    ("registration", "registration"),
    ("ein", "ein"),
    ("insurance", "insurance"),
    ("contract", "contract"),
)
DO_X_RE = re.compile(r"(?i)^\s*(?:\d+\.\s*)?Do X:\s*(.*)$")
FILING_RE = re.compile(
    r"(?i)we filed|we do the filing|doing the filing for you|"
    r"we handle your legal paperwork|we set up your llc|"
    r"compliance guaranteed"
)


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def _heading_key(heading: str) -> str | None:
    text = heading.strip().lower()
    for needle, key in HEADING_KEYS:
        if needle in text:
            return key
    return None


def parse_sheet_homework(text: str) -> dict[str, str]:
    """Map required slot -> first Do X remainder under that heading."""
    found: dict[str, str] = {}
    parts = re.split(r"(?m)^## ", text)
    for part in parts[1:]:
        heading, _, body = part.partition("\n")
        key = _heading_key(heading)
        if key is None or key in found:
            continue
        do_x = ""
        for line in body.splitlines():
            match = DO_X_RE.match(line)
            if match:
                do_x = match.group(1).strip()
                break
        found[key] = do_x
    return found


def _filled_step(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    return value.upper() not in EMPTY_MARKERS


def classify_homework(
    sheet_text: str | None = None, *, sheet_path: Path | None = None
) -> dict[str, Any]:
    """Factory Do X homework. Empty steps make an included claim unsubstantiated."""
    law = load_law()
    if sheet_text is None:
        target = sheet_path or DEFAULT_SHEET
        sheet_text = target.read_text(encoding="utf-8")
    steps = parse_sheet_homework(sheet_text)
    missing = [name for name in REQUIRED if not _filled_step(steps.get(name, ""))]
    step_blob = "\n".join(steps.get(name, "") for name in REQUIRED)
    filing_claim = bool(FILING_RE.search(step_blob))
    if filing_claim:
        verdict = "PAPERWORK_FILING_CLAIM"
    elif missing:
        verdict = "PAPERWORK_CLAIM_UNSUBSTANTIATED"
    else:
        verdict = "PAPERWORK_OK"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "missing": missing,
        "steps": {name: steps.get(name, "") for name in REQUIRED},
        "homework_filled": not missing and not filing_claim,
        "filing_as_lawyer": filing_claim,
        "legal_advice": False,
        "not_legal_advice": True,
        "hold_counsel": True,
        "upl_line": "checklists_links_templates_not_filing",
        "substantiation": "filled_checklist",
        "did_not_remint_paperwork_id": True,
        "did_not_write_scout_paperwork_md": True,
        "did_not_write_state_claim": True,
        "checkout": "NOT_MINTED",
        "agents_spend_ads": False,
        "law_id": str(law.get("id") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", default="", help="override paperwork sheet path")
    parser.add_argument("--law", default="", help="override law path")
    args = parser.parse_args(argv)
    if args.law:
        load_law(Path(args.law))
    sheet_path = Path(args.sheet) if args.sheet else DEFAULT_SHEET
    print(json.dumps(classify_homework(sheet_path=sheet_path), indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
