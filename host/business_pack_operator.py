#!/usr/bin/env python3
"""Classify a sold pack as an employee-day runbook. Not a Commons gate.

Bryce hub 1788327136.593709: treat the customer like an employee.
Onboarding, training, and a direct do-X task list. Paid tjlabs
subscription for support contact — not a Commons seat. Fail-to-profit
is owner runbook framing, not ad copy. Do not invent a subscription
price or a ToS percent.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_OPERATOR.json"
REQUIRED = ("onboarding", "training", "daily_tasks")
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


def _tasks(pack: dict[str, Any]) -> list[str]:
    raw = pack.get("daily_tasks") or pack.get("tasks") or []
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _filled(pack: dict[str, Any], name: str) -> bool:
    if name == "daily_tasks":
        return bool(_tasks(pack))
    value = pack.get(name)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(str(x or "").strip() for x in value)
    return bool(value)


def classify_operator(pack: dict[str, Any] | None) -> dict[str, Any]:
    """Employee-day completeness. Support price stays OWNER_UNSET unless owner-pasted."""
    law = load_law()
    data = pack if isinstance(pack, dict) else {}
    missing = [name for name in REQUIRED if not _filled(data, name)]
    support = data.get("support") if isinstance(data.get("support"), dict) else {}
    price = support.get("price_usd", data.get("support_price_usd"))
    owner_unset = price is None or price == "" or str(price).strip().upper() == "OWNER_UNSET"
    invented_price = (not owner_unset) and not data.get("owner_pasted_support_price")
    ads = str(data.get("ads_copy") or data.get("copy") or "")
    earnings_in_ads = bool(EARNINGS_RE.search(ads))
    if invented_price:
        verdict = "SUPPORT_PRICE_INVENTED"
    elif earnings_in_ads:
        verdict = "EARNINGS_IN_ADS"
    elif missing:
        verdict = "OPERATOR_INCOMPLETE"
    else:
        verdict = "OPERATOR_DAY_OK"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "treat_customer_as": "employee",
        "missing": missing,
        "daily_task_count": len(_tasks(data)),
        "support_paid_to": "tjlabs",
        "support_required_for": "commons_support_contact",
        "support_price": "OWNER_UNSET" if owner_unset else price,
        "support_price_invented": invented_price,
        "fail_to_profit_framing": "owner_runbook_not_ad_copy",
        "earnings_in_ads": earnings_in_ads,
        "did_not_invent_percent_or_equity": True,
        "checkout": "NOT_MINTED",
        "agents_spend_ads": False,
        "law_id": str(law.get("id") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-json", default="", help="JSON operator pack object")
    parser.add_argument("--law", default="", help="override law path")
    args = parser.parse_args(argv)
    if args.law:
        load_law(Path(args.law))
    pack: dict[str, Any] = {}
    if args.pack_json:
        loaded = json.loads(args.pack_json)
        if isinstance(loaded, dict):
            pack = loaded
    print(json.dumps(classify_operator(pack), indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
