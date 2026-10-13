#!/usr/bin/env python3
"""host/shared_one_lever.py — measure the shared-one / voltage-overlap lever.

Owner lever (Slack 1787499595.112409): a write stores voltage on the addressed
substrate (the hard drive). Humans abstract that stored charge as a 1 at an
address. One written 1 can be shared by as much circuitry as the physical
layout allows. Overlapping muhlnickel gates share that same stored charge.

This host instrument reads public excerpts FROM FILE. It does not evaluate
organs. It does not write titan. Destinations come from the header. Dies
after printing numbers.

Header is the live MHA layout: 8-char magic, then LE
n_gate, n_wires, n_in, n_out, depth. Wire plane sits at
28 + n_out*8. W_CONST1 is byte 0x01 at wire-plane + 1. Gate
records are <BQQQ> stride 25 and store absolute addresses.

  python3 host/shared_one_lever.py
  python3 host/shared_one_lever.py excerpts/20260823/muhl_lvin.mno
"""
from __future__ import annotations

import json
import os
import struct
import sys

GATE_STRIDE = 25
MLC_FILE_LEVELS = 256
CHIMERA_PREFIX = "muhl_chimera_"
TITANX_PREFIX = "muhl_titanx_"
EXCERPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "excerpts",
    "20260823",
)


def excerpt_kind(path):
    """Full PLUMB 1-19 organs are MLC dumps. Chimera and TitanX slices are not."""
    name = os.path.basename(path or "")
    if name.startswith(CHIMERA_PREFIX):
        return "chimera"
    if name.startswith(TITANX_PREFIX):
        return "titanx"
    return "plumb_full"


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def header_size(n_out):
    return 28 + int(n_out) * 8


def measure_blob(blob, path=""):
    """Return the sharing receipt for one excerpt. Does not walk the organ as inference."""
    if len(blob) < 28:
        raise ValueError("short header: %s" % path)
    magic = blob[:8]
    n_gate, n_wires, n_in, n_out, depth = struct.unpack_from("<IIIII", blob, 8)
    hsz = header_size(n_out)
    if len(blob) < hsz + n_wires + n_gate * GATE_STRIDE:
        raise ValueError("short body: %s" % path)
    wire_plane = blob[hsz:hsz + n_wires]
    const0_addr = hsz + 0
    const1_addr = hsz + 1
    const0 = wire_plane[0] if n_wires > 0 else None
    const1 = wire_plane[1] if n_wires > 1 else None
    plane_levels = len(set(wire_plane))
    plane_ones = sum(bin(b).count("1") for b in wire_plane)
    file_levels = len(set(blob))
    file_ones = sum(bin(b).count("1") for b in blob)
    unique_in = set()
    unique_out = set()
    fanin = {}
    share0 = 0
    share1 = 0
    off = hsz + n_wires
    for _i in range(n_gate):
        _op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        off += GATE_STRIDE
        unique_out.add(o)
        unique_in.add(a)
        unique_in.add(b)
        fanin[a] = fanin.get(a, 0) + 1
        fanin[b] = fanin.get(b, 0) + 1
        if a == const0_addr or b == const0_addr:
            share0 += 1
        if a == const1_addr or b == const1_addr:
            share1 += 1
    slots = 2 * n_gate
    uniq_in = len(unique_in)
    hottest_addr = None
    hottest_fan = 0
    for addr, count in fanin.items():
        if count > hottest_fan:
            hottest_addr = addr
            hottest_fan = count
    return {
        "path": path,
        "magic": magic.decode("ascii", "replace"),
        "n_gate": n_gate,
        "n_wires": n_wires,
        "n_in": n_in,
        "n_out": n_out,
        "depth": depth,
        "len": len(blob),
        "const0_addr": const0_addr,
        "const1_addr": const1_addr,
        "const0_written": const0,
        "const1_written": const1,
        "share0": share0,
        "share1": share1,
        "unique_in": uniq_in,
        "unique_out": len(unique_out),
        "unique_out_eq_gates": len(unique_out) == n_gate,
        "input_slots": slots,
        "share_factor": (float(slots) / uniq_in) if uniq_in else 0.0,
        "hottest_addr": hottest_addr,
        "hottest_fan": hottest_fan,
        "plane_levels": plane_levels,
        "plane_ones": plane_ones,
        "file_levels": file_levels,
        "file_ones": file_ones,
        "kind": excerpt_kind(path),
        "titan": "NOT_WRITTEN",
    }


