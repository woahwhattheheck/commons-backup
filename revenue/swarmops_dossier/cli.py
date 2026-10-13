from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from .engine import (
    DossierError, canonical_bytes, compile_current_dossier,
    compile_historical_dossier, render_markdown, strict_json_loads,
    verify_current_dossier, verify_historical_dossier,
)

MAX_INPUT = 1_048_576
_READ_CHUNK = 64 * 1024


def _timestamp_ns(st: os.stat_result, name: str) -> int:
    ns_name = f"st_{name}_ns"
    if hasattr(st, ns_name):
        return int(getattr(st, ns_name))
    return int(getattr(st, f"st_{name}") * 1_000_000_000)


def _generation_fingerprint(st: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(st.st_dev),
        int(st.st_ino),
        int(stat.S_IFMT(st.st_mode)),
        int(st.st_size),
        _timestamp_ns(st, "mtime"),
        _timestamp_ns(st, "ctime"),
    )


def read_regular(path: str) -> str:
    p = Path(path)
    inspected = os.lstat(p)
    if not stat.S_ISREG(inspected.st_mode):
        raise DossierError(f"not a regular input file: {path}")
    if inspected.st_size > MAX_INPUT:
        raise DossierError(f"input too large: {path}")

    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise DossierError("platform does not provide O_NOFOLLOW for safe input reads")
    fd = os.open(p, flags | nofollow)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise DossierError(f"not a regular input file: {path}")
        if opened.st_size > MAX_INPUT:
            raise DossierError(f"input too large: {path}")
        opened_generation = _generation_fingerprint(opened)
        if _generation_fingerprint(inspected) != opened_generation:
            raise DossierError(f"input changed before open: {path}")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(_READ_CHUNK, MAX_INPUT + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_INPUT:
                raise DossierError(f"input too large: {path}")
            chunks.append(chunk)

        finished = os.fstat(fd)
        if _generation_fingerprint(finished) != opened_generation:
            raise DossierError(f"input changed during read: {path}")
        data = b"".join(chunks)
        if len(data) != opened.st_size:
            raise DossierError(f"input changed during read: {path}")
    finally:
        os.close(fd)
    return data.decode("utf-8")


def write_new(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            view = view[n:]
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    """Current evaluation and explicitly historical replay with no commercial trust flag."""
    ap = argparse.ArgumentParser(description="Compile current SwarmOps dossiers or replay historical evidence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for command, help_text in (
        ("compile", "evaluate now using process UTC"),
        ("replay", "evaluate a past instant; output is not current"),
        ("verify", "check retained integrity and present evidence classifications"),
        ("verify-replay", "check historical integrity only, including archived v3 dossiers"),
    ):
        parser = sub.add_parser(command, help=help_text)
        parser.add_argument("packet")
        parser.add_argument("policy")
        if command.startswith("verify"):
            parser.add_argument("candidate")
        else:
            parser.add_argument("--json-out", required=True)
            parser.add_argument("--markdown-out", required=True)
        if command in {"replay", "verify-replay"}:
            parser.add_argument("--as-of", required=True, help="past UTC instant in YYYY-MM-DDTHH:MM:SSZ format")
    ns = ap.parse_args(argv)
    try:
        packet = strict_json_loads(read_regular(ns.packet))
        policy = strict_json_loads(read_regular(ns.policy))
        if ns.cmd in {"compile", "replay"}:
            dossier = (compile_current_dossier(packet, policy, {}) if ns.cmd == "compile" else
                       compile_historical_dossier(packet, policy, ns.as_of, {}))
            write_new(ns.json_out, canonical_bytes(dossier) + b"\n")
            write_new(ns.markdown_out, render_markdown(dossier).encode("utf-8"))
            print(f"{dossier['evaluation_mode']}: {dossier['status']} at {dossier['as_of']}")
            for row in dossier["evidence"]:
                if row["reasons"]:
                    print(f"{row['source_id']}: {', '.join(row['reasons'])}")
            missing = dossier["summary"]["missing_required_capabilities"]
            if missing:
                print(f"Missing required capabilities: {', '.join(missing)}", file=sys.stderr)
            return 0 if not missing else 2
        candidate = strict_json_loads(read_regular(ns.candidate))
        if ns.cmd == "verify-replay":
            if not verify_historical_dossier(packet, policy, ns.as_of, candidate, {}):
                print("ERROR: historical dossier does not match the supplied evidence, policy and instant", file=sys.stderr)
                return 3
            print("HISTORICAL_REPLAY: integrity matches; current readiness was not checked")
            return 0
        try:
            verify_current_dossier(packet, policy, candidate, {})
        except DossierError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
        print(f"CURRENT: integrity and present classifications match; dossier status is {candidate['status']}")
        return 0
    except (DossierError, OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
