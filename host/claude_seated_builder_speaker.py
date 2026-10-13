#!/usr/bin/env python3
"""host/claude_seated_builder_speaker.py — A11 leftover speaker vs restatement.

The Slack seated-builder census leftover records counts. Live quoted
hits on this beat are SHIP/MATCH restatements of the search phrase,
not a seated-builder speaker. This leftover *names* that split.
Empty quoted search is FINDER-UNVERIFIED, never CLEAR, never silent 0
(CZ-03). A CLAIM_HIT is still not permission (A11). Restatement
treated as a builder seat is refused.

Does not remint WIRE / STAMP SR01 / seated-receive / A11 /
SR01 leftover / SR01 readback / corner-finder / corner-finder readback /
seated-builder slack / seated-builder slack readback.
Does not rewrite PROOF / BULLY / CHAIR / PAD.
Does not write CLAUDE_CORNER.md.

  python3 host/claude_seated_builder_speaker.py
  python3 host/claude_seated_builder_speaker.py --self-test
  python3 host/claude_seated_builder_speaker.py --quoted-counts 2,2 --quoted-roles restatement,restatement

X = quoted phrases + roles + known-present cards
Y = RESTATEMENT_HIT / CLAIM_HIT / FINDER-UNVERIFIED — never 0
Z = empty is not CLEAR; restatement is not a seated-builder speaker
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
QUOTED_QUERIES = (
    '"I am seated builder"',
    '"seated builder"',
)
ROLES = ("restatement", "claim")
SEARCH_SPACE = QUOTED_QUERIES + (
    PEER_CHECK,
    os.path.join("host", "claude_seated_builder_speaker.py"),
    os.path.join("host", "claude_seated_builder_slack.py"),
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


def _parse_csv(raw, expected):
    if raw is None:
        return [None] * expected
    text = str(raw).strip()
    if not text:
        return [None] * expected
    parts = [item.strip() for item in text.split(",")]
    if len(parts) != expected:
        raise ValueError(
            "expected %s values, got %s: %r" % (expected, len(parts), raw)
        )
    out = []
    for item in parts:
        if item == "" or item.lower() == "none":
            out.append(None)
        else:
            out.append(item)
    return out


def query_row(query, count, role):
    space = [query]
    role_text = None if role is None else str(role).strip().lower()
    if count is None:
        return {
            "query": query,
            "role": role_text,
            "state": "FINDER-UNVERIFIED",
            "count": None,
            "search_space": space,
            "permission": False,
            "note": (
                "quoted speaker/restatement census was not an integer. "
                "FINDER-UNVERIFIED plus search space, never silent 0 (CZ-03)."
            ),
        }
    try:
        count = int(count)
    except (TypeError, ValueError):
        return {
            "query": query,
            "role": role_text,
            "state": "FINDER-FAILED",
            "count": None,
            "search_space": space,
            "permission": False,
            "note": (
                "quoted speaker/restatement count was not an integer. "
                "FINDER-FAILED plus search space, never silent 0."
            ),
        }
    if count == 0:
        return {
            "query": query,
            "role": role_text,
            "state": "FINDER-UNVERIFIED",
            "count": 0,
            "search_space": space,
            "permission": False,
            "note": (
                "empty quoted search is not clearance and not a "
                "seated-builder speaker. Search space: %s. never silent 0 "
                "(CZ-03)." % query
            ),
        }
    if role_text is None:
        return {
            "query": query,
            "role": None,
            "state": "FINDER-UNVERIFIED",
            "count": count,
            "search_space": space,
            "permission": False,
            "note": (
                "quoted hits exist but the speaker/restatement role was not "
                "named. SEARCH_HIT is not a seated-builder speaker. "
                "FINDER-UNVERIFIED, never silent 0."
            ),
        }
    if role_text not in ROLES:
        return {
            "query": query,
            "role": role_text,
            "state": "FINDER-FAILED",
            "count": count,
            "search_space": space,
            "permission": False,
            "note": (
                "quoted role %r is not restatement or claim. FINDER-FAILED "
                "plus search space, never silent 0." % role_text
            ),
        }
    if role_text == "restatement":
        return {
            "query": query,
            "role": role_text,
            "state": "RESTATEMENT_HIT",
            "count": count,
            "search_space": space,
            "permission": False,
            "note": (
                "quoted hits are SHIP/MATCH/ACK/RECEIPT restatements, not a "
                "seated-builder speaker and not permission. never silent 0."
            ),
        }
    return {
        "query": query,
        "role": role_text,
        "state": "CLAIM_HIT",
        "count": count,
        "search_space": space,
        "permission": False,
        "note": (
            "quoted claim hits are not permission and not a builder seat. "
            "A11: soft seat is not Plug RECEIVE-only permission. never silent 0."
        ),
    }


def measure_from_rows(facts):
    facts = facts or {}
    return {
        "measured": True,
        "no_auth": bool(facts.get("no_auth", True)),
        "no_gate": bool(facts.get("no_gate", True)),
        "posting": str(facts.get("posting") or "OPEN"),
        "quoted": list(facts.get("quoted") or []),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "do_not_write": list(facts.get("do_not_write") or list(DO_NOT_WRITE)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "A11-SPEAKER",
        "permission": False,
        "wrote_corner": bool(facts.get("wrote_corner")),
        "treated_empty_as_clear": bool(facts.get("treated_empty_as_clear")),
        "treated_restatement_as_seat": bool(facts.get("treated_restatement_as_seat")),
        "treated_claim_as_permission": bool(facts.get("treated_claim_as_permission")),
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "Slack seated-builder speaker leftover not read. Absence was "
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
    if row.get("treated_empty_as_clear"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "Slack-search miss treated as CLEAR is CZ-03. Refuse that path.",
        }
    if row.get("treated_restatement_as_seat"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "SHIP/MATCH restatement treated as a seated-builder speaker. "
                "Refuse that path. Never 0."
            ),
        }
    if row.get("treated_claim_as_permission"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "quoted claim treated as permission. A11: soft seat is not "
                "Plug RECEIVE-only permission. Never 0."
            ),
        }
    quoted = list(row.get("quoted") or [])
    if not quoted:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-UNVERIFIED",
            "note": (
                "quoted speaker/restatement census empty. Search space was "
                "not opened. Never 0."
            ),
        }
    allowed = (
        "FINDER-UNVERIFIED",
        "RESTATEMENT_HIT",
        "CLAIM_HIT",
        "FINDER-FAILED",
    )
    bad = [
        item["query"]
        for item in quoted
        if item.get("state") not in allowed
    ]
    if bad:
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "query row not FINDER-UNVERIFIED / RESTATEMENT_HIT / "
                "CLAIM_HIT / FINDER-FAILED: "
                + ", ".join(bad)
                + ". Never 0."
            ),
        }
    if any(item.get("state") == "CLEAR" for item in quoted):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "Slack-search miss treated as CLEAR is CZ-03. Refuse that path.",
        }
    if any(item.get("permission") for item in quoted):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "quoted row set permission=True. A11: not permission. Never 0."
            ),
        }
    quoted_states = [item.get("state") for item in quoted]
    return {
        "state": "INTEGRATED",
        "z": {
            "quoted": ",".join(quoted_states),
            "permission": False,
        },
        "note": (
            "quoted Slack seated-builder speaker/restatement search is "
            + ",".join(quoted_states)
            + ". Empty is not CLEAR. Restatement is not a seated-builder "
            "speaker. Claim is not permission. Soft is not permission. "
            "Do not write the corner file."
        ),
    }


def measure_root(root, quoted_counts=None, quoted_roles=None):
    root = os.path.abspath(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    quoted_counts = list(quoted_counts or [None] * len(QUOTED_QUERIES))
    quoted_roles = list(quoted_roles or [None] * len(QUOTED_QUERIES))
    facts = measure_from_rows(
        {
            "quoted": [
                query_row(query, count, role)
                for query, count, role in zip(
                    QUOTED_QUERIES, quoted_counts, quoted_roles
                )
            ],
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
            "wrote_corner": False,
            "treated_empty_as_clear": False,
            "treated_restatement_as_seat": False,
            "treated_claim_as_permission": False,
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "quoted": facts["quoted"],
        "permission": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    slack0 = query_row(QUOTED_QUERIES[0], 0, "restatement")
    assert slack0["state"] == "FINDER-UNVERIFIED"
    assert slack0["count"] == 0
    assert "never silent 0" in slack0["note"]
    restatement = query_row(QUOTED_QUERIES[0], 2, "restatement")
    assert restatement["state"] == "RESTATEMENT_HIT"
    assert restatement["permission"] is False
    claim = query_row(QUOTED_QUERIES[1], 1, "claim")
    assert claim["state"] == "CLAIM_HIT"
    assert claim["permission"] is False
    unnamed = query_row(QUOTED_QUERIES[0], 2, None)
    assert unnamed["state"] == "FINDER-UNVERIFIED"
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
                "quoted": [restatement, restatement],
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    as_seat = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "quoted": [restatement, restatement],
                "treated_restatement_as_seat": True,
            }
        )
    )
    assert as_seat["state"] == "NOT_LANDED"
    as_perm = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "quoted": [claim, claim],
                "treated_claim_as_permission": True,
            }
        )
    )
    assert as_perm["state"] == "NOT_LANDED"
    wrote = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "quoted": [restatement, restatement],
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
                "quoted": [
                    query_row(QUOTED_QUERIES[0], 2, "restatement"),
                    query_row(QUOTED_QUERIES[1], 2, "restatement"),
                ],
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["quoted"] == "RESTATEMENT_HIT,RESTATEMENT_HIT"
    assert ok["z"]["permission"] is False
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--quoted-counts",
        default=None,
        help="comma counts for the two quoted phrases; omit = UNVERIFIED",
    )
    parser.add_argument(
        "--quoted-roles",
        default=None,
        help="comma roles restatement|claim for the two quoted phrases",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    quoted_counts = _parse_csv(args.quoted_counts, len(QUOTED_QUERIES))
    quoted_roles = _parse_csv(args.quoted_roles, len(QUOTED_QUERIES))
    row = measure_root(
        args.root,
        quoted_counts=quoted_counts,
        quoted_roles=quoted_roles,
    )
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y quoted=%s permission=%s"
            % (
                ",".join(item["state"] for item in row["quoted"]),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
