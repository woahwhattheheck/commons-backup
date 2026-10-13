#!/usr/bin/env python3
"""host/titan_test_quarantine.py — tests must not bind live Titan.

Slack 1787641850.308579 (P0 LIVE-TITAN TEST QUARANTINE):
test_go_without_titan_is_absent called main(["--root", ROOT, "--go"])
while find_titan() included C:\\llm\\models\\titan.gguf. Branch
test/live-titan-contract-20260825 commit 09f277bc had
test_go_actuates_live_owner_titan_and_persists_reread_receipt.

Leftover: isolate default discovery under tests; require explicit
--titan to a temp synthetic file; payload-hash idempotence refuses
replay of already-WRITTEN moves. Preserve evidence. Repair stays
apply:false. No Claude testing/verdicts. Does not write titan.gguf.
Never 0.

  python3 host/titan_test_quarantine.py
  python3 host/titan_test_quarantine.py --root .
  python3 host/titan_test_quarantine.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "TITAN_TEST_QUARANTINE.json")
DEFAULT_CARD = os.path.join("ground", "TITAN_TEST_QUARANTINE.md")
SLACK_TS = "1787641850.308579"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "titan_test_quarantine.py"),
    os.path.join("host", "titan_move_offsets.py"),
    os.path.join("host", "titan_move_apply.py"),
    os.path.join("test_titan_move_apply.py"),
    os.path.join("ground", "TITAN_APPEND_GUARD.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "TITAN_APPEND_GUARD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "live-titan test quarantine",
    "temp synthetic titan",
    "under_test",
    "is_owner_titan_path",
    "already_written_move",
    "payload_sha256",
    "commons_titan_test",
    "never 0",
    "finder-failed",
    "open door",
    "no auth",
    "no gate",
    "unseated",
    "apply:false",
)
FORBIDDEN_PHRASES = (
    "test_go_actuates_live_owner_titan_and_persists_reread_receipt",
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
    """Parse the quarantine catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "apply": bool(data.get("apply", False)),
        "refuse_truncate": bool(data.get("refuse_truncate", True)),
        "refuse_repair": bool(data.get("refuse_repair", True)),
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "forbidden_hits": list(facts.get("forbidden_hits") or []),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "apply_off": bool(facts.get("apply_off")),
        "refuse_mutate": bool(facts.get("refuse_mutate")),
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
                "titan-test-quarantine leftover not read. Absence was not "
                "stillness. FINDER-FAILED, never 0."
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
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Live-Titan test quarantine talk is CLAIMED until the "
                "leftover ships. FINDER-FAILED, never 0."
            ),
        }
    forbidden = list(row.get("forbidden_hits") or [])
    if forbidden:
        return {
            "state": "NOT_LANDED",
            "note": (
                "live-owner actuation test still present: "
                + ", ".join(forbidden)
                + ". Quarantine that test. FINDER-FAILED, never 0."
            ),
        }
    phrases = list(row.get("found_phrases") or [])
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in phrases]
    if (
        needed
        or not row.get("posting_open")
        or not row.get("no_auth")
        or not row.get("no_gate")
        or not row.get("apply_off")
        or not row.get("refuse_mutate")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Isolation + payload-hash + apply:false required. "
                "Talk is CLAIMED. FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "titan-test-quarantine leftover is on this tree. Tests use temp "
            "synthetic Titan via --titan. Default discovery does not bind "
            "live Titan under tests. Payload-hash refuses WRITTEN replay. "
            "apply:false. A Slack P0 is still not the file."
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
    test_src = _read(root, "test_titan_move_apply.py")
    forbidden = [phrase for phrase in FORBIDDEN_PHRASES if phrase in test_src]
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
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "found_phrases": found,
        "forbidden_hits": forbidden,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "apply_off": catalog.get("apply") is False and "apply:false" in hay,
        "refuse_mutate": bool(catalog.get("refuse_truncate"))
        and bool(catalog.get("refuse_repair")),
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
            },
            "z": "misses " + json.dumps(misses + forbidden) + " / FINDER-FAILED never 0",
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
                "misses": ["ground/TITAN_TEST_QUARANTINE.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    live_test = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "found_phrases": list(REQUIRED_PHRASES),
                "forbidden_hits": list(FORBIDDEN_PHRASES),
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "apply_off": True,
                "refuse_mutate": True,
                "calibration_ok": True,
            }
        )
    )
    assert live_test["state"] == "NOT_LANDED", live_test
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure live-Titan test quarantine")
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
