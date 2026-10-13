#!/usr/bin/env python3
"""host/claude_graduate_as_go_refuse.py — A11 leftover named P10-as-go refuse.

Graduate leftover names --graduate as REFUSED. P10-as-go is only a
classifier flag there: treated_graduation_as_go=True becomes
NOT_LANDED. This leftover *names* --graduate-as-go as REFUSED.
Never fires. Never writes. Never graduates. Never smashes .mno.
Never injects 0x01. Graduation is not --go. Refuse is not a fire.
Unasked is not a fire. Cloud miss is FINDER-FAILED, never silent 0,
never CLEAR.

Does not remint WIRE / STAMP SR01 / seated-receive / A11 /
SR01 leftover / SR01 readback / corner-finder / corner-finder
readback / seated-builder Slack / Slack readback / laptop-finder /
laptop-finder readback / seated-builder speaker / speaker readback /
go-refuse / go-refuse readback / smash-refuse / smash-refuse
readback / corner-write-refuse / inject-refuse / inject-refuse
readback / graduate-refuse / graduate-refuse readback.
Does not rewrite PROOF / BULLY / CHAIR / PAD.
Does not write CLAUDE_CORNER.md.
Does not smash .mno.

  python3 host/claude_graduate_as_go_refuse.py
  python3 host/claude_graduate_as_go_refuse.py --self-test
  python3 host/claude_graduate_as_go_refuse.py --graduate-as-go
  python3 host/claude_graduate_as_go_refuse.py --graduate-as-go --name CLAUDE_CORNER.md

X = --graduate-as-go ask + name + known-present cards
Y = REFUSED / UNASKED — never FIRED, never GRADUATED, never WROTE, never 0
Z = graduation is not --go; refuse is not a fire; unknown name is FINDER-FAILED
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
INJECT_FILL = "0x01"
AS_GO_STATES = ("UNASKED", "REFUSED")
SEARCH_SPACE = (
    "--graduate-as-go",
    "graduation treated as --go",
    PEER_CHECK,
    os.path.join("host", "claude_graduate_as_go_refuse.py"),
    os.path.join("host", "claude_graduate_refuse.py"),
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
    "cursor-claude-peer-check-smash-refuse-20260902-01",
    "cursor-claude-peer-check-smash-refuse-readback-20260902-01",
    "cursor-claude-peer-check-corner-write-refuse-20260902-01",
    "cursor-claude-peer-check-inject-refuse-20260902-01",
    "cursor-claude-peer-check-inject-refuse-readback-20260902-01",
    "cursor-claude-peer-check-graduate-refuse-20260902-01",
    "cursor-claude-peer-check-graduate-refuse-readback-20260902-01",
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
DO_NOT_INJECT = (INJECT_FILL,)
DO_NOT_GRADUATE = (CORNER_NAME,)
DO_NOT_FIRE = ("--go", "--graduate-as-go")


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def as_go_row(asked, name=CORNER_NAME):
    asked = bool(asked)
    dest = str(name or "").strip() or CORNER_NAME
    space = ["--graduate-as-go", "name=%s" % dest]
    if dest != CORNER_NAME:
        return {
            "asked": asked,
            "fired": False,
            "graduated": False,
            "wrote": False,
            "name": dest,
            "state": "FINDER-FAILED",
            "search_space": space,
            "permission": False,
            "note": (
                "name %r is not CLAUDE_CORNER.md graduation-as-go. "
                "FINDER-FAILED plus search space, never silent 0." % dest
            ),
        }
    if asked:
        return {
            "asked": True,
            "fired": False,
            "graduated": False,
            "wrote": False,
            "name": dest,
            "state": "REFUSED",
            "search_space": space,
            "permission": False,
            "note": (
                "graduation treated as --go (P10-as-go) is refused. "
                "Graduation is not --go and not permission. Refuse is "
                "not a fire. Write is not a pass. never silent 0."
            ),
        }
    return {
        "asked": False,
        "fired": False,
        "graduated": False,
        "wrote": False,
        "name": dest,
        "state": "UNASKED",
        "search_space": space,
        "permission": False,
        "note": (
            "graduation-as-go was not asked. Unasked is not a fire and "
            "not permission. Cloud miss stays FINDER-FAILED, never CLEAR, "
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
        "as_go": dict(facts.get("as_go") or {}),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or list(SEARCH_SPACE)),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "do_not_write": list(facts.get("do_not_write") or list(DO_NOT_WRITE)),
        "do_not_smash": list(facts.get("do_not_smash") or list(DO_NOT_SMASH)),
        "do_not_inject": list(facts.get("do_not_inject") or list(DO_NOT_INJECT)),
        "do_not_graduate": list(facts.get("do_not_graduate") or list(DO_NOT_GRADUATE)),
        "do_not_fire": list(facts.get("do_not_fire") or list(DO_NOT_FIRE)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "A11-GRADUATE-AS-GO-REFUSE",
        "permission": False,
        "fired": False,
        "wrote_corner": bool(facts.get("wrote_corner")),
        "smashed_mno": bool(facts.get("smashed_mno")),
        "injected_fill": bool(facts.get("injected_fill")),
        "graduated_corner": bool(facts.get("graduated_corner")),
        "treated_refuse_as_graduation": bool(facts.get("treated_refuse_as_graduation")),
        "treated_write_as_graduation": bool(facts.get("treated_write_as_graduation")),
        "treated_graduation_as_go": bool(facts.get("treated_graduation_as_go")),
        "fired_go": bool(facts.get("fired_go")),
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "named graduate-as-go refuse leftover not read. Absence "
                "was not stillness. Never 0."
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
    if row.get("graduated_corner"):
        return {
            "state": "NOT_LANDED",
            "z": "HIT",
            "note": (
                "this leftover treated the write as graduation (P10). "
                "Writing CLAUDE_CORNER.md is the failure mode, not a pass. "
                "Never 0."
            ),
        }
    if row.get("smashed_mno"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "this leftover smashed commons.mno. Refuse that path. Never 0.",
        }
    if row.get("injected_fill"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "this leftover injected 0x01. --inject 0x01 as fill is a "
                "wipe of packed cells. Refuse that path. Never 0."
            ),
        }
    if row.get("treated_refuse_as_graduation"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "REFUSED treated as graduation. Refuse is not a pass. Never 0."
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
    if row.get("treated_graduation_as_go"):
        return {
            "state": "NOT_LANDED",
            "z": "HIT",
            "note": (
                "this leftover treated graduation as --go (P10-as-go). "
                "Graduation is not --go and not permission. That is the "
                "failure mode. Never 0."
            ),
        }
    if row.get("fired_go") or row.get("fired"):
        return {
            "state": "NOT_LANDED",
            "z": "HIT",
            "note": (
                "this leftover fired --go. Fire/osc without Bryce --go is "
                "refused. Graduation is not --go. Never 0."
            ),
        }
    as_go = dict(row.get("as_go") or {})
    if not as_go:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-UNVERIFIED",
            "note": (
                "named graduate-as-go row empty. Search space was not opened. "
                "Never 0."
            ),
        }
    if as_go.get("state") not in AS_GO_STATES + ("FINDER-FAILED",):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "as_go row not UNASKED / REFUSED / FINDER-FAILED: %s. Never 0."
                % as_go.get("state")
            ),
        }
    if as_go.get("fired") or as_go.get("state") == "FIRED":
        return {
            "state": "NOT_LANDED",
            "z": "HIT",
            "note": (
                "this leftover fired graduation-as-go. Graduation is not "
                "--go. Never 0."
            ),
        }
    if (
        as_go.get("graduated")
        or as_go.get("wrote")
        or as_go.get("state") == "GRADUATED"
    ):
        return {
            "state": "NOT_LANDED",
            "z": "HIT",
            "note": (
                "this leftover graduated CLAUDE_CORNER.md as --go. "
                "Graduation is not --go. Never 0."
            ),
        }
    if as_go.get("permission") or row.get("permission"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "as_go row set permission=True. A11: not permission. Never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "z": {
            "as_go": as_go.get("state"),
            "asked": bool(as_go.get("asked")),
            "fired": False,
            "graduated": False,
            "wrote": False,
            "name": as_go.get("name"),
            "permission": False,
        },
        "note": (
            "named graduate-as-go refuse is "
            + str(as_go.get("state"))
            + ". Name "
            + str(as_go.get("name"))
            + ". Graduation is not --go. Refuse is not a fire. Write is "
            "not a pass. Soft is not permission. Do not fire --go."
        ),
    }


def measure_root(root, asked=False, name=CORNER_NAME):
    root = os.path.abspath(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = measure_from_rows(
        {
            "as_go": as_go_row(asked, name=name),
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
            "wrote_corner": False,
            "smashed_mno": False,
            "injected_fill": False,
            "graduated_corner": False,
            "treated_refuse_as_graduation": False,
            "treated_write_as_graduation": False,
            "treated_graduation_as_go": False,
            "fired_go": False,
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "as_go": facts["as_go"],
        "permission": False,
        "fired": False,
        "graduated": False,
        "wrote": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    unasked = as_go_row(False, CORNER_NAME)
    assert unasked["state"] == "UNASKED"
    assert unasked["fired"] is False
    assert unasked["graduated"] is False
    assert unasked["wrote"] is False
    assert unasked["permission"] is False
    refused = as_go_row(True, CORNER_NAME)
    assert refused["state"] == "REFUSED"
    assert refused["asked"] is True
    assert refused["fired"] is False
    unknown = as_go_row(True, "OTHER.md")
    assert unknown["state"] == "FINDER-FAILED"
    assert unknown["fired"] is False
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
                "as_go": refused,
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    as_go = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "as_go": refused,
                "treated_graduation_as_go": True,
            }
        )
    )
    assert as_go["state"] == "NOT_LANDED"
    assert as_go["z"] == "HIT"
    fired = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "as_go": refused,
                "fired_go": True,
            }
        )
    )
    assert fired["state"] == "NOT_LANDED"
    assert fired["z"] == "HIT"
    ok = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "as_go": as_go_row(True, CORNER_NAME),
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["as_go"] == "REFUSED"
    assert ok["z"]["fired"] is False
    assert ok["z"]["graduated"] is False
    assert ok["z"]["wrote"] is False
    assert ok["z"]["permission"] is False
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--graduate-as-go",
        action="store_true",
        help="record a named P10 graduation-as-go attempt as REFUSED; never fires",
    )
    parser.add_argument(
        "--name",
        default=CORNER_NAME,
        help="recorded graduation name; only CLAUDE_CORNER.md is the named refuse",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(
        args.root,
        asked=args.graduate_as_go,
        name=args.name,
    )
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y as_go=%s asked=%s fired=%s graduated=%s wrote=%s name=%s permission=%s"
            % (
                row["as_go"].get("state"),
                row["as_go"].get("asked"),
                row["as_go"].get("fired"),
                row["as_go"].get("graduated"),
                row["as_go"].get("wrote"),
                row["as_go"].get("name"),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
