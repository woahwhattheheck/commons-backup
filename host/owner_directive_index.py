#!/usr/bin/env python3
"""Build a deterministic owner-directive broadcast/ACK index.

Input is one JSON object with three lists:
  directives: {op_id, owner, owner_mark, directive}
  broadcasts: {op_id, surface, permalink?}
  heartbeats: {seat, acks:[op_id,...]}

The reducer never infers ownership or acknowledgement. Ownership is accepted only
when owner_mark is the literal boolean true; ACKs are derived only from exact op ids
listed by a seat heartbeat. Unknown ACK ids and duplicate facts fail closed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class DirectiveIndexError(ValueError):
    """Input is ambiguous, malformed, or contradicts the strict ledger contract."""


def _obj(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise DirectiveIndexError(f"{where} must be an object")
    return value


def _list(value: Any, where: str) -> list[Any]:
    if type(value) is not list:
        raise DirectiveIndexError(f"{where} must be a list")
    return value


def _text(value: Any, where: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise DirectiveIndexError(f"{where} must be a non-empty exact string")
    return value


def build_index(payload: Any) -> dict[str, Any]:
    root = _obj(payload, "root")
    allowed = {"directives", "broadcasts", "heartbeats"}
    extra = set(root) - allowed
    missing = allowed - set(root)
    if extra or missing:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(sorted(missing)))
        if extra:
            detail.append("unknown=" + ",".join(sorted(extra)))
        raise DirectiveIndexError("root fields invalid: " + " ".join(detail))

    directives: dict[str, dict[str, str]] = {}
    for i, raw in enumerate(_list(root["directives"], "directives")):
        row = _obj(raw, f"directives[{i}]")
        if set(row) != {"op_id", "owner", "owner_mark", "directive"}:
            raise DirectiveIndexError(f"directives[{i}] fields invalid")
        op_id = _text(row["op_id"], f"directives[{i}].op_id")
        owner = _text(row["owner"], f"directives[{i}].owner")
        directive = _text(row["directive"], f"directives[{i}].directive")
        if type(row["owner_mark"]) is not bool or row["owner_mark"] is not True:
            raise DirectiveIndexError(
                f"directives[{i}].owner_mark must be literal true"
            )
        if op_id in directives:
            raise DirectiveIndexError(f"duplicate directive op_id: {op_id}")
        directives[op_id] = {"owner": owner, "directive": directive}

    broadcasts: dict[str, dict[str, str | None]] = {op: {} for op in directives}
    for i, raw in enumerate(_list(root["broadcasts"], "broadcasts")):
        row = _obj(raw, f"broadcasts[{i}]")
        if set(row) not in ({"op_id", "surface"}, {"op_id", "surface", "permalink"}):
            raise DirectiveIndexError(f"broadcasts[{i}] fields invalid")
        op_id = _text(row["op_id"], f"broadcasts[{i}].op_id")
        if op_id not in directives:
            raise DirectiveIndexError(f"broadcast references unknown op_id: {op_id}")
        surface = _text(row["surface"], f"broadcasts[{i}].surface")
        permalink: str | None = None
        if "permalink" in row:
            permalink = _text(row["permalink"], f"broadcasts[{i}].permalink")
        if surface in broadcasts[op_id]:
            raise DirectiveIndexError(
                f"duplicate broadcast fact: op_id={op_id} surface={surface}"
            )
        broadcasts[op_id][surface] = permalink

    heartbeat_acks: dict[str, set[str]] = {}
    for i, raw in enumerate(_list(root["heartbeats"], "heartbeats")):
        row = _obj(raw, f"heartbeats[{i}]")
        if set(row) != {"seat", "acks"}:
            raise DirectiveIndexError(f"heartbeats[{i}] fields invalid")
        seat = _text(row["seat"], f"heartbeats[{i}].seat")
        if seat in heartbeat_acks:
            raise DirectiveIndexError(f"duplicate heartbeat seat: {seat}")
        acks: set[str] = set()
        for j, raw_op in enumerate(_list(row["acks"], f"heartbeats[{i}].acks")):
            op_id = _text(raw_op, f"heartbeats[{i}].acks[{j}]")
            if op_id not in directives:
                raise DirectiveIndexError(
                    f"heartbeat seat={seat} ACK references unknown op_id: {op_id}"
                )
            if op_id in acks:
                raise DirectiveIndexError(
                    f"duplicate heartbeat ACK: seat={seat} op_id={op_id}"
                )
            acks.add(op_id)
        heartbeat_acks[seat] = acks

    seats = sorted(heartbeat_acks)
    rows: list[dict[str, Any]] = []
    for op_id in sorted(directives):
        surface_rows = [
            {"surface": surface, "permalink": broadcasts[op_id][surface]}
            for surface in sorted(broadcasts[op_id])
        ]
        rows.append(
            {
                "op_id": op_id,
                "owner": directives[op_id]["owner"],
                "owner_mark": True,
                "directive": directives[op_id]["directive"],
                "broadcasts": surface_rows,
                "acks": {seat: op_id in heartbeat_acks[seat] for seat in seats},
            }
        )

    return {
        "schema": "commons.owner-directive-index.v1",
        "seats": seats,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON ledger input")
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = build_index(payload)
    except (OSError, json.JSONDecodeError, DirectiveIndexError) as exc:
        print(f"owner-directive-index: ERROR: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
