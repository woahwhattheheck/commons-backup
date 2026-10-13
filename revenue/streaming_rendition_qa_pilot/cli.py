from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from revenue.streaming_rendition_qa_pilot.pilot import compile_artifacts
from revenue.streaming_rendition_release_gate.fixture import build_fixture

MAX_INPUT_BYTES = 8 * 1024 * 1024


def _load_packets(path: Path) -> tuple[Any, str]:
    if path.is_symlink():
        raise ValueError("input path must not be a symlink")
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("input exceeds 8 MiB metadata-only pilot limit")
    try:
        packets = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc.msg}") from exc
    return packets, hashlib.sha256(raw).hexdigest()


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write without progress")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile a metadata-only Streaming Rendition QA Pilot packet."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Sanitized JSON array of rendition packets.")
    source.add_argument(
        "--canonical-sample",
        action="store_true",
        help="Use the landed 168-packet synthetic fixture.",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.canonical_sample:
        packets, _ = build_fixture()
        raw_sha256 = None
    else:
        packets, raw_sha256 = _load_packets(args.input)

    artifacts = compile_artifacts(packets)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=False)
    try:
        for name, data in artifacts.items():
            _write_exclusive(out_dir / name, data)
    except Exception:
        for name in artifacts:
            candidate = out_dir / name
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
        try:
            out_dir.rmdir()
        except OSError:
            pass
        raise

    summary = {
        "artifact_sha256": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(artifacts.items())
        },
        "out_dir": str(out_dir),
        "source_file_sha256": raw_sha256,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
