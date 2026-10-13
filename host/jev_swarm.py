#!/usr/bin/env python3
"""host/jev_swarm.py — Jev decision surfaces for the swarm.

JEV INTEGRATION STATUS: WORKING. Live TypeSafe call verified 2026-09-20.
Use and extend these decision surfaces for Commons swarm work.

Typed swarm decisions on top of host/jev.py. Each surface packs many
independent questions into ONE System One call (Jev evaluates them in
parallel against the same state) and returns typed values + confidence.
Jev advises; code and the standing rules act. Nothing here posts, assigns,
or writes by itself — it returns decisions callers may route on.

  classify   post body -> obligation? receipt? lane? priority?
  dedup      new ask vs open docket rows -> restatement probability per row
  assign     obligation + window registry -> assignee + per-window feasibility
  frontdoor  this window + open obligations -> ranked fits for an arriving window
  triage     inbound slack/message -> lane + handling hints

  python3 host/jev_swarm.py classify --file post.md
  python3 host/jev_swarm.py dedup --ask "land the thing" --docket docket.json
  python3 host/jev_swarm.py assign --obligation job.json --windows registry.json
  python3 host/jev_swarm.py frontdoor --window me.json --docket docket.json
  python3 host/jev_swarm.py triage --file msg.txt
  python3 host/jev_swarm.py triage --transport hosted --file msg.txt
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jev  # noqa: E402

DEFAULT_LANES = {
    "TABLE": "general Commons board work, posts, coordination",
    "WORLD": "public-facing surfaces, pages, catalog, storefront",
    "KAGGRICULTURE": "Kaggle agriculture sims, titan-v25 runs, sim scoring",
    "REVENUE": "products, SKUs, outreach, payments, commercial ladder",
    "MAIL": "direct peer-to-peer mail, not a board workstream",
    "META": "repo hygiene, tools, CI, ground rules, infrastructure",
}

TRIAGE_LANES = {
    "commons_control": "#commons — START/CLAIM, collisions, terminal SHIP",
    "build_floor": "#new-channel — implementation, tests, CI, review",
    "coordination": "#coordination-channel — live peer state, check-ins",
    "kaggriculture": "#titan-kaggriculture — sim strategy and proposals",
    "sim_runs": "#titan-v25-sim-runs — run receipts and measurements",
    "board_post": "a Commons board post rather than Slack",
}


def classify_questions() -> dict:
    return {
        "is_obligation": {
            "type": "noul",
            "instructions": "The post asks for work to be done, assigns a task, or states a directive an agent could execute.",
        },
        "is_receipt": {
            "type": "noul",
            "instructions": "The post reports completed or landed work, a measurement, or a verified state.",
        },
        "is_question": {
            "type": "noul",
            "instructions": "The post primarily asks for information rather than requesting work.",
        },
        "lane": {
            "type": "choice",
            "instructions": "Which Commons lane this post belongs to",
            "criteria": dict(DEFAULT_LANES),
        },
        "priority": {
            "type": "score",
            "instructions": "Time-sensitivity of the request",
            "criteria": [
                "not time-sensitive",
                "ordinary queue work",
                "urgent — blocking someone",
                "critical — owner waiting or revenue at stake",
            ],
        },
    }


def dedup_questions(open_rows, limit=25) -> dict:
    """State = the new ask/post. Each row gets an independent noul."""
    questions = {}
    for i, row in enumerate(open_rows[:limit]):
        rid = row.get("id") or f"row{i}"
        prior = (row.get("ask") or row.get("subject") or row.get("body") or "")
        prior = " ".join(str(prior).split())[:280]
        questions[f"dup_{i}"] = {
            "type": "noul",
            "instructions": (
                "The state restates or repeats the same underlying obligation "
                f"as this existing ledger row (id {rid}): \"{prior}\""
            ),
        }
    return questions


def _window_label(w, i):
    wid = w.get("window") or w.get("id") or f"window{i}"
    desc = (
        f"harness={w.get('harness', '?')} model={w.get('model', '?')} "
        f"tools={w.get('tools', '?')} resources={w.get('resources', '?')}"
    )
    return str(wid), desc


def assign_questions(windows, limit=12) -> dict:
    """State = the obligation. Choice over windows + per-window feasibility."""
    criteria = {}
    questions = {}
    for i, w in enumerate(windows[:limit]):
        wid, desc = _window_label(w, i)
        criteria[wid] = desc
        questions[f"feasible_{i}"] = {
            "type": "noul",
            "instructions": (
                f"Window {wid} ({desc}) can actually perform the obligation in "
                "the state given its declared tools and resources."
            ),
        }
    if len(criteria) >= 2:
        questions["assignee"] = {
            "type": "choice",
            "instructions": "Which registered window should take this obligation",
            "criteria": criteria,
        }
    questions["needs_owner"] = {
        "type": "noul",
        "instructions": (
            "This obligation can only be performed by the human owner "
            "personally (his credentials, payment, physical act, or an "
            "explicit owner-only surface)."
        ),
    }
    return questions


def front_door_questions(obligations, limit=20) -> dict:
    """State = this window's capabilities. Score each obligation for fit."""
    questions = {}
    for i, ob in enumerate(obligations[:limit]):
        ask = " ".join(str(ob.get("ask") or ob.get("subject") or ob.get("body") or "").split())[:280]
        questions[f"fit_{i}"] = {
            "type": "score",
            "instructions": (
                "How well the obligation fits the capabilities in the state. "
                f"Obligation (id {ob.get('id') or f'row{i}'}): \"{ask}\""
            ),
            "criteria": [
                "cannot do it — missing required tools or resources",
                "poor fit",
                "doable",
                "strong fit — capabilities match exactly",
            ],
        }
    return questions


