#!/usr/bin/env python3
"""host/muhl_train_bridge.py — H-006 synthetic training-bridge leftover.

Slack 1787647412.543649 (JOJO TAKING_BACKEND_SWARM
jojo-clean-grok-modelwork-swarm-20260825-01):

  H-006 Muhlnickel training bridge — source-indexed synthetic-only
  cross-process implementation spec; no host inference or live
  Titan/device/model/container mutation.

That Slack body is CLAIMED. A read-only / no-write-tools swarm
cannot land itself. Talk is not a land.

Already-landed cells stay named, not reminted:
- H-005 Subzero proof artifacts: SUBZERO_TECH / EXPLORER / BUYERS / GTM
- H-007 profitability leftover: LDA_RECEIPT

Unique leftover this run is the H-006 source-indexed synthetic
training packet. It does not remint the JOJO swarm id. It does
not remint MUHL_RECEIPT_LANE or LDA_RECEIPT. It does not copy
private LocalDeviceAgent source. It does not write titan. It
does not smash commons.mno. No auth. No gate. Miss is
FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

The cited Commons pin 6a934ed9d07c293296fead0f403fbbcb3afc15a9
is an ANCESTOR, not current HEAD. A swarm pin is not current main.

  python3 host/muhl_train_bridge.py
  python3 host/muhl_train_bridge.py --root .
  python3 host/muhl_train_bridge.py --self-test
  python3 host/muhl_train_bridge.py --packet ground/muhl_train_bridge/valid-synthetic.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CARD = os.path.join("ground", "MUHL_TRAIN_BRIDGE.md")
DEFAULT_CATALOG = os.path.join("ground", "MUHL_TRAIN_BRIDGE.json")
DEFAULT_DOOR = "muhl-train.html"
FIXTURE_DIR = os.path.join("ground", "muhl_train_bridge")
SLACK_TS = "1787647412.543649"
TAKING_ID = "jojo-clean-grok-modelwork-swarm-20260825-01"
SWARM_PIN = "6a934ed9d07c293296fead0f403fbbcb3afc15a9"
CALIBRATION_POST = os.path.join(
    "p", "bryce-action-pad-open-door-directive-20260822-01.md"
)
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "muhl_train_bridge.py"),
    DEFAULT_DOOR,
    os.path.join(FIXTURE_DIR, "jojo-swarm.json"),
    os.path.join(FIXTURE_DIR, "valid-synthetic.json"),
    os.path.join(FIXTURE_DIR, "invalid-host-inference.json"),
    os.path.join(FIXTURE_DIR, "invalid-live-titan.json"),
    os.path.join(FIXTURE_DIR, "invalid-missing-fields.json"),
    os.path.join("ground", "SUBZERO_TECH.md"),
    os.path.join("ground", "SUBZERO_EXPLORER.md"),
    os.path.join("ground", "SUBZERO_BUYERS.md"),
    os.path.join("ground", "SUBZERO_GTM.md"),
    os.path.join("ground", "LDA_RECEIPT.md"),
    os.path.join("ground", "MUHL_RECEIPT_LANE.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    CALIBRATION_POST,
)
ALREADY_LANDED = (
    os.path.join("ground", "SUBZERO_TECH.md"),
    os.path.join("ground", "SUBZERO_EXPLORER.md"),
    os.path.join("ground", "SUBZERO_BUYERS.md"),
    os.path.join("ground", "SUBZERO_GTM.md"),
    os.path.join("ground", "LDA_RECEIPT.md"),
    os.path.join("ground", "MUHL_RECEIPT_LANE.md"),
)
REQUIRED_PHRASES = (
    "muhlnickel training bridge",
    "taking_backend_swarm",
    "h-006",
    "source-indexed",
    "synthetic-only",
    "cross-process",
    "no host inference",
    "no write tools",
    "ancestor is not current head",
    "6a934ed9d07c293296fead0f403fbbcb3afc15a9",
    "talk is not a land",
    "do not remint",
    "no auth",
    "no gate",
    "never 0",
    "finder-failed",
    "finder-unverified",
)
REQUIRED_FIELDS = (
    "kind",
    "source_index",
    "process",
    "bytes",
    "host_inference",
    "titan",
    "live_device",
    "live_model",
    "live_container",
)
VALID_PROCESS = ("request", "train", "result")
EXPECTED_FIXTURES = {
    "jojo-swarm.json": "CARRIER_ONLY",
    "valid-synthetic.json": "SYNTHETIC_OK",
    "invalid-host-inference.json": "NOT_LANDED",
    "invalid-live-titan.json": "NOT_LANDED",
    "invalid-missing-fields.json": "NOT_LANDED",
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


def load_json(text):
    """Parse one packet or catalog object. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def load_catalog(text):
    """Parse the training-bridge catalog. Invalid is measured empty."""
    data = load_json(text)
    if not data:
        return {"error": "catalog is not JSON", "cells": []}
    rows = []
    for item in data.get("cells") or []:
        if not isinstance(item, dict):
            continue
        cell = str(item.get("id") or "").strip().upper()
        if not cell:
            continue
        rows.append(
            {
                "id": cell,
                "name": str(item.get("name") or "").strip(),
                "state": str(item.get("state") or "").strip().upper(),
                "leftover": str(item.get("leftover") or "").strip(),
            }
        )
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "taking_id": str(data.get("taking_id") or "").strip() or TAKING_ID,
        "swarm_pin": str(data.get("swarm_pin") or "").strip() or SWARM_PIN,
        "pin_relation": str(data.get("pin_relation") or "").strip().upper(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "cells": rows,
        "error": "",
    }


