#!/usr/bin/env python3
"""WINNER FOLD — winner-only inverted return bandwidth.

Practical application of the Muhlnickel provisional patent family
(muhl/docs/PROVISIONAL_SESSION.pdf, sole inventor Bryce Muhlnickel):
inverted return bandwidth (claims 17-19, 32). Germs out; winner-only back.
The nonce is the address. Losing lanes store zero. Return traffic scales
with winners, not with lanes: the fold holds one winner record no matter
how many lanes reported.

Use: distributed search, auctions, telemetry folds, any fan-out where only
the best result may ride home.

Stdlib only. Exit codes: 0 ok, 2 usage, 3 fold inconsistency.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

def fail(code: int, msg: str) -> None:
    print(f"{code}: {msg}", file=sys.stderr)
    raise SystemExit(code)


SCHEMA = "winner-fold/v1"


def _load(path: Path) -> dict:
    if not path.is_file():
        fail(2, f"{path} is not an open fold; run open first")
    fold = json.loads(path.read_text())
    if fold.get("schema") != SCHEMA:
        fail(3, f"{path} is not a {SCHEMA} record")
    return fold


def _save(path: Path, fold: dict) -> None:
    path.write_text(json.dumps(fold, indent=2, sort_keys=True) + "\n")


def _winner_record(lane: str, nonce: str, score: float) -> dict:
    return {"lane": lane, "nonce": nonce, "score": score}


def _return_bytes(fold: dict) -> int:
    winner = fold.get("winner")
    if winner is None:
        return 0
    return len(json.dumps(winner, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _beats(candidate: dict, incumbent: dict) -> bool:
    if candidate["score"] != incumbent["score"]:
        return candidate["score"] > incumbent["score"]
    if candidate["nonce"] != incumbent["nonce"]:
        return candidate["nonce"] < incumbent["nonce"]
    return candidate["lane"] < incumbent["lane"]


def cmd_open(args: argparse.Namespace) -> int:
    path = Path(args.fold)
    if path.exists():
        fail(2, f"{path} already exists; folds are append-only, open a new id")
    fold = {
        "schema": SCHEMA,
        "fold_id": path.stem,
        "question": args.question or "",
        "addr_bits": args.addr_bits,
        "winner_only": 1,
        "stored_per_lane": 0,
        "lanes_seen": 0,
        "winner": None,
        "opened_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "closed_utc": None,
    }
    _save(path, fold)
    print(json.dumps({"opened": str(path), "addr_bits": args.addr_bits,
                      "winner_only": 1, "stored_per_lane": 0}, indent=2))
    return 0


def cmd_lane(args: argparse.Namespace) -> int:
    path = Path(args.fold)
    fold = _load(path)
    if fold.get("closed_utc"):
        fail(3, "fold is closed")
    nonce = args.nonce.lower()
    try:
        value = int(nonce, 16)
    except ValueError:
        fail(2, "nonce must be hex")
    if value >= (1 << fold["addr_bits"]):
        fail(2, f"nonce exceeds addr_bits={fold['addr_bits']}")
    candidate = _winner_record(args.lane, nonce, args.score)
    fold["lanes_seen"] += 1
    incumbent = fold.get("winner")
    won = incumbent is None or _beats(candidate, incumbent)
    if won:
        fold["winner"] = candidate
    _save(path, fold)
    print(json.dumps({"lane": args.lane,
                      "lane_is_current_winner": won,
                      "stored_bytes_for_this_lane": _return_bytes(fold) if won else 0,
                      "return_bytes": _return_bytes(fold),
                      "lanes_seen": fold["lanes_seen"]}, indent=2))
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    path = Path(args.fold)
    fold = _load(path)
    fold["closed_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save(path, fold)
    winner = fold.get("winner")
    print(json.dumps({
        "closed": str(path),
        "winner": winner,
        "lanes_seen": fold["lanes_seen"],
        "stored_per_lane": fold["stored_per_lane"],
        "return_bytes": _return_bytes(fold),
        "return_scales_with": "winners",
    }, indent=2))
    return 0 if winner is not None else 3


def cmd_status(args: argparse.Namespace) -> int:
    fold = _load(Path(args.fold))
    print(json.dumps({**fold, "return_bytes": _return_bytes(fold)}, indent=2))
    return 0


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="winner_fold", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("open", help="open a winner-only fold")
    p.add_argument("fold")
    p.add_argument("--addr-bits", type=int, required=True)
    p.add_argument("--question")
    p.set_defaults(fn=cmd_open)

    p = sub.add_parser("lane", help="report one lane candidate; losers store zero")
    p.add_argument("fold")
    p.add_argument("--lane", required=True)
    p.add_argument("--nonce", required=True)
    p.add_argument("--score", type=float, required=True)
    p.set_defaults(fn=cmd_lane)

    p = sub.add_parser("close", help="surface the winner")
    p.add_argument("fold")
    p.set_defaults(fn=cmd_close)

    p = sub.add_parser("status", help="print the fold record")
    p.add_argument("fold")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