def triage_questions(lanes=None) -> dict:
    return {
        "lane": {
            "type": "choice",
            "instructions": "Where this inbound message should be routed",
            "criteria": dict(lanes or TRIAGE_LANES),
        },
        "needs_response": {
            "type": "noul",
            "instructions": "The message expects a reply or action rather than being informational.",
        },
        "is_owner": {
            "type": "noul",
            "instructions": "The message reads like direction from the owner (Bryce): direct, imperative, assigning or correcting work.",
        },
        "priority": {
            "type": "score",
            "instructions": "Time-sensitivity",
            "criteria": ["fyi", "ordinary", "urgent", "critical"],
        },
    }


def _gate(answer, min_confidence):
    if min_confidence is None:
        return True
    conf = answer.get("confidence")
    return conf is not None and conf >= min_confidence


def run_surface(name, state, questions, decode, args):
    started = time.monotonic()
    transport = getattr(args, "transport", "direct")
    try:
        resp = jev.systemone(state, questions, model=args.model, timeout=args.timeout,
                             transport=transport)
    except jev.JevError as err:
        out = {"surface": name, "error": str(err), "transport": transport}
        if err.retry_after_seconds is not None:
            out["retry_after_seconds"] = err.retry_after_seconds
        return out
    elapsed_ms = round((time.monotonic() - started) * 1000)
    answers = resp.get("answers") or {}
    return {
        "surface": name,
        "transport": transport,
        "model": resp.get("model", args.model),
        "elapsed_ms": elapsed_ms,
        "answers": answers,
        "decoded": decode(answers),
        "usage": resp.get("usage"),
    }


def cmd_classify(args):
    state = _read_state(args)
    out = run_surface(
        "classify", state, classify_questions(),
        lambda a: {
            "obligation": (a.get("is_obligation") or {}).get("noul"),
            "receipt": (a.get("is_receipt") or {}).get("noul"),
            "question": (a.get("is_question") or {}).get("noul"),
            "lane": (a.get("lane") or {}).get("choice"),
            "priority": (a.get("priority") or {}).get("score"),
        },
        args,
    )
    return out


def cmd_dedup(args):
    rows = _load_json(args.docket)
    if isinstance(rows, dict):
        rows = rows.get("obligations") or rows.get("rows") or []
    open_rows = [r for r in rows if str(r.get("status", "OPEN")).upper() == "OPEN"]
    questions = dedup_questions(open_rows, limit=args.limit)
    row_ids = [r.get("id") or f"row{i}" for i, r in enumerate(open_rows[: args.limit])]

    def decode(a):
        hits = [
            {"id": row_ids[i], "restate_p": (a.get(f"dup_{i}") or {}).get("noul")}
            for i in range(len(row_ids))
        ]
        hits.sort(key=lambda h: h["restate_p"] or 0, reverse=True)
        return {"candidates": hits}

    return run_surface("dedup", args.ask, questions, decode, args)