def validate_packet(obj, root=None):
    """Classify one public synthetic training packet. Never 0."""
    if not isinstance(obj, dict) or not obj:
        return {
            "state": "UNMEASURED",
            "note": (
                "packet body not read. Absence was not stillness. "
                "FINDER-FAILED, never 0."
            ),
        }
    kind = str(obj.get("kind") or "").strip().upper()
    if kind in ("TAKING_BACKEND_SWARM", "PROFITABILITY_HANDOFF", "TAKING"):
        return {
            "state": "CARRIER_ONLY",
            "note": (
                "Slack / ntfy swarm taking is mail. A read-only / no-write "
                "swarm is CLAIMED until unique leftover bytes are on current "
                "main. Do not remint. FINDER-UNVERIFIED, never 0."
            ),
        }
    if kind != "MUHL_TRAIN_PACKET":
        return {
            "state": "NOT_LANDED",
            "note": (
                "kind is not MUHL_TRAIN_PACKET. Talk kinds stay CLAIMED. "
                "FINDER-FAILED, never 0."
            ),
        }
    missing = [field for field in REQUIRED_FIELDS if field not in obj]
    if missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing fields: "
                + ", ".join(missing)
                + ". FINDER-FAILED, never 0."
            ),
        }
    if obj.get("host_inference") is True or str(obj.get("host_inference")).lower() == "true":
        return {
            "state": "NOT_LANDED",
            "note": "host inference is refused. Synthetic-only. FINDER-FAILED, never 0.",
        }
    titan = str(obj.get("titan") or "").strip().upper()
    if titan not in ("NOT_WRITTEN", "NOT_LANDED"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "live Titan / titan write is refused. titan stays NOT_WRITTEN. "
                "FINDER-FAILED, never 0."
            ),
        }
    for flag in ("live_device", "live_model", "live_container"):
        if obj.get(flag) is True or str(obj.get(flag)).lower() == "true":
            return {
                "state": "NOT_LANDED",
                "note": (
                    flag
                    + " mutation is refused. Synthetic-only. FINDER-FAILED, never 0."
                ),
            }
    process = str(obj.get("process") or "").strip().lower()
    if process not in VALID_PROCESS:
        return {
            "state": "NOT_LANDED",
            "note": (
                "process must be request / train / result. FINDER-FAILED, never 0."
            ),
        }
    source = str(obj.get("source_index") or "").strip()
    if not source or source.startswith("/") or "LocalDeviceAgent" in source:
        return {
            "state": "NOT_LANDED",
            "note": (
                "source_index must be a public Commons path, not private LDA "
                "source. FINDER-FAILED, never 0."
            ),
        }
    if root and not _exists(root, source):
        return {
            "state": "NOT_LANDED",
            "note": (
                "source_index "
                + source
                + " is FINDER-FAILED on this tree. Never 0."
            ),
        }
    payload = str(obj.get("bytes") or "").strip()
    if not payload:
        return {
            "state": "NOT_LANDED",
            "note": "empty synthetic bytes. FINDER-FAILED, never 0.",
        }
    return {
        "state": "SYNTHETIC_OK",
        "note": (
            "source-indexed synthetic training packet is well-formed. "
            "This is not host inference, live Titan, or a customer train. "
            "A Slack TAKING_BACKEND_SWARM is still not the file."
        ),
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "door_present": bool(facts.get("door_present")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "cells": list(facts.get("cells") or []),
        "names_h006_leftover": bool(facts.get("names_h006_leftover")),
        "names_h005_named": bool(facts.get("names_h005_named")),
        "names_h007_named": bool(facts.get("names_h007_named")),
        "claims_swarm_integrated": bool(facts.get("claims_swarm_integrated")),
        "pin_is_ancestor": bool(facts.get("pin_is_ancestor")),
        "fixture_states": dict(facts.get("fixture_states") or {}),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured training-bridge census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Muhlnickel training-bridge leftover not read. Absence was "
                "not stillness. A read-only swarm taking is not a land."
            ),
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence "
                "proof. FINDER-FAILED, never 0."
            ),
        }
    misses = list(row.get("misses") or [])
    landed_missing = list(row.get("landed_missing") or [])
    if not row.get("card_present") or not row.get("catalog_present") or not row.get("door_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/door"])
                + ". TAKING_BACKEND_SWARM / no-write-tools talk is CLAIMED "
                "until the leftover ships. FINDER-FAILED, never 0."
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
    if row.get("claims_swarm_integrated"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog claims the JOJO swarm INTEGRATED. A read-only / "
                "no-write-tools taking is CARRIER_ONLY, not a second land. "
                "FINDER-FAILED, never 0."
            ),
        }
    if not row.get("names_h006_leftover"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "H-006 is not named as this leftover. Do not remint H-005 / "
                "H-007. FINDER-FAILED, never 0."
            ),
        }
    if not row.get("names_h005_named") or not row.get("names_h007_named"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "H-005 / H-007 already-landed cells are not named. Do not "
                "remint them. FINDER-FAILED, never 0."
            ),
        }
    if not row.get("pin_is_ancestor"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "swarm pin 6a934ed9 is not named ANCESTOR. Ancestor is not "
                "current head. FINDER-FAILED, never 0."
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
    fixture_states = dict(row.get("fixture_states") or {})
    bad = [
        name
        for name, expect in EXPECTED_FIXTURES.items()
        if fixture_states.get(name) != expect
    ]
    if bad:
        return {
            "state": "NOT_LANDED",
            "note": (
                "fixture miss: "
                + ", ".join(bad)
                + ". FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Muhlnickel training-bridge leftover is on this tree. H-006 is "
            "the unique leftover. H-005 Subzero artifacts and H-007 LDA "
            "receipt stay named, not reminted. A Slack TAKING_BACKEND_SWARM "
            "/ no-write-tools taking is still not the file."
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
    cells = catalog.get("cells") or []
    names_h006_leftover = any(
        item.get("id") == "H-006" and item.get("state") == "THIS_LEFTOVER"
        for item in cells
    )
    names_h005_named = any(
        item.get("id") == "H-005" and item.get("state") == "NAMED"
        for item in cells
    )
    names_h007_named = any(
        item.get("id") == "H-007" and item.get("state") == "NAMED"
        for item in cells
    )
    claims_swarm_integrated = any(
        item.get("id") == "SWARM" and item.get("state") == "INTEGRATED"
        for item in cells
    )
    pin_is_ancestor = catalog.get("pin_relation") == "ANCESTOR"
    fixture_states = {}
    for name in EXPECTED_FIXTURES:
        rel = os.path.join(FIXTURE_DIR, name)
        fixture_states[name] = validate_packet(
            load_json(_read(root, rel)), root=root
        )["state"]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "door_present": _exists(root, DEFAULT_DOOR),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "cells": cells,
        "names_h006_leftover": names_h006_leftover,
        "names_h005_named": names_h005_named,
        "names_h007_named": names_h007_named,
        "claims_swarm_integrated": claims_swarm_integrated,
        "pin_is_ancestor": pin_is_ancestor,
        "fixture_states": fixture_states,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
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
                "cells": cells,
                "fixture_states": fixture_states,
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
                "door_present": False,
                "misses": ["ground/MUHL_TRAIN_BRIDGE.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    claimed = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "door_present": True,
                "landed_present": list(ALREADY_LANDED),
                "landed_missing": [],
                "found_phrases": list(REQUIRED_PHRASES),
                "cells": [{"id": "SWARM", "state": "INTEGRATED"}],
                "names_h006_leftover": True,
                "names_h005_named": True,
                "names_h007_named": True,
                "claims_swarm_integrated": True,
                "pin_is_ancestor": True,
                "fixture_states": dict(EXPECTED_FIXTURES),
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert claimed["state"] == "NOT_LANDED", claimed
    assert "CARRIER_ONLY" in claimed["note"] or "no-write" in claimed["note"], claimed
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure H-006 training-bridge leftover")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--packet")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    if args.packet:
        data = load_json(_read(args.root, args.packet))
        verdict = validate_packet(data, root=args.root)
        print(json.dumps({"verdict": verdict, "packet": args.packet}, indent=2, sort_keys=True))
        return 0 if verdict["state"] in ("SYNTHETIC_OK", "CARRIER_ONLY") else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = {"verdict": verdict, "row": row}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
