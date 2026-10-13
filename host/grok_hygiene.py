#!/usr/bin/env python3
"""host/grok_hygiene.py — Grok importing Claude plugin metadata is contained.

Slack 1787642850.967939 (DEMON): Grok Build 1.0.5 still declares three
Claude plugins enabled after every [compat.claude] cell is false.
Cause: Grok imports enabledPlugins=true from ~/.claude/settings.json.
Grok-native deny lists do not override that import.

Do NOT disable those plugins in Claude Code — paid Opus stays.
Do NOT delete Claude sessions or plugins. Do NOT mutate Titan.
Direct Grok Build is FAIL-CLOSED. Codex/local/GitHub Actions is the land lane;
SuperGrok Heavy / Grok Build is the analysis lane; Cursor is held.
Claude/Opus remains isolated UNTRUSTED candidate compute.
Hygiene is diligence, not the build.

X = exact files in SEARCH_SPACE
Y = leak plugins + keep-enabled + fail-closed + Codex/local/Actions land lane + Cursor held
Z = missing leftover / failed calibration / FINDER-FAILED
Calibration = known-present EXECUTE.md + GROK_HARNESS.md + Action Pad
must be found in the same run or the measure is UNMEASURED.
A miss prints FINDER-FAILED / FINDER-UNVERIFIED plus the search space.
Never 0.

  python3 host/grok_hygiene.py
  python3 host/grok_hygiene.py --root .
  python3 host/grok_hygiene.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "GROK_HYGIENE.json")
DEFAULT_CARD = os.path.join("ground", "GROK_HYGIENE.md")
SLACK_TS = "1787642850.967939"
LEAK_PLUGINS = (
    "frontend-design",
    "mcp-server-dev",
    "mcp-tunnels",
)
GATE_PATH = r"C:\Users\lucys\Documents\Codex\2026-08-25\ch\grok_hygiene_gate.ps1"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "grok_hygiene.py"),
    os.path.join("ground", "GROK_HARNESS.md"),
    os.path.join("ground", "CLAUDE_COMPUTE.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "GROK_HARNESS.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "GROK_HARNESS.md"),
    os.path.join("ground", "CLAUDE_COMPUTE.md"),
    os.path.join("ground", "CLAUDE_PARK.md"),
    os.path.join("ground", "MEMORY_SHIP.md"),
)
REQUIRED_PHRASES = (
    "grok/claude hygiene",
    "enabledplugins",
    "frontend-design",
    "mcp-server-dev",
    "mcp-tunnels",
    "fail-closed",
    "do not disable",
    "codex/local/github actions",
    "cursor is held",
    "untrusted candidate",
    "diligence",
    "never 0",
    "finder-failed",
    "open door",
    "no auth",
    "no gate",
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
    """Parse the hygiene catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "leak_plugins": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "leak_plugins": []}
    plugins = []
    for item in data.get("leak_plugins") or []:
        name = str(item or "").strip()
        if name:
            plugins.append(name)
    already = []
    for item in data.get("already_landed") or []:
        name = str(item or "").strip()
        if name:
            already.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "keep_claude_plugins": bool(data.get("keep_claude_plugins", True)),
        "direct_grok": str(data.get("direct_grok") or "").strip(),
        "cursor_surface": str(data.get("cursor_surface") or "").strip(),
        "land_lane": str(data.get("land_lane") or "").strip(),
        "grok_analysis_lane": str(data.get("grok_analysis_lane") or "").strip(),
        "claude_compute": str(data.get("claude_compute") or "").strip(),
        "hygiene": str(data.get("hygiene") or "").strip(),
        "mutate_claude": bool(data.get("mutate_claude", False)),
        "mutate_grok": bool(data.get("mutate_grok", False)),
        "delete_sessions": bool(data.get("delete_sessions", False)),
        "leak_plugins": plugins,
        "already_landed": already,
        "gate_path": str(data.get("gate_path") or "").strip(),
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "leak_plugins": list(facts.get("leak_plugins") or []),
        "keep_claude_plugins": bool(facts.get("keep_claude_plugins")),
        "fail_closed": bool(facts.get("fail_closed")),
        "codex_land_lane": bool(facts.get("codex_land_lane")),
        "cursor_held": bool(facts.get("cursor_held")),
        "untrusted_candidate": bool(facts.get("untrusted_candidate")),
        "diligence_not_build": bool(facts.get("diligence_not_build")),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "closes_door": bool(facts.get("closes_door")),
        "disables_claude_plugins": bool(facts.get("disables_claude_plugins")),
        "mutates_home": bool(facts.get("mutates_home")),
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
                "Grok-hygiene leftover not read. Absence was not stillness. "
                "A Slack hygiene boundary is talk, not a land."
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
    if row.get("closes_door"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover tried to close the door. Possessing the link is "
                "authorization. FINDER-FAILED, never 0."
            ),
        }
    if row.get("disables_claude_plugins"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover tried to disable Claude Code plugins. Paid Opus "
                "stays. Do not disable. FINDER-FAILED, never 0."
            ),
        }
    if row.get("mutates_home"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover tried to mutate ~/.claude or ~/.grok or delete "
                "Claude sessions. Preserve evidence. FINDER-FAILED, never 0."
            ),
        }
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Grok/Claude hygiene-boundary talk is CLAIMED until the "
                "leftover ships. FINDER-FAILED, never 0."
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
    leak = list(row.get("leak_plugins") or [])
    if list(LEAK_PLUGINS) != leak:
        return {
            "state": "NOT_LANDED",
            "note": (
                "leak plugin set is incomplete. Need frontend-design, "
                "mcp-server-dev, mcp-tunnels. FINDER-FAILED, never 0."
            ),
        }
    if (
        not row.get("keep_claude_plugins")
        or not row.get("fail_closed")
        or not row.get("codex_land_lane")
        or not row.get("cursor_held")
        or not row.get("untrusted_candidate")
        or not row.get("diligence_not_build")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "hygiene leftover present but incomplete. Keep Claude plugins. "
                "Direct Grok Build fail-closed. Codex/local/GitHub Actions is the land lane; Cursor held. "
                "Hygiene is diligence, not the build. FINDER-FAILED, never 0."
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
            "Grok-hygiene leftover is on this tree. Three Claude plugin "
            "metadata/payload surfaces stay named. Direct Grok Build is "
            "fail-closed. Codex/local/GitHub Actions is the land lane; Cursor held. Claude plugins stay "
            "enabled. A Slack hygiene boundary is still not the file."
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
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    leak = list(catalog.get("leak_plugins") or [])
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "leak_plugins": leak,
        "keep_claude_plugins": bool(catalog.get("keep_claude_plugins")),
        "fail_closed": catalog.get("direct_grok") == "FAIL_CLOSED",
        "codex_land_lane": catalog.get("land_lane") == "Codex / local / GitHub Actions",
        "cursor_held": catalog.get("cursor_surface") == "QUOTA_HOLD",
        "untrusted_candidate": catalog.get("claude_compute") == "UNTRUSTED_CANDIDATE",
        "diligence_not_build": catalog.get("hygiene") == "DILIGENCE_NOT_BUILD",
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "closes_door": False,
        "disables_claude_plugins": not bool(catalog.get("keep_claude_plugins")),
        "mutates_home": bool(catalog.get("mutate_claude") or catalog.get("mutate_grok") or catalog.get("delete_sessions")),
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "gate_path": catalog.get("gate_path") or GATE_PATH,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "gate_path": facts["gate_path"],
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "landed_present": landed_present,
                "leak_plugins": leak,
                "keep_claude_plugins": facts["keep_claude_plugins"],
                "fail_closed": facts["fail_closed"],
                "codex_land_lane": facts["codex_land_lane"],
                "cursor_held": facts["cursor_held"],
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
                "misses": ["ground/GROK_HYGIENE.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    disabled = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "disables_claude_plugins": True,
                "calibration_ok": True,
            }
        )
    )
    assert disabled["state"] == "NOT_LANDED", disabled
    mutated = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "mutates_home": True,
                "calibration_ok": True,
            }
        )
    )
    assert mutated["state"] == "NOT_LANDED", mutated
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure Grok/Claude hygiene leftover")
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
