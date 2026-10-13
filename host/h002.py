#!/usr/bin/env python3
"""host/h002.py — H-002 filesystem discovery is not gated by compat flags.

Slack 1787647999.742959 (DEMON UPDATE, first clean SuperGrok Heavy receipt):
stable Grok Build 1.0.5 discovers Claude plugins through
~/.claude/settings.json, ~/.claude/plugins/installed_plugins.json,
direct Claude plugin directories, and marketplace metadata outside
the documented compat.claude.* cells.

[plugins].disabled means discover-but-don't-load. grok inspect can
still show trusted/discovered plugins as enabled. Current source's
[claude_compat] imported=true gates the enabledPlugins merge and
does not gate filesystem discovery.

Do NOT restore empty Claude plugin registry maps. Do NOT rely on
compat flags alone. Do NOT patch or file upstream tonight —
independent source verification is running. Opus stays available;
Claude is not a test/verdict lane. Failed finder/tool call is
FINDER-FAILED / UNKNOWN, never 0.

Already landed (do not remint): GROK_HYGIENE, GROK_CLAUDE_HYGIENE,
SUPERGROK_HEAVY, REVIEW_LANE, MUHL_TRAIN_BRIDGE / H-006.
Hygiene PASS-before-job stays. This leftover names the source
finding those desks left open.

X = Slack first-clean receipt + four discovery surfaces +
imported=true merge-only + disabled semantics + containment
(empty registry maps) + do-not-restore + do-not-patch +
three xhigh lanes + Commons leftover paths.

Y = those facts named on this tree.
Z = missing leftover / failed calibration / FINDER-FAILED.
Never 0.

  python3 host/h002.py
  python3 host/h002.py --root .
  python3 host/h002.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "H002.json")
DEFAULT_CARD = os.path.join("ground", "H002.md")
SLACK_TS = "1787647999.742959"
GROK_BUILD = "1.0.5"
DISCOVERY_SURFACES = (
    "~/.claude/settings.json",
    "~/.claude/plugins/installed_plugins.json",
    "direct Claude plugin directories",
    "marketplace metadata",
)
TOKEN_RECEIPT = {
    "calls": 32,
    "total_tokens": 3125077,
    "input": 173401,
    "cache_read": 2914560,
    "output": 37116,
    "reasoning": 19107,
    "quota_429": False,
}
XHIGH_LANES = (
    "ARCHITECT",
    "SKEPTIC",
    "false-zero estate audit",
)
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "h002.py"),
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("ground", "GROK_CLAUDE_HYGIENE.md"),
    os.path.join("ground", "SUPERGROK_HEAVY.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("host", "grok_hygiene.py"),
    os.path.join("ground", "GROK_CLAUDE_HYGIENE.md"),
    os.path.join("host", "grok_claude_hygiene.py"),
    os.path.join("ground", "SUPERGROK_HEAVY.md"),
    os.path.join("host", "supergrok_heavy.py"),
    os.path.join("ground", "HEAVY_LANES.md"),
    os.path.join("host", "heavy_lanes.py"),
)
REQUIRED_PHRASES = (
    "h-002",
    "contamination",
    "first clean supergrok heavy",
    "1787647999.742959",
    "installed_plugins.json",
    "marketplace metadata",
    "discover-but-don't-load",
    "filesystem discovery",
    "imported=true",
    "does not gate",
    "do not restore",
    "do not patch",
    "finder-failed",
    "finder-unverified",
    "never 0",
    "open door",
    "unseated",
    "no auth",
    "no gate",
    "talk is not a land",
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


def classify_discovery(row):
    """Name one filesystem-discovery surface. Miss is FINDER-FAILED, never 0."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "H-002 discovery surface not read. Absence was not stillness. "
                "FINDER-FAILED, never 0."
            ),
        }
    if str(row.get("finder") or "").strip().lower() in {"failed", "unknown", "error"}:
        return {
            "state": "FINDER-FAILED",
            "note": (
                "finder/tool call failed on "
                + str(row.get("surface") or "unknown surface")
                + ". UNKNOWN, never 0."
            ),
        }
    present = bool(row.get("present"))
    disabled = bool(row.get("disabled"))
    inspect_enabled = bool(row.get("inspect_enabled"))
    surface = str(row.get("surface") or "unknown surface")
    if present and not disabled:
        return {
            "state": "CONTAMINATION",
            "note": (
                surface
                + " is discovered and not disabled. Hygiene PASS required "
                "before a Grok job. FINDER-FAILED, never 0."
            ),
        }
    if present and disabled and inspect_enabled:
        return {
            "state": "INSPECT_FALSE_ENABLED",
            "note": (
                surface
                + " is discover-but-don't-load, but grok inspect still "
                "shows enabled. Compat flags are not enough. Never 0."
            ),
        }
    if present and disabled:
        return {
            "state": "DISCOVER_BUT_DONT_LOAD",
            "note": (
                surface
                + " is discovered outside compat.claude.* and marked "
                "disabled. That is H-002, not a clean zero."
            ),
        }
    return {
        "state": "ABSENT",
        "note": surface + " was measured and not present on this host.",
    }


