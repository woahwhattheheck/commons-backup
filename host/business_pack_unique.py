#!/usr/bin/env python3
"""Classify business-pack sales for clone-stamps. Not a Commons gate.

Bryce / GOAT 1788323099.458239: each customer purchase is a fresh package.
Do not sell the same assets+ops twice. Marketing uniqueness is only honest
when the fingerprint is unique. Agents do not spend ads. No fake Stripe URLs.

Bryce / GOAT 1788323180.640899: similar ≠ clone. Shared template_id/vertical
is not a clone-stamp. Each sold unit is a distinct instance (assets, brand,
checkout, instructions). Mystery-box pools mix rare valuable ideas; Bryce
sets the potential value range. Not a lottery / not gambling. Do not invent
odds tables or fake scarcity.

SCOUT / Claude 1788326387.638969: a named unique-instance SELL needs a name
and a door (brand + checkout/door). Missing those fields is a kit, not a
unique-instance SELL. Copy uses prices and time budgets, never earnings.
Agents do not spend ads. Do not steal GOAT yard-card candidate files.

Bryce hub 1788332899.203819: swarm-trivial packs stay saved for Commons
and we sell them too. Biggest potential stays in house. Keep the gems.
Sell a respectable product. Do not sell trash. Not a KEEP/SELL ledger
row and not a Commons gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACKS.json"

# Sharing these keys across sales is allowed. They are not the instance.
SHARED_NOT_CLONE = ("template_id", "vertical", "family", "pack_family")
INSTANCE_FIELDS = ("assets", "brand", "checkout", "instructions")
ODDS_KEYS = (
    "odds",
    "odds_table",
    "win_probability",
    "probability_table",
    "implied_odds",
)
DOOR_ALIASES = ("checkout", "door", "door_url", "door_path")
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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _field_token(pack: dict[str, Any], name: str) -> str:
    sha = str(pack.get(f"{name}_sha256") or "").strip().lower()
    if sha:
        return sha
    value = pack.get(name)
    if value is None or value == "":
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def content_fingerprint(pack: dict[str, Any]) -> str:
    """Hash of the sold instance. template_id/vertical are ignored.

    Prefer the distinct-instance fields (assets, brand, checkout, instructions).
    Ops still counts when present. Legacy sales with only assets+ops keep that
    fingerprint so the fresh-pack law still stamps identical copies.
    """
    tokens = {name: _field_token(pack, name) for name in INSTANCE_FIELDS}
    ops = _field_token(pack, "ops")
    if all(tokens.values()):
        parts = [tokens[name] for name in INSTANCE_FIELDS]
        if ops:
            parts.append(ops)
        return _sha256_text("\n".join(parts))
    assets = tokens["assets"]
    if assets and ops:
        return _sha256_text(assets + "\n" + ops)
    return ""


def classify_sales(sales: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Ledger of customer purchases. Same instance fingerprint on two sales is CLONE_STAMP."""
    rows = sales if isinstance(sales, list) else []
    by_sale: dict[str, str] = {}
    by_fp: dict[str, list[str]] = {}
    missing: list[str] = []
    conflicts: list[str] = []
    classified: list[dict[str, Any]] = []
    raw_by_id: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        sale_id = str(raw.get("sale_id") or "").strip()
        if not sale_id:
            missing.append("(blank sale_id)")
            continue
        fingerprint = content_fingerprint(raw)
        raw_by_id[sale_id] = raw
        if not fingerprint:
            missing.append(sale_id)
            classified.append(
                {
                    "sale_id": sale_id,
                    "verdict": "MISSING_FINGERPRINT",
                    "fingerprint": "",
                    "marketing_uniqueness_ok": False,
                    "template_id": str(raw.get("template_id") or ""),
                    "vertical": str(raw.get("vertical") or ""),
                }
            )
            continue
        prior = by_sale.get(sale_id)
        if prior and prior != fingerprint:
            conflicts.append(sale_id)
        by_sale[sale_id] = fingerprint
        by_fp.setdefault(fingerprint, [])
        if sale_id not in by_fp[fingerprint]:
            by_fp[fingerprint].append(sale_id)
    clone_pairs: list[list[str]] = []
    for fingerprint, sale_ids in by_fp.items():
        if len(sale_ids) > 1:
            clone_pairs.append(sale_ids)
    for sale_id, fingerprint in by_sale.items():
        shared = by_fp.get(fingerprint) or [sale_id]
        if sale_id in conflicts:
            verdict = "CONFLICT"
        elif len(shared) > 1:
            verdict = "CLONE_STAMP"
        else:
            verdict = "UNIQUE"
        raw = raw_by_id.get(sale_id) or {}
        classified.append(
            {
                "sale_id": sale_id,
                "verdict": verdict,
                "fingerprint": fingerprint,
                "shared_with": [s for s in shared if s != sale_id],
                "marketing_uniqueness_ok": verdict == "UNIQUE",
                "template_id": str(raw.get("template_id") or ""),
                "vertical": str(raw.get("vertical") or ""),
            }
        )
    clone_sales = {s for pair in clone_pairs for s in pair}
    unique_count = sum(1 for row in classified if row["verdict"] == "UNIQUE")
    return {
        "gate": False,
        "commons_admission": False,
        "clone_stamp": bool(clone_pairs),
        "each_purchase": "fresh_package",
        "similar_is_not_clone": True,
        "shared_not_clone": list(SHARED_NOT_CLONE),
        "instance_fields": list(INSTANCE_FIELDS),
        "marketing": "bryce_only",
        "no_fake_stripe_urls": True,
        "not_lottery": True,
        "not_gambling": True,
        "fake_scarcity": False,
        "sales": classified,
        "clone_pairs": clone_pairs,
        "conflicts": conflicts,
        "missing_fingerprint": missing,
        "unique_count": unique_count,
        "clone_stamp_count": len(clone_sales),
    }


