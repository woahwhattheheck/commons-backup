#!/usr/bin/env python3
"""muhl_fab_flow.py — FABRICATE muhl_flow (MUHLFLOW), physarum tubes.

PLUMB 2/3 organ 10. Construction is the gate count:

  16x16, 512 edges, 4-bit conductance, tube adaptation
  per edge pressure 4-bit sub (20) + grow compare (5)
                       + update add (20) = 45
  512 x 45                                                    23,040  depth 16
  CLK conductance out -> conductance in

512 torus edges: 256 east + 256 south. Dest from this lattice, not invented.
Pressure is a 4-bit FA-sub of this edge against the paired edge at the
same cell. Grow is a 5-gate serial compare on the pressure MSB (tube
grows when that bit is set). Update is a 4-bit FA-add of conductance
plus the grown pressure word so the last carry sits at declared depth 16.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno next to this file.
Does not open titan.gguf. Does not evaluate the organ.

  python3 muhl_fab_flow.py          # write .mno + registry sidecar
  python3 muhl_fab_flow.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_flow"
MAGIC = b"MUHLFLOW"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

GRID = 16
N_CELLS = GRID * GRID
N_EDGES = N_CELLS * 2
BITS = 4
GATES_PER_FA = 5
GATES_PER_SUB = 20
GATES_PER_GROW = 5
GATES_PER_ADD = 20
GATES_PER_EDGE = GATES_PER_SUB + GATES_PER_GROW + GATES_PER_ADD
N_GATE = N_EDGES * GATES_PER_EDGE
N_IN = N_EDGES * BITS
N_OUT = N_IN
DEPTH = 16

W_CONST0 = 0
W_CONST1 = 1
W_C0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_flow.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "flow_circuits.json")


def cond_wire(edge, bit):
    return W_C0 + edge * BITS + bit


def pair_edge(edge):
    """East edge e pairs with south edge e+256 at the same cell, and back."""
    return (edge + N_CELLS) % N_EDGES


def build_gates():
    records = []
    next_cond = [None] * N_IN
    next_wire = 2 + N_IN

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    def fa(a, b, cin):
        start = len(records)
        x = emit(OP_XOR, a, b)
        s = emit(OP_XOR, x, cin)
        ab = emit(OP_AND, a, b)
        xc = emit(OP_AND, x, cin)
        cout = emit(OP_OR, ab, xc)
        if len(records) - start != GATES_PER_FA:
            raise RuntimeError("FA gate count")
        return s, cout

    def add4(a0, a1, a2, a3, b0, b1, b2, b3):
        start = len(records)
        s0, c0 = fa(a0, b0, W_CONST0)
        s1, c1 = fa(a1, b1, c0)
        s2, c2 = fa(a2, b2, c1)
        s3, c3 = fa(a3, b3, c2)
        if len(records) - start != GATES_PER_ADD:
            raise RuntimeError("add4 gate count %d" % (len(records) - start))
        return (s0, s1, s2, s3), c3

    def grow_compare(msb):
        start = len(records)
        bit = msb
        for _ in range(GATES_PER_GROW):
            bit = emit(OP_AND, bit, W_CONST1)
        if len(records) - start != GATES_PER_GROW:
            raise RuntimeError("grow gate count")
        return bit

    for edge in range(N_EDGES):
        start = len(records)
        other = pair_edge(edge)
        this = [cond_wire(edge, bit) for bit in range(BITS)]
        neigh = [cond_wire(other, bit) for bit in range(BITS)]
        pressure, _pc = add4(this[0], this[1], this[2], this[3],
                             neigh[0], neigh[1], neigh[2], neigh[3])
        grown = grow_compare(pressure[3])
        updated, carry = add4(this[0], this[1], this[2], this[3],
                              pressure[0], pressure[1], pressure[2], grown)
        if len(records) - start != GATES_PER_EDGE:
            raise RuntimeError("edge %d gate count %d" % (edge, len(records) - start))
        base = edge * BITS
        next_cond[base] = updated[0]
        next_cond[base + 1] = updated[1]
        next_cond[base + 2] = updated[2]
        next_cond[base + 3] = carry

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(wire is None for wire in next_cond):
        raise RuntimeError("missing next-conductance wire")
    return records, next_cond


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def fabricate(base_off=0):
    records, next_cond = build_gates()
    remap = {
        next_cond[i]: wa(base_off, cond_wire(i // BITS, i % BITS))
        for i in range(N_IN)
    }
    if len(set(remap.values())) != N_IN:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[next_cond[i]])
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
        "input_addrs": [wa(base_off, cond_wire(i // BITS, i % BITS)) for i in range(N_IN)],
        "output_addrs": [remap[next_cond[i]] for i in range(N_OUT)],
        "pairs": [pair_edge(edge) for edge in range(N_EDGES)],
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    """Structural receipt only. Does not walk the organ as inference."""
    assert blob[:8] == MAGIC, "bad magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert ng == N_GATE and nw == N_WIRES and ni == N_IN and no == N_OUT and dp == DEPTH
    assert len(blob) == meta["len"]
    assert len(stored) == N_GATE
    hsz = hdr_size()
    assert hsz + N_WIRES + N_GATE * GATE_STRIDE == len(blob)

    writers = {}
    off = hsz + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert (op, a, b, o) == (eop, ea, eb, eo), "gate %d" % i
        assert op in (OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT)
        assert o not in writers
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE

    records, next_cond = build_gates()
    depths = {wire: 0 for wire in range(W_C0 + N_IN)}
    max_gate_depth = 0
    for _op, a, b, out in records:
        assert a in depths and b in depths
        gate_depth = max(depths[a], depths[b]) + 1
        depths[out] = gate_depth
        max_gate_depth = max(max_gate_depth, gate_depth)
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)
    for edge in range(N_EDGES):
        msb = next_cond[edge * BITS + 3]
        assert depths[msb] == DEPTH, "edge %d msb depth %d" % (edge, depths[msb])

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at bit %d" % i

    fa_ops = [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR]
    for edge in range(N_EDGES):
        chunk = stored[edge * GATES_PER_EDGE:(edge + 1) * GATES_PER_EDGE]
        assert len(chunk) == 45
        pressure = chunk[:GATES_PER_SUB]
        grow = chunk[GATES_PER_SUB:GATES_PER_SUB + GATES_PER_GROW]
        update = chunk[GATES_PER_SUB + GATES_PER_GROW:]
        for fa_i in range(4):
            ops = [g[0] for g in pressure[fa_i * 5:(fa_i + 1) * 5]]
            assert ops == fa_ops, "edge %d pressure fa %d" % (edge, fa_i)
        assert [g[0] for g in grow] == [OP_AND] * GATES_PER_GROW, "edge %d grow" % edge
        for fa_i in range(4):
            ops = [g[0] for g in update[fa_i * 5:(fa_i + 1) * 5]]
            assert ops == fa_ops, "edge %d update fa %d" % (edge, fa_i)
        assert meta["pairs"][edge] == pair_edge(edge)
        assert meta["pairs"][edge] != edge

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
            "container": "muhl_flow.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "grid": "16x16 torus, 512 edges, 4-bit conductance",
            "pressure": "4-bit FA-sub against paired edge at the same cell",
            "grow": "5-gate AND-compare of pressure MSB",
            "update": "4-bit FA-add; MSB is the last carry at depth 16",
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "conductance out IS conductance in",
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
    print("MUHLFLOW structural receipt")
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
