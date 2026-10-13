#!/usr/bin/env python3
"""Classify tjlabs sold-pack ToS slots. Not a Commons gate.

Bryce 1788326869.732839: tjlabs takes a percentage and partial ownership
of profit from sold business packs, written into the terms of service.

Agents do not invent the percent or the ownership fraction. Empty slots
are OWNER_UNSET. Saleable stays false until the owner pastes both numbers
and counsel_cleared is true. Checkout stays NOT_MINTED. No fake Stripe
URLs. No earnings copy. SCOUT keeps buyer-side research.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "TJLABS_PACK_TERMS.json"
UNSET_TOKENS = frozenset(
    {
        "",
        "OWNER_UNSET",
        "OWNER_PASTE_REQUIRED",
        "null",
        "none",
        "TODO",
        "TBD",
    }
)
EARNINGS_RE = re.compile(
    r"(?i)\bmake\s+\$\d|\bearn\s+\$\d|\bprofit\s+\$\d|"
    r"\bmake \$\d+ this weekend|\bunrealistic result|"
    r"\bearnings claim|\bpayback in\b"
)
STRIPE_RE = re.compile(r"(?i)https?://(?:buy|donate)\.stripe\.com\b")
SLOT_KEYS = ("profit_share_percent", "partial_ownership_fraction")


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def is_unset(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return False
    text = str(value).strip()
    return text.casefold() in {token.casefold() for token in UNSET_TOKENS}


def _combined_text(instance: dict[str, Any]) -> str:
    parts = [
        json.dumps(instance, sort_keys=True),
        str(instance.get("copy") or ""),
        str(instance.get("terms_text") or ""),
        str(instance.get("door_copy") or ""),
    ]
    return "\n".join(parts)


def classify_instance(
    instance: dict[str, Any] | None = None,
    law: dict[str, Any] | None = None,
) -> dict[str, Any]:
    law = law if law is not None else load_law()
    record = dict(instance or {})
    text = _combined_text(record)
    percent = record.get("profit_share_percent", law.get("profit_share_percent"))
    ownership = record.get(
        "partial_ownership_fraction", law.get("partial_ownership_fraction")
    )
    owner_pasted = bool(record.get("owner_pasted", law.get("owner_pasted")))
    counsel_cleared = bool(record.get("counsel_cleared", law.get("counsel_cleared")))

    result: dict[str, Any] = {
        "id": law.get("id"),
        "gate": False,
        "commons_admission": False,
        "checkout": "NOT_MINTED",
        "no_fake_stripe_urls": True,
        "no_earnings_copy": True,
        "hold_counsel": True,
        "saleable": False,
        "owner_pasted": owner_pasted,
        "counsel_cleared": counsel_cleared,
        "profit_share_percent": percent,
        "partial_ownership_fraction": ownership,
        "entity_short": law.get("entity_short", "tjlabs"),
    }

    if STRIPE_RE.search(text):
        result["verdict"] = "FAKE_STRIPE_URL"
        result["no_fake_stripe_urls"] = False
        return result
    if EARNINGS_RE.search(text):
        result["verdict"] = "EARNINGS_CLAIM"
        result["no_earnings_copy"] = False
        return result

    slots_missing = is_unset(percent) or is_unset(ownership) or not owner_pasted
    if slots_missing:
        result["verdict"] = "TOS_INCOMPLETE"
        return result

    if not counsel_cleared:
        result["verdict"] = "TOS_SLOTS_SET"
        return result

    result["verdict"] = "TOS_COUNSEL_CLEARED"
    result["hold_counsel"] = False
    result["saleable"] = True
    return result


def template_has_unset_slots(root: Path | None = None) -> bool:
    base = root or ROOT
    text = (base / "packs" / "_template" / "terms.md").read_text(encoding="utf-8")
    return (
        "tjlabs_profit_share_percent: OWNER_UNSET" in text
        and "tjlabs_partial_ownership_fraction: OWNER_UNSET" in text
        and "NOT_MINTED" in text
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instance",
        help="JSON object for one sold-pack instance overlay",
    )
    args = parser.parse_args(argv)
    instance: dict[str, Any] = {}
    if args.instance:
        loaded = json.loads(args.instance)
        if not isinstance(loaded, dict):
            raise SystemExit("instance must be a JSON object")
        instance = loaded
    print(json.dumps(classify_instance(instance), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