def load_catalog(text):
    """Parse the H-002 catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "discovery_surfaces": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "discovery_surfaces": []}
    surfaces = []
    for item in data.get("discovery_surfaces") or []:
        name = str(item or "").strip()
        if name:
            surfaces.append(name)
    receipt = data.get("token_receipt") or {}
    if not isinstance(receipt, dict):
        receipt = {}
    lanes = []
    for item in data.get("xhigh_lanes") or []:
        name = str(item or "").strip()
        if name:
            lanes.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "discovery_surfaces": surfaces,
        "discovery_gated_by_compat": bool(data.get("discovery_gated_by_compat")),
        "disabled_means": str(data.get("disabled_means") or "").strip().lower(),
        "restore_registry": bool(data.get("restore_registry")),
        "patch_upstream": str(data.get("patch_upstream") or "").strip().upper(),
        "token_receipt": receipt,
        "xhigh_lanes": lanes,
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
        "discovery_surfaces": list(facts.get("discovery_surfaces") or []),
        "names_four_surfaces": bool(facts.get("names_four_surfaces")),
        "discovery_gated_by_compat": bool(facts.get("discovery_gated_by_compat")),
        "disabled_means_discover": bool(facts.get("disabled_means_discover")),
        "restore_registry": bool(facts.get("restore_registry")),
        "patch_upstream": bool(facts.get("patch_upstream")),
        "names_token_receipt": bool(facts.get("names_token_receipt")),
        "names_xhigh_lanes": bool(facts.get("names_xhigh_lanes")),
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
    """Turn a measured H-002 census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "H-002 leftover not read. Absence was not stillness. "
                "A Slack first-clean SuperGrok Heavy receipt is not the file. "
                "not stillness. FINDER-FAILED, never 0."
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
    if not row.get("card_present") or not row.get("catalog_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". DEMON first-clean / H-002 / filesystem-discovery talk is "
                "CLAIMED until the leftover ships. FINDER-FAILED, never 0."
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
    if row.get("discovery_gated_by_compat"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog claims filesystem discovery is gated by compat flags. "
                "[claude_compat] imported=true gates the enabledPlugins merge "
                "only. FINDER-FAILED, never 0."
            ),
        }
    if row.get("restore_registry"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog asks to restore empty Claude plugin registry maps. "
                "Do not restore those keys tonight. FINDER-FAILED, never 0."
            ),
        }
    if row.get("patch_upstream"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog asks to patch or file upstream. Independent source "
                "verification is still running. Do not patch tonight. "
                "FINDER-FAILED, never 0."
            ),
        }
    if not row.get("disabled_means_discover"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "[plugins].disabled must be named discover-but-don't-load. "
                "grok inspect can still show trusted/discovered plugins as "
                "enabled. FINDER-FAILED, never 0."
            ),
        }
    if not row.get("names_four_surfaces"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "H-002 must name all four discovery surfaces: "
                + ", ".join(DISCOVERY_SURFACES)
                + ". FINDER-FAILED, never 0."
            ),
        }
    if not row.get("names_token_receipt") or not row.get("names_xhigh_lanes"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "first-clean token receipt and the three xhigh lanes "
                "(ARCHITECT / SKEPTIC / false-zero estate audit) must stay "
                "named. A Slack receipt is still not the file. "
                "FINDER-FAILED, never 0."
            ),
        }
    needed = [
        phrase
        for phrase in REQUIRED_PHRASES
        if phrase not in (row.get("found_phrases") or [])
    ]
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
            "H-002 leftover is on this tree. Filesystem discovery is outside "
            "compat.claude.*. imported=true does not gate it. Do not restore "
            "registry maps. Do not patch upstream tonight. A Slack first-clean "
            "SuperGrok Heavy receipt is still not the file."
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
    surfaces = catalog.get("discovery_surfaces") or []
    names_four_surfaces = all(name in surfaces for name in DISCOVERY_SURFACES)
    receipt = catalog.get("token_receipt") or {}
    names_token_receipt = (
        int(receipt.get("calls") or 0) == TOKEN_RECEIPT["calls"]
        and int(receipt.get("total_tokens") or 0) == TOKEN_RECEIPT["total_tokens"]
        and receipt.get("quota_429") is False
    )
    lanes = [str(item).strip() for item in (catalog.get("xhigh_lanes") or [])]
    names_xhigh_lanes = all(name in lanes for name in XHIGH_LANES)
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
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "discovery_surfaces": surfaces,
        "names_four_surfaces": names_four_surfaces,
        "discovery_gated_by_compat": bool(catalog.get("discovery_gated_by_compat")),
        "disabled_means_discover": catalog.get("disabled_means")
        == "discover-but-don't-load",
        "restore_registry": bool(catalog.get("restore_registry")),
        "patch_upstream": catalog.get("patch_upstream")
        not in {"", "DO_NOT_PATCH_YET", "FALSE", "NO"},
        "names_token_receipt": names_token_receipt,
        "names_xhigh_lanes": names_xhigh_lanes,
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
                "discovery_surfaces": surfaces,
                "token_receipt": receipt,
                "xhigh_lanes": lanes,
                "grok_build": GROK_BUILD,
            },
            "z": (
                "misses "
                + json.dumps(misses + landed_missing)
                + " / FINDER-FAILED never 0 / live ~/.claude FINDER-UNVERIFIED"
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
                "misses": ["ground/H002.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    gated = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "landed_present": list(ALREADY_LANDED),
                "landed_missing": [],
                "found_phrases": list(REQUIRED_PHRASES),
                "names_four_surfaces": True,
                "discovery_gated_by_compat": True,
                "disabled_means_discover": True,
                "names_token_receipt": True,
                "names_xhigh_lanes": True,
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert gated["state"] == "NOT_LANDED", gated
    assert "merge" in gated["note"], gated
    inspect_row = classify_discovery(
        {
            "measured": True,
            "finder": "ok",
            "surface": "~/.claude/plugins/installed_plugins.json",
            "present": True,
            "disabled": True,
            "inspect_enabled": True,
        }
    )
    assert inspect_row["state"] == "INSPECT_FALSE_ENABLED", inspect_row
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure H-002 leftover")
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
