#!/usr/bin/env python3
"""KEEP vs SELL factory for #business-packs.

Records KEEP / SELL / OPEN decisions for turnkey business packs.
Does not steal the pack-scaffold landing. Marketing stays Bryce.
Never invents Stripe URLs, buyers, cash, or ad spend.

  python3 host/business_pack_keep_sell.py validate
  python3 host/business_pack_keep_sell.py list
  python3 host/business_pack_keep_sell.py record --id NAME --decision KEEP --title TEXT
  python3 host/business_pack_keep_sell.py set-checkout --id NAME --url URL --owner-pasted
  python3 host/business_pack_keep_sell.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_LEDGER = ROOT / "ground" / "BUSINESS_PACK_KEEP_SELL.json"
DEFAULT_CARD = ROOT / "ground" / "BUSINESS_PACK_KEEP_SELL.md"
DEFAULT_DOOR = ROOT / "keep-sell.html"

KIND = "BUSINESS_PACK_KEEP_SELL_FACTORY"
SCHEMA = "business-pack-keep-sell/v1"
RECEIPT_ID = "cursor-business-pack-keep-sell-20260902-01"
CONTROL_PLANE_RECEIPT = "cursor-slack-business-packs-channel-20260902-01"
SLACK_CHANNEL_ID = "C0BU7JAPUH3"
SLACK_CHANNEL_NAME = "#business-packs"
MARKETING = "BRYCE"
DECISIONS = ("OPEN", "KEEP", "SELL")
TIERS_USD = (20, 100, 200, 1000, 10000)
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
# Live Payment Links only. Lookalikes and donate.stripe.com stay out.
STRIPE_PAYMENT_LINK_RE = re.compile(r"^https://buy\.stripe\.com/[A-Za-z0-9]+$")
HONESTY_FLAGS = (
    "no_fake_stripe_urls",
    "no_invented_buyers",
    "no_invented_cash",
    "no_agent_ad_spend",
    "marketing_stays_bryce",
    "checkout_href_requires_chargeable",
)


def load_ledger(path: Path | None = None) -> dict[str, Any]:
    target = Path(path or DEFAULT_LEDGER)
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("ledger is not an object")
    return data


def write_ledger(data: dict[str, Any], path: Path | None = None) -> Path:
    target = Path(path or DEFAULT_LEDGER)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return target


def _pack_map(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {}
    for item in ledger.get("packs") or []:
        if isinstance(item, dict) and item.get("id"):
            rows[str(item["id"])] = item
    return rows


def _finite_decimal(value: Any) -> Decimal | None:
    """Parse one finite JSON-style number without leaking decimal errors."""
    if isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _integral_value(value: Any) -> Decimal | None:
    """Return an exact finite integral Decimal without allocating a Python int."""
    parsed = _finite_decimal(value)
    if parsed is None or parsed != parsed.to_integral_value():
        return None
    return parsed


def checkout_is_live_payment_link(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return False
    if "@" in text or "buy.stripe.com." in text:
        return False
    return bool(STRIPE_PAYMENT_LINK_RE.fullmatch(text))


def public_checkout_href(pack: dict[str, Any], chargeable_urls: set[str] | None = None) -> str:
    """Public doors expose a Stripe href only when CHARGEABLE is proven."""
    url = str(pack.get("checkout_url") or "").strip()
    if not url:
        return ""
    if not pack.get("owner_pasted"):
        return ""
    if not checkout_is_live_payment_link(url):
        return ""
    allowed = chargeable_urls or set()
    if url not in allowed:
        return ""
    return url


def validate_ledger(ledger: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("kind") != KIND:
        errors.append("kind must be %s" % KIND)
    if ledger.get("schema_version") != SCHEMA:
        errors.append("schema_version must be %s" % SCHEMA)
    if ledger.get("marketing") != MARKETING:
        errors.append("marketing must stay BRYCE")
    if ledger.get("no_fake_stripe_urls") is not True:
        errors.append("no_fake_stripe_urls must be true")
    if ledger.get("scaffold_not_stolen") is not True:
        errors.append("scaffold_not_stolen must be true")
    channel = ledger.get("slack_channel") or {}
    if not isinstance(channel, dict) or channel.get("id") != SLACK_CHANNEL_ID:
        errors.append("slack_channel.id must be %s" % SLACK_CHANNEL_ID)
    cash_raw = ledger.get("cash_usd")
    cash = _finite_decimal("0" if cash_raw in (None, "") else cash_raw)
    if cash is None:
        errors.append("cash_usd must be a finite decimal")
    elif cash != Decimal("0.00"):
        errors.append("cash_usd must stay 0.00 without BANK_AVAILABLE")
    buyers_raw = ledger.get("buyers")
    buyers = _integral_value(0 if buyers_raw in (None, "") else buyers_raw)
    if buyers is None:
        errors.append("buyers must be an integer")
    elif buyers != 0:
        errors.append("buyers must stay 0 without a receipt")
    honesty = ledger.get("honesty") or {}
    if not isinstance(honesty, dict):
        errors.append("honesty must be an object")
    else:
        for flag in HONESTY_FLAGS:
            if honesty.get(flag) is not True:
                errors.append("honesty.%s must be true" % flag)
    seen = set()
    packs = ledger.get("packs")
    if packs is None:
        packs = []
    elif not isinstance(packs, list):
        errors.append("packs must be a list")
        packs = []
    for item in packs:
        if not isinstance(item, dict):
            errors.append("pack row is not an object")
            continue
        pack_id = str(item.get("id") or "")
        if not ID_RE.fullmatch(pack_id):
            errors.append("pack id %r is not 8-80 [A-Za-z0-9._-]" % pack_id)
        elif pack_id in seen:
            errors.append("duplicate pack id %s" % pack_id)
        else:
            seen.add(pack_id)
        decision = str(item.get("decision") or "")
        if decision not in DECISIONS:
            errors.append("%s decision must be OPEN|KEEP|SELL" % pack_id)
        title = str(item.get("title") or "").strip()
        if not title:
            errors.append("%s needs a title" % pack_id)
        tier = item.get("tier_usd")
        if tier not in (None, ""):
            parsed_tier = _integral_value(tier)
            if parsed_tier is None:
                errors.append("%s tier_usd must be an integer" % pack_id)
            elif parsed_tier not in TIERS_USD:
                errors.append("%s tier_usd must be one of %s" % (pack_id, TIERS_USD))
        url = str(item.get("checkout_url") or "").strip()
        if url:
            if item.get("owner_pasted") is not True:
                errors.append("%s checkout_url requires owner_pasted" % pack_id)
            if not checkout_is_live_payment_link(url):
                errors.append("%s checkout_url is not a live Payment Link" % pack_id)
        if item.get("marketing") not in (None, "", MARKETING):
            errors.append("%s cannot reassign marketing" % pack_id)
        if item.get("ad_spend"):
            errors.append("%s cannot record agent ad spend" % pack_id)
    return errors


def record_decision(
    ledger: dict[str, Any],
    *,
    pack_id: str,
    decision: str,
    title: str,
    tier_usd: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    pack_id = str(pack_id or "").strip()
    decision = str(decision or "").strip().upper()
    title = str(title or "").strip()
    if not ID_RE.fullmatch(pack_id):
        raise ValueError("id must be 8-80 [A-Za-z0-9._-]")
    if decision not in DECISIONS:
        raise ValueError("decision must be OPEN, KEEP, or SELL")
    if not title:
        raise ValueError("title is required")
    if tier_usd not in (None, "") and int(tier_usd) not in TIERS_USD:
        raise ValueError("tier_usd must be one of %s" % (TIERS_USD,))
    rows = _pack_map(ledger)
    pack = dict(rows.get(pack_id) or {})
    pack.update(
        {
            "id": pack_id,
            "decision": decision,
            "title": title,
            "tier_usd": None if tier_usd in (None, "") else int(tier_usd),
            "notes": str(notes or "").strip(),
            "marketing": MARKETING,
            "checkout_url": str(pack.get("checkout_url") or ""),
            "owner_pasted": bool(pack.get("owner_pasted")),
            "chargeable": False,
            "ad_spend": False,
        }
    )
    if pack_id in rows:
        packs = [pack if item.get("id") == pack_id else item for item in ledger.get("packs") or []]
    else:
        packs = list(ledger.get("packs") or []) + [pack]
    ledger["packs"] = packs
    return pack


def set_checkout(
    ledger: dict[str, Any],
    *,
    pack_id: str,
    url: str,
    owner_pasted: bool,
) -> dict[str, Any]:
    if not owner_pasted:
        raise ValueError("checkout_url requires --owner-pasted; do not invent Stripe URLs")
    url = str(url or "").strip()
    if not checkout_is_live_payment_link(url):
        raise ValueError("not a live Stripe Payment Link")
    rows = _pack_map(ledger)
    if pack_id not in rows:
        raise ValueError("unknown pack id %s" % pack_id)
    pack = rows[pack_id]
    pack["checkout_url"] = url
    pack["owner_pasted"] = True
    pack["chargeable"] = False
    return pack


def render_public_rows(ledger: dict[str, Any], chargeable_urls: set[str] | None = None) -> list[dict[str, Any]]:
    out = []
    for item in ledger.get("packs") or []:
        if not isinstance(item, dict):
            continue
        href = public_checkout_href(item, chargeable_urls)
        out.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "decision": item.get("decision"),
                "tier_usd": item.get("tier_usd"),
                "checkout_state": (
                    "CHARGEABLE" if href
                    else "OWNER_PASTED_NOT_CHARGEABLE" if item.get("owner_pasted") and item.get("checkout_url")
                    else "NEED_OWNER_LINK"
                ),
                "checkout_href": href,
            }
        )
    return out


def empty_ledger() -> dict[str, Any]:
    return {
        "id": RECEIPT_ID,
        "kind": KIND,
        "schema_version": SCHEMA,
        "measured_at": "2026-09-02",
        "source_slack_ts": "1788322816.580769",
        "control_plane_receipt": CONTROL_PLANE_RECEIPT,
        "slack_channel": {"name": SLACK_CHANNEL_NAME, "id": SLACK_CHANNEL_ID},
        "marketing": MARKETING,
        "scaffold_not_stolen": True,
        "scaffold_owned_by": "GOAT",
        "no_fake_stripe_urls": True,
        "product_engines": "private_product_main",
        "tiers_usd": list(TIERS_USD),
        "honesty": {flag: True for flag in HONESTY_FLAGS},
        "cash_usd": "0.00",
        "buyers": 0,
        "packs": [],
    }


def self_test() -> int:
    ledger = empty_ledger()
    assert validate_ledger(ledger) == []
    record_decision(ledger, pack_id="demo-keep-pack-20260902-01", decision="KEEP", title="Keep this winner", tier_usd=100)
    record_decision(ledger, pack_id="demo-sell-pack-20260902-01", decision="SELL", title="Sell this package", tier_usd=200)
    assert validate_ledger(ledger) == []
    try:
        set_checkout(ledger, pack_id="demo-sell-pack-20260902-01", url="https://buy.stripe.com/test_dummy", owner_pasted=False)
        raise AssertionError("invented checkout must fail")
    except ValueError:
        pass
    try:
        set_checkout(ledger, pack_id="demo-sell-pack-20260902-01", url="https://buy.stripe.com.evil.test/x", owner_pasted=True)
        raise AssertionError("lookalike checkout must fail")
    except ValueError:
        pass
    set_checkout(ledger, pack_id="demo-sell-pack-20260902-01", url="https://buy.stripe.com/14kQexample", owner_pasted=True)
    assert validate_ledger(ledger) == []
    rows = render_public_rows(ledger)
    sell = next(row for row in rows if row["id"] == "demo-sell-pack-20260902-01")
    assert sell["checkout_href"] == ""
    assert sell["checkout_state"] == "OWNER_PASTED_NOT_CHARGEABLE"
    charged = render_public_rows(ledger, {"https://buy.stripe.com/14kQexample"})
    sell_live = next(row for row in charged if row["id"] == "demo-sell-pack-20260902-01")
    assert sell_live["checkout_href"] == "https://buy.stripe.com/14kQexample"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ledger.json"
        write_ledger(ledger, path)
        loaded = load_ledger(path)
        assert validate_ledger(loaded) == []
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    errors = validate_ledger(load_ledger(args.ledger))
    if errors:
        print("INVALID")
        for err in errors:
            print(err)
        return 1
    print("VALID")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    errors = validate_ledger(ledger)
    if errors:
        print("INVALID")
        for err in errors:
            print(err)
        return 1
    print(json.dumps(render_public_rows(ledger), indent=2))
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    errors = validate_ledger(ledger)
    if errors:
        print("INVALID")
        for err in errors:
            print(err)
        return 1
    record_decision(
        ledger,
        pack_id=args.id,
        decision=args.decision,
        title=args.title,
        tier_usd=args.tier,
        notes=args.notes or "",
    )
    errors = validate_ledger(ledger)
    if errors:
        print("INVALID")
        for err in errors:
            print(err)
        return 1
    write_ledger(ledger, args.ledger)
    print(json.dumps(_pack_map(ledger)[args.id], indent=2))
    return 0


def _cmd_set_checkout(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    errors = validate_ledger(ledger)
    if errors:
        print("INVALID")
        for err in errors:
            print(err)
        return 1
    set_checkout(ledger, pack_id=args.id, url=args.url, owner_pasted=args.owner_pasted)
    errors = validate_ledger(ledger)
    if errors:
        print("INVALID")
        for err in errors:
            print(err)
        return 1
    write_ledger(ledger, args.ledger)
    print(json.dumps(_pack_map(ledger)[args.id], indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KEEP vs SELL factory for #business-packs")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("validate")
    sub.add_parser("list")
    rec = sub.add_parser("record")
    rec.add_argument("--id", required=True)
    rec.add_argument("--decision", required=True, choices=DECISIONS)
    rec.add_argument("--title", required=True)
    rec.add_argument("--tier", type=int, default=None)
    rec.add_argument("--notes", default="")
    chk = sub.add_parser("set-checkout")
    chk.add_argument("--id", required=True)
    chk.add_argument("--url", required=True)
    chk.add_argument("--owner-pasted", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.cmd == "validate":
        return _cmd_validate(args)
    if args.cmd == "list":
        return _cmd_list(args)
    if args.cmd == "record":
        return _cmd_record(args)
    if args.cmd == "set-checkout":
        return _cmd_set_checkout(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())