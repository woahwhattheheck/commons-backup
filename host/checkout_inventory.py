#!/usr/bin/env python3
"""Compile a read-only Stripe checkout census into a deterministic hygiene report.

This module does not call Stripe or mutate any provider.  It validates a retained
provider snapshot, reconciles the seven historical Commons SKU URLs against the
existing canonical Markdown table, and identifies duplicate/unkeyed checkout
surfaces for owner review.  A live checkout is not a purchase; zero observed
PaymentIntents is not a global zero-revenue claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Iterable, Optional, Sequence

SNAPSHOT_SCHEMA = "tjlabs.checkout-provider-snapshot/v1"
REPORT_SCHEMA = "tjlabs.checkout-inventory-report/v1"
ACCOUNT_ID = "acct_1U6HI9ATH4EDE7XD"
MAX_BYTES = 2_000_000
_LINK_RE = re.compile(r"^plink_[A-Za-z0-9]+$")
_PRICE_RE = re.compile(r"^price_[A-Za-z0-9]+$")
_PRODUCT_RE = re.compile(r"^prod_[A-Za-z0-9]+$")
_URL_RE = re.compile(r"^https://(?:buy|donate)\.stripe\.com/[A-Za-z0-9]+$")
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MODES = frozenset({"automatic", "manual", "subscription"})
_TOP_KEYS = frozenset({
    "schema", "observed_on", "provider", "account_id", "livemode",
    "query_scope", "payment_intents_observed", "balance_transactions_observed", "links",
})
_QUERY_KEYS = frozenset({"payment_links", "line_items", "payment_intents", "balance_transactions"})
_LINK_KEYS = frozenset({
    "link_id", "url", "offer_key", "mode", "completed_count", "completed_limit",
    "price_id", "product_id", "product_name", "currency", "unit_amount_cents",
    "recurring_interval", "product_active",
})


class InventoryError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InventoryError("value is not canonical JSON") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise InventoryError(f"{field} must be an integer >= {minimum}")
    return value


def _bounded_text(value: Any, field: str, *, maximum: int = 512) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise InventoryError(f"{field} must be bounded nonempty text")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        raise InventoryError(f"{field} contains control characters")
    return value


def validate_snapshot(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != _TOP_KEYS:
        raise InventoryError("snapshot has an invalid top-level field set")
    if raw["schema"] != SNAPSHOT_SCHEMA:
        raise InventoryError("snapshot schema is unsupported")
    if raw["provider"] != "stripe" or raw["account_id"] != ACCOUNT_ID or raw["livemode"] is not True:
        raise InventoryError("snapshot provider/account/livemode authority is unexpected")
    if type(raw["observed_on"]) is not str or _DATE_RE.fullmatch(raw["observed_on"]) is None:
        raise InventoryError("observed_on must be canonical YYYY-MM-DD")
    if type(raw["query_scope"]) is not dict or set(raw["query_scope"]) != _QUERY_KEYS:
        raise InventoryError("query_scope is incomplete")
    query_scope = {k: _bounded_text(raw["query_scope"][k], f"query_scope.{k}") for k in sorted(_QUERY_KEYS)}
    payment_count = _integer(raw["payment_intents_observed"], "payment_intents_observed")
    balance_count = _integer(raw["balance_transactions_observed"], "balance_transactions_observed")
    if type(raw["links"]) is not list or not raw["links"]:
        raise InventoryError("links must be a nonempty array")
    if len(raw["links"]) > 100:
        raise InventoryError("links exceeds provider page bound")

    link_ids: set[str] = set()
    urls: set[str] = set()
    normalized = []
    for index, row in enumerate(raw["links"]):
        prefix = f"links[{index}]"
        if type(row) is not dict or set(row) != _LINK_KEYS:
            raise InventoryError(f"{prefix} has an invalid field set")
        link_id = row["link_id"]
        price_id = row["price_id"]
        product_id = row["product_id"]
        url = row["url"]
        if type(link_id) is not str or _LINK_RE.fullmatch(link_id) is None:
            raise InventoryError(f"{prefix}.link_id is invalid")
        if type(price_id) is not str or _PRICE_RE.fullmatch(price_id) is None:
            raise InventoryError(f"{prefix}.price_id is invalid")
        if type(product_id) is not str or _PRODUCT_RE.fullmatch(product_id) is None:
            raise InventoryError(f"{prefix}.product_id is invalid")
        if type(url) is not str or _URL_RE.fullmatch(url) is None:
            raise InventoryError(f"{prefix}.url is invalid")
        if link_id in link_ids:
            raise InventoryError(f"duplicate link_id: {link_id}")
        if url in urls:
            raise InventoryError(f"duplicate payment URL: {url}")
        link_ids.add(link_id); urls.add(url)

        key = row["offer_key"]
        if key is not None and (type(key) is not str or _KEY_RE.fullmatch(key) is None):
            raise InventoryError(f"{prefix}.offer_key is invalid")
        mode = row["mode"]
        if mode not in _MODES:
            raise InventoryError(f"{prefix}.mode is invalid")
        completed_count = row["completed_count"]
        completed_limit = row["completed_limit"]
        if (completed_count is None) != (completed_limit is None):
            raise InventoryError(f"{prefix} completion count/limit must both be null or both integers")
        if completed_count is not None:
            completed_count = _integer(completed_count, f"{prefix}.completed_count")
            completed_limit = _integer(completed_limit, f"{prefix}.completed_limit", minimum=1)
            if completed_count > completed_limit:
                raise InventoryError(f"{prefix} completed_count exceeds completed_limit")
        if row["currency"] != "usd":
            raise InventoryError(f"{prefix}.currency must be usd")
        amount = row["unit_amount_cents"]
        if amount is not None:
            amount = _integer(amount, f"{prefix}.unit_amount_cents", minimum=1)
        recurring = row["recurring_interval"]
        if mode == "subscription":
            if recurring != "month":
                raise InventoryError(f"{prefix} subscription must bind monthly recurrence")
            if amount is None:
                raise InventoryError(f"{prefix} subscription must have fixed amount")
        elif recurring is not None:
            raise InventoryError(f"{prefix} non-subscription cannot carry recurring_interval")
        if row["product_active"] is not True:
            raise InventoryError(f"{prefix} product must be active in an active-link snapshot")
        normalized.append({
            "link_id": link_id,
            "url": url,
            "offer_key": key,
            "mode": mode,
            "completed_count": completed_count,
            "completed_limit": completed_limit,
            "price_id": price_id,
            "product_id": product_id,
            "product_name": _bounded_text(row["product_name"], f"{prefix}.product_name"),
            "currency": "usd",
            "unit_amount_cents": amount,
            "recurring_interval": recurring,
            "product_active": True,
        })
    normalized.sort(key=lambda row: row["link_id"])
    return {
        "schema": SNAPSHOT_SCHEMA,
        "observed_on": raw["observed_on"],
        "provider": "stripe",
        "account_id": ACCOUNT_ID,
        "livemode": True,
        "query_scope": query_scope,
        "payment_intents_observed": payment_count,
        "balance_transactions_observed": balance_count,
        "links": normalized,
    }


def parse_legacy_catalog(text: str) -> dict[str, str]:
    if type(text) is not str:
        raise InventoryError("legacy catalog must be text")
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 4 or cells[0] in {"sku", "---"}:
            continue
        slug, url = cells[0], cells[3].strip("\`")
        if _URL_RE.fullmatch(url) is None:
            continue
        key = f"sku-{slug}-20260826"
        if key in rows:
            raise InventoryError(f"duplicate legacy catalog key: {key}")
        rows[key] = url
    if len(rows) != 7:
        raise InventoryError("legacy catalog must expose exactly seven canonical SKU URLs")
    return rows


def compile_inventory(snapshot: Any, legacy_catalog_text: str) -> dict[str, Any]:
    snap = validate_snapshot(snapshot)
    legacy = parse_legacy_catalog(legacy_catalog_text)
    by_key: dict[str, list[dict[str, Any]]] = {}
    unkeyed = []
    for row in snap["links"]:
        if row["offer_key"] is None:
            unkeyed.append({
                "link_id": row["link_id"],
                "url": row["url"],
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "unit_amount_cents": row["unit_amount_cents"],
            })
        else:
            by_key.setdefault(row["offer_key"], []).append(row)

    duplicate_groups = []
    cleanup_review = []
    for key in sorted(by_key):
        rows = sorted(by_key[key], key=lambda row: row["link_id"])
        if len(rows) <= 1:
            continue
        legacy_url = legacy.get(key)
        canonical_matches = [row for row in rows if legacy_url is not None and row["url"] == legacy_url]
        group = {
            "offer_key": key,
            "link_count": len(rows),
            "legacy_canonical_url": legacy_url,
            "legacy_canonical_match_count": len(canonical_matches),
            "links": [
                {
                    "link_id": row["link_id"],
                    "url": row["url"],
                    "product_name": row["product_name"],
                    "unit_amount_cents": row["unit_amount_cents"],
                    "legacy_canonical": bool(legacy_url is not None and row["url"] == legacy_url),
                }
                for row in rows
            ],
        }
        duplicate_groups.append(group)
        if legacy_url is not None and len(canonical_matches) == 1:
            for row in rows:
                if row["url"] != legacy_url:
                    cleanup_review.append({
                        "offer_key": key,
                        "link_id": row["link_id"],
                        "url": row["url"],
                        "unit_amount_cents": row["unit_amount_cents"],
                        "reason": "ACTIVE_NONCANONICAL_LEGACY_DUPLICATE_REVIEW_ONLY",
                    })

    legacy_reconciliation = []
    for key, canonical_url in sorted(legacy.items()):
        candidates = by_key.get(key, [])
        matches = [row for row in candidates if row["url"] == canonical_url]
        legacy_reconciliation.append({
            "offer_key": key,
            "canonical_url": canonical_url,
            "active_match_count": len(matches),
            "active_link_count_for_key": len(candidates),
            "state": "CANONICAL_ACTIVE" if len(matches) == 1 else "CANONICAL_NOT_UNIQUELY_ACTIVE",
        })

    link_count = len(snap["links"])
    keyed_count = sum(row["offer_key"] is not None for row in snap["links"])
    report = {
        "schema": REPORT_SCHEMA,
        "snapshot_sha256": _sha(snap),
        "observed_on": snap["observed_on"],
        "provider": snap["provider"],
        "account_id": snap["account_id"],
        "livemode": True,
        "counts": {
            "active_links": link_count,
            "keyed_links": keyed_count,
            "unkeyed_links": link_count - keyed_count,
            "manual_capture_links": sum(row["mode"] == "manual" for row in snap["links"]),
            "subscription_links": sum(row["mode"] == "subscription" for row in snap["links"]),
            "single_use_zero_completed_links": sum(row["completed_count"] == 0 and row["completed_limit"] == 1 for row in snap["links"]),
            "payment_intents_observed": snap["payment_intents_observed"],
            "balance_transactions_observed": snap["balance_transactions_observed"],
        },
        "legacy_reconciliation": legacy_reconciliation,
        "duplicate_key_groups": duplicate_groups,
        "unkeyed_links": sorted(unkeyed, key=lambda row: row["link_id"]),
        "cleanup_review": sorted(cleanup_review, key=lambda row: (row["offer_key"], row["link_id"])),
        "authority": {
            "stripe_write_authorized": False,
            "link_deactivation_authorized": False,
            "purchase_inferred": False,
            "buyer_acceptance_inferred": False,
            "payment_inferred": False,
            "cash_inferred": False,
            "revenue_inferred": False,
            "bank_availability_inferred": False,
        },
        "truth_note": "Provider link inventory is checkout supply evidence only. PaymentIntent/balance counts describe this retained Stripe snapshot and do not establish global revenue, bank settlement, or buyer acceptance.",
    }
    report["report_sha256"] = _sha(report)
    return report


def verify_inventory(snapshot: Any, legacy_catalog_text: str, report: Any) -> dict[str, Any]:
    if type(report) is not dict:
        raise InventoryError("report must be an object")
    expected = compile_inventory(snapshot, legacy_catalog_text)
    if _canonical(expected) != _canonical(report):
        raise InventoryError("report differs from deterministic recompilation")
    return expected


def _pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise InventoryError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def read_json(path: Path) -> Any:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        raise InventoryError("cannot open regular input") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
            raise InventoryError("input must be a bounded regular file")
        raw = os.read(fd, st.st_size + 1)
        if len(raw) > MAX_BYTES:
            raise InventoryError("input exceeds size bound")
    finally:
        os.close(fd)
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(InventoryError(f"non-finite JSON constant: {value}")))
    except InventoryError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise InventoryError("input is not valid strict JSON") from exc


def read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise InventoryError("cannot read legacy catalog") from exc
    if len(raw) > MAX_BYTES:
        raise InventoryError("legacy catalog exceeds size bound")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise InventoryError("legacy catalog must be UTF-8") from exc


def write_new(path: Path, value: dict[str, Any]) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags, 0o600)
    except OSError as exc:
        raise InventoryError("refusing to overwrite or follow output path") from exc
    try:
        view = memoryview(payload)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise InventoryError("short output write")
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="checkout-inventory")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify"):
        p = sub.add_parser(name)
        p.add_argument("snapshot", type=Path)
        p.add_argument("legacy_catalog", type=Path)
        if name == "verify":
            p.add_argument("report", type=Path)
        p.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        snapshot = read_json(args.snapshot)
        legacy = read_text(args.legacy_catalog)
        if args.command == "compile":
            result = compile_inventory(snapshot, legacy)
        else:
            result = verify_inventory(snapshot, legacy, read_json(args.report))
        if args.output:
            write_new(args.output, result)
        else:
            sys.stdout.write(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    except (InventoryError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
