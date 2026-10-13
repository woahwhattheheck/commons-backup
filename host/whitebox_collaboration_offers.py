#!/usr/bin/env python3
"""Validate and summarize the dated White Box collaboration-offer catalog."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path("revenue/ip/whitebox_collaboration_offers.json")
SCHEMA_PATH = Path("revenue/ip/whitebox_collaboration_offers.schema.json")
OFFER_IDS = (
    "whitebox-archive-license",
    "whitebox-sponsored-benchmark",
    "whitebox-joint-paper-reproduction",
    "whitebox-private-evaluation",
)
SOURCE_IDS = (
    "diagnostic-page",
    "commercial-page",
    "whitebox-hour-sku",
    "archive-inventory",
    "archive-license-probe",
    "offering-families",
)
TRUTH_KEYS = {
    "buyer_interest_verified",
    "agreement_signed",
    "delivery_completed",
    "cash_received",
    "archive_transfer_cleared",
}
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class CollaborationOfferError(ValueError):
    """The catalog violates its source, offer, or truth contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CollaborationOfferError(message)


def _exact_keys(value: dict, required: set[str], at: str) -> None:
    _require(isinstance(value, dict), f"{at} must be an object")
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    _require(not missing, f"{at} missing keys {missing!r}")
    _require(not extra, f"{at} has extra keys {extra!r}")


def _safe_path(value: str, at: str) -> str:
    _require(isinstance(value, str) and value, f"{at} path is empty")
    _require("\\" not in value, f"{at} path must use POSIX separators")
    parsed = PurePosixPath(value)
    _require(not parsed.is_absolute() and ".." not in parsed.parts, f"{at} path escapes root")
    _require(str(parsed) == value, f"{at} path is not canonical")
    return value


