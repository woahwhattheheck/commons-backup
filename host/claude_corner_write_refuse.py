#!/usr/bin/env python3
"""host/claude_corner_write_refuse.py — A11 leftover named corner-write refuse.

Smash leftover records --smash as REFUSED. Writing CLAUDE_CORNER.md
is only a classifier flag there: wrote_corner=True becomes HIT /
NOT_LANDED. Corner-finder walks absence (FINDER-FAILED), it does
not name a write attempt. This leftover *names* write of
CLAUDE_CORNER.md as REFUSED. Never writes. Never fires --go.
Never smashes .mno. P10 graduation write is refused. Unasked is
not a write. Cloud miss is FINDER-FAILED, never silent 0, never CLEAR.

Does not remint WIRE / STAMP SR01 / seated-receive / A11 /
SR01 leftover / SR01 readback / corner-finder / corner-finder
readback / seated-builder Slack / Slack readback / laptop-finder /
laptop-finder readback / seated-builder speaker / speaker readback /
go-refuse / go-refuse readback / smash-refuse / smash-refuse readback.
Does not rewrite PROOF / BULLY / CHAIR / PAD.
Does not write CLAUDE_CORNER.md.
Does not smash .mno.

  python3 host/claude_corner_write_refuse.py
  python3 host/claude_corner_write_refuse.py --self-test
  python3 host/claude_corner_write_refuse.py --corner
  python3 host/claude_corner_write_refuse.py --corner --name CLAUDE_CORNER.md

X = --corner ask + name + known-present cards
Y = REFUSED / UNASKED — never WROTE, never 0
Z = refuse is not a write; write is not graduation; unknown name is FINDER-FAILED
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
SMASH_TARGET = "commons.mno"
CORNER_STATES = ("UNASKED", "REFUSED")
SEARCH_SPACE = (
    "--corner",
    "write CLAUDE_CORNER.md",
    PEER_CHECK,
    os.path.join("host", "claude_corner_write_refuse.py"),
    os.path.join("host", "claude_smash_refuse.py"),
    os.path.join("host", "claude_corner_finder.py"),
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
    "cursor-claude-peer-check-laptop-finder-20260902-01",
    "cursor-claude-peer-check-laptop-finder-readback-20260902-01",
    "cursor-claude-peer-check-seated-builder-speaker-20260902-01",
    "cursor-claude-peer-check-seated-builder-speaker-readback-20260902-01",
    "cursor-claude-peer-check-go-refuse-20260902-01",
    "cursor-claude-peer-check-go-refuse-readback-20260902-01",
    "cursor-claude-peer-check-smash-refuse-20260902-01",
    "cursor-claude-peer-check-smash-refuse-readback-20260902-01",
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
DO_NOT_SMASH = (SMASH_TARGET,)


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def corner_row(asked, name=CORNER_NAME):
    asked = bool(asked)
    dest = str(name or "").strip() or CORNER_NAME
    space = ["--corner", "name=%s" % dest]
    if dest != CORNER_NAME:
        return {
            "asked": asked,
            "wrote": False,
            "name": dest,
            "state": "FINDER-FAILED",
            "search_space": space,
            "permission": False,
            "note": (
                "name %r is not CLAUDE_CORNER.md. FINDER-FAILED plus search "
                "space, never silent 0." % dest
            ),
        }
    if asked:
        return {
            "asked": True,
            "wrote": False,
            "name": dest,
            "state": "REFUSED",
            "search_space": space,
            "permission": False,
            "note": (
                "write CLAUDE_CORNER.md is refused. Refuse is not a write "
                "and not permission. Write is not graduation (P10). Smash "
                "is not --go. never silent 0."
            ),
        }
    return {
        "asked": False,
        "wrote": False,
        "name": dest,
        "state": "UNASKED",
        "search_space": space,
        "permission": False,
        "note": (
            "corner write was not asked. Unasked is not a write and not "
            "permission. Cloud miss stays FINDER-FAILED, never CLEAR, "
            "never silent 0."
        ),
    }


def measure_from_rows(facts):
    facts = facts or {}
    return {
        "measured": True,
        "no_auth": bool(facts.get("no_auth", True)),
        "no_gate": bool(facts.get("no_gate", True)),
        "posting": str(facts.get("posting") or "OPEN"),
        "corner": dict(facts.get("corner") or {}),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or list(SEARCH_SPACE)),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "do_not_write": list(facts.get("do_not_write") or list(DO_NOT_WRITE)),
        "do_not_smash": list(facts.get("do_not_smash") or list(DO_NOT_SMASH)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "A11-CORNER-WRITE-REFUSE",
        "permission": False,
        "fired": False,
        "wrote_corner": bool(facts.get("wrote_corner")),
        "smashed_mno": bool(facts.get("smashed_mno")),
        "treated_refuse_as_write": bool(facts.get("treated_refuse_as_write")),
        "treated_write_as_graduation": bool(facts.get("treated_write_as_graduation")),
        "treated_corner_as_go": bool(facts.get("treated_corner_as_go")),
        "fired_go": bool(facts.get("fired_go")),
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "named corner-write refuse leftover not read. Absence was "
                "not stillness. Never 0."
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
    if row.get("smashed_mno"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "this leftover smashed commons.mno. Refuse that path. Never 0.",
        }
    if row.get("treated_refuse_as_write"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "REFUSED treated as a write. Refuse is not a write. Never 0."
            ),
        }
    if row.get("treated_write_as_graduation"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "write treated as graduation (P10). Writing CLAUDE_CORNER.md "
                "is the failure mode, not a pass. Never 0."
            ),
        }
    if row.get("treated_corner_as_go"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "corner write treated as --go. Write is not --go and not "
                "permission. Refuse that path. Never 0."
            ),
        }
    if row.get("fired_go") or row.get("fired"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "this leftover fired --go. Fire/osc without Bryce --go is "
                "refused. Never 0."
            ),
        }
    corner = dict(row.get("corner") or {})
    if not corner:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-UNVERIFIED",
            "note": (
                "named corner-write row empty. Search space was not opened. "
                "Never 0."
            ),
        }
    if corner.get("state") not in CORNER_STATES + ("FINDER-FAILED",):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "corner row not UNASKED / REFUSED / FINDER-FAILED: %s. Never 0."
                % corner.get("state")
            ),
        }
    if corner.get("wrote") or corner.get("state") == "WROTE":
        return {
            "state": "NOT_LANDED",
            "z": "HIT",
            "note": (
                "this leftover wrote CLAUDE_CORNER.md. Write without Bryce "
                "ask is refused. Never 0."
            ),
        }
    if corner.get("permission") or row.get("permission"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "corner row set permission=True. A11: not permission. Never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "z": {
            "corner": corner.get("state"),
            "asked": bool(corner.get("asked")),
            "wrote": False,
            "name": corner.get("name"),
            "permission": False,
        },
        "note": (
            "named corner-write refuse is "
            + str(corner.get("state"))
            + ". Name "
            + str(corner.get("name"))
            + ". Refuse is not a write. Write is not graduation. Smash is "
            "not --go. Soft is not permission. Do not write the corner file."
        ),
    }


def measure_root(root, asked=False, name=CORNER_NAME):
    root = os.path.abspath(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = measure_from_rows(
        {
            "corner": corner_row(asked, name=name),
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
            "wrote_corner": False,
            "smashed_mno": False,
            "treated_refuse_as_write": False,
            "treated_write_as_graduation": False,
            "treated_corner_as_go": False,
            "fired_go": False,
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "corner": facts["corner"],
        "permission": False,
        "wrote": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    unasked = corner_row(False, CORNER_NAME)
    assert unasked["state"] == "UNASKED"
    assert unasked["wrote"] is False
    assert unasked["permission"] is False
    refused = corner_row(True, CORNER_NAME)
    assert refused["state"] == "REFUSED"
    assert refused["asked"] is True
    assert refused["wrote"] is False
    unknown = corner_row(True, "OTHER.md")
    assert unknown["state"] == "FINDER-FAILED"
    assert unknown["wrote"] is False
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
                "corner": refused,
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    as_write = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "corner": refused,
                "treated_refuse_as_write": True,
            }
        )
    )
    assert as_write["state"] == "NOT_LANDED"
    wrote = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "corner": refused,
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
                "corner": corner_row(True, CORNER_NAME),
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["corner"] == "REFUSED"
    assert ok["z"]["wrote"] is False
    assert ok["z"]["permission"] is False
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--corner",
        action="store_true",
        help="record a named CLAUDE_CORNER.md write attempt as REFUSED; never writes",
    )
    parser.add_argument(
        "--name",
        default=CORNER_NAME,
        help="recorded write name; only CLAUDE_CORNER.md is the named refuse",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(
        args.root,
        asked=args.corner,
        name=args.name,
    )
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y corner=%s asked=%s wrote=%s name=%s permission=%s"
            % (
                row["corner"].get("state"),
                row["corner"].get("asked"),
                row["corner"].get("wrote"),
                row["corner"].get("name"),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
