"""CLI for the agent false-success survival proof."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .proof import MAX_INPUT_BYTES, ProofError, canonical_bytes, compile_proof, loads_strict, verify_proof


def _stat_key(st: Any) -> tuple[int, int, int, int, int, int, int]:
    return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _read_regular(path: str, *, max_bytes: int = MAX_INPUT_BYTES) -> bytes:
    p = Path(path)
    try:
        before = os.lstat(p)
    except OSError as exc:
        raise ProofError(f"cannot stat input file: {path}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ProofError(f"input must be a regular non-symlink file: {path}")
    if before.st_size > max_bytes:
        raise ProofError(f"input exceeds {max_bytes} bytes: {path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(p, flags)
    except OSError as exc:
        raise ProofError(f"cannot open input file: {path}") from exc
    try:
        opened = os.fstat(fd)
        if _stat_key(opened) != _stat_key(before):
            raise ProofError(f"input generation changed before open: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk); total += len(chunk)
            if total > max_bytes:
                raise ProofError(f"input exceeds {max_bytes} bytes: {path}")
        after_fd = os.fstat(fd)
    except OSError as exc:
        raise ProofError(f"cannot read input file: {path}") from exc
    finally:
        os.close(fd)
    if _stat_key(opened) != _stat_key(after_fd):
        raise ProofError(f"input generation changed while reading: {path}")
    try:
        after_path = os.lstat(p)
    except OSError as exc:
        raise ProofError(f"input path changed after read: {path}") from exc
    if _stat_key(opened) != _stat_key(after_path):
        raise ProofError(f"input path no longer names retained generation: {path}")
    return b"".join(chunks)


def _write_exclusive(path: str, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ProofError(f"refusing to overwrite or follow output: {path}") from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
    except Exception:
        try: os.unlink(path)
        except OSError: pass
        raise


def _emit(value: Any, *, stream: Any = sys.stdout) -> None:
    stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile/verify an agent false-success proof")
    sub = parser.add_subparsers(dest="command", required=True)
    cp = sub.add_parser("compile"); cp.add_argument("bundle"); cp.add_argument("--out", required=True)
    vp = sub.add_parser("verify"); vp.add_argument("bundle"); vp.add_argument("proof")
    dp = sub.add_parser("demo"); dp.add_argument("bundle")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bundle = loads_strict(_read_regular(args.bundle))
        if args.command == "compile":
            proof = compile_proof(bundle); _write_exclusive(args.out, canonical_bytes(proof) + b"\n")
            _emit({"ok": True, "decision": proof["proof"]["decision"], "proof_sha256": proof["proof_sha256"]})
            return 0
        if args.command == "verify":
            proof = loads_strict(_read_regular(args.proof))
            ok = verify_proof(bundle, proof); _emit({"ok": ok})
            return 0 if ok else 1
        proof = compile_proof(bundle)
        _emit({"ok": verify_proof(bundle, proof), "decision": proof["proof"]["decision"], "proof_sha256": proof["proof_sha256"]})
        return 0
    except ProofError as exc:
        _emit({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
