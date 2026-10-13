#!/usr/bin/env python3
"""Classify pack copy so 'for this price' carries running cost. Not a Commons gate.

SCOUT #business-packs 1788327466.578309: X/TikTok reject ads that omit
expenses the customer will incur. Ownership copy waits on LEAD ToS
OWNER_UNSET slots. Do not invent a running-cost dollar or a percent.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_RUNNING_COST.json"
PRICE_PHRASE_RE = re.compile(r"(?i)for this price|for \$\d")
OWNERSHIP_PHRASE_RE = re.compile(
    r"(?i)become (?:a )?business owner|become your own boss|"
    r"your own employee and employer"
)
WORK_PHRASE_RE = re.compile(r"(?i)we did most of the work")
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


def _copy(offer: dict[str, Any]) -> str:
    return str(offer.get("ads_copy") or offer.get("copy") or "")


def _running_cost_raw(offer: dict[str, Any]) -> Any:
    support = offer.get("running_cost")
    if isinstance(support, dict):
        return support.get("usd", support.get("price_usd", support.get("amount")))
    if support not in (None, ""):
        return support
    return offer.get("running_cost_usd")


def _running_cost_unset(offer: dict[str, Any]) -> bool:
    raw = _running_cost_raw(offer)
    if raw is None or raw == "":
        return True
    return str(raw).strip().upper() == "OWNER_UNSET"


def _assets(offer: dict[str, Any]) -> list[str]:
    raw = offer.get("assets") or offer.get("asset_list") or []
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item or "").strip()]


def classify_running_cost(offer: dict[str, Any] | None) -> dict[str, Any]:
    """Price lines need a pasted running cost. Ownership copy waits on ToS."""
    law = load_law()
    data = offer if isinstance(offer, dict) else {}
    copy = _copy(data)
    earnings_in_ads = bool(EARNINGS_RE.search(copy))
    price_phrase = bool(PRICE_PHRASE_RE.search(copy))
    ownership_phrase = bool(OWNERSHIP_PHRASE_RE.search(copy))
    work_phrase = bool(WORK_PHRASE_RE.search(copy))
    unset = _running_cost_unset(data)
    invented = (not unset) and not data.get("owner_pasted_running_cost")
    expense_omitted = price_phrase and unset
    tos_pasted = bool(data.get("tos_owner_pasted") or data.get("owner_pasted_tos"))
    ownership_copy_waits = ownership_phrase and not tos_pasted
    work_unsubstantiated = work_phrase and not _assets(data)
    if earnings_in_ads:
        verdict = "EARNINGS_IN_ADS"
    elif invented:
        verdict = "RUNNING_COST_INVENTED"
    elif expense_omitted:
        verdict = "EXPENSE_OMITTED"
    elif ownership_copy_waits:
        verdict = "OWNERSHIP_COPY_WAITS"
    elif work_unsubstantiated:
        verdict = "WORK_CLAIM_UNSUBSTANTIATED"
    else:
        verdict = "RUNNING_COST_OK"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "price_phrase": price_phrase,
        "expense_omitted": expense_omitted,
        "running_cost": "OWNER_UNSET" if unset else _running_cost_raw(data),
        "running_cost_invented": invented,
        "ownership_copy_waits": ownership_copy_waits,
        "work_claim_unsubstantiated": work_unsubstantiated,
        "earnings_in_ads": earnings_in_ads,
        "did_not_invent_percent_or_equity": True,
        "did_not_write_scout_messaging_angle": True,
        "checkout": "NOT_MINTED",
        "agents_spend_ads": False,
        "law_id": str(law.get("id") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offer-json", default="", help="JSON offer/copy object")
    parser.add_argument("--law", default="", help="override law path")
    args = parser.parse_args(argv)
    if args.law:
        load_law(Path(args.law))
    offer: dict[str, Any] = {}
    if args.offer_json:
        loaded = json.loads(args.offer_json)
        if isinstance(loaded, dict):
            offer = loaded
    print(json.dumps(classify_running_cost(offer), indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
