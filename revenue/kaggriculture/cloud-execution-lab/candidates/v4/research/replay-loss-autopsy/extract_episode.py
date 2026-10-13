#!/usr/bin/env python3
"""Deterministic single-episode extractor for Kaggriculture replay CSVs.

Research tooling only. It summarizes fields that are explicitly present in the
three replay tables and never infers cash, tile state, policy intent, or causal
credit. Ambiguous schemas fail closed.

The extractor is intentionally stdlib-only so a data-holding runner can execute
it without the Titan runtime.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

ALIASES = {
    "episode": ("episode_id", "episode", "match_id", "match", "game_id", "game"),
    "player": ("player", "player_id", "seat", "player_index", "agent_index"),
    "step": ("step", "turn", "callback", "timestep", "step_id"),
    "action_verb": ("action_verb", "verb", "action", "command", "operation"),
    "action_target": ("target", "action_target", "item", "product", "crop", "animal"),
    "action_qty": ("qty", "quantity", "amount", "units"),
    "market_verb": ("order_verb", "verb", "order_type", "action", "operation", "type"),
    "market_item": ("item", "product", "target", "commodity", "animal"),
    "market_qty": ("qty", "quantity", "amount", "units"),
}


def _capture_csv(path: Path) -> tuple[list[str], list[dict[str, str]], dict]:
    """Capture one immutable byte snapshot and derive both rows and provenance.

    The source-bound theorem requires the parsed rows and recorded digest/size to
    describe the same bytes.  Never reopen the pathname after this capture.
    """
    with path.open("rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise ValueError(f"{path}: missing CSV header")
    fields = list(reader.fieldnames)
    if len(fields) != len(set(fields)):
        raise ValueError(f"{path}: duplicate CSV header names")
    rows = []
    for line_no, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{path}: malformed CSV row at line {line_no}")
        rows.append(dict(row))
    source = {
        "path": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return fields, rows, source


def _resolve(fields: list[str], semantic: str, *, required: bool, override: str | None = None) -> str | None:
    if override is not None:
        if override not in fields:
            raise ValueError(f"override for {semantic} names missing column {override!r}; headers={fields}")
        return override
    aliases = ALIASES[semantic]
    exact = [name for name in aliases if name in fields]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(
            f"ambiguous {semantic}: matched {exact}; headers={fields}"
        )
    # Case-insensitive fallback only when it maps to exactly one real header.
    lower = defaultdict(list)
    for field in fields:
        lower[field.casefold()].append(field)
    ci = []
    for alias in aliases:
        ci.extend(lower.get(alias.casefold(), []))
    ci = list(dict.fromkeys(ci))
    if len(ci) == 1:
        return ci[0]
    if len(ci) > 1:
        raise ValueError(
            f"ambiguous {semantic} (case-insensitive): matched {ci}; headers={fields}"
        )
    if required:
        raise ValueError(f"missing {semantic}; headers={fields}")
    return None


def _episode_match(value: str, wanted: str) -> bool:
    return value.strip() == wanted


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    # Strict integer text only; no float/bool coercion.
    sign = text[0] in "+-"
    digits = text[1:] if sign else text
    if not digits.isdigit():
        return None
    return int(text, 10)


def _num_sort_key(value: str) -> tuple[int, int | str]:
    iv = _int_or_none(value)
    return (0, iv) if iv is not None else (1, value)


def _day(step: int | None, turns_per_day: int) -> int | None:
    return None if step is None else step // turns_per_day


def _event_sort_key(event: dict) -> tuple:
    step = event.get("step")
    player = event.get("player_raw", "")
    kind_rank = 0 if event["kind"] == "farmer_action" else 1
    return (
        step is None,
        step if step is not None else math.inf,
        _num_sort_key(player),
        kind_rank,
        event.get("row_index", 0),
    )


def _counter_rows(counter: Counter[tuple]) -> list[dict]:
    out = []
    for key in sorted(counter, key=lambda k: tuple(_num_sort_key(str(v)) for v in k)):
        player, day, verb, target = key
        out.append(
            {
                "player": player,
                "day": day,
                "verb": verb,
                "target": target,
                "rows": counter[key],
            }
        )
    return out


def _market_rows(counts: Counter[tuple], qtys: Counter[tuple]) -> list[dict]:
    out = []
    keys = set(counts) | set(qtys)
    for key in sorted(keys, key=lambda k: tuple(_num_sort_key(str(v)) for v in k)):
        player, day, verb, item = key
        out.append(
            {
                "player": player,
                "day": day,
                "verb": verb,
                "item": item,
                "rows": counts[key],
                "explicit_qty_sum": qtys[key],
            }
        )
    return out


def extract(
    actions_path: Path,
    markets_path: Path,
    meta_path: Path,
    episode: str,
    *,
    tail_callbacks: int = 96,
    turns_per_day: int = 24,
    column_map: dict | None = None,
) -> dict:
    if tail_callbacks < 0:
        raise ValueError("tail_callbacks must be >= 0")
    if turns_per_day <= 0:
        raise ValueError("turns_per_day must be > 0")

    afields, arows, asource = _capture_csv(actions_path)
    mfields, mrows, msource = _capture_csv(markets_path)
    xfields, xrows, xsource = _capture_csv(meta_path)

    column_map = column_map or {}
    acols = column_map.get("farmer_actions", {})
    mcols = column_map.get("market_orders", {})
    xcols = column_map.get("matches_meta", {})
    if not all(isinstance(v, dict) for v in (acols, mcols, xcols)):
        raise ValueError("column_map table entries must be JSON objects")

    amap = {
        "episode": _resolve(afields, "episode", required=True, override=acols.get("episode")),
        "player": _resolve(afields, "player", required=True, override=acols.get("player")),
        "step": _resolve(afields, "step", required=True, override=acols.get("step")),
        "verb": _resolve(afields, "action_verb", required=True, override=acols.get("verb")),
        "target": _resolve(afields, "action_target", required=False, override=acols.get("target")),
        "qty": _resolve(afields, "action_qty", required=False, override=acols.get("qty")),
    }
    mmap = {
        "episode": _resolve(mfields, "episode", required=True, override=mcols.get("episode")),
        "player": _resolve(mfields, "player", required=True, override=mcols.get("player")),
        "step": _resolve(mfields, "step", required=True, override=mcols.get("step")),
        "verb": _resolve(mfields, "market_verb", required=True, override=mcols.get("verb")),
        "item": _resolve(mfields, "market_item", required=False, override=mcols.get("item")),
        "qty": _resolve(mfields, "market_qty", required=False, override=mcols.get("qty")),
    }
    x_episode = _resolve(xfields, "episode", required=True, override=xcols.get("episode"))

    selected_actions = [
        (i, row) for i, row in enumerate(arows, start=2)
        if _episode_match(row[amap["episode"]], episode)
    ]
    selected_markets = [
        (i, row) for i, row in enumerate(mrows, start=2)
        if _episode_match(row[mmap["episode"]], episode)
    ]
    selected_meta = [
        row for row in xrows if _episode_match(row[x_episode], episode)
    ]
    if not selected_actions and not selected_markets and not selected_meta:
        raise LookupError(f"episode {episode!r} not found in any table")

    action_counts: Counter[tuple] = Counter()
    market_counts: Counter[tuple] = Counter()
    market_qtys: Counter[tuple] = Counter()
    events: list[dict] = []
    bad_step_rows = {"farmer_actions": 0, "market_orders": 0}
    bad_qty_rows = {"farmer_actions": 0, "market_orders": 0}

    for row_index, row in selected_actions:
        step = _int_or_none(row[amap["step"]])
        if step is None:
            bad_step_rows["farmer_actions"] += 1
        player = row[amap["player"]]
        verb = row[amap["verb"]]
        target = row[amap["target"]] if amap["target"] else None
        qty_raw = row[amap["qty"]] if amap["qty"] else None
        qty = _int_or_none(qty_raw)
        if qty_raw not in (None, "") and qty is None:
            bad_qty_rows["farmer_actions"] += 1
        action_counts[(player, _day(step, turns_per_day), verb, target)] += 1
        events.append({
            "kind": "farmer_action",
            "row_index": row_index,
            "step": step,
            "player_raw": player,
            "verb": verb,
            "target": target,
            "qty": qty,
            "qty_raw": qty_raw,
        })

    for row_index, row in selected_markets:
        step = _int_or_none(row[mmap["step"]])
        if step is None:
            bad_step_rows["market_orders"] += 1
        player = row[mmap["player"]]
        verb = row[mmap["verb"]]
        item = row[mmap["item"]] if mmap["item"] else None
        qty_raw = row[mmap["qty"]] if mmap["qty"] else None
        qty = _int_or_none(qty_raw)
        if qty_raw not in (None, "") and qty is None:
            bad_qty_rows["market_orders"] += 1
        key = (player, _day(step, turns_per_day), verb, item)
        market_counts[key] += 1
        if qty is not None:
            market_qtys[key] += qty
        events.append({
            "kind": "market_order",
            "row_index": row_index,
            "step": step,
            "player_raw": player,
            "verb": verb,
            "item": item,
            "qty": qty,
            "qty_raw": qty_raw,
        })

    events.sort(key=_event_sort_key)
    numeric_steps = [e["step"] for e in events if e["step"] is not None]
    max_step = max(numeric_steps) if numeric_steps else None
    tail_start = None if max_step is None else max(0, max_step - tail_callbacks + 1)
    tail = [
        e for e in events
        if tail_start is None or (e["step"] is not None and e["step"] >= tail_start)
    ]

    return {
        "schema": "titan.v4.replay-loss-autopsy.v1",
        "episode": episode,
        "parameters": {
            "tail_callbacks": tail_callbacks,
            "turns_per_day": turns_per_day,
        },
        "inputs": {
            "farmer_actions": asource,
            "market_orders": msource,
            "matches_meta": xsource,
        },
        "resolved_columns": {
            "farmer_actions": amap,
            "market_orders": mmap,
            "matches_meta": {"episode": x_episode, "all_columns": xfields},
        },
        "coverage": {
            "farmer_action_rows": len(selected_actions),
            "market_order_rows": len(selected_markets),
            "meta_rows": len(selected_meta),
            "min_step": min(numeric_steps) if numeric_steps else None,
            "max_step": max_step,
            "bad_step_rows": bad_step_rows,
            "bad_qty_rows": bad_qty_rows,
        },
        "meta_rows_exact": selected_meta,
        "farmer_summary": _counter_rows(action_counts),
        "market_summary": _market_rows(market_counts, market_qtys),
        "tail": {
            "requested_callbacks": tail_callbacks,
            "start_step": tail_start,
            "events": tail,
        },
        "limits": [
            "Only fields explicitly present in the CSVs are reported.",
            "No cash, tile state, inventory, opponent identity, economics, or causal credit is inferred.",
            "Market explicit_qty_sum excludes rows whose quantity is absent or not a strict integer.",
            "Ambiguous required schema aliases fail closed.",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--farmer-actions", required=True, type=Path)
    p.add_argument("--market-orders", required=True, type=Path)
    p.add_argument("--matches-meta", required=True, type=Path)
    p.add_argument("--episode", required=True)
    p.add_argument("--tail-callbacks", type=int, default=96)
    p.add_argument("--turns-per-day", type=int, default=24)
    p.add_argument("--output", type=Path)
    p.add_argument("--schema-json", type=Path, help="Optional explicit column map for ambiguous datasets")
    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        column_map = None
        if args.schema_json is not None:
            column_map = json.loads(args.schema_json.read_text(encoding="utf-8"))
            if not isinstance(column_map, dict):
                raise ValueError("schema JSON root must be an object")
        payload = extract(
            args.farmer_actions,
            args.market_orders,
            args.matches_meta,
            args.episode,
            tail_callbacks=args.tail_callbacks,
            turns_per_day=args.turns_per_day,
            column_map=column_map,
        )
    except (OSError, csv.Error, ValueError, LookupError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())