#!/usr/bin/env python3
"""Bounded evidence that the Muhlnickel computer is the file.

This witness never evaluates a gate. It reads a fixed header/control span,
surfaces topology plus host RSS, and dies. Exit: 0 PASS, 3 invalid/FAIL.
"""
from __future__ import annotations
import argparse, ctypes, json, os, struct, sys
from pathlib import Path

SCHEMA = "muhlnickel-capacity-witness/v1"
HEADER_BYTES = 272
MAX_CONTROL_BYTES = 4096
RSS_TOLERANCE = 8 * 1024 * 1024


class WitnessError(ValueError):
    pass


def u32(blob: bytes, off: int) -> int:
    if off + 4 > len(blob):
        raise WitnessError(f"missing u32@{off}")
    return struct.unpack_from("<I", blob, off)[0]


def u64(blob: bytes, off: int) -> int:
    if off + 8 > len(blob):
        raise WitnessError(f"missing u64@{off}")
    return struct.unpack_from("<Q", blob, off)[0]


def rss_bytes() -> int:
    if os.name == "nt":
        class C(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong),
                ("peak_ws", ctypes.c_size_t), ("working_set", ctypes.c_size_t),
                ("qpp", ctypes.c_size_t), ("qp", ctypes.c_size_t),
                ("qnpp", ctypes.c_size_t), ("qnp", ctypes.c_size_t),
                ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t),
            ]
        c = C(); c.cb = ctypes.sizeof(c)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb
        )
        return int(c.working_set) if ok else 0
    statm = Path("/proc/self/statm")
    if statm.is_file():
        fields = statm.read_text(encoding="ascii").split()
        if len(fields) > 1:
            return int(fields[1]) * int(os.sysconf("SC_PAGE_SIZE"))
    try:
        import resource
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except (ImportError, ValueError):
        return 0


def inspect_file(name: str) -> dict:
    path = Path(name)
    before = rss_bytes()
    size = path.stat().st_size
    with path.open("rb", buffering=0) as fh:
        header = fh.read(HEADER_BYTES)
        if len(header) != HEADER_BYTES:
            raise WitnessError("file shorter than fixed header")
        magic = header[:8]
        if magic not in (b"MUHLPKG1", b"MUHLDC01"):
            raise WitnessError(f"unsupported magic {magic!r}")
        if u64(header, 184) != size:
            raise WitnessError("header total does not match file size")
        gates = u32(header, 16)
        gates_per_ring = u32(header, 24)
        wire_off, wire_len = u64(header, 40), u64(header, 48)
        if not gates or not gates_per_ring:
            raise WitnessError("zero-gate container")
        if wire_len > MAX_CONTROL_BYTES or wire_off + wire_len > size:
            raise WitnessError("control span leaves bounded file surface")
        fh.seek(wire_off)
        control = fh.read(wire_len)
        if len(control) != wire_len:
            raise WitnessError("short control read")

    result = {
        "schema": SCHEMA, "path": str(path),
        "magic": magic.decode("ascii"), "file_bytes": size,
        "stored_gate_records": gates,
        "declared_gate_ops_per_pulse": gates,
        "gates_per_ring": gates_per_ring,
        "declared_ticks": u32(header, 36),
        "header_total_matches_file": True,
    }
    if magic == b"MUHLPKG1":
        result.update(rings=1, factory_rings=0, address_bits=None,
                      winner_only=None, stored_per_lane=None)
    else:
        fold_off, fold_len = u64(header, 104), u64(header, 112)
        if fold_off != 224 or fold_len < 48:
            raise WitnessError("unexpected MUHLDC01 fold layout")
        factory = u64(header, fold_off + 16)
        rings = factory + 1
        if gates != rings * gates_per_ring:
            raise WitnessError("gates != rings * gates_per_ring")
        result.update(
            rings=rings, factory_rings=factory,
            address_bits=u32(header, fold_off),
            winner_only=bool(u32(header, fold_off + 4)),
            stored_per_lane=u32(header, fold_off + 8),
            senses=u32(header, fold_off + 12),
            factory_stride_bytes=u64(header, fold_off + 24),
        )
    after = rss_bytes()
    result.update(
        host_bytes_read=HEADER_BYTES + len(control),
        host_rss_before_bytes=before, host_rss_after_bytes=after,
        host_rss_delta_bytes=max(0, after - before),
        host_rss_measured=before > 0 and after > 0,
        control_ones=sum(b.bit_count() for b in control),
        computer_is_file=True,
        host_role=["surface", "measure", "die"],
        host_evaluated_gates=False, pulse_performed=False, file_mutated=False,
    )
    return result


def capacity_ladder(names: list[str], tolerance: int = RSS_TOLERANCE) -> dict:
    if len(names) < 2:
        raise WitnessError("ladder needs at least two files")
    rows = [inspect_file(name) for name in names]
    ordered = sorted(rows, key=lambda row: row["stored_gate_records"])
    low, high = ordered[0], ordered[-1]
    measured = all(row["host_rss_measured"] for row in rows)
    values = [row["host_rss_after_bytes"] for row in rows] if measured else []
    spread = max(values) - min(values) if measured else None
    raised = high["stored_gate_records"] > low["stored_gate_records"]
    flat = measured and spread is not None and spread <= tolerance
    bounded = max(row["host_bytes_read"] for row in rows) <= HEADER_BYTES + MAX_CONTROL_BYTES
    return {
        "schema": SCHEMA, "kind": "capacity-ladder",
        "pass": raised and flat and bounded, "computer_is_file": True,
        "gate_work_increased": raised,
        "gate_work_growth": high["stored_gate_records"] / low["stored_gate_records"],
        "host_ram_measured": measured,
        "host_ram_flat": flat, "host_rss_spread_bytes": spread,
        "host_rss_tolerance_bytes": tolerance, "fixed_bounded_reads": bounded,
        "files": rows,
        "claim_boundary": "No pulse; no host gate evaluation; host I/O time is not computer rate.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("inspect"); one.add_argument("file")
    many = sub.add_parser("ladder"); many.add_argument("files", nargs="+")
    many.add_argument("--rss-tolerance-bytes", type=int, default=RSS_TOLERANCE)
    args = ap.parse_args(argv)
    try:
        out = inspect_file(args.file) if args.cmd == "inspect" else capacity_ladder(
            args.files, args.rss_tolerance_bytes
        )
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0 if out.get("pass", True) else 3
    except (OSError, UnicodeError, WitnessError) as exc:
        print(f"3: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
