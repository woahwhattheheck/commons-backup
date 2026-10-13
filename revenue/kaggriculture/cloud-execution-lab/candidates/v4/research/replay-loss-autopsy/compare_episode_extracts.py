#!/usr/bin/env python3
"""Source-bound recurrence report for canonical replay-loss-autopsy extracts.

Research-only: repeated tokens are descriptive routing evidence, never causal
credit. Inputs fail closed unless raw-source bytes, extraction parameters, and
resolved-column semantics are identical across every compared episode.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

INPUT_SCHEMA = "titan.v4.replay-loss-autopsy.v1"
OUTPUT_SCHEMA = "titan.v4.replay-loss-autopsy.multiloss.v1"
SOURCE_NAMES = ("farmer_actions", "market_orders", "matches_meta")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CompareError(ValueError):
    pass


def _int(value: Any, field: str, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise CompareError(f"{field} must be a plain integer")
    if minimum is not None and value < minimum:
        raise CompareError(f"{field} must be >= {minimum}")
    return value


def _opt_int(value: Any, field: str) -> int | None:
    return None if value is None else _int(value, field)


def _str(value: Any, field: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise CompareError(f"{field} must be {'a string' if empty else 'a nonempty string'}")
    return value


def _opt_str(value: Any, field: str) -> str | None:
    return None if value is None else _str(value, field, empty=True)


def _sources(payload: dict[str, Any], i: int) -> tuple[tuple[str, int], ...]:
    root = payload.get("inputs")
    if not isinstance(root, dict) or set(root) != set(SOURCE_NAMES):
        raise CompareError(f"extract[{i}].inputs must contain exactly {list(SOURCE_NAMES)}")
    out = []
    for name in SOURCE_NAMES:
        row = root[name]
        if not isinstance(row, dict):
            raise CompareError(f"extract[{i}].inputs.{name} must be an object")
        sha = row.get("sha256")
        if not isinstance(sha, str) or _SHA256.fullmatch(sha) is None:
            raise CompareError(f"extract[{i}].inputs.{name}.sha256 must be lowercase sha256")
        size = _int(row.get("bytes"), f"extract[{i}].inputs.{name}.bytes", 0)
        _str(row.get("path"), f"extract[{i}].inputs.{name}.path")
        out.append((sha, size))
    return tuple(out)


def _parameters(payload: dict[str, Any], i: int) -> tuple[int, int]:
    root = payload.get("parameters")
    if not isinstance(root, dict):
        raise CompareError(
            f"extract[{i}].parameters missing; re-extract with the current canonical extractor"
        )
    turns = _int(root.get("turns_per_day"), f"extract[{i}].parameters.turns_per_day", 1)
    tail = _int(root.get("tail_callbacks"), f"extract[{i}].parameters.tail_callbacks", 0)
    return turns, tail


def _mapping(
    value: Any,
    i: int,
    table: str,
    keys: tuple[str, ...],
    nullable: set[str],
) -> dict[str, str | None]:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise CompareError(
            f"extract[{i}].resolved_columns.{table} keys must be exactly {list(keys)}"
        )
    out: dict[str, str | None] = {}
    for key in keys:
        item = value[key]
        out[key] = None if item is None and key in nullable else _str(
            item, f"extract[{i}].resolved_columns.{table}.{key}"
        )
    return out


def _columns(payload: dict[str, Any], i: int) -> dict[str, Any]:
    root = payload.get("resolved_columns")
    if not isinstance(root, dict) or set(root) != set(SOURCE_NAMES):
        raise CompareError(
            f"extract[{i}].resolved_columns tables must be exactly {list(SOURCE_NAMES)}"
        )
    farmer = _mapping(
        root["farmer_actions"], i, "farmer_actions",
        ("episode", "player", "step", "verb", "target", "qty"), {"target", "qty"}
    )
    market = _mapping(
        root["market_orders"], i, "market_orders",
        ("episode", "player", "step", "verb", "item", "qty"), {"item", "qty"}
    )
    meta = root["matches_meta"]
    if not isinstance(meta, dict) or set(meta) != {"episode", "all_columns"}:
        raise CompareError(
            f"extract[{i}].resolved_columns.matches_meta must contain episode and all_columns"
        )
    episode = _str(meta["episode"], f"extract[{i}].resolved_columns.matches_meta.episode")
    names = meta["all_columns"]
    if (
        not isinstance(names, list)
        or not names
        or any(not isinstance(x, str) or not x for x in names)
        or len(names) != len(set(names))
    ):
        raise CompareError(
            f"extract[{i}].resolved_columns.matches_meta.all_columns must be unique nonempty strings"
        )
    if episode not in names:
        raise CompareError(
            f"extract[{i}].resolved_columns.matches_meta.episode absent from all_columns"
        )
    return {
        "farmer_actions": farmer,
        "market_orders": market,
        "matches_meta": {"episode": episode, "all_columns": list(names)},
    }


def _summary(rows: Any, i: int, kind: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise CompareError(f"extract[{i}].{kind}_summary must be a list")
    is_market = kind == "market"
    target_name = "item" if is_market else "target"
    out = []
    seen = set()
    for j, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CompareError(f"extract[{i}].{kind}_summary[{j}] must be an object")
        item = {
            "player": _str(row.get("player"), f"extract[{i}].{kind}_summary[{j}].player", empty=True),
            "day": _opt_int(row.get("day"), f"extract[{i}].{kind}_summary[{j}].day"),
            "verb": _str(row.get("verb"), f"extract[{i}].{kind}_summary[{j}].verb", empty=True),
            target_name: _opt_str(
                row.get(target_name), f"extract[{i}].{kind}_summary[{j}].{target_name}"
            ),
            "rows": _int(row.get("rows"), f"extract[{i}].{kind}_summary[{j}].rows", 1),
        }
        if is_market:
            item["explicit_qty_sum"] = _int(
                row.get("explicit_qty_sum"),
                f"extract[{i}].market_summary[{j}].explicit_qty_sum",
            )
        key = (item["player"], item["day"], item["verb"], item[target_name])
        if key in seen:
            raise CompareError(f"extract[{i}].{kind}_summary contains duplicate semantic key {key!r}")
        seen.add(key)
        out.append(item)
    return out


def _tail(
    value: Any,
    i: int,
    max_step: int | None,
    expected_callbacks: int,
) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        raise CompareError(f"extract[{i}].tail must be an object")
    requested = _int(value.get("requested_callbacks"), f"extract[{i}].tail.requested_callbacks", 0)
    if requested != expected_callbacks:
        raise CompareError(f"extract[{i}].tail.requested_callbacks disagrees with parameters")
    start = _opt_int(value.get("start_step"), f"extract[{i}].tail.start_step")
    expected_start = None if max_step is None else max(0, max_step - requested + 1)
    if start != expected_start:
        raise CompareError(f"extract[{i}].tail.start_step inconsistent with coverage/parameters")
    events = value.get("events")
    if not isinstance(events, list):
        raise CompareError(f"extract[{i}].tail.events must be a list")
    if requested == 0 and events:
        raise CompareError(f"extract[{i}].tail.events must be empty when tail_callbacks is zero")
    out = []
    numeric = []
    for j, event in enumerate(events):
        if not isinstance(event, dict):
            raise CompareError(f"extract[{i}].tail.events[{j}] must be an object")
        kind = event.get("kind")
        if kind not in {"farmer_action", "market_order"}:
            raise CompareError(f"extract[{i}].tail.events[{j}].kind unsupported")
        step = _opt_int(event.get("step"), f"extract[{i}].tail.events[{j}].step")
        if step is not None:
            if max_step is None or step > max_step:
                raise CompareError(f"extract[{i}].tail.events[{j}].step exceeds coverage.max_step")
            if start is not None and step < start:
                raise CompareError(f"extract[{i}].tail.events[{j}].step precedes tail.start_step")
            numeric.append(step)
        target_key = "target" if kind == "farmer_action" else "item"
        out.append({
            "kind": kind,
            "player": _str(
                event.get("player_raw"), f"extract[{i}].tail.events[{j}].player_raw", empty=True
            ),
            "relative_step": None if step is None or max_step is None else step - max_step,
            "verb": _str(event.get("verb"), f"extract[{i}].tail.events[{j}].verb", empty=True),
            "target": _opt_str(
                event.get(target_key), f"extract[{i}].tail.events[{j}].{target_key}"
            ),
            "qty": _opt_int(event.get("qty"), f"extract[{i}].tail.events[{j}].qty"),
            "qty_raw": _opt_str(event.get("qty_raw"), f"extract[{i}].tail.events[{j}].qty_raw"),
        })
    if numeric and max(numeric) != max_step:
        raise CompareError(f"extract[{i}].tail numeric events do not reach coverage.max_step")
    return out


def _extract(payload: Any, i: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CompareError(f"extract[{i}] must be an object")
    if payload.get("schema") != INPUT_SCHEMA:
        raise CompareError(f"extract[{i}].schema must be exactly {INPUT_SCHEMA!r}")
    episode = _str(payload.get("episode"), f"extract[{i}].episode")
    sources = _sources(payload, i)
    parameters = _parameters(payload, i)
    columns = _columns(payload, i)
    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        raise CompareError(f"extract[{i}].coverage must be an object")
    max_step = _opt_int(coverage.get("max_step"), f"extract[{i}].coverage.max_step")
    return {
        "episode": episode,
        "sources": sources,
        "parameters": parameters,
        "columns": columns,
        "farmer": _summary(payload.get("farmer_summary"), i, "farmer"),
        "market": _summary(payload.get("market_summary"), i, "market"),
        "tail": _tail(payload.get("tail"), i, max_step, parameters[1]),
    }


def _nullable(value: Any) -> tuple[int, str]:
    return (1, "") if value is None else (0, str(value))


def _repeat_summary(
    extracts: list[dict[str, Any]],
    key_name: str,
    target_name: str,
    minimum: int,
) -> list[dict[str, Any]]:
    values: dict[tuple[Any, ...], dict[str, dict[str, int]]] = defaultdict(dict)
    for extract in extracts:
        for row in extract[key_name]:
            key = (row["player"], row["day"], row["verb"], row[target_name])
            metrics = {"rows": row["rows"]}
            if key_name == "market":
                metrics["explicit_qty_sum"] = row["explicit_qty_sum"]
            values[key][extract["episode"]] = metrics
    out = []
    for key, episodes in values.items():
        if len(episodes) < minimum:
            continue
        player, day, verb, target = key
        out.append({
            "player": player,
            "day": day,
            "verb": verb,
            target_name: target,
            "episode_count": len(episodes),
            "episodes": [
                {"episode": episode, **episodes[episode]}
                for episode in sorted(episodes)
            ],
        })
    out.sort(key=lambda row: (
        row["player"], _nullable(row["day"]), row["verb"], _nullable(row[target_name])
    ))
    return out


def _repeat_tail(extracts: list[dict[str, Any]], minimum: int) -> list[dict[str, Any]]:
    seen: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    for extract in extracts:
        for row in extract["tail"]:
            if row["relative_step"] is None:
                continue
            key = (
                row["kind"], row["player"], row["relative_step"], row["verb"],
                row["target"], row["qty"], row["qty_raw"],
            )
            seen[key].add(extract["episode"])
    out = []
    for key, episodes in seen.items():
        if len(episodes) < minimum:
            continue
        kind, player, relative_step, verb, target, qty, qty_raw = key
        out.append({
            "kind": kind,
            "player": player,
            "relative_step": relative_step,
            "verb": verb,
            "target": target,
            "qty": qty,
            "qty_raw": qty_raw,
            "episode_count": len(episodes),
            "episodes": sorted(episodes),
        })
    out.sort(key=lambda row: (
        row["relative_step"], row["kind"], row["player"], row["verb"],
        _nullable(row["target"]), _nullable(row["qty"]), _nullable(row["qty_raw"]),
    ))
    return out


def compare_extracts(
    payloads: Iterable[dict[str, Any]], *, min_episodes: int = 2
) -> dict[str, Any]:
    minimum = _int(min_episodes, "min_episodes", 2)
    extracts = [_extract(payload, i) for i, payload in enumerate(payloads)]
    if len(extracts) < minimum:
        raise CompareError(f"need at least {minimum} extracts; received {len(extracts)}")
    episodes = [item["episode"] for item in extracts]
    if len(episodes) != len(set(episodes)):
        raise CompareError("episode ids must be unique")
    for field, message in (
        ("sources", "input source snapshot mismatch; recurrence requires identical raw CSV hashes and byte lengths"),
        ("parameters", "extraction parameter mismatch; recurrence requires identical turns_per_day and tail_callbacks"),
        ("columns", "resolved-column mismatch; recurrence requires identical semantic column bindings"),
    ):
        if any(item[field] != extracts[0][field] for item in extracts[1:]):
            raise CompareError(message)

    sources = extracts[0]["sources"]
    params = extracts[0]["parameters"]
    return {
        "schema": OUTPUT_SCHEMA,
        "episode_count": len(extracts),
        "episodes": sorted(episodes),
        "min_episodes": minimum,
        "source_snapshot": {
            name: {"sha256": sources[i][0], "bytes": sources[i][1]}
            for i, name in enumerate(SOURCE_NAMES)
        },
        "extraction_parameters": {
            "turns_per_day": params[0],
            "tail_callbacks": params[1],
        },
        "resolved_columns": extracts[0]["columns"],
        "repeated_farmer_summary": _repeat_summary(extracts, "farmer", "target", minimum),
        "repeated_market_summary": _repeat_summary(extracts, "market", "item", minimum),
        "repeated_tail_events": _repeat_tail(extracts, minimum),
        "limits": [
            "Only exact descriptive fields already present in canonical replay-loss-autopsy extracts are compared.",
            "All extracts must bind identical raw-source bytes, extraction parameters, and resolved semantic columns.",
            "Relative-tail recurrence does not imply equivalent game state.",
            "No mechanism attribution or causal credit is inferred.",
            "A repeated token is routing evidence only, not evidence that changing it improves score.",
        ],
    }


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CompareError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def load_extract(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_no_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise CompareError(f"{path}: invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise CompareError(f"{path}: JSON root must be an object")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("extracts", nargs="+", type=Path)
    parser.add_argument("--min-episodes", type=int, default=2)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = compare_extracts(
            [load_extract(path) for path in args.extracts],
            min_episodes=args.min_episodes,
        )
        text = json.dumps(
            report, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ) + "\n"
        if args.output is None:
            sys.stdout.write(text)
        else:
            args.output.write_text(text, encoding="utf-8")
    except (OSError, CompareError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
