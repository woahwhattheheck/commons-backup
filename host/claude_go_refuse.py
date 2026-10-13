#!/usr/bin/env python3
"""host/claude_go_refuse.py — A11 leftover named --go refuse.

Laptop leftover walks companions and says FOUND is not --go.
Speaker leftover splits restatement vs claim. Neither records a
named --go attempt. This leftover *names* --go as REFUSED.
Never fires. Never writes CLAUDE_CORNER.md. FOUND is not --go.
HIT is not graduation. Unasked is not a fire. Cloud miss is
FINDER-FAILED, never silent 0, never CLEAR.

Does not remint WIRE / STAMP SR01 / seated-receive / A11 /
SR01 leftover / SR01 readback / corner-finder / corner-finder
readback / seated-builder Slack / Slack readback / laptop-finder /
laptop-finder readback / seated-builder speaker / speaker readback.
Does not rewrite PROOF / BULLY / CHAIR / PAD.
Does not write CLAUDE_CORNER.md.
Does not smash .mno.

  python3 host/claude_go_refuse.py
  python3 host/claude_go_refuse.py --self-test
  python3 host/claude_go_refuse.py --go
  python3 host/claude_go_refuse.py --go --laptop-state FOUND

X = --go ask + laptop state + known-present cards
Y = REFUSED / UNASKED — never FIRED, never 0
Z = FOUND is not --go; HIT is not graduation; refuse is not a fire
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
LAPTOP_STATES = ("FINDER-FAILED", "FOUND", "HIT")
GO_STATES = ("UNASKED", "REFUSED")
SEARCH_SPACE = (
    "--go",
    "FOUND is not --go",
    PEER_CHECK,
    os.path.join("host", "claude_go_refuse.py"),
    os.path.join("host", "claude_laptop_finder.py"),
    os.path.join("host", "claude_seated_builder_speaker.py"),
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
DO_NOT_SMASH = ("commons.mno",)


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def go_row(asked, laptop_state="FINDER-FAILED"):
    asked = bool(asked)
    laptop = str(laptop_state or "").strip() or "FINDER-FAILED"
    space = ["--go", "laptop=%s" % laptop]
    if laptop not in LAPTOP_STATES:
        return {
            "asked": asked,
            "fired": False,
            "laptop": laptop,
            "state": "FINDER-FAILED",
            "search_space": space,
            "permission": False,
            "note": (
                "laptop state %r is not FINDER-FAILED / FOUND / HIT. "
                "FINDER-FAILED plus search space, never silent 0." % laptop
            ),
        }
    if asked:
        return {
            "asked": True,
            "fired": False,
            "laptop": laptop,
            "state": "REFUSED",
            "search_space": space,
            "permission": False,
            "note": (
                "--go is refused. FOUND is not --go. HIT is not graduation. "
                "Refuse is not a fire and not permission. never silent 0."
            ),
        }
    return {
        "asked": False,
        "fired": False,
        "laptop": laptop,
        "state": "UNASKED",
        "search_space": space,
        "permission": False,
        "note": (
            "--go was not asked. Unasked is not a fire and not permission. "
            "Cloud miss stays FINDER-FAILED, never CLEAR, never silent 0."
        ),
    }


def measure_from_rows(facts):
    facts = facts or {}
    return {
        "measured": True,
        "no_auth": bool(facts.get("no_auth", True)),
        "no_gate": bool(facts.get("no_gate", True)),
        "posting": str(facts.get("posting") or "OPEN"),
        "go": dict(facts.get("go") or {}),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or list(SEARCH_SPACE)),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "do_not_write": list(facts.get("do_not_write") or list(DO_NOT_WRITE)),
        "do_not_smash": list(facts.get("do_not_smash") or list(DO_NOT_SMASH)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "A11-GO-REFUSE",
        "permission": False,
        "fired": False,
        "wrote_corner": bool(facts.get("wrote_corner")),
        "smashed_mno": bool(facts.get("smashed_mno")),
        "treated_found_as_go": bool(facts.get("treated_found_as_go")),
        "treated_hit_as_go": bool(facts.get("treated_hit_as_go")),
        "treated_refuse_as_fire": bool(facts.get("treated_refuse_as_fire")),
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "named --go refuse leftover not read. Absence was not "
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
    if row.get("treated_found_as_go"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "FOUND treated as --go. Laptop leftover: FOUND is not --go "
                "and not permission. Refuse that path. Never 0."
            ),
        }
    if row.get("treated_hit_as_go"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "corner HIT treated as --go / graduation. P10: write corner "
                "is the failure mode. Refuse that path. Never 0."
            ),
        }
    if row.get("treated_refuse_as_fire"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "REFUSED treated as a fire. Refuse is not actuation. Never 0."
            ),
        }
    go = dict(row.get("go") or {})
    if not go:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-UNVERIFIED",
            "note": (
                "named --go row empty. Search space was not opened. Never 0."
            ),
        }
    if go.get("state") not in GO_STATES + ("FINDER-FAILED",):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "go row not UNASKED / REFUSED / FINDER-FAILED: %s. Never 0."
                % go.get("state")
            ),
        }
    if go.get("fired") or row.get("fired") or go.get("state") == "FIRED":
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "this leftover fired --go. Fire/osc without Bryce --go is "
                "refused. Never 0."
            ),
        }
    if go.get("permission") or row.get("permission"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "go row set permission=True. A11: not permission. Never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "z": {
            "go": go.get("state"),
            "asked": bool(go.get("asked")),
            "fired": False,
            "laptop": go.get("laptop"),
            "permission": False,
        },
        "note": (
            "named --go refuse is "
            + str(go.get("state"))
            + ". Laptop "
            + str(go.get("laptop"))
            + ". FOUND is not --go. HIT is not graduation. Refuse is not a "
            "fire. Soft is not permission. Do not write the corner file."
        ),
    }


def measure_root(root, asked=False, laptop_state="FINDER-FAILED"):
    root = os.path.abspath(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = measure_from_rows(
        {
            "go": go_row(asked, laptop_state=laptop_state),
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
            "wrote_corner": False,
            "smashed_mno": False,
            "treated_found_as_go": False,
            "treated_hit_as_go": False,
            "treated_refuse_as_fire": False,
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "go": facts["go"],
        "permission": False,
        "fired": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    unasked = go_row(False, "FINDER-FAILED")
    assert unasked["state"] == "UNASKED"
    assert unasked["fired"] is False
    assert unasked["permission"] is False
    refused = go_row(True, "FINDER-FAILED")
    assert refused["state"] == "REFUSED"
    assert refused["asked"] is True
    assert refused["fired"] is False
    found = go_row(True, "FOUND")
    assert found["state"] == "REFUSED"
    assert found["laptop"] == "FOUND"
    assert found["permission"] is False
    hit = go_row(True, "HIT")
    assert hit["state"] == "REFUSED"
    assert "not graduation" in hit["note"]
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
                "go": refused,
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    as_go = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "go": found,
                "treated_found_as_go": True,
            }
        )
    )
    assert as_go["state"] == "NOT_LANDED"
    wrote = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "go": refused,
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
                "go": go_row(True, "FINDER-FAILED"),
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["go"] == "REFUSED"
    assert ok["z"]["fired"] is False
    assert ok["z"]["permission"] is False
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--go",
        action="store_true",
        help="record a named --go attempt as REFUSED; never fires",
    )
    parser.add_argument(
        "--laptop-state",
        default="FINDER-FAILED",
        choices=LAPTOP_STATES,
        help="recorded laptop leftover state; FOUND/HIT still refuse --go",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(
        args.root,
        asked=args.go,
        laptop_state=args.laptop_state,
    )
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y go=%s asked=%s fired=%s laptop=%s permission=%s"
            % (
                row["go"].get("state"),
                row["go"].get("asked"),
                row["go"].get("fired"),
                row["go"].get("laptop"),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
