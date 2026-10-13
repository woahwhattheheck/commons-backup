"""Aggregate saved COK activation JSONL without executing an opponent or engine."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Iterator, Any

from observe import summarize


def records(path: Path) -> Iterator[dict[str, Any]]:
    """Read one detached telemetry record at a time; never collect the input log."""
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid telemetry JSON on line {number}: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Telemetry line {number} must be an object")
            yield row


def build_report(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    """Write a complete summary atomically, retaining inputs and failed outputs."""
    source, destination = Path(input_path), Path(output_path)
    same = source.resolve() == destination.resolve()
    if destination.exists() and source.exists():
        same = same or os.path.samefile(source, destination)
    if same:
        raise ValueError("Use a report destination distinct from the telemetry input")
    # summarize validates every row's schema and source identity. Its accumulator
    # holds per-actor counts, step sets and transitions, not complete input rows.
    summary = summarize(records(source))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=f".{destination.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(summary, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Saved cok-activation-v1 JSONL")
    parser.add_argument("--output", type=Path, required=True, help="Aggregate JSON destination")
    args = parser.parse_args(argv)
    try:
        summary = build_report(args.input, args.output)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"report: {type(exc).__name__}: {exc}\n")
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return int(any(a["telemetry_errors"] or a["expected_action_mismatches"]
                   for a in summary["actors"]))


if __name__ == "__main__":
    raise SystemExit(main())
