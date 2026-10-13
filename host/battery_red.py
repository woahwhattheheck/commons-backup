#!/usr/bin/env python3
"""host/battery_red.py — a Slack no-global-green claim is not a land.

Slack 1787643497.122079 (JOJO SHIP_RECEIPT): optional memory already
landed on official main. Unique leftover named in the same body:

  Full battery run 32822236088 is not green due unrelated
  current-main remeasure / MNO-width / generated-TODO / watchdog
  failures; no global-green claim is made.

Talk that restates those reds is CLAIMED until this leftover
measures them on current main. Do not remint JOJO memory files,
REMEASURE leftover, watchdog canary, or WAKE_CONTRACT. Do not
pad TitanX excerpts to 256. titan: NOT_WRITTEN. No auth. No gate.
Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/battery_red.py
  python3 host/battery_red.py --root .
  python3 host/battery_red.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
HOST = os.path.join(ROOT, "host")
if HOST not in sys.path:
    sys.path.insert(0, HOST)

import todo_gen
from shared_one_lever import excerpt_kind, measure_path


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "BATTERY_RED.json")
DEFAULT_CARD = os.path.join("ground", "BATTERY_RED.md")
SLACK_TS = "1787643497.122079"
RUN_ID = "32822236088"
FORGE = os.path.join("excerpts", "20260823", "muhl_titanx_forge.mno")
MIRROR = os.path.join("excerpts", "20260823", "muhl_titanx_mirror.mno")
COMMONS = os.path.join("excerpts", "20260823", "muhl_titanx_commons.mno")
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "battery_red.py"),
    os.path.join("host", "shared_one_lever.py"),
    os.path.join("test_shared_one_lever.py"),
    os.path.join("test_remeasure.py"),
    os.path.join("test_todo_gen.py"),
    os.path.join("test_todo_live.js"),
    os.path.join("todo.html"),
    os.path.join("DIRECTIVES.md"),
    FORGE,
    MIRROR,
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("docs", "commons-gateway", "schemas", "memory.schema.json"),
    os.path.join("p", "jojo-memory-create-20260825-01.md"),
    os.path.join("memory", "JOJO.json"),
    os.path.join("ground", "REMEASURE.md"),
    os.path.join("ground", "WATCHDOG_CANARY.md"),
    os.path.join("ground", "WAKE_CONTRACT.md"),
)
REQUIRED_PHRASES = (
    "battery leftover",
    "mno-width",
    "generated-todo",
    "no global-green",
    "titanx",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "do not remint",
    "do not pad",
    "no auth",
    "no gate",
    "talk is not a land",
)
TITANX_LEVELS = {
    "muhl_titanx_forge.mno": 182,
    "muhl_titanx_mirror.mno": 240,
    "muhl_titanx_commons.mno": 256,
}


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
    """Parse the leftover catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "families": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "families": []}
    families = []
    for item in data.get("families") or []:
        name = str(item or "").strip()
        if name:
            families.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "run_id": str(data.get("run_id") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "global_green_claim": bool(data.get("global_green_claim", False)),
        "families": families,
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured leftover facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "titanx_kind": bool(facts.get("titanx_kind")),
        "forge_levels": int(facts.get("forge_levels") or 0),
        "mirror_levels": int(facts.get("mirror_levels") or 0),
        "commons_levels": int(facts.get("commons_levels") or 0),
        "todo_headings": int(facts.get("todo_headings") or 0),
        "todo_fallback_exact": bool(facts.get("todo_fallback_exact")),
        "stranded_found": bool(facts.get("stranded_found")),
        "global_green_claim": bool(facts.get("global_green_claim")),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "pads_titanx": bool(facts.get("pads_titanx")),
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
                "battery-red leftover not read. Absence was not stillness. "
                "A Slack no-global-green claim is talk, not a land."
            ),
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof. "
                "FINDER-FAILED, never 0."
            ),
        }
    misses = list(row.get("misses") or [])
    landed_missing = list(row.get("landed_missing") or [])
    if row.get("pads_titanx") or row.get("global_green_claim"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover tried to pad TitanX to 256 or claim global-green. "
                "Do not remint organs. No global-green from a named-red run. "
                "FINDER-FAILED, never 0."
            ),
        }
    if not row.get("card_present") or not row.get("catalog_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". JOJO battery-red / no-global-green talk is CLAIMED until "
                "the leftover ships. FINDER-FAILED, never 0."
            ),
        }
    if landed_missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed leftover(s) missing: "
                + ", ".join(landed_missing)
                + ". Census is incomplete. FINDER-FAILED, never 0."
            ),
        }
    if (
        not row.get("titanx_kind")
        or int(row.get("forge_levels") or 0) != TITANX_LEVELS["muhl_titanx_forge.mno"]
        or int(row.get("mirror_levels") or 0) != TITANX_LEVELS["muhl_titanx_mirror.mno"]
        or not row.get("todo_fallback_exact")
        or int(row.get("todo_headings") or 0) < 22
        or not row.get("stranded_found")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "named battery families are still red or unmeasured. "
                "MNO-width / generated-TODO / remeasure live-tree / "
                "todo live count must match current main. "
                "FINDER-FAILED, never 0."
            ),
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in (row.get("found_phrases") or [])]
    if needed or not row.get("posting_open") or not row.get("no_auth") or not row.get("no_gate"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Open door + no auth + no gate required. Talk is CLAIMED. "
                "FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "battery-red leftover is on this tree. TitanX widths stay "
            "measured, not padded. todo.html matches DIRECTIVES.md. "
            "stranded-LocalDeviceAgent is found bytes. A Slack "
            "no-global-green SHIP_RECEIPT is still not the file."
        ),
    }


