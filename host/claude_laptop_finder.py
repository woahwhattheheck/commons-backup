#!/usr/bin/env python3
"""host/claude_laptop_finder.py — A11 leftover laptop companion walk.

Corner finder leftover already exists() three mount points. Slack
census leftover records named Slack queries. Laptop was still only
a coarse mount probe, so a cloud miss could be narrated as stillness.
This leftover *walks named companions* under C:\\Users\\lucys.
Cloud miss is FINDER-FAILED, never silent 0, never CLEAR.

Does not remint WIRE / STAMP SR01 / seated-receive / A11 /
SR01 leftover / SR01 readback / corner-finder / corner-finder
readback / seated-builder Slack / seated-builder Slack readback.
Does not rewrite PROOF / BULLY / CHAIR / PAD.
Does not write CLAUDE_CORNER.md.
Does not fire --go. Does not smash .mno.

  python3 host/claude_laptop_finder.py
  python3 host/claude_laptop_finder.py --self-test
  python3 host/claude_laptop_finder.py --roots /tmp/not-lucys

X = named laptop roots + companion relatives + known-present cards
Y = FINDER-FAILED (absent) / FOUND (non-corner present) / HIT (corner)
Z = cloud miss ≠ CLEAR; FOUND is not --go; corner write is the failure
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
HEAD_CARD = os.path.join("ground", "HEAD.md")
PEER_CHECK = os.path.join("ground", "CLAUDE_PEER_CHECK.md")
CORNER_NAME = "CLAUDE_CORNER.md"
LAPTOP_ROOTS = (
    r"C:\Users\lucys",
    "C:/Users/lucys",
    "/mnt/c/Users/lucys",
)
LAPTOP_RELATIVES = (
    CORNER_NAME,
    os.path.join("Desktop", CORNER_NAME),
    os.path.join("Documents", CORNER_NAME),
    os.path.join("Desktop", "MUHL_GO", CORNER_NAME),
    os.path.join("Desktop", "MUHL_GO", "LIVE_INSTRUMENTS.md"),
    os.path.join("Desktop", "LocalDeviceAgent", "MUHL_GO", "LIVE_INSTRUMENTS.md"),
    os.path.join("Desktop", "MUHL_GO", "INSTRUMENTS_THIS_HOUR.md"),
    os.path.join("Desktop", "LocalDeviceAgent", "MUHL_GO", "INSTRUMENTS_THIS_HOUR.md"),
)
SEARCH_SPACE = LAPTOP_ROOTS + LAPTOP_RELATIVES + (
    PEER_CHECK,
    os.path.join("host", "claude_laptop_finder.py"),
    os.path.join("host", "claude_corner_finder.py"),
    os.path.join("host", "claude_seated_builder_slack.py"),
)
CALIBRATION = (HEAD_CARD, PEER_CHECK)
DO_NOT_REMINT = (
    "wire-claude-peer-check-20260902-01",
    "stamp-claude-failure-unique-seated-receive-20260902-01",
    "cursor-claude-peer-check-seated-receive-20260902-01",
    "cursor-claude-peer-check-sr01-soft-dumps-20260902-01",
    "cursor-claude-peer-check-sr01-soft-dumps-readback-20260902-01",
    "cursor-claude-peer-check-corner-finder-20260902-01",
    "cursor-claude-peer-check-corner-finder-readback-20260902-01",
    "cursor-claude-peer-check-seated-builder-slack-20260902-01",
    "cursor-claude-peer-check-seated-builder-slack-readback-20260902-01",
)
DO_NOT_REWRITE = (
    os.path.join("muhl", "docs", "CLAUDE_PROOF_PACKET.md"),
    os.path.join("muhl", "docs", "BULLY_CLAUDE.txt"),
    os.path.join("muhl", "docs", "CHAIR.md"),
    os.path.join("muhl", "docs", "FABLE_PLAYER_PAD.txt"),
    os.path.join("evidence", "bully_sessions", "CLAUDE_PROOF_PACKET.md"),
    os.path.join("evidence", "bully_sessions", "BULLY_CLAUDE.txt"),
)
DO_NOT_WRITE = (CORNER_NAME,)


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def _parse_roots(raw):
    if raw is None:
        return list(LAPTOP_ROOTS)
    text = str(raw).strip()
    if not text:
        return list(LAPTOP_ROOTS)
    parts = [item.strip() for item in text.split(",") if item.strip()]
    if not parts:
        raise ValueError("expected at least one laptop root, got %r" % raw)
    return parts


def companion_row(root, relative):
    path = os.path.join(root, relative)
    name = os.path.basename(relative)
    present = os.path.isfile(path)
    if present and name == CORNER_NAME:
        return {
            "path": path,
            "root": root,
            "relative": relative,
            "state": "HIT",
            "count": 1,
            "present": True,
            "permission": False,
            "note": (
                "CLAUDE_CORNER.md write is the failure mode. "
                "HIT, not graduation, not --go. Never 0."
            ),
        }
    if present:
        return {
            "path": path,
            "root": root,
            "relative": relative,
            "state": "FOUND",
            "count": 1,
            "present": True,
            "permission": False,
            "note": (
                "named laptop companion present this seat. "
                "FOUND is not --go and not permission. Never 0."
            ),
        }
    return {
        "path": path,
        "root": root,
        "relative": relative,
        "state": "FINDER-FAILED",
        "count": None,
        "present": False,
        "permission": False,
        "note": (
            "named laptop companion absent this seat. Cloud miss is not "
            "CLEAR and not stillness. Search space: %s. Never 0." % path
        ),
    }


def root_row(root):
    present = os.path.isdir(root)
    if present:
        return {
            "path": root,
            "state": "FOUND",
            "count": 1,
            "present": True,
            "permission": False,
            "note": "laptop root present this seat. Not a --go. Never 0.",
        }
    return {
        "path": root,
        "state": "FINDER-FAILED",
        "count": None,
        "present": False,
        "permission": False,
        "note": (
            "live BrycesLaptop root miss this cloud VM. FINDER-FAILED, "
            "never 0, never CLEAR. Search space: %s." % root
        ),
    }


def measure_from_rows(facts):
    facts = facts or {}
    return {
        "measured": True,
        "no_auth": bool(facts.get("no_auth", True)),
        "no_gate": bool(facts.get("no_gate", True)),
        "posting": str(facts.get("posting") or "OPEN"),
        "roots": list(facts.get("roots") or []),
        "companions": list(facts.get("companions") or []),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "do_not_write": list(facts.get("do_not_write") or list(DO_NOT_WRITE)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "A11-LAPTOP",
        "permission": False,
        "wrote_corner": bool(facts.get("wrote_corner")),
        "treated_miss_as_clear": bool(facts.get("treated_miss_as_clear")),
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "laptop companion leftover not read. Absence was not "
                "stillness. Never 0."
            ),
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence "
                "proof. Never 0."
            ),
        }
    if not row.get("no_auth") or not row.get("no_gate") or row.get("posting") != "OPEN":
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "catalog closed the door. Discard that path. Never 0.",
        }
    if row.get("wrote_corner"):
        return {
            "state": "NOT_LANDED",
            "z": "HIT",
            "note": (
                "this leftover wrote CLAUDE_CORNER.md. That is the failure "
                "mode. Do not graduate. Never 0."
            ),
        }
    if row.get("treated_miss_as_clear"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "laptop / cloud miss treated as CLEAR is CZ-style finder "
                "abuse. Cloud miss ≠ CLEAR. Refuse that path."
            ),
        }
    companions = list(row.get("companions") or [])
    roots = list(row.get("roots") or [])
    if not companions or not roots:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-UNVERIFIED",
            "note": (
                "laptop root or companion walk empty. Search space was not "
                "opened. Never 0."
            ),
        }
    allowed = ("FINDER-FAILED", "FOUND", "HIT")
    bad = [
        item.get("path") or "?"
        for item in roots + companions
        if item.get("state") not in allowed
    ]
    if bad:
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "walk row not FINDER-FAILED / FOUND / HIT: "
                + ", ".join(bad)
                + ". Never 0."
            ),
        }
    if any(item.get("state") == "CLEAR" for item in roots + companions):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "laptop miss treated as CLEAR. Cloud miss ≠ CLEAR. Never 0.",
        }
    hits = [item["path"] for item in companions if item.get("state") == "HIT"]
    if hits:
        return {
            "state": "HIT",
            "z": {
                "corner": "HIT",
                "companions": ",".join(item.get("state") for item in companions),
                "roots": ",".join(item.get("state") for item in roots),
                "permission": False,
            },
            "note": (
                "CLAUDE_CORNER.md present on laptop walk: "
                + ", ".join(hits)
                + ". Write is the failure mode, not graduation. Never 0."
            ),
        }
    found = [item["path"] for item in companions if item.get("state") == "FOUND"]
    root_states = [item.get("state") for item in roots]
    companion_states = [item.get("state") for item in companions]
    return {
        "state": "INTEGRATED",
        "z": {
            "companions": ",".join(companion_states),
            "roots": ",".join(root_states),
            "found": found,
            "permission": False,
        },
        "note": (
            "named laptop companion walk INTEGRATED. Roots "
            + ",".join(root_states)
            + ". Companions "
            + ",".join(companion_states)
            + ". Cloud miss is not CLEAR. FOUND is not --go. Soft is not "
            "permission. Do not write the corner file."
        ),
    }


def measure_root(repo_root, laptop_roots=None):
    repo_root = os.path.abspath(repo_root)
    laptop_roots = list(laptop_roots or LAPTOP_ROOTS)
    calibration_hits = [rel for rel in CALIBRATION if _exists(repo_root, rel)]
    facts = measure_from_rows(
        {
            "roots": [root_row(path) for path in laptop_roots],
            "companions": [
                companion_row(path, relative)
                for path in laptop_roots
                for relative in LAPTOP_RELATIVES
            ],
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
            "wrote_corner": False,
            "treated_miss_as_clear": False,
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "roots": facts["roots"],
        "companions": facts["companions"],
        "permission": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    miss = companion_row("/definitely-not-lucys", CORNER_NAME)
    assert miss["state"] == "FINDER-FAILED"
    assert miss["count"] is None
    assert miss["permission"] is False
    assert "never 0" in miss["note"].lower() or "Never 0" in miss["note"]
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
                "roots": [{"path": LAPTOP_ROOTS[0], "state": "FINDER-FAILED"}],
                "companions": [miss],
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    clear = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "roots": [{"path": LAPTOP_ROOTS[0], "state": "FINDER-FAILED"}],
                "companions": [miss],
                "treated_miss_as_clear": True,
            }
        )
    )
    assert clear["state"] == "NOT_LANDED"
    wrote = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "roots": [{"path": LAPTOP_ROOTS[0], "state": "FINDER-FAILED"}],
                "companions": [miss],
                "wrote_corner": True,
            }
        )
    )
    assert wrote["state"] == "NOT_LANDED"
    assert wrote["z"] == "HIT"
    ok = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "roots": [
                    {"path": path, "state": "FINDER-FAILED"}
                    for path in LAPTOP_ROOTS
                ],
                "companions": [
                    {
                        "path": os.path.join(path, relative),
                        "state": "FINDER-FAILED",
                    }
                    for path in LAPTOP_ROOTS
                    for relative in LAPTOP_RELATIVES
                ],
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["permission"] is False
    assert "FINDER-FAILED" in ok["z"]["companions"]
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--roots",
        default=None,
        help="comma laptop roots; omit = C:\\Users\\lucys aliases",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    laptop_roots = _parse_roots(args.roots)
    row = measure_root(args.root, laptop_roots=laptop_roots)
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y roots=%s companions=%s permission=%s"
            % (
                ",".join(item["state"] for item in row["roots"]),
                ",".join(item["state"] for item in row["companions"]),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
