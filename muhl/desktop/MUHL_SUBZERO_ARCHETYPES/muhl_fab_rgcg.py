#!/usr/bin/env python3
"""muhl_fab_rgcg.py — FABRICATE muhl_rgcg (MUHLRGCG), Renormalisation Group.

PLUMB 2/3 organ 15. Construction is the gate count:

  32x32 = 1024 cells, 2x2 block-spin majority, 4 levels
  per block popcount4 (20) + threshold (3) = 23
  256 + 64 + 16 + 4 = 340 blocks x 23 = 7,820  depth 32

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Does not open titan.gguf. Does not walk the organ as inference.
Existing 19 titan circuits and organs 7/11/17/19 stay untouched.

  python3 muhl_fab_rgcg.py          # write .mno + registry sidecar
  python3 muhl_fab_rgcg.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_rgcg"
MAGIC = b"MUHLRGCG"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

GRID0 = 32
N_CELLS = GRID0 * GRID0
LEVEL_BLOCKS = (256, 64, 16, 4)
N_BLOCKS = sum(LEVEL_BLOCKS)
GATES_PER_BLOCK = 23
N_GATE = N_BLOCKS * GATES_PER_BLOCK
N_IN = N_CELLS
N_OUT = 4
DEPTH = 32

W_CONST0 = 0
W_CONST1 = 1
W_CELL0 = 2
N_WIRES = 2 + N_CELLS + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_rgcg.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "rgcg_circuits.json")


def cell_wire(i):
    return W_CELL0 + i


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def level_sources(level, block, prev):
    """2x2 block inputs from the previous plane."""
    width = 16 >> level
    row, col = divmod(block, width)
    src_width = width * 2
    base = (row * 2) * src_width + (col * 2)
    return (
        prev[base],
        prev[base + 1],
        prev[base + src_width],
        prev[base + src_width + 1],
    )


def build_gates():
    records = []
    next_wire = 2 + N_CELLS

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    def fa(a, b, cin):
        x = emit(OP_XOR, a, b)
        s = emit(OP_XOR, x, cin)
        ab = emit(OP_AND, a, b)
        xc = emit(OP_AND, x, cin)
        cout = emit(OP_OR, ab, xc)
        return s, cout

    prev = [cell_wire(i) for i in range(N_CELLS)]
    planes = [prev]
    for level, count in enumerate(LEVEL_BLOCKS):
        nxt = []
        for block in range(count):
            a, b, c, d = level_sources(level, block, prev)
            s, carry = fa(a, W_CONST0, W_CONST0)
            s, carry = fa(s, b, carry)
            s, carry = fa(s, c, carry)
            s, carry = fa(s, d, carry)
            hi = emit(OP_OR, s, carry)
            mid = emit(OP_AND, s, carry)
            bit = emit(OP_OR, hi, mid)
            nxt.append(bit)
            if len(records) != sum(LEVEL_BLOCKS[:level]) * GATES_PER_BLOCK + (block + 1) * GATES_PER_BLOCK:
                raise RuntimeError("level %d block %d count %d" % (level, block, len(records)))
        planes.append(nxt)
        prev = nxt

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    return records, planes[-1]


def fabricate(base_off=0):
    records, top = build_gates()
    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    out_addrs = [wa(base_off, w) for w in top]
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, out_addrs[i])
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1

    off = gate_start
    stored = []
    for op, a, b, out_w in records:
        out_addr = wa(base_off, out_w)
        a_addr = wa(base_off, a)
        b_addr = wa(base_off, b)
        struct.pack_into("<BQQQ", blob, off, op, a_addr, b_addr, out_addr)
        stored.append((op, a_addr, b_addr, out_addr))
        off += GATE_STRIDE

    meta = {
        "name": NAME,
        "magic": MAGIC.decode(),
        "n_gate": N_GATE,
        "n_wires": N_WIRES,
        "n_in": N_IN,
        "n_out": N_OUT,
        "depth": DEPTH,
        "len": total,
        "base_off": base_off,
        "input_addrs": [wa(base_off, cell_wire(i)) for i in range(N_IN)],
        "output_addrs": out_addrs,
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    """Structural receipt only. Does not walk the organ as inference."""
    assert blob[:8] == MAGIC, "bad magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert (ng, nw, ni, no, dp) == (N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    assert len(blob) == meta["len"] == hdr_size() + N_WIRES + N_GATE * GATE_STRIDE
    assert len(stored) == N_GATE

    writers = {}
    off = hdr_size() + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert (op, a, b, o) == (eop, ea, eb, eo), "gate %d" % i
        assert op in (OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT)
        assert o not in writers
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]

    for block in range(N_BLOCKS):
        chunk = stored[block * GATES_PER_BLOCK:(block + 1) * GATES_PER_BLOCK]
        ops = [g[0] for g in chunk]
        assert ops.count(OP_XOR) == 8, "block %d XOR" % block
        assert ops.count(OP_AND) == 9, "block %d AND" % block
        assert ops.count(OP_OR) == 6, "block %d OR" % block
        assert len(chunk) == GATES_PER_BLOCK

    hsz = hdr_size()
    assert blob[hsz + W_CONST0] == 0 and blob[hsz + W_CONST1] == 1
    return True


def write_files(blob, meta):
    os.makedirs(os.path.dirname(MNO_PATH), exist_ok=True)
    with open(MNO_PATH, "wb") as f:
        f.write(blob)
    sidecar = {
        NAME: {
            "name": NAME,
            "magic": meta["magic"],
            "n_gate": meta["n_gate"],
            "n_wires": meta["n_wires"],
            "n_in": meta["n_in"],
            "n_out": meta["n_out"],
            "depth": meta["depth"],
            "len": meta["len"],
            "offset": 0,
            "container": "muhl_rgcg.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "four-level 2x2 majority; result plane is the top 4 bits",
            "titan": "NOT_WRITTEN",
        }
    }
    with open(REG_PATH, "w") as f:
        json.dump(sidecar, f, indent=2)
        f.write("\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry" in argv
    blob, meta, stored = fabricate(0)
    verify_physical(blob, meta, stored)
    print("MUHLRGCG structural receipt")
    print("  n_gate=%d n_wires=%d n_in=%d n_out=%d depth=%d" % (
        meta["n_gate"], meta["n_wires"], meta["n_in"], meta["n_out"], meta["depth"]))
    print("  len=%d sha256=%s" % (meta["len"], meta["sha256"]))
    print("  titan: NOT_WRITTEN")
    if dry:
        print("  --dry: no files written")
        return 0
    write_files(blob, meta)
    print("  wrote %s" % MNO_PATH)
    print("  wrote %s" % REG_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
