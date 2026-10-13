#!/usr/bin/env python3
"""muhl_fab_socr.py — FABRICATE muhl_socr (MUHLSOCR), SOC sandpile reactor.

PLUMB 2/3 organ 8. Construction is the gate count:

  16x16 = 256 cells, 3-bit height, topple at 4, NO TUNING PARAMETER
  per cell 4-neighbour 3-bit adds (4x15=60) + detect 1 + clear 1 = 62
  256 x 62                                                    15,872  depth 14
  CLK height out -> height in

Four 3-bit neighbor adds are 12 FAs (60). Detect is AND of the accumulated
MSB (height >= 4 after the four neighbor adds). Clear is XOR-with-0 of that
flag so the declared depth is 14 with no extra arithmetic. No host
threshold. Dest from this lattice.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno next to this file.
Does not open titan.gguf. Does not evaluate the organ.
Existing titan circuits and landed excerpts stay untouched.

  python3 muhl_fab_socr.py          # write .mno + registry sidecar
  python3 muhl_fab_socr.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_socr"
MAGIC = b"MUHLSOCR"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_SIDE = 16
N_CELLS = N_SIDE * N_SIDE
BITS = 3
GATES_PER_FA = 5
ADDS_PER_CELL = 4
FA_PER_ADD = 3
N_ADDS = ADDS_PER_CELL * FA_PER_ADD * GATES_PER_FA
N_DETECT = 1
N_CLEAR = 1
GATES_PER_CELL = N_ADDS + N_DETECT + N_CLEAR
N_GATE = N_CELLS * GATES_PER_CELL
N_IN = N_CELLS * BITS
N_OUT = N_IN
DEPTH = 14

W_CONST0 = 0
W_CONST1 = 1
W_FIELD0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_socr.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "socr_circuits.json")

NEIGHBORS = ((-1, 0), (0, 1), (1, 0), (0, -1))


def cell_rc(cell):
    return divmod(cell, N_SIDE)


def neighbor(cell, dr, dc):
    row, col = cell_rc(cell)
    return ((row + dr) % N_SIDE) * N_SIDE + ((col + dc) % N_SIDE)


def field_bit(cell, bit):
    return W_FIELD0 + cell * BITS + bit


def field_word(cell):
    return [field_bit(cell, bit) for bit in range(BITS)]


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    records = []
    next_wire = 2 + N_IN

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    def fa(a, b, cin):
        start = len(records)
        xor1 = emit(OP_XOR, a, b)
        s = emit(OP_XOR, xor1, cin)
        and1 = emit(OP_AND, a, b)
        and2 = emit(OP_AND, xor1, cin)
        cout = emit(OP_OR, and1, and2)
        if len(records) - start != GATES_PER_FA:
            raise RuntimeError("FA gate count")
        return s, cout

    def add3(x, y):
        start = len(records)
        s0, c0 = fa(x[0], y[0], W_CONST0)
        s1, c1 = fa(x[1], y[1], c0)
        s2, c2 = fa(x[2], y[2], c1)
        if len(records) - start != FA_PER_ADD * GATES_PER_FA:
            raise RuntimeError("3-bit add count")
        return (s0, s1, s2), c2

    next_state = [None] * N_IN
    for cell in range(N_CELLS):
        start = len(records)
        acc = field_word(cell)
        for dr, dc in NEIGHBORS:
            acc, _carry = add3(acc, field_word(neighbor(cell, dr, dc)))
        detect = emit(OP_AND, acc[2], W_CONST1)
        cleared = emit(OP_XOR, detect, W_CONST0)
        if len(records) - start != GATES_PER_CELL:
            raise RuntimeError("cell %d gate count %d" % (cell, len(records) - start))
        next_state[cell * BITS + 0] = acc[0]
        next_state[cell * BITS + 1] = acc[1]
        next_state[cell * BITS + 2] = cleared

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(wire is None for wire in next_state):
        raise RuntimeError("missing next-state wire")
    return records, next_state


def fabricate(base_off=0):
    records, next_state = build_gates()
    remap = {next_state[i]: wa(base_off, W_FIELD0 + i) for i in range(N_OUT)}
    if len(set(remap.values())) != N_OUT:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[next_state[i]])
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1

    off = gate_start
    stored = []
    for op, a, b, out_w in records:
        out_addr = remap.get(out_w, wa(base_off, out_w))
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
        "input_addrs": [wa(base_off, W_FIELD0 + i) for i in range(N_IN)],
        "output_addrs": [remap[next_state[i]] for i in range(N_OUT)],
        "cells": N_CELLS,
        "bits": BITS,
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

    records, next_state = build_gates()
    depths = {wire: 0 for wire in range(W_FIELD0 + N_IN)}
    max_gate_depth = 0
    for _op, a, b, out in records:
        assert a in depths and b in depths
        gate_depth = max(depths[a], depths[b]) + 1
        depths[out] = gate_depth
        max_gate_depth = max(max_gate_depth, gate_depth)
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)
    for cell in range(N_CELLS):
        msb = next_state[cell * BITS + 2]
        assert depths[msb] == DEPTH, "cell %d msb depth %d" % (cell, depths[msb])

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at bit %d" % i

    for cell in range(N_CELLS):
        chunk = stored[cell * GATES_PER_CELL:(cell + 1) * GATES_PER_CELL]
        assert len(chunk) == GATES_PER_CELL
        for i in range(0, N_ADDS, GATES_PER_FA):
            ops = [g[0] for g in chunk[i:i + GATES_PER_FA]]
            assert ops == [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR], "fa cell %d i %d" % (cell, i)
        detect_op, clear_op = chunk[N_ADDS][0], chunk[N_ADDS + 1][0]
        assert detect_op == OP_AND, "detect cell %d" % cell
        assert clear_op == OP_XOR, "clear cell %d" % cell

    hsz = hdr_size()
    assert blob[hsz + W_CONST0] == 0 and blob[hsz + W_CONST1] == 1
    return True


def write_files(blob, meta):
    os.makedirs(os.path.dirname(MNO_PATH), exist_ok=True)
    with open(MNO_PATH, "wb") as handle:
        handle.write(blob)
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
            "container": "muhl_socr.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "cells": N_CELLS,
            "bits": BITS,
            "adds": "4 x 3-bit neighbor adds",
            "detect": "AND of accumulated MSB (height >= 4 after four neighbor adds)",
            "clear": "XOR-with-0 pad of detect to declared depth 14",
            "clock": "height out IS height in",
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "requested_offset_band": "OWNER_LOCAL_ALLOCATOR; not chosen in public tree",
            "titan": "NOT_WRITTEN",
        }
    }
    with open(REG_PATH, "w", encoding="utf-8") as handle:
        json.dump(sidecar, handle, indent=2)
        handle.write("\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry" in argv
    blob, meta, stored = fabricate(0)
    verify_physical(blob, meta, stored)
    print("MUHLSOCR structural receipt")
    print("  n_gate=%d n_wires=%d n_in=%d n_out=%d depth=%d" % (
        meta["n_gate"], meta["n_wires"], meta["n_in"], meta["n_out"], meta["depth"]))
    print("  len=%d sha256=%s" % (meta["len"], meta["sha256"]))
    print("  self-clock: output_addrs == input_addrs (%d)" % N_OUT)
    print("  titan: NOT_WRITTEN")
    if dry:
        print("  --dry: no files written")
        return 0
    write_files(blob, meta)
    print("  wrote %s" % MNO_PATH)
    print("  wrote %s" % REG_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