def measure_path(path):
    with open(path, "rb") as handle:
        blob = handle.read()
    return measure_blob(blob, path)


def list_excerpts(root):
    names = []
    if not os.path.isdir(root):
        return names
    for name in sorted(os.listdir(root)):
        if name.endswith(".mno"):
            names.append(os.path.join(root, name))
    return names


def census(paths):
    rows = [measure_path(path) for path in paths]
    with_one = [row for row in rows if row["const1_written"] == 1]
    sharing = [row for row in with_one if row["share1"] > 0]
    best = max(sharing, key=lambda row: row["share1"]) if sharing else None
    densest = max(rows, key=lambda row: row["share_factor"]) if rows else None
    mlc = [row for row in rows if row["kind"] == "plumb_full"]
    chimera = [row for row in rows if row["kind"] == "chimera"]
    return {
        "computer": "host surfaces; excerpts are the addressed substrate",
        "titan": "NOT_WRITTEN",
        "excerpts": len(rows),
        "mlc_excerpts": len(mlc),
        "chimera_excerpts": len(chimera),
        "const1_written": len(with_one),
        "const1_shared": len(sharing),
        "best_share1": best,
        "densest_factor": densest,
        "rows": rows,
    }


def print_row(row):
    print(
        "  %s  kind=%s  magic=%s  gates=%d  C1@%d=%s  share1=%d  factor=%.2f  hottest=(%s,%s)  file_levels=%d"
        % (
            os.path.basename(row["path"]),
            row.get("kind") or excerpt_kind(row.get("path")),
            row["magic"],
            row["n_gate"],
            row["const1_addr"],
            row["const1_written"],
            row["share1"],
            row["share_factor"],
            row["hottest_addr"],
            row["hottest_fan"],
            row["file_levels"],
        )
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    want_json = "--json" in argv
    argv = [arg for arg in argv if arg != "--json"]
    print("SHARED_ONE — I haven't measured yet.")
    if argv:
        paths = [os.path.abspath(arg) for arg in argv]
    else:
        paths = list_excerpts(EXCERPT_DIR)
    if not paths:
        print("NEED_BRYCE — name a .mno or land excerpts/20260823")
        print("  (button dies)")
        return 1
    data = census(paths)
    print("  excerpts=%d  mlc=%d  chimera=%d  written_1=%d  shared_1=%d  titan=%s" % (
        data["excerpts"], data["mlc_excerpts"], data["chimera_excerpts"],
        data["const1_written"], data["const1_shared"], data["titan"]))
    for row in data["rows"]:
        print_row(row)
    best = data["best_share1"]
    densest = data["densest_factor"]
    if best:
        print(
            "  BEST SHARE  %s  one written 1 at %d shared by %d gates"
            % (os.path.basename(best["path"]), best["const1_addr"], best["share1"])
        )
    if densest:
        print(
            "  DENSEST FACTOR  %s  %.2f input-slots per unique address"
            % (os.path.basename(densest["path"]), densest["share_factor"])
        )
    print("  file_levels=256 is MLC discrimination on PLUMB 1-19 full organs.")
    print("  chimera excerpts are small slices; unique-byte count is not 256 and must not be padded.")
    print("  wire plane stays 2 levels (0/1). Overlap is address sharing, not a new spec.")
    print("  (button dies)")
    if want_json:
        print(json.dumps(data, indent=2))
    if data["const1_written"] < 1 or data["const1_shared"] < 1:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
