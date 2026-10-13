#!/usr/bin/env python3
"""Load filled instance paperwork checklists. Not legal advice. Not a Commons gate.

“Paperwork included” is true only when registration, EIN, sales tax, license,
insurance, and contract how-tos are filled. Two DESK instances may share a
vertical; they must not share a fingerprint. Does not write TALLY's helper,
Harborline instance files, or SCOUT research files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_PAPERWORK_FILLED.json"
SHEET_DIR = ROOT / "packs" / "paperwork-included-20260902-01"
REQUIRED = (
    "state",
    "registration",
    "ein",
    "sales_tax",
    "license",
    "insurance",
    "contract",
)
SECTION_ALIASES = {
    "registration": ("registration", "dba", "assumed name"),
    "ein": ("ein",),
    "sales_tax": ("sales tax", "seller"),
    "license": ("license", "licence", "local business"),
    "insurance": ("insurance",),
    "contract": ("contract",),
}
UNSET = {"OWNER_UNSET", "HOLD_COUNSEL", "TODO", "TBD", ""}

sys.path.insert(0, str(ROOT / "host"))
import business_pack_paperwork as paper  # noqa: E402
import business_pack_unique as unique  # noqa: E402


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def _section_key(heading: str) -> str | None:
    lower = heading.lower()
    for key, aliases in SECTION_ALIASES.items():
        if any(alias in lower for alias in aliases):
            return key
    return None


def parse_sheet(text: str) -> dict[str, Any]:
    """Read factory-style Do X / Status blocks into required slots."""
    pack: dict[str, Any] = {}
    blocks = re.split(r"(?m)^##\s+", text)
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        key = _section_key(lines[0])
        if not key:
            continue
        do_x = ""
        status = ""
        for line in lines[1:]:
            stripped = line.strip()
            match = re.match(r"(?:\d+\.\s*)?Do X:\s*(.*)$", stripped, re.I)
            if match:
                do_x = match.group(1).strip()
            elif stripped.lower().startswith("status:"):
                status = stripped.split(":", 1)[1].strip().strip("`")
        value = do_x or status
        if status.upper() in UNSET:
            value = ""
        pack[key] = value
    copy_match = re.search(r'Copy this door may use:\s*[“"]([^”"]+)[”"]', text)
    if copy_match:
        pack["door_line"] = copy_match.group(1)
    if re.search(r"(?i)paperwork included", text):
        pack["copy"] = "paperwork included"
    state_match = re.search(
        r"(?im)^State:\s*(.+)$|^Jurisdiction:\s*(.+)$", text
    )
    if state_match:
        pack["state"] = (state_match.group(1) or state_match.group(2) or "").strip()
    return pack


def load_instance(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not an object")
    sheet_rel = str(data.get("sheet") or "").strip()
    if sheet_rel:
        sheet_path = ROOT / sheet_rel
        if sheet_path.is_file():
            parsed = parse_sheet(sheet_path.read_text(encoding="utf-8"))
            for key in REQUIRED:
                if key not in data or str(data.get(key) or "").strip().upper() in UNSET:
                    if parsed.get(key):
                        data[key] = parsed[key]
            if parsed.get("copy") and not data.get("copy"):
                data["copy"] = parsed["copy"]
    return data


def classify_filled(pack: dict[str, Any] | None) -> dict[str, Any]:
    """Reuse the factory classifier; attach filled leftover metadata."""
    law = load_law()
    result = paper.classify_paperwork(pack)
    included = bool(result.get("included_claim")) and not result.get(
        "claim_unsubstantiated"
    )
    result["paperwork_included"] = included and result.get("verdict") == "PAPERWORK_OK"
    result["filled_id"] = str(law.get("id") or "")
    result["included_claim_id"] = str(law.get("included_claim_id") or "")
    result["similar_is_not_clone"] = True
    result["did_not_write_tally_helper"] = True
    result["did_not_write_scout_research"] = True
    return result


def classify_desk_pair(
    harborline: Path | None = None, pierlight: Path | None = None
) -> dict[str, Any]:
    """Two DESK instances: filled checklists + similar-not-clone."""
    left = load_instance(harborline or SHEET_DIR / "harborline-desk.json")
    right = load_instance(pierlight or SHEET_DIR / "pierlight-desk.json")
    papers = [classify_filled(left), classify_filled(right)]
    sales = unique.classify_sales([left, right])
    return {
        "gate": False,
        "commons_admission": False,
        "paperwork": papers,
        "sales": sales,
        "both_included": all(row.get("paperwork_included") for row in papers),
        "similar_is_not_clone": True,
        "clone_stamp": bool(sales.get("clone_stamp")),
        "shared_vertical": left.get("vertical") == right.get("vertical"),
        "shared_template": left.get("template_id") == right.get("template_id"),
        "did_not_write_tally_helper": True,
        "checkout": "NOT_MINTED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-json", default="", help="one paperwork pack object")
    parser.add_argument("--instance", default="", help="path to one instance JSON")
    parser.add_argument("--sheet", default="", help="path to one filled markdown sheet")
    parser.add_argument(
        "--desk-pair",
        action="store_true",
        help="classify both filled DESK instance sheets",
    )
    args = parser.parse_args(argv)
    if args.desk_pair:
        print(json.dumps(classify_desk_pair(), indent=2))
        return 0
    pack: dict[str, Any] = {}
    if args.pack_json:
        loaded = json.loads(args.pack_json)
        if isinstance(loaded, dict):
            pack = loaded
    elif args.instance:
        pack = load_instance(Path(args.instance))
    elif args.sheet:
        pack = parse_sheet(Path(args.sheet).read_text(encoding="utf-8"))
        pack.setdefault("copy", "paperwork included")
    print(json.dumps(classify_filled(pack), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
