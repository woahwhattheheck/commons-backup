#!/usr/bin/env python3
"""Read state-grounded context from a peer's optional Commons memory board."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory_board  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor", required=True, help="Commons actor claim")
    parser.add_argument("--goal", default="", help="current goal text")
    parser.add_argument("--state", default="", help="current execution state")
    parser.add_argument("--limit", type=int, default=6, help="maximum context entries")
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = parser.parse_args(argv)
    actor = memory_board.canonical_actor(args.actor)
    if not actor:
        parser.error("actor must canonicalize to a valid Commons claim")
    limit = memory_board.clamp_retrieval_limit(args.limit)
    path = os.path.join(args.root, "memory", "%s.json" % actor)
    try:
        with open(path, encoding="utf-8") as handle:
            board = json.load(handle)
    except (OSError, ValueError) as exc:
        parser.error("cannot read %s: %s" % (path, exc))
    result = {
        "actor_id": actor,
        "goal": args.goal,
        "state": args.state,
        "working_memory": board.get("working_memory") or {},
        "context": memory_board.retrieve_for_state(board, args.goal, args.state, limit),
        "admission_effect": "NONE",
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
