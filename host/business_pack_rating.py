#!/usr/bin/env python3
"""Classify the empty pack rating slot. Not a Commons gate.

Bryce / SCOUT 1788327092.565209: a third-party rating partner at a bulk
rate is the owner's pick. This helper only classifies the factory slot:
badge URL + report URL, empty by default. Completeness audit is allowed.
Dollar valuation on the door is an earnings claim. Agents do not pick a
partner or invent a bulk price.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_RATING.json"
URL_RE = re.compile(r"(?i)https?://")
STRIPE_FAKE_RE = re.compile(r"(?i)https?://(?:buy|donate)\.stripe\.com/")
EARNINGS_RE = re.compile(
    r"(?i)\bmake\s+\$\d|\bearn\s+\$\d|\bprofit\s+\$\d|"
    r"\bmake \$\d+ this weekend|\bunrealistic result"
)
VALUATION_RE = re.compile(
    r"(?i)valued at\s*\$|worth\s*\$|revenue projection|"
    r"will (?:make|earn|gross)\s*\$|appraised at\s*\$|"
    r"dollar valuation|income projection"
)
AUDITED_RE = re.compile(
    r"(?i)independently audited|third-party rated|rated by our partner|"
    r"completeness audit (?:included|complete)|seal of completeness"
)
EMPTY_MARKERS = {"", "OWNER_UNSET", "HOLD_COUNSEL", "TODO", "TBD"}


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def _slot(value: Any) -> str:
    text = str(value or "").strip()
    if text.upper() in EMPTY_MARKERS:
        return ""
    return text


def classify_rating(
    pack: dict[str, Any] | None = None, *, law_path: Path | None = None
) -> dict[str, Any]:
    if pack is not None and not isinstance(pack, dict):
        raise ValueError("pack must be a JSON object")
    data = dict(pack) if pack is not None else {}
    owner_pasted = data.get("owner_pasted_rating", False)
    if not isinstance(owner_pasted, bool):
        raise ValueError("owner_pasted_rating must be a boolean")
    law = load_law(law_path)
    badge = _slot(data.get("badge_url", law.get("badge_url")))
    report = _slot(data.get("report_url", law.get("report_url")))
    partner = _slot(data.get("partner_name", law.get("partner_name")))
    bulk = _slot(data.get("bulk_price", law.get("bulk_price")))
    ads = str(data.get("ads_copy") or data.get("copy") or "")
    invented_url = (
        bool(URL_RE.search(badge) or URL_RE.search(report)) and not owner_pasted
    )
    invented_stripe = bool(STRIPE_FAKE_RE.search(json.dumps(data, default=str)))
    earnings_in_ads = bool(EARNINGS_RE.search(ads))
    valuation = bool(VALUATION_RE.search(ads) or VALUATION_RE.search(badge + report))
    audited_claim = bool(AUDITED_RE.search(ads))
    filled = bool(badge and report and owner_pasted)
    empty = not badge and not report
    unsubstantiated = audited_claim and not filled
    if invented_stripe or invented_url:
        verdict = "RATING_LINK_INVENTED"
    elif valuation:
        verdict = "RATING_EARNINGS_CLAIM"
    elif earnings_in_ads:
        verdict = "EARNINGS_IN_ADS"
    elif unsubstantiated:
        verdict = "RATING_CLAIM_UNSUBSTANTIATED"
    elif filled:
        verdict = "RATING_SLOT_OWNER_FILLED"
    else:
        verdict = "RATING_SLOT_EMPTY"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "badge_empty": badge == "",
        "report_empty": report == "",
        "partner_empty": partner == "",
        "bulk_price_empty": bulk == "",
        "empty": empty,
        "filled": filled,
        "owner_pasted_rating": owner_pasted,
        "agents_pick_partner": False,
        "agents_invent_bulk_price": False,
        "agents_spend_ads": False,
        "did_not_write_scout_advertising_general": True,
        "checkout": "NOT_MINTED",
        "id": law.get("id"),
        "unique_pack_id": law.get("unique_pack_id"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", default="", help="JSON object to classify")
    args = parser.parse_args(argv)
    try:
        pack = json.loads(args.pack) if args.pack else None
        if args.pack and not isinstance(pack, dict):
            raise ValueError("--pack must be a JSON object")
        result = classify_rating(pack)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
