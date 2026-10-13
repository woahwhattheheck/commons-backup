#!/usr/bin/env python3
"""host/subzero_buyers.py — SUBZERO buyer packet is a land, not Slack.

Dispatch demon-redteam-subzero-buyers-20260825-05. Talk in
#commons is CLAIMED until this leftover names the unique packet
files and remeasures the pinned excerpt hashes.

Does not overwrite commercial.json, DIO, portfolio, Bazaar, or
Cash Now. Does not walk an organ. Does not write titan. Does not
message buyers. No auth. No gate. Miss is FINDER-FAILED. Never 0.

  python3 host/subzero_buyers.py
  python3 host/subzero_buyers.py --root .
  python3 host/subzero_buyers.py --check
  python3 host/subzero_buyers.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys


DEFAULT_ROOT = "."
PACK = os.path.join("revenue", "subzero_buyers", "pack.json")
CARD = os.path.join("ground", "SUBZERO_BUYERS.md")
RECEIPT = os.path.join("p", "grok-subzero-buyers-panel-20260825-01.md")
COMMERCIAL = "commercial.json"
SEARCH_SPACE = (
    PACK,
    CARD,
    RECEIPT,
    os.path.join("host", "subzero_buyers.py"),
    COMMERCIAL,
    os.path.join("revenue", "dio", "foundation.json"),
    os.path.join("excerpts", "20260823", "muhl_grbn.mno"),
)
REQUIRED_PACK_KEYS = (
    "schema_version",
    "kind",
    "dispatch_id",
    "receipt_id",
    "base_main_sha_at_write",
    "does_not_replace",
    "remeasured_excerpts_on_base",
    "rank_order",
    "paths",
    "official_sources",
)
REQUIRED_PATH_KEYS = (
    "id",
    "rank",
    "sell_class",
    "buyer_class",
    "painful_job",
    "offer",
    "price_usd_from",
    "price_usd_to",
    "delivery_days",
    "acceptance",
    "falsifier",
    "horizon",
    "sell_class",
)
REQUIRED_CARD_PHRASES = (
    "three evidence classes",
    "do not compete",
    "can sell immediately",
    "proof-first",
    "defense readiness is not claimed",
    "not overwrite",
)
FORBIDDEN_COMMERCIAL_TOUCH = (
    "white-box-gguf-pilot-30d",
)


def _read(root: str, rel: str) -> bytes:
    path = os.path.join(root, rel)
    with open(path, "rb") as handle:
        return handle.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fail(message: str) -> int:
    print("FINDER-FAILED: " + message, file=sys.stderr)
    return 2


def load_pack(root: str) -> dict:
    raw = _read(root, PACK)
    pack = json.loads(raw.decode("utf-8"))
    if not isinstance(pack, dict):
        raise ValueError("pack is not an object")
    return pack


def check_pack_shape(pack: dict) -> list[str]:
    misses: list[str] = []
    for key in REQUIRED_PACK_KEYS:
        if key not in pack:
            misses.append("missing pack key " + key)
    if pack.get("kind") != "SUBZERO_BUYERS_PACKET":
        misses.append("kind is not SUBZERO_BUYERS_PACKET")
    if pack.get("dispatch_id") != "demon-redteam-subzero-buyers-20260825-05":
        misses.append("dispatch_id mismatch")
    if pack.get("overwrites_commercial_json") is not False:
        misses.append("pack must not overwrite commercial.json")
    if pack.get("defense_readiness_claimed") is not False:
        misses.append("pack must not claim defense readiness")
    if pack.get("computer_is_the_product") is not False:
        misses.append("computer must not be the product")
    does_not_replace = pack.get("does_not_replace") or []
    for offer_id in FORBIDDEN_COMMERCIAL_TOUCH:
        if offer_id not in does_not_replace:
            misses.append("does_not_replace missing " + offer_id)
    paths = pack.get("paths") or []
    if len(paths) < 12:
        misses.append("need at least 12 paths, have %d" % len(paths))
    ranks = [row.get("rank") for row in paths if isinstance(row, dict)]
    if ranks != list(range(1, len(paths) + 1)):
        misses.append("path ranks must be 1..n in order")
    for row in paths:
        if not isinstance(row, dict):
            misses.append("path row is not an object")
            continue
        for key in REQUIRED_PATH_KEYS:
            if key not in row:
                misses.append("%s missing %s" % (row.get("id"), key))
        sell = row.get("sell_class")
        if sell not in ("can_sell_immediately", "proof_first"):
            misses.append("%s bad sell_class" % row.get("id"))
    order = pack.get("rank_order") or []
    ids = [row.get("id") for row in paths if isinstance(row, dict)]
    if order != ids:
        misses.append("rank_order does not match path ids")
    return misses


def check_excerpts(root: str, pack: dict) -> list[str]:
    misses: list[str] = []
    rows = pack.get("remeasured_excerpts_on_base") or []
    if len(rows) < 6:
        misses.append("need at least 6 remeasured excerpts")
    for row in rows:
        rel = row["path"]
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            misses.append("missing " + rel)
            continue
        data = _read(root, rel)
        digest = _sha256(data)
        if len(data) != int(row["bytes"]):
            misses.append("%s bytes %d != %s" % (rel, len(data), row["bytes"]))
        if digest != row["sha256"]:
            misses.append("%s sha mismatch" % rel)
    return misses


def check_card(root: str) -> list[str]:
    text = _read(root, CARD).decode("utf-8").lower()
    misses: list[str] = []
    for phrase in REQUIRED_CARD_PHRASES:
        if phrase not in text:
            misses.append("card missing phrase: " + phrase)
    return misses


def check_occupied_untouched(root: str, pack: dict) -> list[str]:
    misses: list[str] = []
    commercial = json.loads(_read(root, COMMERCIAL).decode("utf-8"))
    offer = commercial.get("offer") or {}
    if offer.get("offer_id") != "white-box-gguf-pilot-30d":
        misses.append("commercial.json offer_id drifted; do not win that tree")
    if int(offer.get("fee", {}).get("fixed_amount") or 0) != 30000:
        misses.append("commercial.json fee drifted; do not win that tree")
    if pack.get("overwrites_commercial_json"):
        misses.append("pack claims commercial overwrite")
    return misses


def run_check(root: str) -> int:
    try:
        pack = load_pack(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _fail("pack unreadable: " + str(exc))
    misses = []
    misses.extend(check_pack_shape(pack))
    misses.extend(check_excerpts(root, pack))
    misses.extend(check_card(root))
    misses.extend(check_occupied_untouched(root, pack))
    if not os.path.isfile(os.path.join(root, RECEIPT)):
        misses.append("board receipt missing " + RECEIPT)
    if misses:
        for row in misses:
            print("FINDER-FAILED: " + row, file=sys.stderr)
        print("search_space=" + " ".join(SEARCH_SPACE))
        return 2
    immediate = [
        row["id"]
        for row in pack["paths"]
        if row.get("sell_class") == "can_sell_immediately"
    ]
    proof = [
        row["id"]
        for row in pack["paths"]
        if row.get("sell_class") == "proof_first"
    ]
    print("SUBZERO_BUYERS_OK")
    print("dispatch=" + str(pack["dispatch_id"]))
    print("paths=%d" % len(pack["paths"]))
    print("can_sell_immediately=" + ",".join(immediate))
    print("proof_first=" + ",".join(proof))
    print("demand=" + str(pack.get("demand")))
    print("collected_cash_usd=" + str(pack.get("collected_cash_usd")))
    print("titan=" + str(pack.get("titan")))
    print("defense_readiness_claimed=" + str(pack.get("defense_readiness_claimed")))
    print("white_box_left_alone=white-box-gguf-pilot-30d")
    return 0


def self_test(root: str) -> int:
    code = run_check(root)
    if code != 0:
        return code
    pack = load_pack(root)
    if len(pack["paths"]) < 12:
        return _fail("self-test path count")
    sell_classes = {row["sell_class"] for row in pack["paths"]}
    if sell_classes != {"can_sell_immediately", "proof_first"}:
        return _fail("self-test missing a sell_class")
    print("SELF_TEST_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.root)
    return run_check(args.root)


if __name__ == "__main__":
    sys.exit(main())