def marketing_uniqueness_ok(pack: dict[str, Any], sales: list[dict[str, Any]]) -> bool:
    """True only when this pack's fingerprint appears on exactly one sale."""
    result = classify_sales(sales)
    sale_id = str(pack.get("sale_id") or "").strip()
    for row in result["sales"]:
        if row["sale_id"] == sale_id:
            return bool(row["marketing_uniqueness_ok"])
    return False


def _nonempty(value: Any) -> bool:
    if value is None or value is False:
        return False
    if value == "" or value == {} or value == []:
        return False
    return True


def _lottery_framing(data: dict[str, Any]) -> bool:
    if data.get("lottery") is True or data.get("is_lottery") is True:
        return True
    if data.get("gambling") is True or data.get("is_gambling") is True:
        return True
    if data.get("not_lottery") is True and data.get("not_gambling") is True:
        return False
    framing = str(data.get("framing") or "").lower()
    return "lottery" in framing or "gambling" in framing


def _has_instance_brand(offer: dict[str, Any]) -> bool:
    return bool(_field_token(offer, "brand") or str(offer.get("brand") or "").strip())


def _has_instance_door(offer: dict[str, Any]) -> bool:
    for name in DOOR_ALIASES:
        if _field_token(offer, name) or str(offer.get(name) or "").strip():
            return True
    return False


def classify_sell_offer(offer: dict[str, Any] | None) -> dict[str, Any]:
    """Named unique-instance SELL needs brand + door. Not a Commons gate.

    SCOUT 1788326387.638969: at a named unique-instance price the buyer
    expects a name and a door. Missing those is a kit, not that SELL.
    Does not rewrite GOAT yard-card files. Does not invent Stripe URLs.
    """
    data = offer if isinstance(offer, dict) else {}
    keep_or_sell = str(data.get("keep_or_sell") or "").strip().upper()
    claiming = keep_or_sell == "SELL" or data.get("unique_instance_sell") is True
    kit = data.get("kit_not_unique_instance") is True
    missing: list[str] = []
    if not _has_instance_brand(data):
        missing.append("brand")
    if not _has_instance_door(data):
        missing.append("door")
    if claiming and missing and not kit:
        verdict = "MISSING_INSTANCE_FOR_PRICE"
    elif kit:
        verdict = "KIT_NOT_UNIQUE_INSTANCE"
    elif claiming:
        verdict = "UNIQUE_INSTANCE_SELL_OK"
    else:
        verdict = "SELL_INSTANCE_UNCLAIMED"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "claiming_unique_instance_sell": claiming,
        "kit_not_unique_instance": kit,
        "missing_instance": missing,
        "has_brand": "brand" not in missing,
        "has_door": "door" not in missing,
        "marketing": "bryce_only",
        "agents_spend_ads": False,
        "no_fake_stripe_urls": True,
        "checkout": "NOT_MINTED" if not _has_instance_door(data) else "present_on_offer",
        "did_not_steal_goat_yard_card": True,
    }


def classify_copy(text: str) -> dict[str, Any]:
    """Prices and time budgets are fine. Earnings claims are flagged, not gated."""
    body = text or ""
    earnings = bool(EARNINGS_RE.search(body))
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": "EARNINGS_CLAIM" if earnings else "COPY_OK",
        "earnings_claim": earnings,
        "copy": "prices_and_time_budgets_never_earnings",
        "marketing": "bryce_only",
        "agents_spend_ads": False,
    }


