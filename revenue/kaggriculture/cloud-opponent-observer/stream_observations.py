"""Stream supplied observations through the existing COK observer.

Uses one persistent original controller per match/seat. Neither policies nor
summary semantics are changed; complete telemetry rows are not retained in RAM.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Iterator, TextIO

from observe import CokObserver, summarize


def iter_records(source: str | Path, pack: str | Path,
                 lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Consume an observation stream lazily, preserving independent histories.

    Same schema as observe.run_jsonl: observation, optional configuration,
    match_id and expected_action. This is observation replay, not engine replay.
    Open controller histories stay in memory to support interleaved matches.
    """
    agents: dict[tuple[str, int], CokObserver] = {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("the input record must be an object")
            obs = payload["observation"]
            if not isinstance(obs, dict):
                raise ValueError("observation must be an object")
            match = str(payload.get("match_id", "default"))
            seat = 1 if int(obs.get("player", 0) or 0) == 1 else 0
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            # Identify the line without printing an observation or private state.
            raise ValueError(f"Invalid observation record on line {number}: {type(exc).__name__}") from exc
        key = (match, seat)
        if key not in agents:
            agents[key] = CokObserver(source, pack)
        action = agents[key].act(obs, payload.get("configuration", {}))
        record = copy.deepcopy(agents[key].last_record)
        record["match_id"], record["input_line"] = match, number
        if "expected_action" in payload:
            record["expected_action_matches"] = action == payload["expected_action"]
        yield record


def _distinct_files(inputs: Iterable[Path], outputs: Iterable[Path]) -> None:
    sources, targets = list(inputs), list(outputs)
    for i, target in enumerate(targets):
        for other in [*sources, *targets[:i]]:
            same = target.resolve() == other.resolve()
            if not same and target.exists() and other.exists():
                same = os.path.samefile(target, other)
            if same:
                raise ValueError("Input, source, telemetry and summary must refer to distinct files")
        if target.exists() and not target.is_file():
            raise ValueError("Each output must name a file")


def _temporary(destination: Path) -> tuple[Path, TextIO]:
    stream = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
        dir=destination.parent, prefix=f".{destination.name}.", delete=False)
    return Path(stream.name), stream


def _publish_pair(staged: list[tuple[Path, Path]]) -> None:
    """Publish completed files; roll back ordinary replacement errors.

    Individual replacements are atomic, but this is NOT a crash-atomic two-file
    transaction. Interrupted-process readers must retain that distinction.
    """
    backups: dict[Path, Path | None] = {}
    changed: list[Path] = []
    recovery_errors: list[Path] = []
    try:
        for _, destination in staged:
            backup = None
            if destination.exists():
                fd, name = tempfile.mkstemp(dir=destination.parent,
                    prefix=f".{destination.name}.previous.")
                os.close(fd)
                backup = Path(name)
                backups[destination] = backup
                shutil.copyfile(destination, backup)
            backups[destination] = backup
        for temporary, destination in staged:
            os.replace(temporary, destination)
            changed.append(destination)
    except BaseException as publish_error:
        for destination in reversed(changed):
            backup = backups[destination]
            try:
                if backup is None:
                    destination.unlink(missing_ok=True)
                else:
                    os.replace(backup, destination)
            except OSError:
                recovery_errors.append(destination)
        if recovery_errors:
            # Leave remaining original copies in place for manual recovery.
            paths = ", ".join(str(backups[p]) for p in recovery_errors if backups[p])
            raise OSError(f"Output replacement and rollback failed; retained original copies: {paths}") from publish_error
        raise
    finally:
        # A backup still needed after failed rollback is deliberately retained.
        for destination, backup in backups.items():
            if backup is not None and destination not in recovery_errors:
                backup.unlink(missing_ok=True)


def run_jsonl(source: str | Path, pack: str | Path, input_path: str | Path,
              output_path: str | Path, summary_path: str | Path) -> dict[str, Any]:
    """Stream telemetry and aggregate it in one pass, then publish both outputs."""
    original_input, original_source = Path(input_path), Path(source)
    outputs = [Path(output_path), Path(summary_path)]
    _distinct_files([original_input, original_source], outputs)
    # Preserve existing symlink destinations as links to their intended files.
    destinations = [p.resolve() for p in outputs]
    staged: list[tuple[Path, Path]] = []
    try:
        with ExitStack() as stack:
            incoming = stack.enter_context(original_input.open(encoding="utf-8"))
            handles = []
            for destination in destinations:
                temporary, stream = _temporary(destination)
                staged.append((temporary, destination))
                handles.append(stack.enter_context(stream))
            outgoing, summary_stream = handles
            def emit() -> Iterator[dict[str, Any]]:
                for record in iter_records(original_source, pack, incoming):
                    outgoing.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
                    yield record
            result = summarize(emit())
            json.dump(result, summary_stream, sort_keys=True, indent=2, allow_nan=False)
            summary_stream.write("\n")
        # Detect a caller-created alias again before replacing final outputs.
        _distinct_files([original_input, original_source], outputs)
        if [p.resolve() for p in outputs] != destinations:
            raise ValueError("An output target changed during observation processing")
        _publish_pair(staged)
        return result
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "pack", "input", "output", "summary"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_jsonl(args.source, args.pack, args.input, args.output, args.summary)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"stream: {type(exc).__name__}: {exc}\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return int(any(a["telemetry_errors"] or a["expected_action_mismatches"] for a in result["actors"]))


if __name__ == "__main__":
    raise SystemExit(main())
