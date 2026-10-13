#!/usr/bin/env python3
"""Creative brief template + Harborline instance fill. Compose leftover.

SCOUT scout-demand-instance-creative-brief-20260902-01: one brief per SELL
instance so Bryce can shoot the ad the day a Payment Link is pasted. GOAT
owns packs/_template/; this leftover adds creative_brief.md only and does
not rewrite the other template files. Harborline fill stays on this seat's
instance. Sidewalk Signal, LotRibbon, waitlist, thanks, TALLY helper, and
the sold-once badge paths stay with their owners. Prices yes. Earnings
never. Checkout NOT_MINTED. Agents do not spend ads.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "packs" / "_template" / "creative_brief.md"
HARBORLINE = (
    ROOT / "packs" / "desk-website-service-20260902-01" / "creative_brief.md"
)
DO_NOT_OVERWRITE = (
    "packs/_template/README.md",
    "packs/_template/checkout.md",
    "packs/_template/offer.md",
    "packs/waitlist.html",
    "host/pack_waitlist.py",
    "packs/thanks.html",
    "host/pack_thanks_pixel.py",
    "host/pack_waitlist_pixel_gate.py",
    "packs/desk-website-service-20260902-01/door.html",
    "host/harborline_tally_pack_map.py",
    "host/business_pack_desk_instance.py",
    "packs/sidewalk-signal-web-desk-20260902-01",
    "packs/lotribbon-greetings-20260902-01",
    "revenue/business_packs_marketing/ADVERTISING_GENERAL.md",
    "revenue/business_packs_marketing/BUYER_TIERS.md",
    "revenue/business_packs_marketing/DATA_BUYING.md",
    "revenue/business_packs_marketing/FERTILE_GROUND.md",
    "revenue/business_packs_marketing/MESSAGING_ANGLE.md",
    "revenue/business_packs_marketing/PAPERWORK.md",
    "revenue/business_packs_marketing/PRICE_ANCHORS.md",
)

REQUIRED_HEADINGS = (
    "Buyer",
    "Hooks",
    "Runtime",
    "CTA",
    "Anchor",
    "Channel order",
    "Launch metros",
    "Never say",
    "UTM",
)
EARNINGS_RE = re.compile(
    r"(?i)\bmake\s+\$\d|\bearn\s+\$\d|\bprofit\s+\$\d|"
    r"\bmake \$\d+ this weekend|\bunrealistic result|"
    r"\bland \d+ clients|\bpayback\b|\bguaranteed income|"
    r"\bquit your job\b|\bfinancial freedom\b|\bpassive income"
)
FORBIDDEN_RE = re.compile(
    r"(?i)done[\s-]*for[\s-]*you|\bbecome your own boss|"
    r"\bwe bring you customers\b|\bwe bring you leads\b"
)
UTM_RE = re.compile(
    r"utm_source=\{channel\}.*utm_medium=paid.*utm_campaign=.+.*utm_content="
    r"(door|thanks)",
    re.I,
)
HEADING_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.M)


def strip_section(text: str, title: str) -> str:
    """Never-say lists name banned phrases; do not score that section."""
    pattern = rf"^#{{1,3}}\s+{re.escape(title)}\s*$"
    match = re.search(pattern, text or "", flags=re.I | re.M)
    if not match:
        return text or ""
    rest = text[match.end() :]
    nxt = re.search(r"^#{1,3}\s+", rest, flags=re.M)
    end = match.end() + nxt.start() if nxt else len(text)
    return (text[: match.start()] + text[end:]).strip()


def headings(text: str) -> list[str]:
    found: list[str] = []
    for match in HEADING_RE.finditer(text or ""):
        name = match.group(1).strip()
        if name.lower().startswith("creative brief"):
            continue
        found.append(name)
    return found


def missing_headings(text: str) -> list[str]:
    present = {item.lower() for item in headings(text)}
    return [name for name in REQUIRED_HEADINGS if name.lower() not in present]


def classify(text: str, *, kind: str = "instance") -> dict[str, Any]:
    body = text or ""
    scored = strip_section(body, "Never say")
    missing = missing_headings(body)
    earnings = bool(EARNINGS_RE.search(scored))
    forbidden = bool(FORBIDDEN_RE.search(scored))
    has_utm = bool(UTM_RE.search(body)) and "utm_content=door" in body.lower()
    has_thanks_utm = "utm_content=thanks" in body.lower()
    owner_unset = "OWNER_UNSET" in body
    price_yes = "$200" in body or "pack price" in body.lower() or "USD" in body
    checkout_empty = "NOT_MINTED" in body or "OWNER_PASTE_REQUIRED" in body
    never_say = "earnings never" in body.lower() or "never say" in body.lower()
    problems: list[str] = []
    if missing:
        problems.append("headings")
    if earnings:
        problems.append("earnings")
    if forbidden:
        problems.append("forbidden")
    if not has_utm or not has_thanks_utm:
        problems.append("utm")
    if not never_say:
        problems.append("never_say")
    if kind == "template":
        if not owner_unset:
            problems.append("template_slots")
        verdict = (
            "CREATIVE_BRIEF_TEMPLATE_OK" if not problems else "CREATIVE_BRIEF_INCOMPLETE"
        )
    else:
        verdict = (
            "CREATIVE_BRIEF_INSTANCE_OK" if not problems else "CREATIVE_BRIEF_INCOMPLETE"
        )
    if earnings or forbidden:
        verdict = "CREATIVE_BRIEF_EARNINGS"
    return {
        "kind": "CREATIVE_BRIEF",
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "role": kind,
        "missing_headings": missing,
        "earnings_claim": earnings,
        "forbidden_phrase": forbidden,
        "utm_door": has_utm,
        "utm_thanks": has_thanks_utm,
        "owner_unset_present": owner_unset,
        "price_stated": price_yes,
        "checkout_not_minted": checkout_empty,
        "problems": problems,
        "sends": 0,
        "agents_spend_ads": False,
        "agents_mint_pixel_id": False,
        "checkout": "NOT_MINTED",
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "scout_demand_id": "scout-demand-instance-creative-brief-20260902-01",
        "receipt_id": "cursor-pack-creative-brief-template-20260902-01",
    }


def classify_path(path: Path, *, kind: str) -> dict[str, Any]:
    if not path.is_file():
        return {
            "kind": "CREATIVE_BRIEF",
            "gate": False,
            "commons_admission": False,
            "verdict": "CREATIVE_BRIEF_MISSING",
            "role": kind,
            "path": str(path),
            "sends": 0,
            "checkout": "NOT_MINTED",
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
        }
    result = classify(path.read_text(encoding="utf-8"), kind=kind)
    result["path"] = str(path)
    return result


def classify_tree(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    template = classify_path(base / "packs" / "_template" / "creative_brief.md", kind="template")
    harborline = classify_path(
        base / "packs" / "desk-website-service-20260902-01" / "creative_brief.md",
        kind="instance",
    )
    ok = (
        template.get("verdict") == "CREATIVE_BRIEF_TEMPLATE_OK"
        and harborline.get("verdict") == "CREATIVE_BRIEF_INSTANCE_OK"
    )
    return {
        "kind": "CREATIVE_BRIEF",
        "gate": False,
        "commons_admission": False,
        "verdict": "CREATIVE_BRIEF_OK" if ok else "CREATIVE_BRIEF_INCOMPLETE",
        "template": template,
        "harborline": harborline,
        "did_not_rewrite_goat_template_files": True,
        "did_not_fill_sidewalk": True,
        "did_not_fill_lotribbon": True,
        "did_not_overwrite_harborline_door": True,
        "sends": 0,
        "agents_spend_ads": False,
        "checkout": "NOT_MINTED",
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "scout_demand_id": "scout-demand-instance-creative-brief-20260902-01",
        "receipt_id": "cursor-pack-creative-brief-template-20260902-01",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="classify")
    parser.add_argument("--file", default="")
    parser.add_argument("--kind", default="instance")
    args = parser.parse_args(argv)
    if args.file:
        print(json.dumps(classify_path(Path(args.file), kind=args.kind), indent=2))
        return 0
    print(json.dumps(classify_tree(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