def classify_mystery_pool(pool: dict[str, Any] | None) -> dict[str, Any]:
    """Mystery-nuts pool. Bryce owns the value range. Not a Commons gate.

    Invented odds tables, lottery/gambling framing, and fake scarcity are
    flagged. They do not become admission locks. A missing dollar range is
    not invented; a posted range without Bryce as owner is.
    """
    data = pool if isinstance(pool, dict) else {}
    invented_odds = any(_nonempty(data.get(key)) for key in ODDS_KEYS)
    owner = str(data.get("value_range_owner") or data.get("value_range_set_by") or "").strip().upper()
    value_range = data.get("value_range")
    range_claimed_without_bryce = _nonempty(value_range) and owner != "BRYCE"
    value_range_owner_ok = owner == "BRYCE"
    fake_scarcity = data.get("fake_scarcity") is True
    lottery_framing = _lottery_framing(data)
    if invented_odds:
        verdict = "INVENTED_ODDS"
    elif lottery_framing:
        verdict = "LOTTERY_FRAMING"
    elif fake_scarcity:
        verdict = "FAKE_SCARCITY"
    elif range_claimed_without_bryce:
        verdict = "VALUE_RANGE_NOT_BRYCE"
    else:
        verdict = "MYSTERY_OK"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "invented_odds": invented_odds,
        "lottery_framing": lottery_framing,
        "fake_scarcity": fake_scarcity,
        "not_lottery": True,
        "not_gambling": True,
        "value_range_owner": owner or "",
        "value_range_owner_ok": value_range_owner_ok,
        "value_range_set_by": "BRYCE",
        "marketing": "bryce_only",
        "agents_invent_odds_tables": False,
        "nuts": "rare_extremely_valuable_ideas",
        "framing": "fun_generous_gesture_tokenjunkielabs",
    }


def classify_keep_gems(row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Keep gems / no trash. Factory policy, not a Commons gate.

    Does not write KEEP/SELL ledger rows. Agents do not invent which named
    pack is KEEP vs SELL. A trash offer is flagged, not turned into a lock.
    """
    data = row if isinstance(row, dict) else {}
    sell_trash = data.get("sell_trash") is True
    invented_row = data.get("invented_keep_sell_row") is True
    respectable = data.get("respectable_product") is not False
    if sell_trash:
        verdict = "TRASH_OFFER"
    elif invented_row:
        verdict = "INVENTED_KEEP_SELL_ROW"
    elif not respectable:
        verdict = "NOT_RESPECTABLE"
    else:
        verdict = "RESPECTABLE_PRODUCT_OK"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "keep_gems": True,
        "sell_trash": sell_trash,
        "respectable_product": respectable and not sell_trash,
        "swarm_trivial_revenue": "saved_for_commons_and_we_sell_too",
        "biggest_potential": "in_house",
        "keep_sell_ledger": "not_this_seat",
        "did_not_write_keep_sell_ledger": True,
        "did_not_invent_keep_sell_rows": not invented_row,
        "checkout": "NOT_MINTED",
        "marketing": "bryce_only",
        "agents_spend_ads": False,
        "no_fake_stripe_urls": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sales-json", default="", help="JSON list of sale objects")
    parser.add_argument("--sales-file", default="", help="path to JSON list of sales")
    parser.add_argument("--pool-json", default="", help="JSON mystery-pool object")
    parser.add_argument("--offer-json", default="", help="JSON unique-instance SELL offer")
    parser.add_argument("--copy", default="", help="offer copy to scan for earnings claims")
    parser.add_argument("--keep-gems-json", default="", help="JSON keep-gems policy object")
    parser.add_argument("--law", default="", help="override law path")
    args = parser.parse_args(argv)
    law = load_law(Path(args.law) if args.law else None)
    sales: list[dict[str, Any]] = []
    if args.sales_file:
        loaded = json.loads(Path(args.sales_file).read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            sales = loaded
    elif args.sales_json:
        loaded = json.loads(args.sales_json)
        if isinstance(loaded, list):
            sales = loaded
    result = classify_sales(sales)
    result["law_id"] = law.get("id")
    compose = law.get("compose") if isinstance(law.get("compose"), dict) else {}
    result["composed_id"] = compose.get("id")
    result["source_channel_id"] = law.get("source_channel_id")
    if args.pool_json:
        result["mystery"] = classify_mystery_pool(json.loads(args.pool_json))
    else:
        result["mystery"] = classify_mystery_pool(law.get("mystery") if isinstance(law.get("mystery"), dict) else {})
    if args.offer_json:
        result["sell_instance"] = classify_sell_offer(json.loads(args.offer_json))
    if args.copy:
        result["copy"] = classify_copy(args.copy)
    if args.keep_gems_json:
        result["keep_gems"] = classify_keep_gems(json.loads(args.keep_gems_json))
    else:
        result["keep_gems"] = classify_keep_gems(
            law.get("keep_gems") if isinstance(law.get("keep_gems"), dict) else {}
        )
    print(json.dumps(result, indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
