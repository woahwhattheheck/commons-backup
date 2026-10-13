#!/usr/bin/env python3
"""host/portfolio_overdrive.py — rank ten revenue lanes; do not erase.

Slack 1787643743.338469 (DEMON revenue/README taking):
55_portfolio_overdrive as a many-path portfolio. Talk that restates
the mandate is CLAIMED until this leftover measures the catalog,
seven horizons, ten ranked un-erased lanes, collected-cash
NOT_LANDED, and no forbidden financial fields.

This leftover does not remint demon-redteam-revenue-readme-20260825-01.
It does not open accounts. It does not store bank, routing, card,
tax, credential, or private buyer data. It does not write titan.
It does not smash commons.mno. It does not add a gate.

  python3 host/portfolio_overdrive.py
  python3 host/portfolio_overdrive.py --root .
  python3 host/portfolio_overdrive.py --self-test

X = exact files in SEARCH_SPACE
Y = horizons / lane ids / ranks / collectable_usd found
Z = missing file / missing lane / forbidden field / FINDER-FAILED
Calibration = known-present EXECUTE.md + Action Pad directive
must be found in the same run or the measure is UNMEASURED.
A miss never prints 0.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("revenue", "portfolio_overdrive", "portfolio.json")
DEFAULT_CARD = os.path.join("ground", "PORTFOLIO_OVERDRIVE.md")
COMMERCIAL_PATH = "commercial.json"
BAZAAR_PATH = "bazaar.json"
DIO_FOUNDATION = os.path.join("revenue", "dio", "foundation.json")
TAKING_PATH = os.path.join("p", "demon-redteam-revenue-readme-20260825-01.md")
SLACK_TS = "1787643743.338469"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "portfolio_overdrive.py"),
    os.path.join("revenue", "portfolio_overdrive", "dissent.md"),
    os.path.join("revenue", "portfolio_overdrive", "source_ledger.md"),
    COMMERCIAL_PATH,
    BAZAAR_PATH,
    DIO_FOUNDATION,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_HORIZONS = ("now", "10d", "30d", "90d", "180d", "365d", "730d")
REQUIRED_LANES = (
    "high-ticket-white-box",
    "failure-packets",
    "paid-briefings-training",
    "tools-receipts",
    "licensing",
    "retainers",
    "expert-networks",
    "grants",
    "sponsorships-partners",
    "later-marketplace",
)
LANE_FIELDS = (
    "founder_slot_collision",
    "buyer",
    "channel",
    "acceptance",
    "falsifier",
    "owner_private_blockers",
    "cash_to_bank_timing",
    "collected_cash_gate",
    "horizons",
)
FORBIDDEN_PATTERNS = (
    r"\brouting[_\s-]?number\b.+\d{9}\b",
    r"\baccount[_\s-]?number\b.+\d{8,17}\b",
    r"\bIBAN\b\s*[A-Z]{2}\d{2}[A-Z0-9]{10,}",
    r"\b(?:4\d{15}|5[1-5]\d{14})\b",
    r"\bcvv\b\s*\d{3,4}\b",
    r"\bssn\b\s*\d{3}-\d{2}-\d{4}\b",
)


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def load_catalog(text):
    """Parse the portfolio catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    lanes = []
    for item in data.get("lanes") or []:
        if isinstance(item, dict) and item.get("id"):
            lanes.append(item)
    return {
        "error": "",
        "mandate": str(data.get("mandate") or "").strip(),
        "landing_owner": str(data.get("landing_owner") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "taking_id": str(data.get("taking_id") or "").strip(),
        "taking_state": str(data.get("taking_state") or "").strip().upper(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "xyz_required": bool(data.get("xyz_required")),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "collectable_usd": str(data.get("collectable_usd") or "").strip().upper(),
        "banking_only_blocker": bool(data.get("banking_only_blocker")),
        "rank_but_do_not_erase": bool(data.get("rank_but_do_not_erase")),
        "computer_is_the_product": bool(data.get("computer_is_the_product")),
        "horizons": [str(item).strip() for item in (data.get("horizons") or []) if str(item).strip()],
        "required_lanes": [
            str(item).strip() for item in (data.get("required_lanes") or []) if str(item).strip()
        ],
        "rank_order": [str(item).strip() for item in (data.get("rank_order") or []) if str(item).strip()],
        "lanes": lanes,
        "preserved": [
            str(item).strip()
            for item in (data.get("preserved_noncompeting_routes") or [])
            if str(item).strip()
        ],
    }


def lane_gaps(lanes):
    """Return missing ids, bad ranks, erased rows, and missing fields."""
    ids = []
    ranks = []
    erased = []
    field_miss = []
    horizon_miss = []
    for lane in lanes:
        lane_id = str(lane.get("id") or "").strip()
        ids.append(lane_id)
        try:
            ranks.append(int(lane.get("rank")))
        except (TypeError, ValueError):
            ranks.append(0)
        if lane.get("erased"):
            erased.append(lane_id)
        for field in LANE_FIELDS:
            if not lane.get(field):
                field_miss.append("%s.%s" % (lane_id, field))
        horizons = lane.get("horizons") if isinstance(lane.get("horizons"), dict) else {}
        for name in REQUIRED_HORIZONS:
            if not str(horizons.get(name) or "").strip():
                horizon_miss.append("%s.%s" % (lane_id, name))
    missing_ids = [item for item in REQUIRED_LANES if item not in ids]
    rank_ok = sorted(ranks) == list(range(1, len(REQUIRED_LANES) + 1))
    return {
        "ids": ids,
        "ranks": ranks,
        "missing_ids": missing_ids,
        "erased": erased,
        "field_miss": field_miss,
        "horizon_miss": horizon_miss,
        "rank_ok": rank_ok and not missing_ids,
    }


def measure_commercial(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "commercial is not JSON", "fixed_amount": 0}
    offer = data.get("offer") if isinstance(data.get("offer"), dict) else {}
    fee = offer.get("fee") if isinstance(offer.get("fee"), dict) else {}
    return {
        "error": "",
        "fixed_amount": fee.get("fixed_amount"),
        "offer_id": str(offer.get("offer_id") or ""),
    }


def measure_bazaar(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "bazaar is not JSON", "usd_offer_count": 0, "currency": ""}
    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    currency = str(payment.get("first_catalog_currency") or "").strip()
    offers = data.get("offers") if isinstance(data.get("offers"), list) else []
    usd = 0
    for item in offers:
        if not isinstance(item, dict):
            continue
        offer_currency = str(item.get("currency") or "").strip().upper()
        price = str(item.get("price") or "").strip()
        if offer_currency == "USD" and price not in ("", "0", "0.0", "0.00"):
            usd += 1
    return {"error": "", "offer_count": len(offers), "usd_offer_count": usd, "currency": currency}


def forbidden_hits(text):
    body = str(text or "")
    hits = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, body, flags=re.I):
            hits.append(pattern)
    return hits


def measure_from_rows(facts):
    facts = dict(facts or {})
    facts["measured"] = True
    return facts


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "portfolio leftover was not read. Absence is not stillness. Z=FINDER-FAILED. Never 0.",
            "z": "FINDER-FAILED",
        }
    if not row.get("calibration_ok"):
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration missed EXECUTE.md and/or the Action Pad "
                "directive. Instrument failure, not a portfolio result. Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    misses = [str(item) for item in (row.get("misses") or []) if item != TAKING_PATH]
    if not row.get("card_present") or not row.get("catalog_present") or misses:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Portfolio talk is CLAIMED until the leftover ships. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    gaps = row.get("lane_gaps") if isinstance(row.get("lane_gaps"), dict) else {}
    if (
        str(row.get("mandate") or "") != "55_portfolio_overdrive"
        or list(row.get("horizons") or []) != list(REQUIRED_HORIZONS)
        or gaps.get("missing_ids")
        or gaps.get("erased")
        or gaps.get("field_miss")
        or gaps.get("horizon_miss")
        or not gaps.get("rank_ok")
        or not row.get("rank_but_do_not_erase")
        or row.get("computer_is_the_product")
        or str(row.get("collectable_usd") or "") != "NOT_LANDED"
        or row.get("banking_only_blocker")
        or row.get("usd_offer_count") != 0
        or str(row.get("bazaar_currency") or "") != "FREE_COLONY_COMPUTE"
        or row.get("white_box_fee") != 30000
        or not row.get("dio_present")
        or str(row.get("taking_state") or "") != "CARRIER_ONLY"
        or not row.get("xyz_required")
        or "Codex / Grok Build" not in str(row.get("remeasurement_owner") or "")
        or str(row.get("titan") or "") != "NOT_WRITTEN"
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog present but incomplete. missing_ids="
                + ",".join(gaps.get("missing_ids") or [])
                + " erased="
                + ",".join(gaps.get("erased") or [])
                + ". Collectable USD stays NOT_LANDED. Talk is CLAIMED. Z=FINDER-FAILED."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("forbidden_hits"):
        return {
            "state": "NOT_LANDED",
            "note": "forbidden financial or private-buyer field pattern found. Z=FINDER-FAILED.",
            "z": "FINDER-FAILED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "portfolio leftover is on this tree. Ten lanes ranked, none erased. "
            "White Box stays the now-active HIGH founder-slot lane. "
            "Collectable USD stays NOT_LANDED. A Slack taking is still not the file."
        ),
        "z": "",
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    search_hits = {}
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        search_hits[rel] = text
    catalog = load_catalog(search_hits.get(DEFAULT_CATALOG, ""))
    commercial = measure_commercial(search_hits.get(COMMERCIAL_PATH, ""))
    bazaar = measure_bazaar(search_hits.get(BAZAAR_PATH, ""))
    taking_present = _exists(root, TAKING_PATH)
    taking_state = "DURABLE_ON_MAIN" if taking_present else "CARRIER_ONLY"
    card_text = search_hits.get(DEFAULT_CARD, "")
    blob = "\n".join(
        [
            card_text,
            search_hits.get(DEFAULT_CATALOG, ""),
            search_hits.get(os.path.join("host", "portfolio_overdrive.py"), ""),
        ]
    )
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    lanes = catalog.get("lanes") or []
    facts = {
        "card_present": bool(card_text) and "55_portfolio_overdrive" in card_text,
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "mandate": catalog.get("mandate") or "",
        "horizons": catalog.get("horizons") or [],
        "lane_gaps": lane_gaps(lanes),
        "rank_but_do_not_erase": bool(catalog.get("rank_but_do_not_erase")),
        "computer_is_the_product": bool(catalog.get("computer_is_the_product")),
        "collectable_usd": catalog.get("collectable_usd") or "",
        "banking_only_blocker": bool(catalog.get("banking_only_blocker")),
        "usd_offer_count": bazaar.get("usd_offer_count"),
        "bazaar_currency": bazaar.get("currency") or "",
        "white_box_fee": commercial.get("fixed_amount"),
        "dio_present": bool(search_hits.get(DIO_FOUNDATION, "")),
        "taking_state": taking_state,
        "taking_present": taking_present,
        "remeasurement_owner": catalog.get("remeasurement_owner") or "",
        "xyz_required": bool(catalog.get("xyz_required")),
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "forbidden_hits": forbidden_hits(blob),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "landing_owner": catalog.get("landing_owner") or "",
    }
    row = measure_from_rows(facts)
    row["catalog"] = DEFAULT_CATALOG
    return row


def _self_test():
    empty = classify({})
    if empty.get("state") != "UNMEASURED" or empty.get("z") != "FINDER-FAILED":
        return False
    missing = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "card_present": False,
                "catalog_present": False,
                "misses": [DEFAULT_CARD],
            }
        )
    )
    return missing.get("state") == "NOT_LANDED" and missing.get("z") == "FINDER-FAILED"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the 55_portfolio_overdrive leftover"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    payload["x"] = list(SEARCH_SPACE) + [TAKING_PATH]
    payload["y"] = {
        "mandate": row.get("mandate"),
        "horizons": row.get("horizons") or [],
        "lane_ids": (row.get("lane_gaps") or {}).get("ids") or [],
        "usd_offer_count": row.get("usd_offer_count"),
        "collectable_usd": row.get("collectable_usd"),
    }
    payload["z"] = verdict.get("z") or "none"
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
