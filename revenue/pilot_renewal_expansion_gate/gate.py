#!/usr/bin/env python3
"""Evidence-bound pilot delivery -> renewal/expansion review gate CLI."""
from __future__ import annotations

import argparse
import os
import re
import stat
from pathlib import Path
from typing import Any

from .common import GateError, TRUTH_CEILING, canonical_json, sha256, strict_loads, _read_regular
from .schema import normalize
from .engine import compile_current, evaluate, verify_current

_MD_META = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>])")

def _markdown_text(value: Any) -> str:
    text = " ".join(str(value).split())
    return _MD_META.sub(r"\\\1", text)


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Renewal / Expansion Owner Review Packet", "",
        f"- Engagement: `{_markdown_text(packet['engagement_id'])}`",
        f"- Organization: `{_markdown_text(packet['organization_id'])}`",
        f"- Decision: **{_markdown_text(packet['decision'])}**",
        f"- Verified at: `{_markdown_text(packet['verified_at'])}`",
        f"- Truth ceiling: `{_markdown_text(packet['truth_ceiling'])}`", "",
        "## Expansion hypotheses",
    ]
    if packet["expansion_hypotheses"]:
        for item in packet["expansion_hypotheses"]:
            lines.append(f"- `{_markdown_text(item['id'])}` — {_markdown_text(item['statement'])} — **{_markdown_text(item['state'])}**")
    else:
        lines.append("- None recorded.")
    lines += ["", "## Holds / reasons"]
    if packet["reasons"]:
        for reason in packet["reasons"]:
            lines.append(f"- `{_markdown_text(reason['code'])}` / `{_markdown_text(reason['ref'])}` — {_markdown_text(reason['detail'])}")
    else:
        lines.append("- None.")
    lines += ["", "## Authority ceiling", "This packet is owner-review evidence only. It does not authorize external send, signature/contract, buyer acceptance, renewal/expansion approval, invoicing/payment, cash/revenue recognition, deployment, scheduling, or CRM mutation.", ""]
    return "\n".join(lines)


def _same_inode(a: os.stat_result, b: os.stat_result) -> bool:
    return stat.S_ISREG(a.st_mode) and stat.S_ISREG(b.st_mode) and a.st_dev == b.st_dev and a.st_ino == b.st_ino


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    dir_fd = os.open(path.parent, dir_flags)
    fd = -1
    created: os.stat_result | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path.name, flags, 0o600, dir_fd=dir_fd)
        created = os.fstat(fd)
        try:
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.fsync(dir_fd)
        except Exception:
            if fd >= 0:
                try:
                    os.close(fd)
                finally:
                    fd = -1
            try:
                current = os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
            except OSError:
                current = None
            if created is not None and current is not None and _same_inode(created, current):
                try:
                    os.unlink(path.name, dir_fd=dir_fd)
                    os.fsync(dir_fd)
                except OSError:
                    pass
            raise
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(dir_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile"); c.add_argument("input"); c.add_argument("output_dir")
    v = sub.add_parser("verify"); v.add_argument("input"); v.add_argument("packet"); v.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        raw = strict_loads(_read_regular(Path(args.input)))
        if args.cmd == "compile":
            _, packet, receipt = compile_current(raw)
            out = Path(args.output_dir)
            if out.exists():
                raise GateError("output_dir must not already exist")
            out.mkdir(parents=True, exist_ok=False)
            _atomic_write(out / "packet.json", canonical_json(packet))
            _atomic_write(out / "packet.md", render_markdown(packet).encode("utf-8"))
            _atomic_write(out / "receipt.json", canonical_json(receipt))
            print(packet["decision"])
            return 0
        packet = strict_loads(_read_regular(Path(args.packet)))
        receipt = strict_loads(_read_regular(Path(args.receipt)))
        result = verify_current(raw, packet, receipt)
        print(canonical_json(result).decode("utf-8"), end="")
        return 0 if result["integrity_valid"] else 2
    except (GateError, OSError, UnicodeError, ValueError, RecursionError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
