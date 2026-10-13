#!/usr/bin/env python3
"""host/grok_recovery.py — Grok session prefixes + dests-FROM-FILE handoff.

Slack 1787638974.401269 (JOJO): recover already-created Grok sessions
and publish the smallest Muhlnickel-only local-model request/result
handoff. A Slack taking is CLAIMED. Session prefixes on an install
list are not Commons HEAD.

This leftover reads. It does not write posts. It does not fire the
receiver. It does not edit host/pfc_*. It does not mutate Titan.
It does not add a gate. Do not remint
jojo-grok-recovery-muhlnickel-subagent-contract-20260825-01.

  python3 host/grok_recovery.py
  python3 host/grok_recovery.py --root .
  python3 host/grok_recovery.py --self-test

X = exact files in SEARCH_SPACE
Y = session hits + dests FROM FILE found in those bytes
Z = FINDER UNVERIFIED miss (never 0) plus failed calibration
Calibration = known-present EXECUTE.md + Action Pad directive +
lda/docs/INGRESS.md must be found in the same run or the measure
is UNMEASURED.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "GROK_RECOVERY.json")
DEFAULT_CARD = os.path.join("ground", "GROK_RECOVERY.md")
DEFAULT_INSTRUMENT = os.path.join("host", "grok_recovery.py")
DEFAULT_INGRESS = os.path.join("lda", "docs", "INGRESS.md")
DEFAULT_ADDRESS = os.path.join("infra", "host", "muhl_address_agent.py")
SLACK_TS = "1787638974.401269"
SOURCE_ID = "jojo-grok-recovery-muhlnickel-subagent-contract-20260825-01"
FINDER_UNVERIFIED = "FINDER UNVERIFIED"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    DEFAULT_INSTRUMENT,
    DEFAULT_INGRESS,
    DEFAULT_ADDRESS,
)
SELF_PATHS = (DEFAULT_CARD, DEFAULT_CATALOG, DEFAULT_INSTRUMENT)
INDEPENDENT_SEARCH = (DEFAULT_INGRESS, DEFAULT_ADDRESS)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
    DEFAULT_INGRESS,
)
REQUIRED_PHRASES = (
    "grok recovery",
    "muhlnickel-only",
    "prompt-address",
    "result-register",
    "no-host-inference",
    "no-titan-mutation",
    "01a0373e",
    "50_cross_synthesis",
    "finder unverified",
    "dests from file",
)
DEST_MARKERS = (
    "2380246639",
    "2467652405",
    "2383480831",
    "32768",
)
SESSION_PREFIXES = (
    "01a0373e",
    "01a03750",
    "01a03741",
    "50_cross_synthesis.txt",
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
    """Parse the Grok-recovery catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"sessions": [], "error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"sessions": [], "error": "catalog is not an object"}
    sessions = []
    seen = set()
    for item in data.get("sessions") or []:
        if not isinstance(item, dict):
            continue
        prefix = str(item.get("prefix") or "").strip()
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)
        sessions.append(
            {
                "lane": str(item.get("lane") or "").strip(),
                "prefix": prefix,
                "kind": str(item.get("kind") or "").strip(),
            }
        )
    dests = data.get("dests_from_file") if isinstance(data.get("dests_from_file"), dict) else {}
    handoff = data.get("handoff") if isinstance(data.get("handoff"), dict) else {}
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "sessions": sessions,
        "handoff": {
            "request": str(handoff.get("request") or "").strip(),
            "pulse": str(handoff.get("pulse") or "").strip(),
            "result": str(handoff.get("result") or "").strip(),
        },
        "dests_from_file": {
            "source": str(dests.get("source") or "").strip(),
            "cpu_fwd": dests.get("cpu_fwd"),
            "fwd_answer": dests.get("fwd_answer"),
            "receiver": dests.get("receiver"),
        },
        "no_host_inference": bool(data.get("no_host_inference")),
        "no_titan_mutation": bool(data.get("no_titan_mutation")),
        "apply": bool(data.get("apply")),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "hands_off": [
            str(item or "").strip()
            for item in (data.get("hands_off") or [])
            if str(item or "").strip()
        ],
        "error": "",
    }


