#!/usr/bin/env python3
"""host/claude_corner_finder.py — A11 leftover filename walk.

A11 / HIT-SR01 already indexes Plug RECEIVE-only vs git-soft
"may edit/build/ship". This leftover *measures* the named
CLAUDE_CORNER.md walk. Writing that file is the failure mode.
Absence is FINDER-FAILED, never silent 0, never CLEAR.

Does not remint WIRE / STAMP SR01 / seated-receive / A11 /
the SR01 leftover / the independent readback.
Does not rewrite PROOF / BULLY / CHAIR / PAD.

  python3 host/claude_corner_finder.py
  python3 host/claude_corner_finder.py --root .
  python3 host/claude_corner_finder.py --self-test

X = named walk dirs + Slack seated-builder query + laptop lucys
Y = FINDER-FAILED (absent) or HIT (file present) — never 0
Z = empty Slack search FINDER-UNVERIFIED (CZ-03) / laptop miss
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
WALK_DIRS = (
    ".",
    os.path.join("muhl", "docs"),
    "ground",
    os.path.join("ground", "pc-purge-20260820"),
    os.path.join("evidence", "bully_sessions"),
)
LAPTOP_PATHS = (
    r"C:\Users\lucys",
    "C:/Users/lucys",
    "/mnt/c/Users/lucys",
)
SLACK_QUERIES = (
    '"I am seated builder"',
    '"seated builder"',
)
SEARCH_SPACE = tuple(
    os.path.join(rel, CORNER_NAME) if rel != "." else CORNER_NAME
    for rel in WALK_DIRS
) + (
    PEER_CHECK,
    os.path.join("host", "claude_corner_finder.py"),
)
CALIBRATION = (HEAD_CARD, PEER_CHECK)
DO_NOT_REMINT = (
    "wire-claude-peer-check-20260902-01",
    "stamp-claude-failure-unique-seated-receive-20260902-01",
    "cursor-claude-peer-check-seated-receive-20260902-01",
    "cursor-claude-peer-check-sr01-soft-dumps-20260902-01",
    "cursor-claude-peer-check-sr01-soft-dumps-readback-20260902-01",
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


def _isdir(root, rel):
    if rel == ".":
        return os.path.isdir(root)
    return os.path.isdir(os.path.join(root, rel))


def walk_row(root, rel):
    path = CORNER_NAME if rel == "." else os.path.join(rel, CORNER_NAME)
    present = _exists(root, path)
    if present:
        return {
            "path": path,
            "dir": rel,
            "state": "HIT",
            "count": 1,
            "present": True,
            "note": (
                "CLAUDE_CORNER.md write is the failure mode. "
                "HIT, not graduation. Never 0."
            ),
        }
    return {
        "path": path,
        "dir": rel,
        "state": "FINDER-FAILED",
        "count": None,
        "present": False,
        "note": "filename absent this beat. Absence is not CLEAR. Never 0.",
    }


def slack_search_census(count, search_space=None):
    space = list(search_space or SLACK_QUERIES)
    if count is None:
        return {
            "state": "FINDER-UNVERIFIED",
            "count": None,
            "search_space": space,
            "note": (
                "Slack seated-builder census was not an integer. "
                "FINDER-UNVERIFIED plus search space, never silent 0 (CZ-03)."
            ),
        }
    try:
        count = int(count)
    except (TypeError, ValueError):
        return {
            "state": "FINDER-FAILED",
            "count": None,
            "search_space": space,
            "note": (
                "Slack census count was not an integer. FINDER-FAILED plus "
                "search space, never silent 0."
            ),
        }
    if count == 0:
        return {
            "state": "FINDER-UNVERIFIED",
            "count": 0,
            "search_space": space,
            "note": (
                "empty Slack search is not clearance and not a seated-builder "
                "sample. Search space: %s. never silent 0 (CZ-03)."
                % ", ".join(space)
            ),
        }
    return {
        "state": "SEARCH_HIT",
        "count": count,
        "search_space": space,
        "note": (
            "keyword hits are not permission and not a builder seat. "
            "Known-present read still required."
        ),
    }


def laptop_row(paths=None):
    hits = []
    for path in paths or LAPTOP_PATHS:
        if os.path.exists(path):
            hits.append(path)
    if hits:
        return {
            "state": "FOUND",
            "count": len(hits),
            "paths": list(paths or LAPTOP_PATHS),
            "hits": hits,
            "note": "laptop lucys path present this seat. Not a --go.",
        }
    return {
        "state": "FINDER-FAILED",
        "count": None,
        "paths": list(paths or LAPTOP_PATHS),
        "hits": [],
        "note": (
            "live BrycesLaptop C:\\Users\\lucys / MUHL_GO miss this cloud VM. "
            "FINDER-FAILED, never 0, never CLEAR."
        ),
    }


def measure_from_rows(facts):
    facts = facts or {}
    return {
        "measured": True,
        "no_auth": bool(facts.get("no_auth", True)),
        "no_gate": bool(facts.get("no_gate", True)),
        "posting": str(facts.get("posting") or "OPEN"),
        "walk": list(facts.get("walk") or []),
        "slack": dict(facts.get("slack") or {}),
        "laptop": dict(facts.get("laptop") or {}),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "do_not_write": list(facts.get("do_not_write") or list(DO_NOT_WRITE)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "A11-CORNER",
        "permission": False,
        "wrote_corner": bool(facts.get("wrote_corner")),
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "CLAUDE_CORNER leftover not read. Absence was not stillness. "
                "Never 0."
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
    slack = row.get("slack") or {}
    if slack.get("state") == "CLEAR":
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "Slack-search miss treated as CLEAR is CZ-03. Refuse that path.",
        }
    if slack.get("state") not in ("FINDER-UNVERIFIED", "SEARCH_HIT", "FINDER-FAILED"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-UNVERIFIED",
            "note": (
                "Slack seated-builder sample not classified. Empty is not "
                "CLEAR. Never 0."
            ),
        }
    laptop = row.get("laptop") or {}
    if laptop.get("state") not in ("FINDER-FAILED", "FOUND"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": "laptop lucys walk not classified. Never 0.",
        }
    walk = list(row.get("walk") or [])
    if not walk:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": "filename walk empty. Search space was not opened. Never 0.",
        }
    hits = [item["path"] for item in walk if item.get("state") == "HIT"]
    if hits:
        return {
            "state": "HIT",
            "z": {
                "corner": "HIT",
                "slack": slack.get("state"),
                "laptop": laptop.get("state"),
                "permission": False,
            },
            "note": (
                "CLAUDE_CORNER.md present: "
                + ", ".join(hits)
                + ". Write is the failure mode, not graduation. Never 0."
            ),
        }
    misses = [item["path"] for item in walk if item.get("state") != "FINDER-FAILED"]
    if misses:
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "walk row not FINDER-FAILED or HIT: "
                + ", ".join(misses)
                + ". Never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "z": {
            "corner": "FINDER-FAILED",
            "slack": slack.get("state"),
            "laptop": laptop.get("state"),
            "permission": False,
        },
        "note": (
            "CLAUDE_CORNER.md filename walk FINDER-FAILED on every named "
            "dir. Absence is not CLEAR. Slack seated-builder is "
            + str(slack.get("state"))
            + ". Laptop is "
            + str(laptop.get("state"))
            + ". Soft is not permission. Do not write the corner file."
        ),
    }


def measure_root(root, slack_count=None):
    root = os.path.abspath(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = measure_from_rows(
        {
            "walk": [walk_row(root, rel) for rel in WALK_DIRS],
            "slack": slack_search_census(slack_count),
            "laptop": laptop_row(),
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
            "wrote_corner": False,
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "walk": facts["walk"],
        "slack": facts["slack"],
        "laptop": facts["laptop"],
        "permission": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    slack0 = slack_search_census(0)
    assert slack0["state"] == "FINDER-UNVERIFIED"
    assert slack0["count"] == 0
    assert "never silent 0" in slack0["note"]
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
                "walk": [{"path": CORNER_NAME, "state": "FINDER-FAILED"}],
                "slack": slack0,
                "laptop": {"state": "FINDER-FAILED"},
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    wrote = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "wrote_corner": True,
                "walk": [{"path": CORNER_NAME, "state": "FINDER-FAILED"}],
                "slack": slack0,
                "laptop": {"state": "FINDER-FAILED"},
            }
        )
    )
    assert wrote["state"] == "NOT_LANDED"
    assert wrote["z"] == "HIT"
    hit = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "walk": [
                    {
                        "path": os.path.join("muhl", "docs", CORNER_NAME),
                        "state": "HIT",
                    }
                ],
                "slack": slack0,
                "laptop": {"state": "FINDER-FAILED"},
            }
        )
    )
    assert hit["state"] == "HIT"
    assert hit["z"]["corner"] == "HIT"
    ok = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "walk": [
                    {"path": CORNER_NAME, "state": "FINDER-FAILED"},
                    {
                        "path": os.path.join("muhl", "docs", CORNER_NAME),
                        "state": "FINDER-FAILED",
                    },
                ],
                "slack": slack0,
                "laptop": {"state": "FINDER-FAILED"},
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["corner"] == "FINDER-FAILED"
    assert ok["z"]["permission"] is False
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--slack-count",
        default=None,
        help="recorded Slack seated-builder hit count; omit = UNVERIFIED",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    slack_count = args.slack_count
    if slack_count is not None:
        try:
            slack_count = int(slack_count)
        except ValueError:
            slack_count = slack_count
    row = measure_root(args.root, slack_count=slack_count)
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y corner=%s slack=%s laptop=%s permission=%s"
            % (
                ",".join(item["state"] for item in row["walk"]),
                (row.get("slack") or {}).get("state"),
                (row.get("laptop") or {}).get("state"),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
