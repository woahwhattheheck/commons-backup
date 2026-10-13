#!/usr/bin/env python3
"""Owner-paste X Pixel slot on the shared pack thank-you door. Not a Commons gate.

SCOUT #build-demand scout-demand-pack-door-thanks-pixel-20260902-01:
Stripe Payment Links complete on stripe.com. A Purchase event needs a
thank-you page we control. Empty pixel_id loads zero third-party scripts.
Owner pastes the pixel ID the same way they paste Payment Links.
Agents do not mint a pixel, open an ads account, or spend ads.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_THANKS.json"
DEFAULT_DOOR = ROOT / "packs" / "thanks.html"
THIRD_PARTY_SRC = (
    "ads-twitter.com",
    "static.ads-twitter.com",
    "facebook.net",
    "connect.facebook.net",
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
)
SRC_RE = re.compile(r"""\bsrc\s*=\s*['\"]([^'\"]+)['\"]""", re.I)
EARNINGS_RE = re.compile(
    r"(?i)\bmake\s+\$\d|\bearn\s+\$\d|\bprofit\s+\$\d|"
    r"\bmake \$\d+ this weekend|\bunrealistic result"
)


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def third_party_script_srcs(html: str) -> list[str]:
    found: list[str] = []
    for match in SRC_RE.finditer(html or ""):
        src = match.group(1)
        lowered = src.lower()
        if any(marker in lowered for marker in THIRD_PARTY_SRC):
            found.append(src)
    return found


def purchase_value(query: str | None = None, url: str = "") -> float | None:
    raw = query
    if raw is None and url:
        raw = parse_qs(urlparse(url).query).get("value", [None])[0]
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = float(str(raw).strip())
    except ValueError:
        return None
    if value < 0:
        return None
    return value


def classify(
    law: dict[str, Any] | None = None,
    html: str | None = None,
    pixel_id: str | None = None,
    value: str | float | None = None,
) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    door_html = html if html is not None else DEFAULT_DOOR.read_text(encoding="utf-8")
    slot = str(pixel_id if pixel_id is not None else data.get("pixel_id") or "").strip()
    scripts = third_party_script_srcs(door_html)
    empty = slot == ""
    if empty:
        verdict = "PIXEL_SLOT_EMPTY"
    else:
        verdict = "PIXEL_SLOT_OWNER_FILLED"
    amount = purchase_value(query=None if value is None else str(value))
    payload: dict[str, Any] = {"event": str(data.get("purchase_event") or "Purchase")}
    if amount is not None:
        payload["value"] = amount
        payload["currency"] = "USD"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "pixel_slot": "owner_paste",
        "pixel_id_present": not empty,
        "agents_mint_pixel_id": False,
        "agents_spend_ads": False,
        "empty_loads_zero_third_party_scripts": empty and not scripts,
        "static_third_party_scripts": scripts,
        "would_load_script": (
            [] if empty else [str(data.get("script_src_when_filled") or "")]
        ),
        "purchase": payload,
        "checkout": str(data.get("checkout") or "NOT_MINTED"),
        "nuts_in_ad_copy": False,
        "copy": "prices_and_time_budgets_never_earnings",
        "earnings_claim": bool(EARNINGS_RE.search(door_html)),
        "law_id": str(data.get("id") or ""),
        "scout_demand_id": str(data.get("scout_demand_id") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixel-id", default=None, help="override slot (tests only)")
    parser.add_argument("--value", default="", help="Purchase value query")
    parser.add_argument("--law", default="", help="override law path")
    args = parser.parse_args(argv)
    law = load_law(Path(args.law) if args.law else None)
    result = classify(law=law, pixel_id=args.pixel_id, value=args.value or None)
    print(json.dumps(result, indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
