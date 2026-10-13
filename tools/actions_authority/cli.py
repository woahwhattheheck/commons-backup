from __future__ import annotations

import argparse
import errno
import os
import secrets
import stat
from pathlib import Path

from .authority import classify
from .common import EvidenceError, MAX_INPUT_BYTES, _canonical_bytes, _time, parse_json_bytes


def _read_input(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise EvidenceError("input must be an existing ordinary non-symlink file") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise EvidenceError("input must be an ordinary file")
        if before.st_size > MAX_INPUT_BYTES:
            raise EvidenceError(f"input exceeds {MAX_INPUT_BYTES} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, MAX_INPUT_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise EvidenceError(f"input exceeds {MAX_INPUT_BYTES} bytes")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise EvidenceError("input changed while being read")
        try:
            visible = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            raise EvidenceError("input path changed while being read") from exc
        if (visible.st_dev, visible.st_ino) != (after.st_dev, after.st_ino):
            raise EvidenceError("input path changed while being read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _publish_create_exclusive(path: Path, raw: bytes) -> None:
    parent = path.parent
    name = path.name
    if name in {"", ".", ".."}:
        raise EvidenceError("output must name a file")
    parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        parent_fd = os.open(parent, parent_flags)
    except OSError as exc:
        raise EvidenceError("output parent must be an existing directory") from exc
    stage_name = f".{name}.{secrets.token_hex(16)}.stage"
    stage_fd: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        stage_fd = os.open(stage_name, flags, 0o600, dir_fd=parent_fd)
        view = memoryview(raw)
        while view:
            written = os.write(stage_fd, view)
            if written <= 0:
                raise EvidenceError("short write while staging output")
            view = view[written:]
        os.fsync(stage_fd)
        os.close(stage_fd)
        stage_fd = None
        try:
            os.link(stage_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
        except FileExistsError as exc:
            raise EvidenceError("output already exists") from exc
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                raise EvidenceError("output already exists") from exc
            raise
        os.fsync(parent_fd)
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        try:
            os.unlink(stage_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify policy-bound exact-head GitHub Actions evidence without calling GitHub."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-age-seconds", type=int, default=1800)
    parser.add_argument("--max-future-skew-seconds", type=int, default=300)
    parser.add_argument("--now", help="Explicit ISO-8601 evaluation time for reproducible/offline classification")
    args = parser.parse_args(argv)
    try:
        raw = _read_input(args.input.absolute())
        payload = parse_json_bytes(raw)
        now = _time(args.now, "--now") if args.now is not None else None
        receipt = classify(
            payload,
            now=now,
            max_age_seconds=args.max_age_seconds,
            max_future_skew_seconds=args.max_future_skew_seconds,
        )
        _publish_create_exclusive(args.out.absolute(), _canonical_bytes(receipt))
        return 3
    except (EvidenceError, OSError) as exc:
        print(f"ACTIONS_AUTHORITY_ERROR: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
