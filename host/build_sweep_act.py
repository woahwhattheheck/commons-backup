#!/usr/bin/env python3
"""host/build_sweep_act.py — act on the build sweep; talk is not a land.

Slack 1787644673.314949 (DEMON LANDED + ship-talk): hygiene landed.
OWNER_MACHINE_BUILD_SWEEP named the next ownerable actions.
Unique leftover: add a current pixel heartbeat emitter, the first
next action on an already-LANDED build. Hygiene is not the colony
build.

Do not remint OWNER_MACHINE_BUILD_SWEEP, PIXEL_HEARTBEAT contract,
SITTING_REMINT, GROK_HYGIENE, GROK_CLAUDE_HYGIENE, or TERMINAL_CATALOG.
Do not fabricate a PLAYER2 refresh. titan: NOT_WRITTEN. No auth.
No gate. Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/build_sweep_act.py
  python3 host/build_sweep_act.py --root .
  python3 host/build_sweep_act.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
HOST = os.path.join(ROOT, "host")
if HOST not in sys.path:
    sys.path.insert(0, HOST)

from pixel_heartbeat import measure_root as measure_pixels


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "BUILD_SWEEP_ACT.json")
DEFAULT_CARD = os.path.join("ground", "BUILD_SWEEP_ACT.md")
SWEEP_CARD = os.path.join("ground", "OWNER_MACHINE_BUILD_SWEEP.md")
SWEEP_CATALOG = os.path.join("ground", "OWNER_MACHINE_BUILD_SWEEP.json")
EMITTER = os.path.join("host", "pixel_heartbeat_emit.py")
HEARTBEAT = os.path.join("host", "pixel_heartbeat.py")
RIVET_REL = os.path.join("pixels", "RIVET.json")
PLAYER2_REL = os.path.join("pixels", "PLAYER2.json")
INDEX_REL = os.path.join("pixels", "index.json")
SLACK_TS = "1787644673.314949"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "build_sweep_act.py"),
    EMITTER,
    HEARTBEAT,
    SWEEP_CARD,
    SWEEP_CATALOG,
    RIVET_REL,
    PLAYER2_REL,
    INDEX_REL,
    os.path.join("ground", "PIXEL_HEARTBEAT.md"),
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
    SWEEP_CARD,
    SWEEP_CATALOG,
    os.path.join("ground", "PIXEL_HEARTBEAT.md"),
    os.path.join("ground", "PIXEL_HEARTBEAT.json"),
    HEARTBEAT,
    os.path.join("ground", "SITTING_REMINT.md"),
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("ground", "GROK_CLAUDE_HYGIENE.md"),
    os.path.join("ground", "TERMINAL_CATALOG.md"),
)
REQUIRED_PHRASES = (
    "build sweep leftover",
    "current pixel heartbeat emitter",
    "hygiene is not the colony build",
    "do not remint",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "open door",
    "no auth",
    "no gate",
    "talk is not a land",
)
LOCAL_ONLY = (
    "rook resident evolution runtime",
    "MORROW rollback controller",
    "PFC bake boundary scanner",
    "MUHL KEYB",
    "LocalDeviceAgent Android",
    "Gemma E4B LiteRT",
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
    """Parse the build-sweep-act catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "already_landed": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "already_landed": []}
    already = []
    for item in data.get("already_landed") or []:
        name = str(item or "").strip()
        if name:
            already.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "first_action": str(data.get("first_action") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "already_landed": already,
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "emitter_present": bool(facts.get("emitter_present")),
        "sweep_present": bool(facts.get("sweep_present")),
        "rivet_valid": bool(facts.get("rivet_valid")),
        "player2_preserved": bool(facts.get("player2_preserved")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "local_only": list(facts.get("local_only") or []),
        "freshness": dict(facts.get("freshness") or {}),
    }


def classify(row):
    """Turn a measured leftover census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "build-sweep leftover not read. Absence was not stillness. "
                "Talk is not a land."
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
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    phrases = list(row.get("found_phrases") or [])
    posting_open = bool(row.get("posting_open"))
    no_auth = bool(row.get("no_auth"))
    no_gate = bool(row.get("no_gate"))
    if not card or not catalog or not row.get("emitter_present") or not row.get("sweep_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/emitter/sweep"])
                + ". Act-on-the-build-sweep / current-pixel-heartbeat-emitter talk "
                "is CLAIMED until the leftover ships. FINDER-FAILED, never 0."
            ),
        }
    if landed_missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed leftover(s) missing: "
                + ", ".join(landed_missing)
                + ". Do not remint. FINDER-FAILED, never 0."
            ),
        }
    if not row.get("rivet_valid") or not row.get("player2_preserved"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "current heartbeat missing or PLAYER2 was dropped. "
                "Do not invent presence. Do not refresh PLAYER2. "
                "FINDER-FAILED / FINDER-UNVERIFIED, never 0."
            ),
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in phrases]
    if needed or not posting_open or not no_auth or not no_gate:
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
            "Build-sweep leftover is on this tree. Current pixel heartbeat "
            "emitter shipped. Hygiene is not the colony build. A Slack "
            "receipt is still not the file."
        ),
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    blobs = []
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        else:
            blobs.append(text)
    hay = "\n".join(blobs).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in hay]
    landed_present = [rel for rel in ALREADY_LANDED if _exists(root, rel)]
    landed_missing = [rel for rel in ALREADY_LANDED if not _exists(root, rel)]
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    pixels = measure_pixels(root)
    rivet = {}
    player2 = False
    for item in pixels.get("heartbeats") or []:
        name = str(item.get("name") or "")
        if name == "RIVET.json":
            rivet = item
        if name == "PLAYER2.json":
            player2 = True
    listed = list(pixels.get("listed") or [])
    player2_preserved = player2 and "PLAYER2.json" in listed
    rivet_valid = bool(
        rivet.get("valid")
        and not rivet.get("fabricated")
        and rivet.get("path")
        and "RIVET.json" in listed
    )
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    sweep_text = _read(root, SWEEP_CATALOG).lower()
    local_only = [name for name in LOCAL_ONLY if name.lower() in sweep_text or name.lower() in hay]
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "emitter_present": _exists(root, EMITTER),
        "sweep_present": _exists(root, SWEEP_CARD) and _exists(root, SWEEP_CATALOG),
        "rivet_valid": rivet_valid,
        "player2_preserved": player2_preserved,
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "local_only": local_only,
        "freshness": {
            "rivet": rivet.get("freshness") or "",
            "stale": list(pixels.get("stale") or []),
            "hot": list(pixels.get("hot") or []),
        },
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "landed_present": landed_present,
                "emitter_present": facts["emitter_present"],
                "rivet_valid": rivet_valid,
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
                "emitter_present": False,
                "sweep_present": False,
                "misses": ["ground/BUILD_SWEEP_ACT.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    no_heart = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "emitter_present": True,
                "sweep_present": True,
                "rivet_valid": False,
                "player2_preserved": True,
                "landed_present": list(ALREADY_LANDED),
                "landed_missing": [],
                "found_phrases": list(REQUIRED_PHRASES),
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert no_heart["state"] == "NOT_LANDED", no_heart
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure build-sweep leftover")
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
