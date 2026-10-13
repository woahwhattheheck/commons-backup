#!/usr/bin/env python3
"""host/claude_inject_refuse.py — A11 leftover named --inject 0x01 refuse.

Smash leftover names smash commons.mno as REFUSED. Inject 0x01 as
fill is only on the peer-check refuse card (P7): writing 0x01 over
packed 11111111 subtracts seven ones. This leftover *names*
--inject 0x01 as REFUSED. Never writes. Never injects. Never
wipes. Never fires --go. Never writes CLAUDE_CORNER.md.
Refuse is not an inject. Fill is not permission. Unasked is
not a write. Cloud miss is FINDER-FAILED, never silent 0,
never CLEAR.

Does not remint WIRE / STAMP SR01 / seated-receive / A11 /
SR01 leftover / SR01 readback / corner-finder / corner-finder
readback / seated-builder Slack / Slack readback / laptop-finder /
laptop-finder readback / seated-builder speaker / speaker readback /
go-refuse / go-refuse readback / smash-refuse / smash-refuse
readback / corner-write-refuse.
Does not rewrite PROOF / BULLY / CHAIR / PAD.
Does not write CLAUDE_CORNER.md.
Does not smash .mno.

  python3 host/claude_inject_refuse.py
  python3 host/claude_inject_refuse.py --self-test
  python3 host/claude_inject_refuse.py --inject
  python3 host/claude_inject_refuse.py --inject --fill 0x01

X = inject ask + fill + known-present cards
Y = REFUSED / UNASKED — never INJECTED, never WIPED, never 0
Z = refuse is not an inject; inject 0x01 is not fill; unknown fill is FINDER-FAILED
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
INJECT_FILL = "0x01"
INJECT_STATES = ("UNASKED", "REFUSED")
SEARCH_SPACE = (
    "--inject",
    "inject 0x01 as fill",
    PEER_CHECK,
    os.path.join("host", "claude_inject_refuse.py"),
    os.path.join("host", "claude_smash_refuse.py"),
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
DO_NOT_INJECT = (INJECT_FILL,)


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def _norm_fill(fill):
    raw = str(fill or "").strip().lower()
    if raw in ("0x01", "1", "01"):
        return INJECT_FILL
    return raw or INJECT_FILL


def inject_row(asked, fill=INJECT_FILL):
    asked = bool(asked)
    dest = _norm_fill(fill)
    space = ["--inject", "fill=%s" % dest]
    if dest != INJECT_FILL:
        return {
            "asked": asked,
            "injected": False,
            "wiped": False,
            "wrote": False,
            "fill": dest,
            "state": "FINDER-FAILED",
            "search_space": space,
            "permission": False,
            "note": (
                "fill %r is not --inject 0x01. FINDER-FAILED plus search "
                "space, never silent 0." % dest
            ),
        }
    if asked:
        return {
            "asked": True,
            "injected": False,
            "wiped": False,
            "wrote": False,
            "fill": dest,
            "state": "REFUSED",
            "search_space": space,
            "permission": False,
            "note": (
                "--inject 0x01 as fill is refused. Law is new=old|mask. "
                "Refuse is not an inject and not permission. Inject is "
                "not --go. never silent 0."
            ),
        }
    return {
        "asked": False,
        "injected": False,
        "wiped": False,
        "wrote": False,
        "fill": dest,
        "state": "UNASKED",
        "search_space": space,
        "permission": False,
        "note": (
            "inject was not asked. Unasked is not an inject and not "
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
        "inject": dict(facts.get("inject") or {}),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or list(SEARCH_SPACE)),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "do_not_write": list(facts.get("do_not_write") or list(DO_NOT_WRITE)),
        "do_not_smash": list(facts.get("do_not_smash") or list(DO_NOT_SMASH)),
        "do_not_inject": list(facts.get("do_not_inject") or list(DO_NOT_INJECT)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "A11-INJECT-REFUSE",
        "permission": False,
        "fired": False,
        "wrote_corner": bool(facts.get("wrote_corner")),
        "smashed_mno": bool(facts.get("smashed_mno")),
        "injected_fill": bool(facts.get("injected_fill")),
        "treated_refuse_as_inject": bool(facts.get("treated_refuse_as_inject")),
        "treated_inject_as_fill": bool(facts.get("treated_inject_as_fill")),
        "treated_inject_as_go": bool(facts.get("treated_inject_as_go")),
        "fired_go": bool(facts.get("fired_go")),
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "named inject refuse leftover not read. Absence was not "
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
    if row.get("injected_fill"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "this leftover injected 0x01. --inject 0x01 as fill is a "
                "wipe of packed cells. Refuse that path. Never 0."
            ),
        }
    if row.get("treated_refuse_as_inject"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "REFUSED treated as an inject. Refuse is not a write. Never 0."
            ),
        }
    if row.get("treated_inject_as_fill"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "inject 0x01 treated as fill. Law is new=old|mask. Ones "
                "only go up. Refuse that path. Never 0."
            ),
        }
    if row.get("treated_inject_as_go"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "inject treated as --go. Inject is not --go and not "
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
    inject = dict(row.get("inject") or {})
    if not inject:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-UNVERIFIED",
            "note": (
                "named inject row empty. Search space was not opened. Never 0."
            ),
        }
    if inject.get("state") not in INJECT_STATES + ("FINDER-FAILED",):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "inject row not UNASKED / REFUSED / FINDER-FAILED: %s. Never 0."
                % inject.get("state")
            ),
        }
    if (
        inject.get("injected")
        or inject.get("wiped")
        or inject.get("wrote")
        or inject.get("state") == "INJECTED"
    ):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "this leftover injected 0x01. Inject without Bryce fill "
                "is refused. Never 0."
            ),
        }
    if inject.get("permission") or row.get("permission"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "inject row set permission=True. A11: not permission. Never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "z": {
            "inject": inject.get("state"),
            "asked": bool(inject.get("asked")),
            "injected": False,
            "wiped": False,
            "fill": inject.get("fill"),
            "permission": False,
        },
        "note": (
            "named inject refuse is "
            + str(inject.get("state"))
            + ". Fill "
            + str(inject.get("fill"))
            + ". Refuse is not an inject. Inject 0x01 is not fill. Soft is "
            "not permission. Do not write the corner file."
        ),
    }


def measure_root(root, asked=False, fill=INJECT_FILL):
    root = os.path.abspath(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = measure_from_rows(
        {
            "inject": inject_row(asked, fill=fill),
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
            "wrote_corner": False,
            "smashed_mno": False,
            "injected_fill": False,
            "treated_refuse_as_inject": False,
            "treated_inject_as_fill": False,
            "treated_inject_as_go": False,
            "fired_go": False,
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "inject": facts["inject"],
        "permission": False,
        "injected": False,
        "wiped": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    unasked = inject_row(False, INJECT_FILL)
    assert unasked["state"] == "UNASKED"
    assert unasked["injected"] is False
    assert unasked["wiped"] is False
    assert unasked["permission"] is False
    refused = inject_row(True, INJECT_FILL)
    assert refused["state"] == "REFUSED"
    assert refused["asked"] is True
    assert refused["injected"] is False
    unknown = inject_row(True, "0x02")
    assert unknown["state"] == "FINDER-FAILED"
    assert unknown["injected"] is False
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
                "inject": refused,
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    as_inject = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "inject": refused,
                "treated_refuse_as_inject": True,
            }
        )
    )
    assert as_inject["state"] == "NOT_LANDED"
    wrote = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "inject": refused,
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
                "inject": inject_row(True, INJECT_FILL),
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["inject"] == "REFUSED"
    assert ok["z"]["injected"] is False
    assert ok["z"]["wiped"] is False
    assert ok["z"]["permission"] is False
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--inject",
        action="store_true",
        help="record a named --inject 0x01 attempt as REFUSED; never writes",
    )
    parser.add_argument(
        "--fill",
        default=INJECT_FILL,
        help="recorded inject fill; only 0x01 is the named refuse",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(
        args.root,
        asked=args.inject,
        fill=args.fill,
    )
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y inject=%s asked=%s injected=%s wiped=%s fill=%s permission=%s"
            % (
                row["inject"].get("state"),
                row["inject"].get("asked"),
                row["inject"].get("injected"),
                row["inject"].get("wiped"),
                row["inject"].get("fill"),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
