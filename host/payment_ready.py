#!/usr/bin/env python3
"""host/payment_ready.py — secrets-absent first-cash pack.

Slack 1787645021.043069 (DEMON payment-ready taking):
reduce the first-cash lane to the smallest legitimate owner-private
handoff. Talk that restates the taking is CLAIMED until this leftover
measures the $12k / 10d offer, AT1-AT6, rails citations, private-input
manifest, $0 / NOT_LANDED cash gate, and no forbidden financial fields.

This leftover does not remint demon-redteam-payment-ready-20260825-02.
It does not open accounts. It does not store bank, routing, card, tax,
credential, address, or private buyer data. It does not write titan.
It does not smash commons.mno. It does not add a gate. It does not
overwrite commercial.json or revenue/dio/.

  python3 host/payment_ready.py
  python3 host/payment_ready.py --root .
  python3 host/payment_ready.py --self-test

X = exact files in SEARCH_SPACE
Y = offer / AT1-AT6 / gate states / collected_cash_usd found
Z = missing file / wrong offer / claimed cash / forbidden field / FINDER-FAILED
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
DEFAULT_PACK = os.path.join("revenue", "payment_ready", "pack.json")
DEFAULT_CARD = os.path.join("ground", "PAYMENT_READY.md")
COMMERCIAL_PATH = "commercial.json"
BAZAAR_PATH = "bazaar.json"
PORTFOLIO_PATH = os.path.join("revenue", "portfolio_overdrive", "portfolio.json")
CASH_NOW_PATH = os.path.join("ground", "CASH_NOW.json")
DIO_FOUNDATION = os.path.join("revenue", "dio", "foundation.json")
TAKING_PATH = os.path.join("p", "demon-redteam-payment-ready-20260825-02.md")
SLACK_TS = "1787645021.043069"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_PACK,
    os.path.join("host", "payment_ready.py"),
    os.path.join("revenue", "payment_ready", "README.md"),
    os.path.join("revenue", "payment_ready", "buyer_pack.md"),
    os.path.join("revenue", "payment_ready", "rails.md"),
    os.path.join("revenue", "payment_ready", "private_input_manifest.md"),
    os.path.join("revenue", "payment_ready", "dissent.md"),
    os.path.join("revenue", "payment_ready", "source_ledger.md"),
    COMMERCIAL_PATH,
    BAZAAR_PATH,
    PORTFOLIO_PATH,
    CASH_NOW_PATH,
    DIO_FOUNDATION,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_AT = ("AT1", "AT2", "AT3", "AT4", "AT5", "AT6")
REQUIRED_GATE_OPEN = ("NEEDS_OWNER_PRIVATE", "NEEDS_BUYER", "NOT_LANDED")
REQUIRED_RAIL_EVENTS = ("AUTHORIZATION", "SETTLEMENT", "PAYOUT", "BANK_AVAILABLE")
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


def load_pack(text):
    """Parse the payment-ready pack. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "pack is not JSON"}
    if not isinstance(data, dict):
        return {"error": "pack is not an object"}
    offer = data.get("offer") if isinstance(data.get("offer"), dict) else {}
    gate = data.get("gate") if isinstance(data.get("gate"), dict) else {}
    tests = []
    for item in data.get("acceptance_tests") or []:
        if isinstance(item, dict) and item.get("id"):
            tests.append(item)
    rails = []
    for item in data.get("rails") or []:
        if isinstance(item, dict) and item.get("provider"):
            rails.append(item)
    return {
        "error": "",
        "kind": str(data.get("kind") or "").strip(),
        "mandate": str(data.get("mandate") or "").strip(),
        "landing_owner": str(data.get("landing_owner") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "taking_id": str(data.get("slack_taking_id") or "").strip(),
        "taking_state": str(data.get("taking_state") or "").strip().upper(),
        "xyz_required": bool(data.get("xyz_required")),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "collectable_usd": str(data.get("collectable_usd") or "").strip().upper(),
        "collected_cash_usd": data.get("collected_cash_usd"),
        "banking_only_blocker": bool(data.get("banking_only_blocker")),
        "computer_is_the_product": bool(data.get("computer_is_the_product")),
        "overwrites_commercial_json": bool(data.get("overwrites_commercial_json")),
        "overwrites_dio": bool(data.get("overwrites_dio")),
        "offer_id": str(offer.get("offer_id") or "").strip(),
        "offer_status": str(offer.get("status") or "").strip().upper(),
        "fixed_amount": offer.get("fixed_amount"),
        "term_calendar_days": offer.get("term_calendar_days"),
        "payment_collection": str(offer.get("payment_collection") or "").strip(),
        "does_not_replace": str(offer.get("does_not_replace") or "").strip(),
        "demand": str(offer.get("demand") or "").strip().upper(),
        "acceptance_rule": str(offer.get("acceptance_rule") or "").strip().lower(),
        "milestones": offer.get("milestones") if isinstance(offer.get("milestones"), list) else [],
        "falsifier": offer.get("falsifier") if isinstance(offer.get("falsifier"), list) else [],
        "downgrade_path": (
            offer.get("downgrade_path") if isinstance(offer.get("downgrade_path"), list) else []
        ),
        "acceptance_tests": tests,
        "rails": rails,
        "gate_pack": str(gate.get("pack") or "").strip().upper(),
        "gate_owner": str(gate.get("owner_private") or "").strip().upper(),
        "gate_buyer": str(gate.get("buyer") or "").strip().upper(),
        "gate_cash": str(gate.get("collected_cash") or "").strip().upper(),
        "gate_cash_usd": gate.get("collected_cash_usd"),
        "gate_open": [str(item).strip().upper() for item in (gate.get("open") or [])],
        "ready_does_not_mean_cash": bool(gate.get("ready_does_not_mean_cash")),
        "d0_status": str((data.get("d0_plumbing") or {}).get("status") or "").strip().upper()
        if isinstance(data.get("d0_plumbing"), dict)
        else "",
    }


def at_gaps(tests):
    """Return missing AT ids and empty pass text."""
    ids = [str(item.get("id") or "").strip() for item in tests]
    missing = [item for item in REQUIRED_AT if item not in ids]
    empty_pass = [
        str(item.get("id") or "")
        for item in tests
        if not str(item.get("pass") or "").strip()
    ]
    return {"ids": ids, "missing": missing, "empty_pass": empty_pass}


def milestone_amounts(milestones):
    amounts = []
    for item in milestones:
        if isinstance(item, dict):
            try:
                amounts.append(int(item.get("amount")))
            except (TypeError, ValueError):
                amounts.append(0)
    return amounts


def measure_commercial(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "commercial is not JSON", "fixed_amount": 0, "offer_id": ""}
    offer = data.get("offer") if isinstance(data.get("offer"), dict) else {}
    fee = offer.get("fee") if isinstance(offer.get("fee"), dict) else {}
    return {
        "error": "",
        "fixed_amount": fee.get("fixed_amount"),
        "offer_id": str(offer.get("offer_id") or ""),
        "payment_collection": str(fee.get("payment_collection") or ""),
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


def measure_portfolio(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "portfolio is not JSON"}
    return {
        "error": "",
        "collectable_usd": str(data.get("collectable_usd") or "").strip().upper(),
        "banking_only_blocker": bool(data.get("banking_only_blocker")),
    }


def forbidden_hits(text):
    body = str(text or "")
    hits = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, body, flags=re.I):
            hits.append(pattern)
    return hits


def rail_events_present(card_text, rails_text):
    blob = "%s\n%s" % (card_text, rails_text)
    found = []
    for name in REQUIRED_RAIL_EVENTS:
        if name.lower() in blob.lower():
            found.append(name)
    return found


def measure_from_rows(facts):
    facts = dict(facts or {})
    facts["measured"] = True
    return facts


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "payment-ready leftover was not read. Absence is not stillness. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if not row.get("calibration_ok"):
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration missed EXECUTE.md and/or the Action Pad "
                "directive. Instrument failure, not a cash result. Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    misses = [str(item) for item in (row.get("misses") or []) if item != TAKING_PATH]
    if not row.get("card_present") or not row.get("pack_present") or misses:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/pack"])
                + ". Payment-ready talk is CLAIMED until the leftover ships. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    gaps = row.get("at_gaps") if isinstance(row.get("at_gaps"), dict) else {}
    open_gate = [str(item).strip().upper() for item in (row.get("gate_open") or [])]
    rail_events = [str(item) for item in (row.get("rail_events") or [])]
    if (
        str(row.get("kind") or "") != "PAYMENT_READY_PACK"
        or str(row.get("mandate") or "") != "demon-redteam-payment-ready-20260825-02"
        or row.get("fixed_amount") != 12000
        or row.get("term_calendar_days") != 10
        or list(row.get("milestone_amounts") or []) != [6000, 6000]
        or str(row.get("payment_collection") or "") != "NOT_PROVIDED_ON_THIS_PAGE"
        or str(row.get("does_not_replace") or "") != "white-box-gguf-pilot-30d"
        or str(row.get("demand") or "") != "UNKNOWN"
        or "rollback" not in str(row.get("acceptance_rule") or "")
        or not row.get("falsifier")
        or not row.get("downgrade_path")
        or gaps.get("missing")
        or gaps.get("empty_pass")
        or str(row.get("gate_pack") or "") != "READY"
        or str(row.get("gate_owner") or "") != "NEEDS_OWNER_PRIVATE"
        or str(row.get("gate_buyer") or "") != "NEEDS_BUYER"
        or str(row.get("gate_cash") or "") != "NOT_LANDED"
        or row.get("gate_cash_usd") != 0
        or row.get("collected_cash_usd") != 0
        or str(row.get("collectable_usd") or "") != "NOT_LANDED"
        or any(name not in open_gate for name in REQUIRED_GATE_OPEN)
        or "READY" in open_gate
        or not row.get("ready_does_not_mean_cash")
        or row.get("banking_only_blocker")
        or row.get("computer_is_the_product")
        or row.get("overwrites_commercial_json")
        or row.get("overwrites_dio")
        or row.get("usd_offer_count") != 0
        or str(row.get("bazaar_currency") or "") != "FREE_COLONY_COMPUTE"
        or row.get("white_box_fee") != 30000
        or str(row.get("commercial_offer_id") or "") != "white-box-gguf-pilot-30d"
        or not row.get("dio_present")
        or str(row.get("portfolio_collectable") or "") != "NOT_LANDED"
        or row.get("portfolio_banking_only")
        or str(row.get("taking_state") or "") != "CARRIER_ONLY"
        or not row.get("xyz_required")
        or "Codex / Grok Build" not in str(row.get("remeasurement_owner") or "")
        or len(row.get("rails") or []) < 2
        or any(name not in rail_events for name in REQUIRED_RAIL_EVENTS)
        or not row.get("private_manifest_present")
        or not row.get("dissent_present")
        or str(row.get("d0_status") or "") != "OPEN"
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "pack present but incomplete or it claimed cash. missing_at="
                + ",".join(gaps.get("missing") or [])
                + " collected_cash_usd="
                + str(row.get("collected_cash_usd"))
                + ". Collected cash stays $0 / NOT_LANDED. Talk is CLAIMED. Z=FINDER-FAILED."
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
            "payment-ready leftover is on this tree. $12k / 10d diagnostic is a "
            "CANDIDATE SKU. commercial.json $30k offer is preserved. Collected cash "
            "stays $0 / NOT_LANDED. Banking is not the only blocker. A Slack taking "
            "is still not the file."
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
    pack = load_pack(search_hits.get(DEFAULT_PACK, ""))
    commercial = measure_commercial(search_hits.get(COMMERCIAL_PATH, ""))
    bazaar = measure_bazaar(search_hits.get(BAZAAR_PATH, ""))
    portfolio = measure_portfolio(search_hits.get(PORTFOLIO_PATH, ""))
    taking_present = _exists(root, TAKING_PATH)
    taking_state = "DURABLE_ON_MAIN" if taking_present else "CARRIER_ONLY"
    card_text = search_hits.get(DEFAULT_CARD, "")
    buyer = search_hits.get(os.path.join("revenue", "payment_ready", "buyer_pack.md"), "")
    rails_md = search_hits.get(os.path.join("revenue", "payment_ready", "rails.md"), "")
    manifest = search_hits.get(
        os.path.join("revenue", "payment_ready", "private_input_manifest.md"), ""
    )
    dissent = search_hits.get(os.path.join("revenue", "payment_ready", "dissent.md"), "")
    blob = "\n".join(
        [
            card_text,
            search_hits.get(DEFAULT_PACK, ""),
            search_hits.get(os.path.join("host", "payment_ready.py"), ""),
            buyer,
            rails_md,
            manifest,
            dissent,
        ]
    )
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    tests = pack.get("acceptance_tests") or []
    facts = {
        "card_present": bool(card_text) and "PAYMENT READY" in card_text,
        "pack_present": bool(pack) and not pack.get("error"),
        "kind": pack.get("kind") or "",
        "mandate": pack.get("mandate") or "",
        "fixed_amount": pack.get("fixed_amount"),
        "term_calendar_days": pack.get("term_calendar_days"),
        "milestone_amounts": milestone_amounts(pack.get("milestones") or []),
        "payment_collection": pack.get("payment_collection") or "",
        "does_not_replace": pack.get("does_not_replace") or "",
        "demand": pack.get("demand") or "",
        "acceptance_rule": pack.get("acceptance_rule") or "",
        "falsifier": pack.get("falsifier") or [],
        "downgrade_path": pack.get("downgrade_path") or [],
        "at_gaps": at_gaps(tests),
        "gate_pack": pack.get("gate_pack") or "",
        "gate_owner": pack.get("gate_owner") or "",
        "gate_buyer": pack.get("gate_buyer") or "",
        "gate_cash": pack.get("gate_cash") or "",
        "gate_cash_usd": pack.get("gate_cash_usd"),
        "gate_open": pack.get("gate_open") or [],
        "ready_does_not_mean_cash": bool(pack.get("ready_does_not_mean_cash")),
        "collectable_usd": pack.get("collectable_usd") or "",
        "collected_cash_usd": pack.get("collected_cash_usd"),
        "banking_only_blocker": bool(pack.get("banking_only_blocker")),
        "computer_is_the_product": bool(pack.get("computer_is_the_product")),
        "overwrites_commercial_json": bool(pack.get("overwrites_commercial_json")),
        "overwrites_dio": bool(pack.get("overwrites_dio")),
        "usd_offer_count": bazaar.get("usd_offer_count"),
        "bazaar_currency": bazaar.get("currency") or "",
        "white_box_fee": commercial.get("fixed_amount"),
        "commercial_offer_id": commercial.get("offer_id") or "",
        "dio_present": bool(search_hits.get(DIO_FOUNDATION, "")),
        "portfolio_collectable": portfolio.get("collectable_usd") or "",
        "portfolio_banking_only": bool(portfolio.get("banking_only_blocker")),
        "taking_state": taking_state,
        "taking_present": taking_present,
        "remeasurement_owner": pack.get("remeasurement_owner") or "",
        "xyz_required": bool(pack.get("xyz_required")),
        "rails": pack.get("rails") or [],
        "rail_events": rail_events_present(card_text, rails_md),
        "private_manifest_present": "Official surface only" in manifest,
        "dissent_present": "banking is not the last blocker" in dissent.lower(),
        "d0_status": pack.get("d0_status") or "",
        "forbidden_hits": forbidden_hits(blob),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "slack_ts": pack.get("slack_ts") or SLACK_TS,
        "landing_owner": pack.get("landing_owner") or "",
    }
    row = measure_from_rows(facts)
    row["pack"] = DEFAULT_PACK
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
                "pack_present": False,
                "misses": [DEFAULT_CARD],
            }
        )
    )
    return missing.get("state") == "NOT_LANDED" and missing.get("z") == "FINDER-FAILED"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure the payment-ready leftover")
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
        "kind": row.get("kind"),
        "fixed_amount": row.get("fixed_amount"),
        "term_calendar_days": row.get("term_calendar_days"),
        "at_ids": (row.get("at_gaps") or {}).get("ids") or [],
        "gate_open": row.get("gate_open") or [],
        "collected_cash_usd": row.get("collected_cash_usd"),
        "collectable_usd": row.get("collectable_usd"),
    }
    payload["z"] = verdict.get("z") or "none"
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
