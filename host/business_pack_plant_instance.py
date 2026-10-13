#!/usr/bin/env python3
"""Classify the LotRibbon $1000 plant yard-greeting instance. Not a Commons gate.

SCOUT demand 1788326371.557759. Claim id cursor-plant-yard-greeting-pack-20260902-01
does not remint scout-demand-plant-yard-greeting-pack-20260902-01.

Brand + door required. Inventory rows must be costed. Checkout stays
NOT_MINTED. Running cost stays OWNER_UNSET until Bryce pastes it.
ToS percent and ownership stay OWNER_UNSET. No franchise vocabulary on
the door. No earnings copy. No invented Stripe URLs. Agents do not spend ads.
"""
from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import business_pack_operator as operator
import business_pack_running_cost as running_cost
import business_pack_unique as unique
import tjlabs_pack_terms as tos


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_PLANT.json"
INSTANCE_DIR = ROOT / "packs" / "lotribbon-greetings-20260902-01"
REQUIRED_FILES = (
    "README.md",
    "offer.md",
    "instructions.md",
    "assets.md",
    "checkout.md",
    "keep-vs-sell.md",
    "week1.md",
    "calendar.md",
    "terms.md",
    "day.md",
    "running-cost.md",
    "inventory.json",
    "pricing.md",
    "insurance-licensing.md",
    "sop-delivery.md",
    "paperwork.md",
    "index.html",
    "manifest.json",
)
DOOR_SCAN_FILES = (
    "index.html",
    "offer.md",
    "pricing.md",
    "instructions.md",
    "day.md",
    "running-cost.md",
    "README.md",
    "checkout.md",
    "week1.md",
    "calendar.md",
    "sop-delivery.md",
    "insurance-licensing.md",
    "terms.md",
    "assets.md",
    "paperwork.md",
)
PUBLIC_COPY_FILES = (
    "index.html",
    "offer.md",
    "pricing.md",
    "README.md",
)
FRANCHISE_RE = re.compile(r"(?i)\bfranchis")
YARD_CARD_RE = re.compile(r"(?i)yard[\s-]?card")
STRIPE_RE = re.compile(r"(?i)https?://(?:buy|donate)\.stripe\.com\b")
ROYALTY_LIVE_RE = re.compile(r"(?i)no royalty")
MIN_ITEMS = 12
MAX_ITEMS = 20
SOLD_ONCE_BADGE = (
    "Instance 1 of 1. This brand, this domain, this door are sold once."
)
MATCH_METHOD_BADGE = "Built from the same method as our sold instances."
PLANT_ANCHOR_ATTR = 'data-owner-slot="plant-anchor"'


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def instance_dir(root: Path | None = None) -> Path:
    return (root or ROOT) / "packs" / "lotribbon-greetings-20260902-01"


def missing_files(root: Path | None = None) -> list[str]:
    base = instance_dir(root)
    missing: list[str] = []
    for name in REQUIRED_FILES:
        if not (base / name).is_file():
            missing.append(name)
    return missing


def _read(base: Path, name: str) -> str:
    path = base / name
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def combined_door_text(root: Path | None = None) -> str:
    base = instance_dir(root)
    return "\n".join(_read(base, name) for name in DOOR_SCAN_FILES)


def public_copy(root: Path | None = None) -> str:
    """Ads/door surfaces only. Instruction sheets may name the forbidden phrases."""
    base = instance_dir(root)
    return "\n".join(_read(base, name) for name in PUBLIC_COPY_FILES)


def load_inventory(root: Path | None = None) -> dict[str, Any]:
    path = instance_dir(root) / "inventory.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("inventory is not an object")
    return data


def load_manifest(root: Path | None = None) -> dict[str, Any]:
    path = instance_dir(root) / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest is not an object")
    return data


def inventory_report(data: dict[str, Any] | None = None) -> dict[str, Any]:
    record = data if isinstance(data, dict) else {}
    items = record.get("items") if isinstance(record.get("items"), list) else []
    errors: list[str] = []
    computed = Decimal("0")
    if not MIN_ITEMS <= len(items) <= MAX_ITEMS:
        errors.append(f"item_count_{len(items)}")
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            errors.append(f"row_{index}_not_object")
            continue
        try:
            qty = Decimal(str(raw.get("qty")))
            unit = Decimal(str(raw.get("unit_cost_usd")))
            declared = Decimal(str(raw.get("line_total_usd")))
        except (InvalidOperation, TypeError):
            errors.append(f"row_{index}_not_costed")
            continue
        line = qty * unit
        if declared != line:
            errors.append(f"row_{index}_line_mismatch")
        options = raw.get("supplier_options")
        if not isinstance(options, list) or not any(str(x or "").strip() for x in options):
            errors.append(f"row_{index}_missing_supplier")
        if not str(raw.get("sku") or "").strip() or not str(raw.get("name") or "").strip():
            errors.append(f"row_{index}_missing_name")
        computed += line
    try:
        declared_total = Decimal(str(record.get("planning_total_usd")))
    except (InvalidOperation, TypeError):
        declared_total = None
        errors.append("planning_total_missing")
    if declared_total is not None and declared_total != computed:
        errors.append("planning_total_mismatch")
    if record.get("planning_not_owner_pasted_running_cost") is not True:
        errors.append("planning_must_not_be_pasted_running_cost")
    return {
        "item_count": len(items),
        "computed_total_usd": str(computed),
        "declared_total_usd": str(declared_total) if declared_total is not None else "",
        "ok": not errors,
        "errors": errors,
        "asset_names": [
            str(item.get("name") or "").strip()
            for item in items
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ],
    }


