#!/usr/bin/env python3
"""host/claude_smash_refuse.py — A11 leftover named smash .mno refuse.

Go leftover records --go as REFUSED. Smash is only a classifier flag
there: smashed_mno=True becomes NOT_LANDED. This leftover *names*
smash commons.mno as REFUSED. Never writes. Never fires --go.
Never writes CLAUDE_CORNER.md. Refuse is not a smash. Unasked is
not a write. Cloud miss is FINDER-FAILED, never silent 0, never CLEAR.

Does not remint WIRE / STAMP SR01 / seated-receive / A11 /
SR01 leftover / SR01 readback / corner-finder / corner-finder
readback / seated-builder Slack / Slack readback / laptop-finder /
laptop-finder readback / seated-builder speaker / speaker readback /
go-refuse / go-refuse readback.
Does not rewrite PROOF / BULLY / CHAIR / PAD.
Does not write CLAUDE_CORNER.md.
Does not smash .mno.

  python3 host/claude_smash_refuse.py
  python3 host/claude_smash_refuse.py --self-test
  python3 host/claude_smash_refuse.py --smash
  python3 host/claude_smash_refuse.py --smash --target commons.mno

X = smash ask + target + known-present cards
Y = REFUSED / UNASKED — never SMASHED, never 0
Z = refuse is not a smash; smash is not --go; unknown target is FINDER-FAILED
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
SMASH_STATES = ("UNASKED", "REFUSED")
SEARCH_SPACE = (
    "--smash",
    "smash commons.mno",
    PEER_CHECK,
    os.path.join("host", "claude_smash_refuse.py"),
    os.path.join("host", "claude_go_refuse.py"),
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


def smash_row(asked, target=SMASH_TARGET):
    asked = bool(asked)
    dest = str(target or "").strip() or SMASH_TARGET
    space = ["--smash", "target=%s" % dest]
    if dest != SMASH_TARGET:
        return {
            "asked": asked,
            "smashed": False,
            "wrote": False,
            "target": dest,
            "state": "FINDER-FAILED",
            "search_space": space,
            "permission": False,
            "note": (
                "target %r is not commons.mno. FINDER-FAILED plus search "
                "space, never silent 0." % dest
            ),
        }
    if asked:
        return {
            "asked": True,
            "smashed": False,
            "wrote": False,
            "target": dest,
            "state": "REFUSED",
            "search_space": space,
            "permission": False,
            "note": (
                "smash commons.mno is refused. Refuse is not a smash and "
                "not permission. Smash is not --go. never silent 0."
            ),
        }
    return {
        "asked": False,
        "smashed": False,
        "wrote": False,
        "target": dest,
        "state": "UNASKED",
        "search_space": space,
        "permission": False,
        "note": (
            "smash was not asked. Unasked is not a smash and not "
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
        "smash": dict(facts.get("smash") or {}),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or list(SEARCH_SPACE)),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "do_not_write": list(facts.get("do_not_write") or list(DO_NOT_WRITE)),
        "do_not_smash": list(facts.get("do_not_smash") or list(DO_NOT_SMASH)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "A11-SMASH-REFUSE",
        "permission": False,
        "fired": False,
        "wrote_corner": bool(facts.get("wrote_corner")),
        "smashed_mno": bool(facts.get("smashed_mno")),
        "treated_refuse_as_smash": bool(facts.get("treated_refuse_as_smash")),
        "treated_smash_as_go": bool(facts.get("treated_smash_as_go")),
        "fired_go": bool(facts.get("fired_go")),
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "named smash refuse leftover not read. Absence was not "
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
    if row.get("smashed_mno"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "this leftover smashed commons.mno. Refuse that path. Never 0.",
        }
    if row.get("treated_refuse_as_smash"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "REFUSED treated as a smash. Refuse is not a write. Never 0."
            ),
        }
    if row.get("treated_smash_as_go"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "smash treated as --go. Smash is not --go and not "
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
    smash = dict(row.get("smash") or {})
    if not smash:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-UNVERIFIED",
            "note": (
                "named smash row empty. Search space was not opened. Never 0."
            ),
        }
    if smash.get("state") not in SMASH_STATES + ("FINDER-FAILED",):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "smash row not UNASKED / REFUSED / FINDER-FAILED: %s. Never 0."
                % smash.get("state")
            ),
        }
    if smash.get("smashed") or smash.get("wrote") or smash.get("state") == "SMASHED":
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "this leftover smashed commons.mno. Smash without Bryce "
                "write is refused. Never 0."
            ),
        }
    if smash.get("permission") or row.get("permission"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "smash row set permission=True. A11: not permission. Never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "z": {
            "smash": smash.get("state"),
            "asked": bool(smash.get("asked")),
            "smashed": False,
            "target": smash.get("target"),
            "permission": False,
        },
        "note": (
            "named smash refuse is "
            + str(smash.get("state"))
            + ". Target "
            + str(smash.get("target"))
            + ". Refuse is not a smash. Smash is not --go. Soft is not "
            "permission. Do not write the corner file."
        ),
    }


def measure_root(root, asked=False, target=SMASH_TARGET):
    root = os.path.abspath(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = measure_from_rows(
        {
            "smash": smash_row(asked, target=target),
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
            "wrote_corner": False,
            "smashed_mno": False,
            "treated_refuse_as_smash": False,
            "treated_smash_as_go": False,
            "fired_go": False,
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "smash": facts["smash"],
        "permission": False,
        "smashed": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    unasked = smash_row(False, SMASH_TARGET)
    assert unasked["state"] == "UNASKED"
    assert unasked["smashed"] is False
    assert unasked["permission"] is False
    refused = smash_row(True, SMASH_TARGET)
    assert refused["state"] == "REFUSED"
    assert refused["asked"] is True
    assert refused["smashed"] is False
    unknown = smash_row(True, "other.mno")
    assert unknown["state"] == "FINDER-FAILED"
    assert unknown["smashed"] is False
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
                "smash": refused,
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    as_smash = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "smash": refused,
                "treated_refuse_as_smash": True,
            }
        )
    )
    assert as_smash["state"] == "NOT_LANDED"
    wrote = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "smash": refused,
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
                "smash": smash_row(True, SMASH_TARGET),
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["smash"] == "REFUSED"
    assert ok["z"]["smashed"] is False
    assert ok["z"]["permission"] is False
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--smash",
        action="store_true",
        help="record a named smash commons.mno attempt as REFUSED; never writes",
    )
    parser.add_argument(
        "--target",
        default=SMASH_TARGET,
        help="recorded smash target; only commons.mno is the named refuse",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(
        args.root,
        asked=args.smash,
        target=args.target,
    )
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y smash=%s asked=%s smashed=%s target=%s permission=%s"
            % (
                row["smash"].get("state"),
                row["smash"].get("asked"),
                row["smash"].get("smashed"),
                row["smash"].get("target"),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
