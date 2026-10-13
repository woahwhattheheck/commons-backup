from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from revenue.multi_framework_evidence_freshness.gate import GateError, load_strict_json

from .wrapper import DiagnosticError, compile_diagnostic, render_buyer_page, verify_diagnostic


def _write_new(path: Path, data: bytes) -> None:
    parent = path.parent if str(path.parent) else Path(".")
    dflags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        dflags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        dflags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        dflags |= os.O_NOFOLLOW
    dfd = os.open(parent, dflags)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path.name, flags, 0o600, dir_fd=dfd)
        try:
            view = memoryview(data)
            sent = 0
            while sent < len(view):
                n = os.write(fd, view[sent:])
                if n <= 0:
                    raise OSError("short_write")
                sent += n
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(dfd)


def _exists(path: Path) -> bool:
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixed multi-framework evidence freshness diagnostic")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("input")
    c.add_argument("diagnostic")
    c.add_argument("markdown")
    v = sub.add_parser("verify")
    v.add_argument("diagnostic")
    ns = parser.parse_args(argv)
    try:
        if ns.cmd == "compile":
            raw = load_strict_json(ns.input)
            envelope = compile_diagnostic(raw)
            page = render_buyer_page(envelope)
            out = Path(ns.diagnostic)
            md = Path(ns.markdown)
            if _exists(out) or _exists(md):
                raise DiagnosticError("output_exists")
            payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            _write_new(out, payload)
            _write_new(md, page.encode("utf-8"))
            print(envelope["diagnostic_sha256"])
            return 0
        envelope = load_strict_json(ns.diagnostic)
        print(verify_diagnostic(envelope))
        return 0
    except (DiagnosticError, GateError, OSError) as exc:
        print(f"ERROR:{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
