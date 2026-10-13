#!/usr/bin/env python3
"""host/claude_seated_builder_slack.py — A11 leftover Slack census.

Corner finder leftover already walks CLAUDE_CORNER.md. Slack seated-builder
was still FINDER-UNVERIFIED because that finder only accepted
`--slack-count 0` (empty-search stand-in). This leftover *records* the
named Slack queries. Empty quoted search is FINDER-UNVERIFIED, never
CLEAR, never silent 0 (CZ-03). Keyword hits on SHIP receipts are
SEARCH_HIT, not a seated-builder claim and not permission.

Does not remint WIRE / STAMP SR01 / seated-receive / A11 /
SR01 leftover / SR01 readback / corner-finder / corner-finder readback.
Does not rewrite PROOF / BULLY / CHAIR / PAD.
Does not write CLAUDE_CORNER.md.

  python3 host/claude_seated_builder_slack.py
  python3 host/claude_seated_builder_slack.py --self-test
  python3 host/claude_seated_builder_slack.py --quoted-counts 0,0 --keyword-counts 3,3

X = quoted phrases + keyword restatements + known-present cards
Y = FINDER-UNVERIFIED (empty quoted) / SEARCH_HIT (keyword) — never 0
Z = empty is not CLEAR; keyword hits are not a seated-builder sample
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
KEYWORD_QUERIES = (
    "seated-builder",
    "seated_builder",
)
SEARCH_SPACE = QUOTED_QUERIES + KEYWORD_QUERIES + (
    PEER_CHECK,
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


def _parse_counts(raw, expected):
    if raw is None:
        return [None] * expected
    text = str(raw).strip()
    if not text:
        return [None] * expected
    parts = [item.strip() for item in text.split(",")]
    if len(parts) != expected:
        raise ValueError(
            "expected %s counts, got %s: %r" % (expected, len(parts), raw)
        )
    out = []
    for item in parts:
        if item == "" or item.lower() == "none":
            out.append(None)
        else:
            out.append(item)
    return out


def query_row(query, count, kind):
    space = [query]
    if count is None:
        return {
            "query": query,
            "kind": kind,
            "state": "FINDER-UNVERIFIED",
            "count": None,
            "search_space": space,
            "permission": False,
            "note": (
                "Slack %s census was not an integer. FINDER-UNVERIFIED plus "
                "search space, never silent 0 (CZ-03)." % kind
            ),
        }
    try:
        count = int(count)
    except (TypeError, ValueError):
        return {
            "query": query,
            "kind": kind,
            "state": "FINDER-FAILED",
            "count": None,
            "search_space": space,
            "permission": False,
            "note": (
                "Slack %s census count was not an integer. FINDER-FAILED plus "
                "search space, never silent 0." % kind
            ),
        }
    if count == 0:
        return {
            "query": query,
            "kind": kind,
            "state": "FINDER-UNVERIFIED",
            "count": 0,
            "search_space": space,
            "permission": False,
            "note": (
                "empty Slack %s search is not clearance and not a "
                "seated-builder sample. Search space: %s. never silent 0 "
                "(CZ-03)." % (kind, query)
            ),
        }
    if kind == "quoted":
        note = (
            "quoted-phrase hits are not permission and not a builder seat. "
            "Known-present read still required."
        )
    else:
        note = (
            "keyword hits on SHIP/ACK receipts are not a seated-builder "
            "claim and not permission. never silent 0."
        )
    return {
        "query": query,
        "kind": kind,
        "state": "SEARCH_HIT",
        "count": count,
        "search_space": space,
        "permission": False,
        "note": note,
    }


def measure_from_rows(facts):
    facts = facts or {}
    return {
        "measured": True,
        "no_auth": bool(facts.get("no_auth", True)),
        "no_gate": bool(facts.get("no_gate", True)),
        "posting": str(facts.get("posting") or "OPEN"),
        "quoted": list(facts.get("quoted") or []),
        "keyword": list(facts.get("keyword") or []),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "do_not_write": list(facts.get("do_not_write") or list(DO_NOT_WRITE)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "A11-SLACK",
        "permission": False,
        "wrote_corner": bool(facts.get("wrote_corner")),
        "treated_empty_as_clear": bool(facts.get("treated_empty_as_clear")),
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "Slack seated-builder leftover not read. Absence was not "
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
    if row.get("treated_empty_as_clear"):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "Slack-search miss treated as CLEAR is CZ-03. Refuse that path.",
        }
    quoted = list(row.get("quoted") or [])
    keyword = list(row.get("keyword") or [])
    if not quoted or not keyword:
        return {
            "state": "UNMEASURED",
            "z": "FINDER-UNVERIFIED",
            "note": (
                "quoted or keyword census empty. Search space was not opened. "
                "Never 0."
            ),
        }
    allowed = ("FINDER-UNVERIFIED", "SEARCH_HIT", "FINDER-FAILED")
    bad = [
        item["query"]
        for item in quoted + keyword
        if item.get("state") not in allowed
    ]
    if bad:
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "query row not FINDER-UNVERIFIED / SEARCH_HIT / FINDER-FAILED: "
                + ", ".join(bad)
                + ". Never 0."
            ),
        }
    if any(item.get("state") == "CLEAR" for item in quoted + keyword):
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "Slack-search miss treated as CLEAR is CZ-03. Refuse that path.",
        }
    quoted_states = [item.get("state") for item in quoted]
    keyword_states = [item.get("state") for item in keyword]
    return {
        "state": "INTEGRATED",
        "z": {
            "quoted": ",".join(quoted_states),
            "keyword": ",".join(keyword_states),
            "permission": False,
        },
        "note": (
            "quoted Slack seated-builder search is "
            + ",".join(quoted_states)
            + ". Keyword restatement search is "
            + ",".join(keyword_states)
            + ". Empty is not CLEAR. Keyword hits are not a seated-builder "
            "claim. Soft is not permission. Do not write the corner file."
        ),
    }


def measure_root(root, quoted_counts=None, keyword_counts=None):
    root = os.path.abspath(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    quoted_counts = list(quoted_counts or [None] * len(QUOTED_QUERIES))
    keyword_counts = list(keyword_counts or [None] * len(KEYWORD_QUERIES))
    facts = measure_from_rows(
        {
            "quoted": [
                query_row(query, count, "quoted")
                for query, count in zip(QUOTED_QUERIES, quoted_counts)
            ],
            "keyword": [
                query_row(query, count, "keyword")
                for query, count in zip(KEYWORD_QUERIES, keyword_counts)
            ],
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
            "wrote_corner": False,
            "treated_empty_as_clear": False,
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "quoted": facts["quoted"],
        "keyword": facts["keyword"],
        "permission": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    slack0 = query_row(QUOTED_QUERIES[0], 0, "quoted")
    assert slack0["state"] == "FINDER-UNVERIFIED"
    assert slack0["count"] == 0
    assert "never silent 0" in slack0["note"]
    keyword_hit = query_row(KEYWORD_QUERIES[0], 3, "keyword")
    assert keyword_hit["state"] == "SEARCH_HIT"
    assert keyword_hit["permission"] is False
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
                "quoted": [slack0],
                "keyword": [keyword_hit],
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    clear = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "quoted": [slack0],
                "keyword": [keyword_hit],
                "treated_empty_as_clear": True,
            }
        )
    )
    assert clear["state"] == "NOT_LANDED"
    wrote = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "quoted": [slack0],
                "keyword": [keyword_hit],
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
                    query_row(QUOTED_QUERIES[0], 0, "quoted"),
                    query_row(QUOTED_QUERIES[1], 0, "quoted"),
                ],
                "keyword": [
                    query_row(KEYWORD_QUERIES[0], 3, "keyword"),
                    query_row(KEYWORD_QUERIES[1], 3, "keyword"),
                ],
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["quoted"] == "FINDER-UNVERIFIED,FINDER-UNVERIFIED"
    assert ok["z"]["keyword"] == "SEARCH_HIT,SEARCH_HIT"
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
        "--keyword-counts",
        default=None,
        help="comma counts for seated-builder / seated_builder; omit = UNVERIFIED",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    quoted_counts = _parse_counts(args.quoted_counts, len(QUOTED_QUERIES))
    keyword_counts = _parse_counts(args.keyword_counts, len(KEYWORD_QUERIES))
    row = measure_root(
        args.root,
        quoted_counts=quoted_counts,
        keyword_counts=keyword_counts,
    )
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y quoted=%s keyword=%s permission=%s"
            % (
                ",".join(item["state"] for item in row["quoted"]),
                ",".join(item["state"] for item in row["keyword"]),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
