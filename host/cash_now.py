#!/usr/bin/env python3
"""host/cash_now.py — authorization is not settlement is not bank cash.

Slack 1787639560.086549 (DEMON cash-now taking):
72-juror cash-now room / first collectable USD / private payout.
Talk that restates the taking is CLAIMED until this leftover
measures the card, the rail catalog, bazaar USD=0, the taking's
carrier state, the three stages, and the #needs-bryce form.
Banking setup is not the only blocker. Collectable USD stays
NOT_LANDED until a priced offer exists.

This leftover does not remint demon-cash-now-overdrive-20260825-01.
It does not open accounts. It does not store bank, routing, card,
tax, or credential data. It does not write titan. It does not
smash commons.mno. It does not add a gate.

  python3 host/cash_now.py
  python3 host/cash_now.py --root .
  python3 host/cash_now.py --self-test

X = exact files in SEARCH_SPACE
Y = phrases / stages / bazaar USD count / taking state found
Z = missing file / missing stage / forbidden field / FINDER-FAILED
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

if __package__:
    from .carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection
else:
    from carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CASH_NOW.json")
DEFAULT_CARD = os.path.join("ground", "CASH_NOW.md")
BAZAAR_PATH = "bazaar.json"
TAKING_PATH = os.path.join("p", "demon-cash-now-overdrive-20260825-01.md")
SLACK_TS = "1787639560.086549"
TAKING_SHA256 = "69b3b8261570ff721b8bb483ab3a898a98ff4c4a23d1253a7f7ffec3fd133cd6"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "cash_now.py"),
    BAZAAR_PATH,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "authorization",
    "settlement",
    "bank-available",
    "cash-now",
    "needs-bryce",
    "collectable usd",
    "banking setup is not the only blocker",
    "do not paste",
)
REQUIRED_STAGES = ("AUTHORIZATION", "SETTLEMENT", "BANK_AVAILABLE")
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
    """Parse the cash-now catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    stages = []
    for item in data.get("stages") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().upper()
        if name:
            stages.append(name)
    rails = []
    for item in data.get("rails") or []:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip()
        source = str(item.get("source") or "").strip()
        if provider:
            rails.append({"provider": provider, "source": source})
    needs = data.get("needs_bryce") if isinstance(data.get("needs_bryce"), dict) else {}
    bazaar = data.get("commons_bazaar") if isinstance(data.get("commons_bazaar"), dict) else {}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "taking_id": str(data.get("taking_id") or "").strip(),
        "taking_state": str(data.get("taking_state") or "").strip().upper(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "xyz_required": bool(data.get("xyz_required")),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "collectable_usd": str(data.get("collectable_usd") or "").strip().upper(),
        "banking_only_blocker": bool(data.get("banking_only_blocker")),
        "stages": stages,
        "rails": rails,
        "needs_bryce": {
            "need": str(needs.get("need") or "").strip(),
            "why_only_bryce": str(needs.get("why_only_bryce") or "").strip(),
            "smallest_action": str(needs.get("smallest_action") or "").strip(),
            "evidence": str(needs.get("evidence") or "").strip(),
            "after": str(needs.get("after") or "").strip(),
        },
        "bazaar_currency": str(bazaar.get("first_catalog_currency") or "").strip(),
        "usd_offer_expected": bazaar.get("usd_offer_expected"),
        "forbidden_in_public": [
            str(item).strip() for item in (data.get("forbidden_in_public") or []) if str(item).strip()
        ],
    }


