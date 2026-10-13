#!/usr/bin/env python3
"""host/claude_sr01_soft_dumps.py — HIT-SR01 phrase diverge leftover.

A11 indexes Plug RECEIVE-only vs git-soft "may edit/build/ship".
This leftover *measures* the named dumps. It does not remint
WIRE / STAMP SR01 / seated-receive / the A11 SOURCE_ID pin.
It does not rewrite PROOF / BULLY / CHAIR / PAD.

Soft "may edit, build, ship" is a law-violation vs Plug RECEIVE-only
/ seated_claude=NO, not permission. Not a posting gate.

  python3 host/claude_sr01_soft_dumps.py
  python3 host/claude_sr01_soft_dumps.py --root .
  python3 host/claude_sr01_soft_dumps.py --self-test

X = catalog soft dumps + RECEIVE baseline + known-present cards
Y = phrase hits + pair diverge, or FINDER-FAILED
Z = missing file / missing phrase / same-blob pair / failed calibration
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
HEAD_CARD = os.path.join("ground", "HEAD.md")
PEER_CHECK = os.path.join("ground", "CLAUDE_PEER_CHECK.md")
SOFT_DUMPS = (
    os.path.join("muhl", "docs", "CLAUDE_PROOF_PACKET.md"),
    os.path.join("muhl", "docs", "BULLY_CLAUDE.txt"),
    os.path.join("muhl", "docs", "CHAIR.md"),
    os.path.join("muhl", "docs", "FABLE_PLAYER_PAD.txt"),
)
RECEIVE_BASELINE = (
    os.path.join("evidence", "bully_sessions", "CLAUDE_PROOF_PACKET.md"),
    os.path.join("evidence", "bully_sessions", "BULLY_CLAUDE.txt"),
)
PAIRS = (
    (
        os.path.join("muhl", "docs", "CLAUDE_PROOF_PACKET.md"),
        os.path.join("evidence", "bully_sessions", "CLAUDE_PROOF_PACKET.md"),
    ),
    (
        os.path.join("muhl", "docs", "BULLY_CLAUDE.txt"),
        os.path.join("evidence", "bully_sessions", "BULLY_CLAUDE.txt"),
    ),
)
SOFT_NEEDLE = "may edit, build, ship"
RECEIVE_NEEDLES = (
    "seated_claude",
    "receives only",
    "writes nothing",
    "not a builder",
)
SEARCH_SPACE = SOFT_DUMPS + RECEIVE_BASELINE + (
    PEER_CHECK,
    os.path.join("host", "claude_sr01_soft_dumps.py"),
)
CALIBRATION = (HEAD_CARD, PEER_CHECK)
DO_NOT_REMINT = (
    "wire-claude-peer-check-20260902-01",
    "stamp-claude-failure-unique-seated-receive-20260902-01",
    "cursor-claude-peer-check-seated-receive-20260902-01",
    "cursor-ship-claude-peer-check-sr01-20260902-01",
)
DO_NOT_REWRITE = SOFT_DUMPS + RECEIVE_BASELINE
# Live dumps keep their soft/RECEIVE needles. Current HEAD blobs include
# additive live-cash / Latch Pad KEEP tails. Stamp receipts not reminted.
KNOWN_BLOBS = {
    os.path.join("muhl", "docs", "CLAUDE_PROOF_PACKET.md"): "357213256815377675c0fb638019bd63ac38b439",
    os.path.join("muhl", "docs", "BULLY_CLAUDE.txt"): "a6adc3088fa94f71e3930eac4441cef5313315f8",
    os.path.join("muhl", "docs", "CHAIR.md"): "66d5c2af91f516445d14da4925a6e08376010292",
    os.path.join("muhl", "docs", "FABLE_PLAYER_PAD.txt"): "cdaf8484ac1184bccf3330c1cc577f69edede7c5",
    os.path.join("evidence", "bully_sessions", "CLAUDE_PROOF_PACKET.md"): "56954b0adef0b1c0aff174e31c3d94d10203c0bb",
    os.path.join("evidence", "bully_sessions", "BULLY_CLAUDE.txt"): "f637231f453edc7a77b86707a482edeb8632ae39",
}


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def has_soft_phrase(text):
    return SOFT_NEEDLE in str(text or "").lower()


def has_receive_phrase(text):
    blob = str(text or "").lower()
    return any(needle in blob for needle in RECEIVE_NEEDLES)


def file_row(root, rel, kind):
    text = _read(root, rel)
    present = _exists(root, rel)
    if not present:
        return {
            "path": rel,
            "kind": kind,
            "state": "FINDER-FAILED",
            "count": None,
            "present": False,
            "soft_phrase": False,
            "receive_phrase": False,
            "note": "file missing. Never 0.",
        }
    soft = has_soft_phrase(text)
    receive = has_receive_phrase(text)
    if kind == "soft":
        ok = soft
        miss = "soft phrase missing"
    else:
        ok = receive
        miss = "RECEIVE phrase missing"
    return {
        "path": rel,
        "kind": kind,
        "state": "FOUND" if ok else "FINDER-FAILED",
        "count": None if not ok else 1,
        "present": True,
        "soft_phrase": soft,
        "receive_phrase": receive,
        "note": "" if ok else (miss + ". Never 0."),
    }


def pair_row(root, soft_rel, hard_rel):
    if not (_exists(root, soft_rel) and _exists(root, hard_rel)):
        missing = [rel for rel in (soft_rel, hard_rel) if not _exists(root, rel)]
        return {
            "soft": soft_rel,
            "hard": hard_rel,
            "state": "FINDER-FAILED",
            "count": None,
            "diverge": False,
            "note": "pair path(s) missing: " + ", ".join(missing) + ". Never 0.",
        }
    soft_text = _read(root, soft_rel)
    hard_text = _read(root, hard_rel)
    diverge = soft_text != hard_text
    return {
        "soft": soft_rel,
        "hard": hard_rel,
        "state": "DIVERGE" if diverge else "SAME",
        "count": None if not diverge else 1,
        "diverge": diverge,
        "note": (
            "soft dump and RECEIVE baseline still differ. Do not silent-merge."
            if diverge
            else "pair is byte-identical — HIT-SR01 diverge lost. Never 0."
        ),
    }


def measure_from_rows(facts):
    facts = facts or {}
    return {
        "measured": True,
        "no_auth": bool(facts.get("no_auth", True)),
        "no_gate": bool(facts.get("no_gate", True)),
        "posting": str(facts.get("posting") or "OPEN"),
        "soft_dumps": list(facts.get("soft_dumps") or []),
        "baselines": list(facts.get("baselines") or []),
        "pairs": list(facts.get("pairs") or []),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "do_not_remint": list(facts.get("do_not_remint") or list(DO_NOT_REMINT)),
        "do_not_rewrite": list(facts.get("do_not_rewrite") or list(DO_NOT_REWRITE)),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "hit": "HIT-SR01",
        "permission": False,
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "z": "FINDER-FAILED",
            "note": (
                "SR01 soft-dump leftover not read. Absence was not stillness. "
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
                + ". Search-zero testing is instrument failure, not absence proof. Never 0."
            ),
        }
    if not row.get("no_auth") or not row.get("no_gate") or row.get("posting") != "OPEN":
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": "catalog closed the door. Discard that path. Never 0.",
        }
    soft_miss = [
        item["path"]
        for item in (row.get("soft_dumps") or [])
        if item.get("state") != "FOUND"
    ]
    if soft_miss:
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "soft dump miss: "
                + ", ".join(soft_miss)
                + ". Keep looking. Never 0."
            ),
        }
    base_miss = [
        item["path"]
        for item in (row.get("baselines") or [])
        if item.get("state") != "FOUND"
    ]
    if base_miss:
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "RECEIVE baseline miss: "
                + ", ".join(base_miss)
                + ". Keep looking. Never 0."
            ),
        }
    same = [
        "%s vs %s" % (item.get("soft"), item.get("hard"))
        for item in (row.get("pairs") or [])
        if item.get("state") != "DIVERGE"
    ]
    if same:
        return {
            "state": "NOT_LANDED",
            "z": "FINDER-FAILED",
            "note": (
                "HIT-SR01 pair no longer diverges: "
                + ", ".join(same)
                + ". Do not silent-merge. Never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "z": {
            "soft_phrase": "FOUND",
            "receive_baseline": "FOUND",
            "pairs": "DIVERGE",
            "permission": False,
        },
        "note": (
            "HIT-SR01 stands: soft dumps still say may-edit; RECEIVE baseline "
            "still says seated_claude=NO / writes nothing. Soft is not "
            "permission. Posting stays OPEN. Do not rewrite those dumps."
        ),
    }


def measure_root(root):
    root = os.path.abspath(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = measure_from_rows(
        {
            "soft_dumps": [file_row(root, rel, "soft") for rel in SOFT_DUMPS],
            "baselines": [file_row(root, rel, "receive") for rel in RECEIVE_BASELINE],
            "pairs": [pair_row(root, soft, hard) for soft, hard in PAIRS],
            "calibration_ok": calibration_hits == list(CALIBRATION),
            "calibration_hits": calibration_hits,
            "no_auth": True,
            "no_gate": True,
            "posting": "OPEN",
        }
    )
    verdict = classify(facts)
    facts["state"] = verdict["state"]
    facts["z"] = verdict["z"]
    facts["note"] = verdict["note"]
    facts["x"] = facts["search_space"]
    facts["y"] = {
        "soft_dumps": facts["soft_dumps"],
        "baselines": facts["baselines"],
        "pairs": facts["pairs"],
        "permission": False,
    }
    return facts


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == "FINDER-FAILED"
    assert "0" not in str(empty.get("count"))
    bad_cal = classify(
        measure_from_rows({"calibration_ok": False, "calibration_hits": []})
    )
    assert bad_cal["state"] == "UNMEASURED"
    assert bad_cal["z"] == "FINDER-FAILED"
    closed = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "no_auth": False,
            }
        )
    )
    assert closed["state"] == "NOT_LANDED"
    missing_soft = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "soft_dumps": [
                    {
                        "path": "missing.md",
                        "state": "FINDER-FAILED",
                        "count": None,
                    }
                ],
            }
        )
    )
    assert missing_soft["state"] == "NOT_LANDED"
    assert missing_soft["z"] == "FINDER-FAILED"
    assert "missing.md" in missing_soft["note"]
    same_pair = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "soft_dumps": [{"path": "s.md", "state": "FOUND"}],
                "baselines": [{"path": "h.md", "state": "FOUND"}],
                "pairs": [
                    {
                        "soft": "s.md",
                        "hard": "h.md",
                        "state": "SAME",
                        "diverge": False,
                    }
                ],
            }
        )
    )
    assert same_pair["state"] == "NOT_LANDED"
    assert "diverge" in same_pair["note"].lower()
    ok = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "calibration_hits": list(CALIBRATION),
                "soft_dumps": [{"path": "s.md", "state": "FOUND"}],
                "baselines": [{"path": "h.md", "state": "FOUND"}],
                "pairs": [
                    {
                        "soft": "s.md",
                        "hard": "h.md",
                        "state": "DIVERGE",
                        "diverge": True,
                    }
                ],
            }
        )
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["z"]["permission"] is False
    assert has_soft_phrase("Claude peers may edit, build, ship, merge, and deploy.")
    assert has_receive_phrase("seated_claude = NO. OPUS RECEIVES ONLY.")
    assert not has_soft_phrase("Claude RECEIVES. Claude writes nothing.")
    assert not has_receive_phrase("Fable peers may edit, build, ship, merge.")
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(args.root)
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print(row["state"])
        print("X", ", ".join(row["x"]))
        print(
            "Y soft=%s baseline=%s pairs=%s permission=%s"
            % (
                ",".join(item["state"] for item in row["soft_dumps"]),
                ",".join(item["state"] for item in row["baselines"]),
                ",".join(item["state"] for item in row["pairs"]),
                row.get("permission"),
            )
        )
        print("Z", row["z"])
        print(row["note"])
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())