def sold_once_checks(
    *,
    unique: str,
    manifest_sold_once: Any,
    door_html: str,
) -> dict[str, Any]:
    """Verifier-written sold-once badge + empty PLANT price-anchor slot.

    UNIQUE doors get the sold-once sentence. MATCH doors get the method
    sentence. Manifest sold_once must match UNIQUE. Live 'No royalty' is
    blocked while ToS is HOLD_COUNSEL / OWNER_UNSET.
    """
    sold_once = unique == "UNIQUE"
    badge = SOLD_ONCE_BADGE if sold_once else MATCH_METHOD_BADGE
    base: dict[str, Any] = {
        "sold_once": sold_once,
        "sold_once_badge": badge,
        "plant_anchor_slot": "OWNER_UNSET",
    }
    if sold_once:
        if manifest_sold_once is not True:
            return {**base, "ok": False, "verdict": "SOLD_ONCE_MISMATCH"}
        if SOLD_ONCE_BADGE not in door_html:
            return {**base, "ok": False, "verdict": "SOLD_ONCE_BADGE_MISSING"}
        if PLANT_ANCHOR_ATTR not in door_html:
            return {**base, "ok": False, "verdict": "PLANT_ANCHOR_SLOT_MISSING"}
        if ROYALTY_LIVE_RE.search(door_html):
            return {**base, "ok": False, "verdict": "ROYALTY_CLAIM_BEFORE_TOS"}
    elif manifest_sold_once is True:
        return {**base, "ok": False, "verdict": "SOLD_ONCE_MISMATCH"}
    return {**base, "ok": True, "verdict": None}


def _offer_from_instance(root: Path | None = None) -> dict[str, Any]:
    law = load_law()
    manifest = load_manifest(root)
    inventory = inventory_report(load_inventory(root))
    text = public_copy(root)
    offer = dict(manifest)
    offer.setdefault("brand", law.get("brand"))
    offer.setdefault("door", law.get("door_path"))
    offer.setdefault("door_path", law.get("door_path"))
    offer.setdefault("checkout", law.get("door_path"))
    offer.setdefault("keep_or_sell", "SELL")
    offer.setdefault("unique_instance_sell", True)
    offer["copy"] = text
    offer["ads_copy"] = text
    offer["assets"] = inventory["asset_names"] or offer.get("assets")
    offer["instructions"] = _read(instance_dir(root), "instructions.md")
    offer.setdefault("running_cost_usd", "OWNER_UNSET")
    offer.setdefault("owner_pasted_running_cost", False)
    offer.setdefault("tos_owner_pasted", False)
    return offer