def search_sessions(blobs, prefixes, self_paths=None):
    """Hit each published prefix. Self-hits are not recovery evidence."""
    skip = set(self_paths or SELF_PATHS)
    rows = []
    for prefix in prefixes:
        independent = []
        self_hits = []
        for rel, text in blobs:
            if prefix not in str(text or "") and prefix not in str(rel or ""):
                continue
            if rel in skip:
                self_hits.append(rel)
            else:
                independent.append(rel)
        if independent:
            rows.append(
                {
                    "prefix": prefix,
                    "state": "FOUND",
                    "hits": independent,
                    "self_hits": self_hits,
                    "note": "prefix present in an independent file.",
                }
            )
        else:
            rows.append(
                {
                    "prefix": prefix,
                    "state": FINDER_UNVERIFIED,
                    "hits": [],
                    "self_hits": self_hits,
                    "note": (
                        "prefix absent from independent search space "
                        + ", ".join(INDEPENDENT_SEARCH)
                        + ". Catalog self-hit is not recovery. "
                        "FINDER UNVERIFIED, never 0."
                    ),
                }
            )
    return rows


def measure_from_rows(facts):
    """Classify measured leftover + session facts. Failed calibration is void."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "instrument_present": bool(facts.get("instrument_present")),
        "ingress_present": bool(facts.get("ingress_present")),
        "address_present": bool(facts.get("address_present")),
        "address_no_fire": bool(facts.get("address_no_fire")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "dest_hits": list(facts.get("dest_hits") or []),
        "sessions": list(facts.get("sessions") or []),
        "no_host_inference": bool(facts.get("no_host_inference")),
        "no_titan_mutation": bool(facts.get("no_titan_mutation")),
        "apply": bool(facts.get("apply")),
        "xyz_required": bool(facts.get("xyz_required", True)),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured leftover census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Grok-recovery leftover not read. Absence was not stillness. "
                "A Slack taking is not the file."
            ),
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof."
            ),
        }
    misses = list(row.get("misses") or [])
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    instrument = bool(row.get("instrument_present"))
    ingress = bool(row.get("ingress_present"))
    dest_hits = list(row.get("dest_hits") or [])
    phrases = list(row.get("found_phrases") or [])
    no_host = bool(row.get("no_host_inference"))
    no_titan = bool(row.get("no_titan_mutation"))
    apply_false = row.get("apply") is False
    address_no_fire = bool(row.get("address_no_fire"))
    if not card or not catalog or not instrument:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/instrument"])
                + ". Grok-recovery / muhlnickel-subagent talk is CLAIMED "
                "until the leftover ships."
            ),
        }
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    dest_needed = [item for item in DEST_MARKERS if item not in dest_hits]
    if (
        needed
        or dest_needed
        or not ingress
        or not no_host
        or not no_titan
        or not apply_false
        or not address_no_fire
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed + dest_needed)
                + ". dests FROM FILE + no-host-inference + no-Titan-mutation "
                "+ apply:false + NO FIRE required. Talk is CLAIMED."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Grok-recovery leftover is on this tree. Session prefixes "
            "stay FINDER UNVERIFIED until a durable output/branch/SHA "
            "is on current main. dests FROM FILE named. no-host-inference "
            "and no-Titan-mutation hold. A Slack taking is still not the file."
        ),
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
    card_text = search_hits.get(DEFAULT_CARD, "")
    instrument_text = search_hits.get(DEFAULT_INSTRUMENT, "")
    ingress_text = search_hits.get(DEFAULT_INGRESS, "")
    address_text = search_hits.get(DEFAULT_ADDRESS, "")
    blob = "\n".join([card_text, search_hits.get(DEFAULT_CATALOG, ""), instrument_text]).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    dest_blob = ingress_text + "\n" + search_hits.get(DEFAULT_CATALOG, "")
    dest_hits = [marker for marker in DEST_MARKERS if marker in dest_blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    prefixes = [item["prefix"] for item in catalog.get("sessions") or []] or list(SESSION_PREFIXES)
    session_blobs = [(rel, search_hits.get(rel, "")) for rel in SEARCH_SPACE]
    sessions = search_sessions(session_blobs, prefixes)
    address_no_fire = (
        "does not fire" in address_text.lower()
        or "no fire" in address_text.lower()
    )
    facts = {
        "card_present": bool(card_text) and "grok recovery" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "instrument_present": bool(instrument_text) and FINDER_UNVERIFIED in instrument_text,
        "ingress_present": bool(ingress_text) and "2380246639" in ingress_text,
        "address_present": bool(address_text),
        "address_no_fire": address_no_fire,
        "found_phrases": found,
        "dest_hits": dest_hits,
        "sessions": sessions,
        "no_host_inference": bool(catalog.get("no_host_inference")),
        "no_titan_mutation": bool(catalog.get("no_titan_mutation")),
        "apply": bool(catalog.get("apply")),
        "xyz_required": True,
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
    }
    row = measure_from_rows(facts)
    row["slack_ts"] = catalog.get("slack_ts") or SLACK_TS
    row["source_id"] = catalog.get("source_id") or SOURCE_ID
    row["handoff"] = catalog.get("handoff") or {}
    row["dests_from_file"] = catalog.get("dests_from_file") or {}
    row["hands_off"] = catalog.get("hands_off") or []
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure Grok session prefixes and the Muhlnickel subagent handoff"
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
    payload["x"] = list(SEARCH_SPACE)
    payload["y"] = {
        "found_phrases": row.get("found_phrases") or [],
        "dest_hits": row.get("dest_hits") or [],
        "session_hits": [
            item["prefix"]
            for item in (row.get("sessions") or [])
            if item.get("state") == "FOUND"
        ],
        "calibration_hits": row.get("calibration_hits") or [],
    }
    payload["z"] = {
        "misses": row.get("misses") or [],
        "session_unverified": [
            item["prefix"]
            for item in (row.get("sessions") or [])
            if item.get("state") == FINDER_UNVERIFIED
        ],
        "verdict": FINDER_UNVERIFIED,
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    failed_cal = classify(
        {
            "measured": True,
            "calibration_ok": False,
            "calibration_hits": [],
            "card_present": True,
            "catalog_present": True,
            "instrument_present": True,
        }
    )
    assert failed_cal["state"] == "UNMEASURED"
    assert "instrument failure" in failed_cal["note"]
    missing = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": False,
            "catalog_present": False,
            "instrument_present": False,
            "misses": [DEFAULT_CARD],
        }
    )
    assert missing["state"] == "NOT_LANDED"
    incomplete = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "instrument_present": True,
            "ingress_present": True,
            "found_phrases": ["grok recovery"],
            "dest_hits": [],
            "no_host_inference": True,
            "no_titan_mutation": True,
            "apply": False,
            "address_no_fire": True,
        }
    )
    assert incomplete["state"] == "NOT_LANDED"
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "instrument_present": True,
            "ingress_present": True,
            "found_phrases": list(REQUIRED_PHRASES),
            "dest_hits": list(DEST_MARKERS),
            "no_host_inference": True,
            "no_titan_mutation": True,
            "apply": False,
            "address_no_fire": True,
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    hits = search_sessions(
        [
            (DEFAULT_CARD, "recovery 01a0373e leftover"),
            (DEFAULT_INGRESS, "cpu_fwd only"),
            (DEFAULT_ADDRESS, "NO FIRE 01a0373e"),
        ],
        ["01a0373e", "01a03750"],
        self_paths=SELF_PATHS,
    )
    assert hits[0]["state"] == "FOUND"
    assert hits[0]["hits"] == [DEFAULT_ADDRESS]
    assert hits[1]["state"] == FINDER_UNVERIFIED
    assert "never 0" in hits[1]["note"]
    catalog = load_catalog(
        json.dumps(
            {
                "source_id": SOURCE_ID,
                "sessions": [{"lane": "discovery", "prefix": "01a0373e"}],
                "no_host_inference": True,
                "no_titan_mutation": True,
                "apply": False,
            }
        )
    )
    assert catalog["source_id"] == SOURCE_ID
    assert catalog["no_host_inference"] is True
    assert catalog["apply"] is False
    return True


if __name__ == "__main__":
    sys.exit(main())
