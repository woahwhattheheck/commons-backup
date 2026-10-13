from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .engine import BackplannerError, load_spec_text, render_markdown, render_resource_csv, solve, verify_result

MAX_RESULT_BYTES = 2_000_000


def _read_text(path: Path, limit: int = 1_000_000) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise BackplannerError(f"cannot read {path}: {exc}") from exc
    if len(data) > limit:
        raise BackplannerError(f"{path}: file too large")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BackplannerError(f"{path}: not UTF-8") from exc


def _load_result(path: Path) -> dict:
    text = _read_text(path, MAX_RESULT_BYTES)
    try:
        value = json.loads(text, parse_constant=lambda v: (_ for _ in ()).throw(BackplannerError(f"non-finite JSON number: {v}")))
    except (json.JSONDecodeError, BackplannerError) as exc:
        raise BackplannerError(f"invalid result JSON: {exc}") from exc
    if type(value) is not dict:
        raise BackplannerError("result root must be object")
    return value


def _write_exclusive(path: Path, text: str) -> tuple[int, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        data = text.encode("utf-8")
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        os.fsync(fd)
        st = os.fstat(fd)
        return st.st_dev, st.st_ino
    finally:
        os.close(fd)


def command_solve(spec_path: Path, out_dir: Path) -> int:
    spec = load_spec_text(_read_text(spec_path))
    result = solve(spec)
    if out_dir.exists():
        if not out_dir.is_dir():
            raise BackplannerError("output path exists and is not a directory")
    else:
        out_dir.mkdir(parents=False)
    targets = {
        "result.json": json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        "timeline.md": render_markdown(spec, result),
        "resource_load.csv": render_resource_csv(result),
    }
    collisions = [name for name in targets if (out_dir / name).exists()]
    if collisions:
        raise BackplannerError(f"refusing to overwrite existing outputs: {collisions}")
    created: list[tuple[Path, int, int]] = []
    try:
        for name, text in targets.items():
            path = out_dir / name
            dev, ino = _write_exclusive(path, text)
            created.append((path, dev, ino))
    except Exception:
        for path, dev, ino in reversed(created):
            try:
                st = path.stat()
            except OSError:
                continue
            if (st.st_dev, st.st_ino) != (dev, ino):
                continue
            try:
                path.unlink()
            except OSError:
                pass
        raise
    print(result["status"])
    print(result["result_sha256"])
    return 0 if result["status"] == "PLAN_FOUND" else (2 if result["status"] == "NO_FEASIBLE_PLAN" else 3)


def command_verify(spec_path: Path, result_path: Path) -> int:
    spec = load_spec_text(_read_text(spec_path))
    result = _load_result(result_path)
    verdict = verify_result(spec, result)
    print(json.dumps(verdict, sort_keys=True, separators=(",", ":")))
    return 0 if verdict.get("valid") else 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic pre-sale delivery backplanner")
    sub = parser.add_subparsers(dest="command", required=True)
    solve_p = sub.add_parser("solve")
    solve_p.add_argument("spec", type=Path)
    solve_p.add_argument("out_dir", type=Path)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("spec", type=Path)
    verify_p.add_argument("result", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "solve":
            return command_solve(args.spec, args.out_dir)
        return command_verify(args.spec, args.result)
    except (BackplannerError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
