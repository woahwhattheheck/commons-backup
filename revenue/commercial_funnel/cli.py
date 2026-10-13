from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import (
    HOLD,
    FunnelError,
    canonical_json,
    compile_funnel,
    strict_loads,
    verify_artifacts_current,
)


def _trusted_now() -> str:
    """Return the process runtime UTC second used by current CLI decisions."""
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise FunnelError(f"refusing non-regular input: {path}")
    return strict_loads(path.read_text(encoding="utf-8"))


def _ensure_output_dir(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise FunnelError(f"output path is not a real directory: {path}")
        return
    path.mkdir(mode=0o755, parents=True, exist_ok=False)


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o644)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)
    mode = os.stat(path, follow_symlinks=False).st_mode
    if not stat.S_ISREG(mode):
        raise FunnelError(f"output is not regular file: {path}")


def command_compile(args: argparse.Namespace) -> int:
    source = _read_json(Path(args.input))
    result = compile_funnel(source, as_of=_trusted_now())
    out_dir = Path(args.out_dir)
    _ensure_output_dir(out_dir)
    outputs = {
        "report.json": result["json"],
        "report.csv": result["csv"],
        "report.md": result["markdown"],
        "packet.json": canonical_json(result["packet"]),
        "receipt.json": canonical_json(result["receipt"]),
    }
    collisions = [name for name in outputs if (out_dir / name).exists() or (out_dir / name).is_symlink()]
    if collisions:
        raise FunnelError(f"refusing to overwrite existing outputs: {sorted(collisions)}")
    for name, data in outputs.items():
        _write_exclusive(out_dir / name, data)
    print(json.dumps({
        "state": result["packet"]["state"],
        "packet_sha256": result["receipt"]["packet_sha256"],
        "receipt_sha256": result["receipt"]["receipt_sha256"],
        "opportunity_count": result["packet"]["metrics"]["opportunity_count"],
        "held_opportunity_count": result["packet"]["metrics"]["held_opportunity_count"],
    }, sort_keys=True))
    return 3 if result["packet"]["state"] == HOLD else 0


def _read_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FunnelError(f"refusing non-regular input: {path}")
    return path.read_bytes()


def command_verify(args: argparse.Namespace) -> int:
    source = _read_json(Path(args.input))
    packet = _read_json(Path(args.packet))
    receipt = _read_json(Path(args.receipt))
    ok = verify_artifacts_current(
        source,
        trusted_now=_trusted_now(),
        packet=packet,
        receipt=receipt,
        report_json=_read_bytes(Path(args.report_json)),
        report_csv=_read_bytes(Path(args.report_csv)),
        report_markdown=_read_bytes(Path(args.report_md)),
    )
    print(json.dumps({"verified": ok}, sort_keys=True))
    return 0 if ok else 4


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Compile and currently verify evidence-bound Commons commercial funnel packets.")
    sub = ap.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser(
        "compile",
        help="compile one input ledger at trusted process UTC into current review artifacts",
    )
    compile_p.add_argument("input")
    compile_p.add_argument("--out-dir", required=True)
    compile_p.set_defaults(func=command_compile)
    verify_p = sub.add_parser(
        "verify",
        help="byte-verify original artifacts and re-evaluate their semantics at trusted process UTC",
    )
    verify_p.add_argument("input")
    verify_p.add_argument("--packet", required=True)
    verify_p.add_argument("--receipt", required=True)
    verify_p.add_argument("--report-json", required=True)
    verify_p.add_argument("--report-csv", required=True)
    verify_p.add_argument("--report-md", required=True)
    verify_p.set_defaults(func=command_verify)
    return ap


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return int(args.func(args))
    except FunnelError as exc:
        print(json.dumps({"error": str(exc), "state": "HOLD"}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