def classify_instance(root: Path | None = None) -> dict[str, Any]:
    law = load_law()
    missing = missing_files(root)
    result: dict[str, Any] = {
        "id": law.get("id"),
        "gate": False,
        "commons_admission": False,
        "checkout": "NOT_MINTED",
        "booking": "OWNER_PASTE_REQUIRED",
        "saleable": False,
        "hold_counsel": True,
        "running_cost": "OWNER_UNSET",
        "support_price": "OWNER_UNSET",
        "did_not_remint_scout_demand": True,
        "matched_demand_id": law.get("matched_demand_id"),
        "brand": law.get("brand"),
        "missing_files": missing,
        "no_franchise_vocabulary": True,
        "no_earnings_copy": True,
        "no_fake_stripe_urls": True,
        "agents_spend_ads": False,
        "marketing": "bryce_only",
    }
    if missing:
        result["verdict"] = "MISSING_FILES"
        return result

    inventory = inventory_report(load_inventory(root))
    result["inventory"] = {
        "item_count": inventory["item_count"],
        "planning_total_usd": inventory["declared_total_usd"],
        "ok": inventory["ok"],
        "errors": inventory["errors"],
    }
    if not inventory["ok"]:
        result["verdict"] = "INVENTORY_NOT_COSTED"
        return result

    text = combined_door_text(root)
    if FRANCHISE_RE.search(text):
        result["verdict"] = "FRANCHISE_VOCAB"
        result["no_franchise_vocabulary"] = False
        return result
    if YARD_CARD_RE.search(text):
        result["verdict"] = "YARD_CARD_COPY"
        return result
    if STRIPE_RE.search(text):
        result["verdict"] = "FAKE_STRIPE_URL"
        result["no_fake_stripe_urls"] = False
        return result

    copy = unique.classify_copy(text)
    if copy["verdict"] == "EARNINGS_CLAIM":
        result["verdict"] = "EARNINGS_CLAIM"
        result["no_earnings_copy"] = False
        result["copy"] = copy
        return result

    offer = _offer_from_instance(root)
    sell = unique.classify_sell_offer(offer)
    result["sell_instance"] = sell
    if sell["verdict"] != "UNIQUE_INSTANCE_SELL_OK":
        result["verdict"] = sell["verdict"]
        return result

    cost = running_cost.classify_running_cost(offer)
    result["running_cost_class"] = cost
    if cost["verdict"] != "RUNNING_COST_OK":
        result["verdict"] = cost["verdict"]
        return result

    terms = tos.classify_instance(
        {
            "copy": text,
            "terms_text": _read(instance_dir(root), "terms.md"),
            "door_copy": _read(instance_dir(root), "index.html"),
        }
    )
    result["tos"] = {
        "verdict": terms["verdict"],
        "saleable": terms["saleable"],
        "hold_counsel": terms["hold_counsel"],
        "profit_share_percent": terms["profit_share_percent"],
        "partial_ownership_fraction": terms["partial_ownership_fraction"],
    }
    if terms["verdict"] in {"EARNINGS_CLAIM", "FAKE_STRIPE_URL"}:
        result["verdict"] = terms["verdict"]
        result["saleable"] = False
        return result

    day_text = _read(instance_dir(root), "day.md")
    op = operator.classify_operator(
        {
            "onboarding": "filled" if "## Onboarding" in day_text else "",
            "training": "filled" if "## Training" in day_text else "",
            "daily_tasks": [
                line.strip()
                for line in day_text.splitlines()
                if line.strip().startswith("1.")
                or line.strip().startswith("2.")
                or line.strip().startswith("3.")
            ],
            "copy": "",
            "support": {"price_usd": "OWNER_UNSET"},
        }
    )
    result["operator"] = {
        "verdict": op["verdict"],
        "support_price": op["support_price"],
        "daily_task_count": op["daily_task_count"],
    }
    if op["verdict"] != "OPERATOR_DAY_OK":
        result["verdict"] = op["verdict"]
        return result

    fingerprint = unique.content_fingerprint(offer)
    sales = unique.classify_sales(
        [
            {
                "sale_id": str(offer.get("sale_id") or law.get("slug") or "plant"),
                "assets": offer.get("assets"),
                "brand": offer.get("brand"),
                "checkout": offer.get("checkout"),
                "instructions": _read(instance_dir(root), "instructions.md"),
            }
        ]
    )
    result["fingerprint"] = fingerprint
    result["unique"] = sales["sales"][0]["verdict"] if sales["sales"] else "MISSING_FINGERPRINT"
    if result["unique"] != "UNIQUE":
        result["verdict"] = result["unique"]
        return result

    door_html = _read(instance_dir(root), "index.html")
    sold = sold_once_checks(
        unique=str(result["unique"]),
        manifest_sold_once=load_manifest(root).get("sold_once"),
        door_html=door_html,
    )
    result["sold_once"] = sold["sold_once"]
    result["sold_once_badge"] = sold["sold_once_badge"]
    result["plant_anchor_slot"] = sold["plant_anchor_slot"]
    if not sold["ok"]:
        result["verdict"] = sold["verdict"]
        return result

    keep = _read(instance_dir(root), "keep-vs-sell.md")
    result["ops_sell_checklist"] = (
        "- [x] a buyer can run it from instructions.md" in keep
        and "- [x] assets.md is complete" in keep
        and "- [x] week1.md is complete" in keep
    )
    if not result["ops_sell_checklist"]:
        result["verdict"] = "SELL_CHECKLIST_INCOMPLETE"
        return result

    result["verdict"] = "PLANT_INSTANCE_OK"
    result["saleable"] = False
    result["tos_blocks_factory_sale"] = terms["verdict"] == "TOS_INCOMPLETE"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--law", default="", help="override law path")
    args = parser.parse_args(argv)
    if args.law:
        load_law(Path(args.law))
    print(json.dumps(classify_instance(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