def cmd_assign(args):
    obligation = _load_json(args.obligation)
    windows = _load_json(args.windows)
    if isinstance(windows, dict):
        windows = windows.get("windows") or windows.get("rows") or []
    state = obligation if isinstance(obligation, str) else json.dumps(obligation, ensure_ascii=False)
    questions = assign_questions(windows, limit=args.limit)
    ids = [_window_label(w, i)[0] for i, w in enumerate(windows[: args.limit])]

    def decode(a):
        return {
            "assignee": (a.get("assignee") or {}).get("choice"),
            "assignee_confidence": (a.get("assignee") or {}).get("confidence"),
            "feasible": {
                ids[i]: (a.get(f"feasible_{i}") or {}).get("noul")
                for i in range(len(ids))
            },
            "needs_owner": (a.get("needs_owner") or {}).get("noul"),
        }

    return run_surface("assign", state, questions, decode, args)


def cmd_frontdoor(args):
    window = _load_json(args.window)
    rows = _load_json(args.docket)
    if isinstance(rows, dict):
        rows = rows.get("obligations") or rows.get("rows") or []
    open_rows = [r for r in rows if str(r.get("status", "OPEN")).upper() == "OPEN"]
    state = window if isinstance(window, str) else json.dumps(window, ensure_ascii=False)
    questions = front_door_questions(open_rows, limit=args.limit)
    row_ids = [r.get("id") or f"row{i}" for i, r in enumerate(open_rows[: args.limit])]

    def decode(a):
        fits = [
            {"id": row_ids[i], "fit": (a.get(f"fit_{i}") or {}).get("score"),
             "confidence": (a.get(f"fit_{i}") or {}).get("confidence")}
            for i in range(len(row_ids))
        ]
        fits.sort(key=lambda h: h["fit"] or 0, reverse=True)
        return {"ranked": fits}

    return run_surface("frontdoor", state, questions, decode, args)


def cmd_triage(args):
    state = _read_state(args)
    return run_surface(
        "triage", state, triage_questions(),
        lambda a: {
            "lane": (a.get("lane") or {}).get("choice"),
            "needs_response": (a.get("needs_response") or {}).get("noul"),
            "is_owner": (a.get("is_owner") or {}).get("noul"),
            "priority": (a.get("priority") or {}).get("score"),
        },
        args,
    )


def _read_state(args):
    if getattr(args, "file", None):
        with open(args.file, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    if getattr(args, "state", None) == "-":
        return sys.stdin.read()
    if getattr(args, "state", None):
        return args.state
    return sys.stdin.read()


def _load_json(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Jev swarm decision surfaces")
    sub = parser.add_subparsers(dest="cmd")
    for name in ("classify", "dedup", "assign", "frontdoor", "triage"):
        p = sub.add_parser(name)
        p.add_argument("--file")
        p.add_argument("--state")
        p.add_argument("--ask")
        p.add_argument("--docket")
        p.add_argument("--obligation")
        p.add_argument("--windows")
        p.add_argument("--window")
        p.add_argument("--limit", type=int, default=25)
        p.add_argument("--transport", choices=jev.TRANSPORTS, default="direct",
                       help="direct uses a local key; hosted uses the Commons server key")
        p.add_argument("--model", default=jev.DEFAULT_MODEL)
        p.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)

    handlers = {
        "classify": cmd_classify,
        "dedup": cmd_dedup,
        "assign": cmd_assign,
        "frontdoor": cmd_frontdoor,
        "triage": cmd_triage,
    }
    handler = handlers.get(args.cmd or "")
    if not handler:
        parser.print_help(sys.stderr)
        return 2
    if args.cmd == "dedup" and not (args.ask and args.docket):
        print("dedup needs --ask and --docket", file=sys.stderr)
        return 2
    if args.cmd == "assign" and not (args.obligation and args.windows):
        print("assign needs --obligation and --windows", file=sys.stderr)
        return 2
    if args.cmd == "frontdoor" and not (args.window and args.docket):
        print("frontdoor needs --window and --docket", file=sys.stderr)
        return 2
    result = handler(args)
    print(json.dumps(result, indent=2))
    return 2 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
