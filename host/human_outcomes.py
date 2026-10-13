#!/usr/bin/env python3
"""host/human_outcomes.py — human-outcomes leftover.

Slack 1787648711.782309 (DEMON revenue/human-outcomes taking):
four named human jobs, not proof worship. Talk that restates the
taking is CLAIMED until this leftover measures fixed scope, price,
acceptance, refund, intake, founder-sent contact, $0 / NOT_LANDED
cash, and no remint of White Box / $12k diagnostic.

This leftover does not remint demon-human-outcomes-revenue-20260825-01.
It does not open a checkout. It does not store bank, routing, card,
tax, credential, address, or private buyer data. It does not write
titan. It does not smash commons.mno. It does not add a gate. It
does not overwrite commercial.json, revenue/dio/, payment_ready,
portfolio_overdrive, or SUBZERO packs.

  python3 host/human_outcomes.py
  python3 host/human_outcomes.py --root .
  python3 host/human_outcomes.py --self-test

X = exact files in SEARCH_SPACE
Y = kind / four offer ids / gate / collected_cash_usd found
Z = missing file / remint / claimed cash / checkout / FINDER-FAILED
Calibration = known-present EXECUTE.md + Action Pad directive
must be found in the same run or the measure is UNMEASURED.
A miss never prints 0. Never 0. FINDER-FAILED / FINDER-UNVERIFIED.
Open door. No auth. No gate. Talk is not a land.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


DEFAULT_ROOT = "."
DEFAULT_CARD = os.path.join("ground", "HUMAN_OUTCOMES.md")
DEFAULT_CATALOG = os.path.join("ground", "HUMAN_OUTCOMES.json")
DEFAULT_OFFERS = os.path.join("revenue", "human_outcomes", "offers.json")
DOOR = "humans.html"
COMMERCIAL_PATH = "commercial.json"
PAYMENT_PACK = os.path.join("revenue", "payment_ready", "pack.json")
PORTFOLIO_PATH = os.path.join("revenue", "portfolio_overdrive", "portfolio.json")
DIO_FOUNDATION = os.path.join("revenue", "dio", "foundation.json")
TAKING_PATH = os.path.join("p", "demon-human-outcomes-revenue-20260825-01.md")
SLACK_TS = "1787648711.782309"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    DEFAULT_OFFERS,
    os.path.join("host", "human_outcomes.py"),
    os.path.join("revenue", "human_outcomes", "README.md"),
    os.path.join("revenue", "human_outcomes", "fulfillment.md"),
    DOOR,
    COMMERCIAL_PATH,
    PAYMENT_PACK,
    PORTFOLIO_PATH,
    DIO_FOUNDATION,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_OFFER_IDS = (
    "ho-issue-to-pr",
    "ho-meeting-packet",
    "ho-security-questionnaire",
    "ho-pixel-pack",
)
REQUIRED_PRICES = {
    "ho-issue-to-pr": 2500,
    "ho-meeting-packet": 1200,
    "ho-security-questionnaire": 3000,
    "ho-pixel-pack": 800,
}
REQUIRED_GATE_OPEN = ("NEEDS_OWNER_PRIVATE", "NEEDS_BUYER", "NOT_LANDED")
REQUIRED_MODULES = ("SUBZERO", "compression", "DIO")
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
    """Parse the human-outcomes pack. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "offers is not JSON"}
    if not isinstance(data, dict):
        return {"error": "offers is not an object"}
    gate = data.get("gate") if isinstance(data.get("gate"), dict) else {}
    # Missing/null arrays retain their empty defaults. Other JSON containers
    # must not be iterated as keys/characters or escape as Python exceptions.
    for name in ("offers", "does_not_replace", "fulfillment_modules_remain"):
        value = data.get(name)
        if value is not None and not isinstance(value, list):
            return {"error": name + " is not an array"}
    if gate.get("open") is not None and not isinstance(gate.get("open"), list):
        return {"error": "gate.open is not an array"}
    offers = []
    for item in data.get("offers") or []:
        if isinstance(item, dict) and item.get("id"):
            offers.append(item)
    return {
        "error": "",
        "kind": str(data.get("kind") or "").strip(),
        "mandate": str(data.get("mandate") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "taking_state": str(data.get("taking_state") or "").strip().upper(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "xyz_required": bool(data.get("xyz_required")),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "collectable_usd": str(data.get("collectable_usd") or "").strip().upper(),
        "collected_cash_usd": data.get("collected_cash_usd"),
        "banking_only_blocker": bool(data.get("banking_only_blocker")),
        "computer_is_the_product": bool(data.get("computer_is_the_product")),
        "overwrites_commercial_json": bool(data.get("overwrites_commercial_json")),
        "overwrites_dio": bool(data.get("overwrites_dio")),
        "overwrites_payment_ready": bool(data.get("overwrites_payment_ready")),
        "overwrites_portfolio_overdrive": bool(data.get("overwrites_portfolio_overdrive")),
        "overwrites_subzero_buyers": bool(data.get("overwrites_subzero_buyers")),
        "overwrites_subzero_gtm": bool(data.get("overwrites_subzero_gtm")),
        "no_checkout": bool(data.get("no_checkout")),
        "no_auth": bool(data.get("no_auth")),
        "no_gate": bool(data.get("no_gate")),
        "no_buyer_fiction": bool(data.get("no_buyer_fiction")),
        "demand": str(data.get("demand") or "").strip().upper(),
        "payment_collection": str(data.get("payment_collection") or "").strip(),
        "founder_sent_contact": bool(data.get("founder_sent_contact")),
        "human_value_not_proof_worship": bool(data.get("human_value_not_proof_worship")),
        "does_not_replace": [
            str(item).strip() for item in (data.get("does_not_replace") or []) if item
        ],
        "fulfillment_modules_remain": [
            str(item).strip() for item in (data.get("fulfillment_modules_remain") or []) if item
        ],
        "white_box_offer_id": str(
            (data.get("white_box_upgrade") or {}).get("offer_id") or ""
        )
        if isinstance(data.get("white_box_upgrade"), dict)
        else "",
        "gate_pack": str(gate.get("pack") or "").strip().upper(),
        "gate_owner": str(gate.get("owner_private") or "").strip().upper(),
        "gate_buyer": str(gate.get("buyer") or "").strip().upper(),
        "gate_cash": str(gate.get("collected_cash") or "").strip().upper(),
        "gate_cash_usd": gate.get("collected_cash_usd"),
        "gate_open": [
            str(item).strip().upper() for item in (gate.get("open") or []) if item
        ],
        "ready_does_not_mean_cash": bool(gate.get("ready_does_not_mean_cash")),
        "offers": offers,
        "offer_ids": [str(item.get("id")) for item in offers],
        "offer_prices": {
            str(item.get("id")): item.get("fixed_amount") for item in offers
        },
    }


def measure_commercial(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "commercial is not JSON", "offer_id": "", "fixed_amount": 0}
    if not isinstance(data, dict):
        return {"error": "commercial is not an object", "offer_id": "", "fixed_amount": 0}
    offer = data.get("offer") if isinstance(data.get("offer"), dict) else {}
    fee = offer.get("fee") if isinstance(offer.get("fee"), dict) else {}
    return {
        "error": "",
        "offer_id": str(offer.get("offer_id") or ""),
        "fixed_amount": fee.get("fixed_amount"),
    }


def measure_payment_pack(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "payment pack is not JSON", "offer_id": "", "fixed_amount": 0}
    if not isinstance(data, dict):
        return {"error": "payment pack is not an object", "offer_id": "", "fixed_amount": 0}
    offer = data.get("offer") if isinstance(data.get("offer"), dict) else {}
    return {
        "error": "",
        "offer_id": str(offer.get("offer_id") or ""),
        "fixed_amount": offer.get("fixed_amount"),
    }


def forbidden_hits(text):
    hits = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, str(text or ""), flags=re.I):
            hits.append(pattern)
    return hits


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = dict(facts or {})
    facts["measured"] = True
    return facts


def classify(row):
    """Turn a measured human-outcomes census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Human-outcomes leftover was not read. Absence is not stillness. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("calibration_ok") is False:
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
                + ". Human-outcomes talk is CLAIMED until the leftover ships. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    open_gate = [str(item).strip().upper() for item in (row.get("gate_open") or [])]
    offer_ids = [str(item) for item in (row.get("offer_ids") or [])]
    prices = row.get("offer_prices") or {}
    modules = [str(item) for item in (row.get("fulfillment_modules_remain") or [])]
    if (
        str(row.get("kind") or "") != "HUMAN_OUTCOMES_PACK"
        or str(row.get("mandate") or "") != "demon-human-outcomes-revenue-20260825-01"
        or str(row.get("demand") or "") != "UNKNOWN"
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
        or row.get("overwrites_payment_ready")
        or row.get("overwrites_portfolio_overdrive")
        or row.get("overwrites_subzero_buyers")
        or row.get("overwrites_subzero_gtm")
        or not row.get("no_checkout")
        or not row.get("no_auth")
        or not row.get("no_gate")
        or not row.get("no_buyer_fiction")
        or not row.get("founder_sent_contact")
        or not row.get("human_value_not_proof_worship")
        or "white-box-gguf-pilot-30d" not in (row.get("does_not_replace") or [])
        or "gguf-diagnostic-10d-12k" not in (row.get("does_not_replace") or [])
        or any(name not in offer_ids for name in REQUIRED_OFFER_IDS)
        or any(prices.get(name) != REQUIRED_PRICES[name] for name in REQUIRED_OFFER_IDS)
        or any(name not in modules for name in REQUIRED_MODULES)
        or str(row.get("white_box_offer_id") or "") != "white-box-gguf-pilot-30d"
        or str(row.get("commercial_offer_id") or "") != "white-box-gguf-pilot-30d"
        or row.get("white_box_fee") != 30000
        or str(row.get("payment_offer_id") or "") != "gguf-diagnostic-10d-12k"
        or row.get("payment_fee") != 12000
        or not row.get("dio_present")
        or not row.get("door_present")
        or not row.get("fulfillment_present")
        or str(row.get("taking_state") or "") != "CARRIER_ONLY"
        or not row.get("xyz_required")
        or "Codex / Grok Build" not in str(row.get("remeasurement_owner") or "")
        or str(row.get("titan") or "") != "NOT_WRITTEN"
        or str(row.get("payment_collection") or "") != "NOT_PROVIDED_ON_THIS_PAGE"
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "pack present but incomplete, reminting, claimed cash, or invented "
                "a checkout. collected_cash_usd="
                + str(row.get("collected_cash_usd"))
                + ". Collected cash stays $0 / NOT_LANDED. Talk is CLAIMED. "
                "Z=FINDER-FAILED. Never 0."
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
            "Human-outcomes leftover is on this tree. Four named human jobs exist. "
            "White Box remains the high-ticket upgrade. Collected cash stays "
            "$0 / NOT_LANDED. A Slack taking is still not the file."
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
    pack = load_pack(search_hits.get(DEFAULT_OFFERS, ""))
    commercial = measure_commercial(search_hits.get(COMMERCIAL_PATH, ""))
    payment = measure_payment_pack(search_hits.get(PAYMENT_PACK, ""))
    taking_present = _exists(root, TAKING_PATH)
    taking_state = "DURABLE_ON_MAIN" if taking_present else "CARRIER_ONLY"
    card_text = search_hits.get(DEFAULT_CARD, "")
    fulfill = search_hits.get(os.path.join("revenue", "human_outcomes", "fulfillment.md"), "")
    door = search_hits.get(DOOR, "")
    blob = "\n".join(
        [
            card_text,
            search_hits.get(DEFAULT_OFFERS, ""),
            search_hits.get(os.path.join("host", "human_outcomes.py"), ""),
            search_hits.get(os.path.join("revenue", "human_outcomes", "README.md"), ""),
            fulfill,
            door,
        ]
    )
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "Human outcomes leftover" in card_text,
        "pack_present": bool(pack) and not pack.get("error"),
        "kind": pack.get("kind") or "",
        "mandate": pack.get("mandate") or "",
        "demand": pack.get("demand") or "",
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
        "overwrites_payment_ready": bool(pack.get("overwrites_payment_ready")),
        "overwrites_portfolio_overdrive": bool(pack.get("overwrites_portfolio_overdrive")),
        "overwrites_subzero_buyers": bool(pack.get("overwrites_subzero_buyers")),
        "overwrites_subzero_gtm": bool(pack.get("overwrites_subzero_gtm")),
        "no_checkout": bool(pack.get("no_checkout")) and "no checkout" in blob.lower(),
        "no_auth": bool(pack.get("no_auth")) and "no auth" in blob.lower(),
        "no_gate": bool(pack.get("no_gate")) and "no gate" in blob.lower(),
        "no_buyer_fiction": bool(pack.get("no_buyer_fiction")),
        "founder_sent_contact": bool(pack.get("founder_sent_contact"))
        and "founder-sent" in fulfill.lower(),
        "human_value_not_proof_worship": bool(pack.get("human_value_not_proof_worship")),
        "does_not_replace": pack.get("does_not_replace") or [],
        "fulfillment_modules_remain": pack.get("fulfillment_modules_remain") or [],
        "offer_ids": pack.get("offer_ids") or [],
        "offer_prices": pack.get("offer_prices") or {},
        "white_box_offer_id": pack.get("white_box_offer_id") or "",
        "commercial_offer_id": commercial.get("offer_id") or "",
        "white_box_fee": commercial.get("fixed_amount"),
        "payment_offer_id": payment.get("offer_id") or "",
        "payment_fee": payment.get("fixed_amount"),
        "dio_present": bool(search_hits.get(DIO_FOUNDATION)),
        "door_present": "ho-issue-to-pr" in door and "HUMAN OUTCOMES INTEREST" in door,
        "fulfillment_present": "Founder-sent contact" in fulfill and "Refund" in fulfill,
        "taking_state": taking_state,
        "xyz_required": bool(pack.get("xyz_required")),
        "remeasurement_owner": pack.get("remeasurement_owner") or "",
        "titan": pack.get("titan") or "NOT_WRITTEN",
        "payment_collection": pack.get("payment_collection") or "",
        "forbidden_hits": forbidden_hits(blob),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "slack_ts": pack.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "kind": facts["kind"],
                "offer_ids": facts["offer_ids"],
                "collected_cash_usd": facts["collected_cash_usd"],
                "taking_state": taking_state,
            },
            "z": (
                "misses " + json.dumps(misses) + " / FINDER-FAILED never 0"
                if misses
                else "FINDER-UNVERIFIED until classify"
            ),
        }
    )
    return row


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED", empty
    missing = classify(
        measure_from_rows(
            {
                "card_present": False,
                "pack_present": False,
                "misses": ["ground/HUMAN_OUTCOMES.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure human-outcomes leftover")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(args.root)
    verdict = classify(row)
    payload = {"verdict": verdict, "row": row}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