def measure_bazaar(text):
    """Count offers and USD-priced rows. Invalid JSON is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "bazaar is not JSON", "offer_count": 0, "usd_offer_count": 0, "currency": ""}
    if not isinstance(data, dict):
        return {"error": "bazaar is not an object", "offer_count": 0, "usd_offer_count": 0, "currency": ""}
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
    return {
        "offer_count": len(offers),
        "usd_offer_count": usd,
        "currency": currency,
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
            "note": "cash-now leftover was not read. Absence is not stillness. Z=FINDER-FAILED. Never 0.",
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
    if not row.get("card_present") or not row.get("catalog_present") or misses:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Cash-now talk is CLAIMED until the leftover ships. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    phrases = [str(item).lower() for item in (row.get("found_phrases") or [])]
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    stages = [str(item).upper() for item in (row.get("stages") or [])]
    stage_miss = [item for item in REQUIRED_STAGES if item not in stages]
    forbidden = list(row.get("forbidden_hits") or [])
    needs = row.get("needs_bryce") if isinstance(row.get("needs_bryce"), dict) else {}
    needs_ok = all(
        needs.get(key)
        for key in ("need", "why_only_bryce", "smallest_action", "evidence", "after")
    )
    taking_state = str(row.get("taking_state") or CARRIER_ONLY).strip().upper()
    taking_present = bool(row.get("taking_present"))
    taking_ok = (
        taking_state == CARRIER_ONLY and not taking_present
    ) or (
        taking_state == DURABLE_ON_MAIN
        and taking_present
        and bool(row.get("taking_provenance_ok"))
    )
    if (
        needed
        or stage_miss
        or not needs_ok
        or row.get("usd_offer_count") != 0
        or str(row.get("bazaar_currency") or "") != "FREE_COLONY_COMPUTE"
        or not taking_ok
        or row.get("banking_only_blocker")
        or str(row.get("collectable_usd") or "") != "NOT_LANDED"
        or not row.get("xyz_required")
        or "Codex / Grok Build" not in str(row.get("remeasurement_owner") or "")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/catalog present but incomplete. Missing phrases/stages: "
                + ", ".join(needed + stage_miss)
                + ". Banking is not the only blocker. Collectable USD stays NOT_LANDED. "
                "Talk is CLAIMED. Z=FINDER-FAILED."
            ),
            "z": "FINDER-FAILED",
        }
    if forbidden:
        return {
            "state": "NOT_LANDED",
            "note": "forbidden financial field pattern found. Do not store bank/routing/card/tax data. Z=FINDER-FAILED.",
            "z": "FINDER-FAILED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "cash-now leftover is on this tree. Authorization is not settlement "
            "is not bank-available cash. Bazaar USD offers=0. Taking state is "
            + taking_state
            + ". Banking setup is not the only blocker. Only an exact Slack "
            "carrier projection is durable; a Slack taking without that projection "
            "is still not the file, and an arbitrary same-ID file is not durable."
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
    card_text = search_hits.get(DEFAULT_CARD, "")
    catalog_text = search_hits.get(DEFAULT_CATALOG, "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    bazaar = measure_bazaar(search_hits.get(BAZAAR_PATH, ""))
    taking = measure_slack_projection(
        root,
        TAKING_PATH,
        post_id="demon-cash-now-overdrive-20260825-01",
        carrier_ts=SLACK_TS,
        sender="DEMON",
        inner_kind="TAKING",
        expected_sha256=TAKING_SHA256,
    )
    blob = "\n".join(
        [
            card_text,
            catalog_text,
            search_hits.get(os.path.join("host", "cash_now.py"), ""),
        ]
    )
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob.lower()]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "cash-now" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "found_phrases": found,
        "stages": catalog.get("stages") or [],
        "rails": catalog.get("rails") or [],
        "needs_bryce": catalog.get("needs_bryce") or {},
        "taking_state": taking["state"],
        "taking_present": taking["present"],
        "taking_provenance_ok": taking["provenance_ok"],
        "taking_provenance_mismatches": taking["mismatches"],
        "usd_offer_count": bazaar.get("usd_offer_count"),
        "offer_count": bazaar.get("offer_count"),
        "bazaar_currency": bazaar.get("currency") or catalog.get("bazaar_currency") or "",
        "banking_only_blocker": bool(catalog.get("banking_only_blocker")),
        "collectable_usd": catalog.get("collectable_usd") or "",
        "remeasurement_owner": catalog.get("remeasurement_owner") or "",
        "xyz_required": bool(catalog.get("xyz_required")),
        "forbidden_hits": forbidden_hits(blob),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row["catalog"] = DEFAULT_CATALOG
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the cash-now leftover against official rails and bazaar.json"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    payload["x"] = list(SEARCH_SPACE) + [TAKING_PATH]
    payload["y"] = {
        "found_phrases": row.get("found_phrases") or [],
        "stages": row.get("stages") or [],
        "usd_offer_count": row.get("usd_offer_count"),
        "bazaar_currency": row.get("bazaar_currency") or "",
        "taking_state": row.get("taking_state") or "",
        "calibration_hits": row.get("calibration_hits") or [],
        "needs_bryce": row.get("needs_bryce") or {},
    }
    if not payload.get("z"):
        payload["z"] = row.get("misses") or []
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    assert empty["z"] == "FINDER-FAILED"
    failed_cal = classify(
        {
            "measured": True,
            "calibration_ok": False,
            "calibration_hits": [],
            "card_present": True,
            "catalog_present": True,
        }
    )
    assert failed_cal["state"] == "UNMEASURED"
    assert "Instrument failure" in failed_cal["note"]
    assert "Never 0" in failed_cal["note"]
    missing = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": False,
            "catalog_present": False,
            "misses": [DEFAULT_CARD],
        }
    )
    assert missing["state"] == "NOT_LANDED"
    assert missing["z"] == "FINDER-FAILED"
    bazaar = measure_bazaar(
        '{"payment":{"first_catalog_currency":"FREE_COLONY_COMPUTE"},"offers":[{"price":"0","currency":"FREE_COLONY_COMPUTE"}]}'
    )
    assert bazaar["usd_offer_count"] == 0
    assert bazaar["offer_count"] == 1
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "found_phrases": list(REQUIRED_PHRASES),
            "stages": list(REQUIRED_STAGES),
            "needs_bryce": {
                "need": "payout destination",
                "why_only_bryce": "owner UI only",
                "smallest_action": "connect destination privately",
                "evidence": "CASH_NOW.json",
                "after": "list a USD offer",
            },
            "usd_offer_count": 0,
            "bazaar_currency": "FREE_COLONY_COMPUTE",
            "taking_state": "CARRIER_ONLY",
            "banking_only_blocker": False,
            "collectable_usd": "NOT_LANDED",
            "xyz_required": True,
            "remeasurement_owner": "Codex / Grok Build",
            "forbidden_hits": [],
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    return True


if __name__ == "__main__":
    sys.exit(main())