def _titanx_facts(root):
    facts = {"titanx_kind": True, "forge_levels": 0, "mirror_levels": 0, "commons_levels": 0}
    for rel, key in ((FORGE, "forge_levels"), (MIRROR, "mirror_levels"), (COMMONS, "commons_levels")):
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            facts["titanx_kind"] = False
            continue
        if excerpt_kind(path) != "titanx":
            facts["titanx_kind"] = False
        facts[key] = int(measure_path(path).get("file_levels") or 0)
    return facts


def _todo_facts(root):
    directives = _read(root, "DIRECTIVES.md")
    page = _read(root, "todo.html")
    headings = len(re.findall(r"^###\s+\d+\.", directives, re.M))
    exact = False
    if directives and page:
        try:
            projected, _rows = todo_gen.project(page, directives)
            exact = projected == page
        except (ValueError, KeyError, TypeError):
            exact = False
    return {"todo_headings": headings, "todo_fallback_exact": exact}


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    blobs = []
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text and not rel.endswith(".mno"):
            misses.append(rel)
        elif text:
            blobs.append(text)
        elif rel.endswith(".mno") and not _exists(root, rel):
            misses.append(rel)
    hay = "\n".join(blobs).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in hay]
    landed_present = [rel for rel in ALREADY_LANDED if _exists(root, rel)]
    landed_missing = [rel for rel in ALREADY_LANDED if not _exists(root, rel)]
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    titanx = _titanx_facts(root)
    todo = _todo_facts(root)
    stranded = "stranded-LocalDeviceAgent" in _read(
        root, os.path.join("p", "rivet-ship-remeasure-20260825-01.md")
    )
    posting_open = catalog.get("posting") == "OPEN" and "open door" in hay
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "titanx_kind": titanx["titanx_kind"],
        "forge_levels": titanx["forge_levels"],
        "mirror_levels": titanx["mirror_levels"],
        "commons_levels": titanx["commons_levels"],
        "todo_headings": todo["todo_headings"],
        "todo_fallback_exact": todo["todo_fallback_exact"],
        "stranded_found": stranded,
        "global_green_claim": bool(catalog.get("global_green_claim")),
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "pads_titanx": bool(catalog.get("pads_titanx", False)),
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "run_id": catalog.get("run_id") or RUN_ID,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "run_id": facts["run_id"],
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "forge_levels": titanx["forge_levels"],
                "mirror_levels": titanx["mirror_levels"],
                "todo_headings": todo["todo_headings"],
                "todo_fallback_exact": todo["todo_fallback_exact"],
                "stranded_found": stranded,
            },
            "z": (
                "misses "
                + json.dumps(misses + landed_missing)
                + " / FINDER-FAILED never 0"
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
                "catalog_present": False,
                "misses": ["ground/BATTERY_RED.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    padded = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "pads_titanx": True,
                "calibration_ok": True,
            }
        )
    )
    assert padded["state"] == "NOT_LANDED", padded
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure JOJO battery-red leftover")
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