def _git(root: Path, *args: str, binary: bool = False):
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise CollaborationOfferError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def load(root: Path = ROOT) -> tuple[dict, dict]:
    data = json.loads((root / CATALOG_PATH).read_text(encoding="utf-8"))
    schema = json.loads((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    return data, schema


def _validate_sources(root: Path, base: str, sources: list[dict]) -> dict[str, dict]:
    _require([source.get("id") for source in sources] == list(SOURCE_IDS), "source order/set drift")
    result = {}
    for index, source in enumerate(sources):
        at = f"sources[{index}]"
        _exact_keys(source, {"id", "path", "blob_sha", "evidence_phrase"}, at)
        path = _safe_path(source["path"], at)
        _require(bool(HEX40.fullmatch(source["blob_sha"])), f"{at} blob invalid")
        actual = _git(root, "rev-parse", f"{base}:{path}")
        _require(actual == source["blob_sha"], f"{at} source blob drift: {actual}")
        raw = _git(root, "cat-file", "blob", actual, binary=True).decode("utf-8", "replace")
        _require(source["evidence_phrase"] in raw, f"{at} evidence phrase missing")
        result[source["id"]] = source
    return result


def _validate_price(price: dict, known: bool, amount: int | None, basis: str, at: str) -> None:
    _exact_keys(price, {"known", "amount_usd", "basis"}, at)
    _require(price == {"known": known, "amount_usd": amount, "basis": basis}, f"{at} price drift")


def validate(root: Path, data: dict, schema: dict) -> dict:
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema draft mismatch")
    _require(schema.get("$id", "").endswith("/revenue/ip/whitebox_collaboration_offers.schema.json"), "schema id mismatch")
    _require(schema.get("additionalProperties") is False, "schema root must be closed")
    _exact_keys(
        data,
        {
            "schema_version", "kind", "generated_at", "generated_from_main", "assessed_at", "scope",
            "commercial_boundary", "truth", "sources", "entry_routes", "offers",
        },
        "catalog",
    )
    _require(data["schema_version"] == "commons-whitebox-collaboration-offers/v1", "schema_version mismatch")
    _require(data["kind"] == "WHITEBOX_COLLABORATION_OFFERS", "kind mismatch")
    _require(bool(HEX40.fullmatch(data["generated_from_main"])), "generated_from_main invalid")
    _git(root, "cat-file", "-e", f"{data['generated_from_main']}^{{commit}}")
    _require(data["assessed_at"] == "2026-08-26", "assessed_at drift")
    _require(isinstance(data["generated_at"], str) and "T" in data["generated_at"], "generated_at invalid")
    _require(isinstance(data["scope"], str) and data["scope"], "scope empty")
    _require("no archive payload" in data["commercial_boundary"].lower(), "archive payload boundary missing")
    _exact_keys(data["truth"], TRUTH_KEYS, "truth")
    _require(not any(data["truth"].values()), "truth block may not invent commercial or transfer outcomes")
    source_by_id = _validate_sources(root, data["generated_from_main"], data["sources"])

    routes = data["entry_routes"]
    _require(isinstance(routes, list) and len(routes) == 1, "exactly one entry route required")
    route = routes[0]
    _exact_keys(route, {"id", "family", "status", "price", "checkout_url", "source_ids", "uses_owner_archive_payload"}, "entry_routes[0]")
    _require(route["id"] == "whitebox-advisory-hour", "entry route id drift")
    _require(route["family"] == "EXPERTISE" and route["status"] == "LIVE_CHECKOUT", "entry route state drift")
    _validate_price(route["price"], True, 250, "HOURLY", "entry_routes[0]")
    _require(route["checkout_url"] == "https://buy.stripe.com/8x27sK2Kp3UZ9uF2SC43S07", "checkout route drift")
    _require(route["source_ids"] == ["whitebox-hour-sku"], "entry route source drift")
    _require(route["uses_owner_archive_payload"] is False, "entry route may not use archive payload")

    offers = data["offers"]
    _require(isinstance(offers, list) and len(offers) == 4, "exactly four offers required")
    _require([offer.get("id") for offer in offers] == list(OFFER_IDS), "offer order/set drift")
    required_offer_keys = {
        "id", "name", "family", "state", "price", "duration_days", "asset_boundary", "deliverable",
        "customer_supplies", "source_ids", "uses_owner_archive_payload", "transfer_payload", "blocker",
    }
    for index, offer in enumerate(offers):
        _exact_keys(offer, required_offer_keys, f"offers[{index}]")
        _require(all(source_id in source_by_id for source_id in offer["source_ids"]), f"offers[{index}] unknown source")
        _require(offer["uses_owner_archive_payload"] is False, f"offers[{index}] archive payload use must remain false")
        _require(offer["transfer_payload"] is False, f"offers[{index}] payload transfer must remain false")

    archive, benchmark, paper, private = offers
    _require(archive["family"] == "DATA" and archive["state"] == "BLOCKED_EVIDENCE_REQUIRED", "archive license must remain blocked")
    _validate_price(archive["price"], False, None, "UNKNOWN", "archive license")
    _require(archive["asset_boundary"] == "OWNER_ARCHIVE", "archive license boundary drift")
    _require("quantized-copy source provenance" in archive["blocker"], "archive evidence blocker missing")
    _require({"archive-inventory", "archive-license-probe"}.issubset(archive["source_ids"]), "archive sources incomplete")

    _require(benchmark["family"] == "SERVICES" and benchmark["state"] == "AVAILABLE_CUSTOMER_OWNED_ASSET", "benchmark state drift")
    _validate_price(benchmark["price"], True, 12000, "FIXED", "sponsored benchmark")
    _require(benchmark["duration_days"] == 10 and benchmark["source_ids"][0] == "diagnostic-page", "benchmark terms drift")
    _require(benchmark["asset_boundary"] == "CUSTOMER_OWNED_OR_INDEPENDENTLY_CLEARED", "benchmark asset boundary drift")
    _require("customer-controlled GGUF" in benchmark["customer_supplies"], "benchmark customer asset boundary missing")

    _require(paper["family"] == "EXPERTISE" and paper["state"] == "SCOPING_AVAILABLE", "joint-paper state drift")
    _validate_price(paper["price"], False, None, "CUSTOM_UNKNOWN", "joint-paper reproduction")
    _require(paper["duration_days"] is None and paper["blocker"], "joint-paper scope must remain custom")
    _require(paper["asset_boundary"] == "CUSTOMER_OWNED_OR_INDEPENDENTLY_CLEARED", "joint-paper asset boundary drift")
    _require("independently licensed inputs" in paper["customer_supplies"], "joint-paper cleared-input boundary missing")

    _require(private["family"] == "SERVICES" and private["state"] == "AVAILABLE_CUSTOMER_OWNED_ASSET", "private evaluation state drift")
    _validate_price(private["price"], True, 30000, "FIXED", "private evaluation")
    _require(private["duration_days"] == 30 and private["source_ids"][0] == "commercial-page", "private evaluation terms drift")
    _require(private["asset_boundary"] == "CUSTOMER_OWNED_OR_INDEPENDENTLY_CLEARED", "private evaluation asset boundary drift")
    _require("customer-owned GGUF" in private["customer_supplies"], "private evaluation customer asset boundary missing")

    states = Counter(offer["state"] for offer in offers)
    return {
        "status": "VALID",
        "offers": len(offers),
        "available": states["AVAILABLE_CUSTOMER_OWNED_ASSET"],
        "scoping": states["SCOPING_AVAILABLE"],
        "blocked": states["BLOCKED_EVIDENCE_REQUIRED"],
        "entry_routes": len(routes),
        "archive_transfer_cleared": data["truth"]["archive_transfer_cleared"],
        "cash_received": data["truth"]["cash_received"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("validate", "summary"), default="validate")
    parser.add_argument("--root", default=str(ROOT), help="Commons repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        data, schema = load(root)
        result = validate(root, data, schema)
    except (CollaborationOfferError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"WHITE BOX COLLABORATION OFFERS INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
