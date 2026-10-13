#!/usr/bin/env python3
"""host/claude_tester.py — Slack Claude-tester rule is not a land.

Slack 1787638370.166649 (DEMON OWNER_RULE_RELAY): stop using Claude
models as testers / verifiers. Talk that restates the rule is
CLAIMED until this leftover measures the card, the resource ledger
row, the XYZ+calibration law, and the preserve-artifacts clause.

This leftover does not assign Claude a tester role. It does not
erase Claude-authored build artifacts. It does not authorize
destructive actions. DIO/JOJO keep their named-builder lanes.

  python3 host/claude_tester.py
  python3 host/claude_tester.py --root .
  python3 host/claude_tester.py --self-test

X = exact files in SEARCH_SPACE
Y = phrases found in those bytes
Z = missing file / missing phrase / failed calibration
Calibration = known-present EXECUTE.md + owner Action Pad directive
must be found in the same run or the measure is UNMEASURED.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CLAUDE_TESTER.json")
DEFAULT_CARD = os.path.join("ground", "CLAUDE_TESTER.md")
DEFAULT_LEDGER = "resources.html"
SLACK_TS = "1787638370.166649"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    DEFAULT_LEDGER,
    os.path.join("host", "claude_tester.py"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "stop using claude",
    "testers",
    "xyz",
    "known-present calibration",
    "preserve",
    "deterministic local",
    "github actions",
    "codex",
    "codex / grok build",
    "claude_intermediate_untrusted",
    "non-claude",
)
LEDGER_PHRASES = (
    "claude_tester",
    "verification",
    "not testers",
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
    """Parse the Claude-tester catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    routes = []
    for item in data.get("allowed_verifiers") or []:
        name = str(item or "").strip()
        if name:
            routes.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "preserve_claude_artifacts": bool(data.get("preserve_claude_artifacts", True)),
        "xyz_required": bool(data.get("xyz_required", True)),
        "calibration_required": bool(data.get("calibration_required", True)),
        "allowed_verifiers": routes,
        "prior_claude_verdicts": str(data.get("prior_claude_verdicts") or "").strip(),
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    card = bool(facts.get("card_present"))
    catalog = bool(facts.get("catalog_present"))
    ledger = bool(facts.get("ledger_present"))
    phrases = list(facts.get("found_phrases") or [])
    ledger_phrases = list(facts.get("found_ledger_phrases") or [])
    routes = list(facts.get("allowed_verifiers") or [])
    preserve = bool(facts.get("preserve_claude_artifacts"))
    xyz = bool(facts.get("xyz_required"))
    calibration_ok = bool(facts.get("calibration_ok"))
    calibration_hits = list(facts.get("calibration_hits") or [])
    return {
        "measured": True,
        "card_present": card,
        "catalog_present": catalog,
        "ledger_present": ledger,
        "found_phrases": phrases,
        "found_ledger_phrases": ledger_phrases,
        "allowed_verifiers": routes,
        "preserve_claude_artifacts": preserve,
        "xyz_required": xyz,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
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
                "Claude-tester leftover not read. Absence was not stillness. "
                "A Slack OWNER_RULE_RELAY is not the file."
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
    ledger = bool(row.get("ledger_present"))
    phrases = list(row.get("found_phrases") or [])
    ledger_phrases = list(row.get("found_ledger_phrases") or [])
    routes = list(row.get("allowed_verifiers") or [])
    preserve = bool(row.get("preserve_claude_artifacts"))
    xyz = bool(row.get("xyz_required"))
    if not card or not catalog or not ledger:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/ledger"])
                + ". Stop-using-Claude-testers talk is CLAIMED until the leftover ships."
            ),
        }
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    ledger_needed = [item for item in LEDGER_PHRASES if item not in ledger_phrases]
    if needed or ledger_needed or len(routes) < 4 or not preserve or not xyz:
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/ledger present but incomplete. Missing phrases: "
                + ", ".join(needed + ledger_needed)
                + ". XYZ+preserve+routes required. Talk is CLAIMED."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Claude-tester leftover is on this tree. Resource ledger names "
            "the rule. XYZ + known-present calibration required. Claude "
            "artifacts preserved. A Slack OWNER_RULE_RELAY is still not the file."
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
    card_text = search_hits.get(DEFAULT_CARD, "")
    catalog_text = search_hits.get(DEFAULT_CATALOG, "")
    ledger_text = search_hits.get(DEFAULT_LEDGER, "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join([card_text, catalog_text, search_hits.get(os.path.join("host", "claude_tester.py"), "")]).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    ledger_found = [phrase for phrase in LEDGER_PHRASES if phrase in ledger_text.lower()]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "stop using claude" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "ledger_present": bool(ledger_text) and "claude_tester" in ledger_text.lower(),
        "found_phrases": found,
        "found_ledger_phrases": ledger_found,
        "allowed_verifiers": catalog.get("allowed_verifiers") or [],
        "preserve_claude_artifacts": bool(catalog.get("preserve_claude_artifacts")),
        "xyz_required": bool(catalog.get("xyz_required")),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row["slack_ts"] = facts["slack_ts"]
    row["catalog"] = DEFAULT_CATALOG
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the Claude-tester leftover against the resource ledger"
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
        "found_ledger_phrases": row.get("found_ledger_phrases") or [],
        "calibration_hits": row.get("calibration_hits") or [],
    }
    payload["z"] = row.get("misses") or []
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
            "ledger_present": True,
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
            "ledger_present": False,
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
            "ledger_present": True,
            "found_phrases": ["stop using claude"],
            "found_ledger_phrases": [],
            "allowed_verifiers": ["Codex"],
            "preserve_claude_artifacts": True,
            "xyz_required": True,
        }
    )
    assert incomplete["state"] == "NOT_LANDED"
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "ledger_present": True,
            "found_phrases": list(REQUIRED_PHRASES),
            "found_ledger_phrases": list(LEDGER_PHRASES),
            "allowed_verifiers": [
                "deterministic local checks",
                "GitHub Actions",
                "Codex",
                "Grok / direct xAI",
                "Codex / Grok Build",
            ],
            "preserve_claude_artifacts": True,
            "xyz_required": True,
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    catalog = load_catalog(
        json.dumps(
            {
                "slack_ts": SLACK_TS,
                "allowed_verifiers": ["Codex", "Grok Build"],
                "preserve_claude_artifacts": True,
                "xyz_required": True,
            }
        )
    )
    assert catalog["slack_ts"] == SLACK_TS
    assert catalog["preserve_claude_artifacts"] is True
    return True


if __name__ == "__main__":
    sys.exit(main())
