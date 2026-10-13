#!/usr/bin/env python3
"""host/subzero_gtm.py — SUBZERO panel 3/3 pricing/GTM leftover.

Slack 1787645951.270489 (DEMON SUBZERO GTM taking):
honest revenue architecture across horizons. Talk that restates the
taking is CLAIMED until this leftover measures additive SKUs, the
artifact/runtime/demand split, $0 / NOT_LANDED cash, and no remint of
White Box / $12k diagnostic.

This leftover does not remint demon-redteam-subzero-gtm-20260825-06.
It does not open accounts. It does not store bank, routing, card, tax,
credential, address, or private buyer data. It does not write titan.
It does not smash commons.mno. It does not add a gate. It does not
overwrite commercial.json, revenue/dio/, payment_ready, or
portfolio_overdrive.

  python3 host/subzero_gtm.py
  python3 host/subzero_gtm.py --root .
  python3 host/subzero_gtm.py --self-test

X = exact files in SEARCH_SPACE
Y = kind / first SKU / gate / collected_cash_usd found
Z = missing file / remint / claimed cash / intelligence claim / FINDER-FAILED
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
DEFAULT_ARCH = os.path.join("revenue", "subzero_gtm", "architecture.json")
DEFAULT_CARD = os.path.join("ground", "SUBZERO_GTM.md")
COMMERCIAL_PATH = "commercial.json"
PAYMENT_PACK = os.path.join("revenue", "payment_ready", "pack.json")
PORTFOLIO_PATH = os.path.join("revenue", "portfolio_overdrive", "portfolio.json")
DIO_FOUNDATION = os.path.join("revenue", "dio", "foundation.json")
CASH_NOW_PATH = os.path.join("ground", "CASH_NOW.json")
EXCERPTS = os.path.join("ground", "SUBZERO_EXCERPTS.md")
BUYERS_PACK = os.path.join("revenue", "subzero_buyers", "pack.json")
TAKING_PATH = os.path.join("p", "demon-redteam-subzero-gtm-20260825-06.md")
SLACK_TS = "1787645951.270489"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_ARCH,
    os.path.join("host", "subzero_gtm.py"),
    os.path.join("revenue", "subzero_gtm", "README.md"),
    os.path.join("revenue", "subzero_gtm", "dissent.md"),
    os.path.join("revenue", "subzero_gtm", "source_ledger.md"),
    COMMERCIAL_PATH,
    PAYMENT_PACK,
    PORTFOLIO_PATH,
    DIO_FOUNDATION,
    CASH_NOW_PATH,
    EXCERPTS,
    BUYERS_PACK,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_GATE_OPEN = ("NEEDS_OWNER_PRIVATE", "NEEDS_BUYER", "NOT_LANDED")
REQUIRED_PATH_IDS = (
    "sz-paid-validation",
    "sz-failure-packet",
    "sz-fabricator-audit",
    "sz-handoff-whitebox",
    "sz-public-catalog",
)
FORBIDDEN_PATTERNS = (
    r"\brouting[_\s-]?number\b.+\d{9}\b",
    r"\baccount[_\s-]?number\b.+\d{8,17}\b",
    r"\bIBAN\b\s*[A-Z]{2}\d{2}[A-Z0-9]{10,}",
    r"\b(?:4\d{15}|5[1-5]\d{14})\b",
    r"\bcvv\b\s*\d{3,4}\b",
    r"\bssn\b\s*\d{3}-\d{2}-\d{4}\b",
)
REQUIRED_HORIZONS = ("now", "10d", "30d", "90d", "180d", "365d", "730d")


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def load_arch(text):
    """Parse the SUBZERO GTM architecture. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "architecture is not JSON"}
    if not isinstance(data, dict):
        return {"error": "architecture is not an object"}
    gate = data.get("gate") if isinstance(data.get("gate"), dict) else {}
    product = data.get("product_definition") if isinstance(data.get("product_definition"), dict) else {}
    evidence = data.get("evidence_classes") if isinstance(data.get("evidence_classes"), dict) else {}
    founder = data.get("founder_slot") if isinstance(data.get("founder_slot"), dict) else {}
    paths = []
    for item in data.get("paths") or []:
        if isinstance(item, dict) and item.get("id"):
            paths.append(item)
    horizons = data.get("horizons") if isinstance(data.get("horizons"), dict) else {}
    return {
        "error": "",
        "kind": str(data.get("kind") or "").strip(),
        "mandate": str(data.get("mandate") or "").strip(),
        "panel": str(data.get("panel") or "").strip(),
        "landing_owner": str(data.get("landing_owner") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "taking_id": str(data.get("slack_taking_id") or "").strip(),
        "taking_state": str(data.get("taking_state") or "").strip().upper(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "xyz_required": bool(data.get("xyz_required")),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "collectable_usd": str(data.get("collectable_usd") or "").strip().upper(),
        "collected_cash_usd": data.get("collected_cash_usd"),
        "banking_only_blocker": bool(data.get("banking_only_blocker")),
        "computer_is_the_product": bool(data.get("computer_is_the_product")),
        "runtime_intelligence_claimed": bool(data.get("runtime_intelligence_claimed")),
        "demand": str(data.get("demand") or "").strip().upper(),
        "overwrites_commercial_json": bool(data.get("overwrites_commercial_json")),
        "overwrites_dio": bool(data.get("overwrites_dio")),
        "overwrites_payment_ready": bool(data.get("overwrites_payment_ready")),
        "overwrites_portfolio_overdrive": bool(data.get("overwrites_portfolio_overdrive")),
        "overwrites_subzero_buyers": bool(data.get("overwrites_subzero_buyers")),
        "implements_p01": str(
            (data.get("implements_buyers_paths") or {}).get("sz-paid-validation") or ""
        )
        if isinstance(data.get("implements_buyers_paths"), dict)
        else "",
        "does_not_replace": [
            str(item).strip() for item in (data.get("does_not_replace") or []) if item
        ],
        "gate_pack": str(gate.get("pack") or "").strip().upper(),
        "gate_owner": str(gate.get("owner_private") or "").strip().upper(),
        "gate_buyer": str(gate.get("buyer") or "").strip().upper(),
        "gate_cash": str(gate.get("collected_cash") or "").strip().upper(),
        "gate_cash_usd": gate.get("collected_cash_usd"),
        "gate_open": [str(item).strip().upper() for item in (gate.get("open") or [])],
        "ready_does_not_mean_cash": bool(gate.get("ready_does_not_mean_cash")),
        "path_ids": [str(item.get("id") or "").strip() for item in paths],
        "paths": paths,
        "rank_order": [
            str(item).strip() for item in (data.get("rank_order") or []) if item
        ],
        "horizon_keys": [str(key) for key in horizons.keys()],
        "founder_now_active": str(founder.get("now_active_occupied_by") or "").strip(),
        "subzero_now_active": str(founder.get("subzero_now_active") or "").strip(),
        "runtime_status": str(
            (evidence.get("RUNTIME_BEHAVIOR") or {}).get("status") or ""
        ).strip().upper()
        if isinstance(evidence.get("RUNTIME_BEHAVIOR"), dict)
        else "",
        "demand_status": str(
            (evidence.get("CUSTOMER_DEMAND") or {}).get("status") or ""
        ).strip().upper()
        if isinstance(evidence.get("CUSTOMER_DEMAND"), dict)
        else "",
        "structural_status": str(
            (evidence.get("STRUCTURAL_ARTIFACT") or {}).get("status") or ""
        ).strip().upper()
        if isinstance(evidence.get("STRUCTURAL_ARTIFACT"), dict)
        else "",
        "product_is_not": str(product.get("what_subzero_is_not") or ""),
        "first_validation": next(
            (item for item in paths if item.get("id") == "sz-paid-validation"),
            {},
        ),
    }


def first_validation_price(arch):
    offer = arch.get("first_validation") if isinstance(arch.get("first_validation"), dict) else {}
    try:
        return int(offer.get("price_usd"))
    except (TypeError, ValueError):
        return None


def measure_commercial(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "commercial is not JSON", "offer_id": "", "fixed_amount": 0}
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
    offer = data.get("offer") if isinstance(data.get("offer"), dict) else {}
    return {
        "error": "",
        "offer_id": str(offer.get("offer_id") or ""),
        "fixed_amount": offer.get("fixed_amount"),
        "does_not_replace": str(offer.get("does_not_replace") or ""),
    }


def measure_portfolio(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "portfolio is not JSON"}
    founder = data.get("founder_slot") if isinstance(data.get("founder_slot"), dict) else {}
    return {
        "error": "",
        "collectable_usd": str(data.get("collectable_usd") or "").strip().upper(),
        "now_active": str(founder.get("now_active") or ""),
        "banking_only_blocker": bool(data.get("banking_only_blocker")),
    }


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
            "note": (
                "SUBZERO GTM leftover was not read. Absence is not stillness. "
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
    if not row.get("card_present") or not row.get("arch_present") or misses:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/arch"])
                + ". SUBZERO GTM talk is CLAIMED until the leftover ships. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    open_gate = [str(item).strip().upper() for item in (row.get("gate_open") or [])]
    path_ids = [str(item) for item in (row.get("path_ids") or [])]
    horizon_keys = [str(item) for item in (row.get("horizon_keys") or [])]
    if (
        str(row.get("kind") or "") != "SUBZERO_GTM_ARCHITECTURE"
        or str(row.get("mandate") or "") != "demon-redteam-subzero-gtm-20260825-06"
        or str(row.get("panel") or "") != "3/3"
        or row.get("first_price") != 2500
        or str(row.get("demand") or "") != "UNKNOWN"
        or row.get("runtime_intelligence_claimed")
        or "UNMEASURED" not in str(row.get("runtime_status") or "")
        or str(row.get("demand_status") or "") != "UNKNOWN"
        or "MEASURED" not in str(row.get("structural_status") or "")
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
        or str(row.get("implements_p01") or "") != "P01_catalog_receipt"
        or not row.get("buyers_present")
        or "white-box-gguf-pilot-30d" not in (row.get("does_not_replace") or [])
        or "gguf-diagnostic-10d-12k" not in (row.get("does_not_replace") or [])
        or any(name not in path_ids for name in REQUIRED_PATH_IDS)
        or any(name not in horizon_keys for name in REQUIRED_HORIZONS)
        or str(row.get("commercial_offer_id") or "") != "white-box-gguf-pilot-30d"
        or row.get("white_box_fee") != 30000
        or str(row.get("payment_offer_id") or "") != "gguf-diagnostic-10d-12k"
        or row.get("payment_fee") != 12000
        or str(row.get("portfolio_now_active") or "") != "high-ticket-white-box"
        or str(row.get("portfolio_collectable") or "") != "NOT_LANDED"
        or not row.get("dio_present")
        or not row.get("excerpts_present")
        or str(row.get("taking_state") or "") != "CARRIER_ONLY"
        or not row.get("xyz_required")
        or "Codex / Grok Build" not in str(row.get("remeasurement_owner") or "")
        or str(row.get("titan") or "") != "NOT_WRITTEN"
        or str(row.get("subzero_now_active") or "") != "none"
        or not row.get("dissent_present")
        or "intelligence" not in str(row.get("product_is_not") or "").lower()
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "architecture present but incomplete, reminting, or it claimed cash. "
                "collected_cash_usd="
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
            "SUBZERO GTM leftover is on this tree. $2500 validation is a CANDIDATE "
            "SKU. White Box $30k and $12k diagnostic are preserved. Collected cash "
            "stays $0 / NOT_LANDED. Runtime intelligence is not claimed. A Slack "
            "taking is still not the file."
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
    arch = load_arch(search_hits.get(DEFAULT_ARCH, ""))
    commercial = measure_commercial(search_hits.get(COMMERCIAL_PATH, ""))
    payment = measure_payment_pack(search_hits.get(PAYMENT_PACK, ""))
    portfolio = measure_portfolio(search_hits.get(PORTFOLIO_PATH, ""))
    taking_present = _exists(root, TAKING_PATH)
    taking_state = "DURABLE_ON_MAIN" if taking_present else "CARRIER_ONLY"
    card_text = search_hits.get(DEFAULT_CARD, "")
    dissent = search_hits.get(os.path.join("revenue", "subzero_gtm", "dissent.md"), "")
    blob = "\n".join(
        [
            card_text,
            search_hits.get(DEFAULT_ARCH, ""),
            search_hits.get(os.path.join("host", "subzero_gtm.py"), ""),
            search_hits.get(os.path.join("revenue", "subzero_gtm", "README.md"), ""),
            dissent,
        ]
    )
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "SUBZERO GTM" in card_text,
        "arch_present": bool(arch) and not arch.get("error"),
        "kind": arch.get("kind") or "",
        "mandate": arch.get("mandate") or "",
        "panel": arch.get("panel") or "",
        "first_price": first_validation_price(arch),
        "demand": arch.get("demand") or "",
        "runtime_intelligence_claimed": bool(arch.get("runtime_intelligence_claimed")),
        "runtime_status": arch.get("runtime_status") or "",
        "demand_status": arch.get("demand_status") or "",
        "structural_status": arch.get("structural_status") or "",
        "gate_pack": arch.get("gate_pack") or "",
        "gate_owner": arch.get("gate_owner") or "",
        "gate_buyer": arch.get("gate_buyer") or "",
        "gate_cash": arch.get("gate_cash") or "",
        "gate_cash_usd": arch.get("gate_cash_usd"),
        "gate_open": arch.get("gate_open") or [],
        "ready_does_not_mean_cash": bool(arch.get("ready_does_not_mean_cash")),
        "collectable_usd": arch.get("collectable_usd") or "",
        "collected_cash_usd": arch.get("collected_cash_usd"),
        "banking_only_blocker": bool(arch.get("banking_only_blocker")),
        "computer_is_the_product": bool(arch.get("computer_is_the_product")),
        "overwrites_commercial_json": bool(arch.get("overwrites_commercial_json")),
        "overwrites_dio": bool(arch.get("overwrites_dio")),
        "overwrites_payment_ready": bool(arch.get("overwrites_payment_ready")),
        "overwrites_portfolio_overdrive": bool(arch.get("overwrites_portfolio_overdrive")),
        "overwrites_subzero_buyers": bool(arch.get("overwrites_subzero_buyers")),
        "implements_p01": arch.get("implements_p01") or "",
        "buyers_present": bool(search_hits.get(BUYERS_PACK, ""))
        and "P01_catalog_receipt" in search_hits.get(BUYERS_PACK, ""),
        "does_not_replace": arch.get("does_not_replace") or [],
        "path_ids": arch.get("path_ids") or [],
        "horizon_keys": arch.get("horizon_keys") or [],
        "commercial_offer_id": commercial.get("offer_id") or "",
        "white_box_fee": commercial.get("fixed_amount"),
        "payment_offer_id": payment.get("offer_id") or "",
        "payment_fee": payment.get("fixed_amount"),
        "portfolio_now_active": portfolio.get("now_active") or "",
        "portfolio_collectable": portfolio.get("collectable_usd") or "",
        "dio_present": bool(search_hits.get(DIO_FOUNDATION, "")),
        "excerpts_present": "muhl_grbn" in search_hits.get(EXCERPTS, ""),
        "taking_state": taking_state,
        "taking_present": taking_present,
        "remeasurement_owner": arch.get("remeasurement_owner") or "",
        "xyz_required": bool(arch.get("xyz_required")),
        "titan": arch.get("titan") or "NOT_WRITTEN",
        "subzero_now_active": arch.get("subzero_now_active") or "",
        "dissent_present": "demand is unknown" in dissent.lower(),
        "product_is_not": arch.get("product_is_not") or "",
        "forbidden_hits": forbidden_hits(blob),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "slack_ts": arch.get("slack_ts") or SLACK_TS,
        "landing_owner": arch.get("landing_owner") or "",
    }
    row = measure_from_rows(facts)
    row["arch"] = DEFAULT_ARCH
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
                "arch_present": False,
                "misses": [DEFAULT_CARD],
            }
        )
    )
    return missing.get("state") == "NOT_LANDED" and missing.get("z") == "FINDER-FAILED"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure the SUBZERO GTM leftover")
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
        "first_price": row.get("first_price"),
        "path_ids": row.get("path_ids") or [],
        "gate_open": row.get("gate_open") or [],
        "collected_cash_usd": row.get("collected_cash_usd"),
        "collectable_usd": row.get("collectable_usd"),
        "demand": row.get("demand"),
        "runtime_status": row.get("runtime_status"),
    }
    payload["z"] = verdict.get("z") or "none"
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
