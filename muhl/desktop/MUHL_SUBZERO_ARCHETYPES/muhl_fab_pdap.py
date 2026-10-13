#!/usr/bin/env python3
"""muhl_fab_pdap.py - FABRICATE muhl_pdap (MUHLPDAP), Pushdown Parser.

PLUMB 2/3 organ 17. 32 steps x 83 gates = 2656. Depth 192.
Header: 8-char magic + LE n_gate, n_wires, n_in, n_out, depth.
Records <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.
Does not open titan.gguf. Does not evaluate the organ.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_pdap"
MAGIC = b"MUHLPDAP"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4
N_STEPS = 32
GATES_PER_STEP = 83
N_GATE = N_STEPS * GATES_PER_STEP
N_IN = 32
N_OUT = 32
DEPTH = 192
W_CONST0 = 0
W_CONST1 = 1
W_STATE0 = 2
N_WIRES = 2 + N_IN + N_GATE
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_pdap.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "pdap_circuits.json")


def state_wire(bit):
    return W_STATE0 + bit


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def or_tree(emit, nodes):
    level = list(nodes)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(emit(OP_OR, level[i], level[i + 1]))
            else:
                nxt.append(level[i])
        level = nxt
    return level[0]


def build_gates():
    records = []
    next_wire = 2 + N_IN
    cur = [state_wire(i) for i in range(N_IN)]

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    for step in range(N_STEPS):
        s0, s1, s2 = cur[0], cur[1], cur[2]
        n0 = emit(OP_NOT, s0, s0)
        n1 = emit(OP_NOT, s1, s1)
        n2 = emit(OP_NOT, s2, s2)
        bits = (s0, s1, s2)
        invs = (n0, n1, n2)
        minterms = []
        for t in range(8):
            a = bits[0] if (t & 1) else invs[0]
            b = bits[1] if (t & 2) else invs[1]
            c = bits[2] if (t & 4) else invs[2]
            ab = emit(OP_AND, a, b)
            minterms.append(emit(OP_AND, ab, c))
        muxed = []
        for j in range(4):
            terms = []
            for t in range(8):
                src = cur[(4 + j + t + step) % N_IN]
                terms.append(emit(OP_AND, minterms[t], src))
            muxed.append(or_tree(emit, terms))
        written = [emit(OP_AND, muxed[j], W_CONST1) for j in range(4)]
        nxt = [None] * N_IN
        for j in range(4):
            nxt[j] = muxed[j]
            nxt[4 + j] = written[j]
        for b in range(8, 32):
            nxt[b] = cur[b - 4]
        cur = nxt
        if len(records) != (step + 1) * GATES_PER_STEP:
            raise RuntimeError("step %d count" % step)
    if len(records) != N_GATE or next_wire != N_WIRES:
        raise RuntimeError("gate/wire mismatch")
    return records, cur


def fabricate(base_off=0):
    records, next_state = build_gates()
    remap = {next_state[i]: wa(base_off, state_wire(i)) for i in range(N_OUT)}
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
        a_addr = remap.get(a, wa(base_off, a))
        b_addr = remap.get(b, wa(base_off, b))
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
        "input_addrs": [wa(base_off, state_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[next_state[i]] for i in range(N_OUT)],
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    assert blob[:8] == MAGIC
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert (ng, nw, ni, no, dp) == (N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    assert len(blob) == meta["len"] == hdr_size() + N_WIRES + N_GATE * GATE_STRIDE
    writers = {}
    off = hdr_size() + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert (op, a, b, o) == (eop, ea, eb, eo)
        assert op in (OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT)
        assert o not in writers
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE
    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i] == meta["input_addrs"][i]
    for step in range(N_STEPS):
        chunk = stored[step * GATES_PER_STEP:(step + 1) * GATES_PER_STEP]
        ops = [g[0] for g in chunk]
        assert ops.count(OP_NOT) == 3
        assert ops.count(OP_AND) == 52
        assert ops.count(OP_OR) == 28
    hsz = hdr_size()
    assert blob[hsz + W_CONST0] == 0 and blob[hsz + W_CONST1] == 1
    return True


def write_files(blob, meta):
    os.makedirs(os.path.dirname(MNO_PATH), exist_ok=True)
    with open(MNO_PATH, "wb") as f:
        f.write(blob)
    sidecar = {NAME: {
        "name": NAME, "magic": meta["magic"], "n_gate": meta["n_gate"],
        "n_wires": meta["n_wires"], "n_in": meta["n_in"], "n_out": meta["n_out"],
        "depth": meta["depth"], "len": meta["len"], "offset": 0,
        "container": "muhl_pdap.mno", "format": "physical", "gate_stride": GATE_STRIDE,
        "input_addrs": meta["input_addrs"], "output_addrs": meta["output_addrs"],
        "sha256": meta["sha256"], "clock": "control/stack out IS control/stack in",
        "titan": "NOT_WRITTEN",
    }}
    with open(REG_PATH, "w") as f:
        json.dump(sidecar, f, indent=2)
        f.write("\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry" in argv
    blob, meta, stored = fabricate(0)
    verify_physical(blob, meta, stored)
    print("MUHLPDAP structural receipt")
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
    sys.exit(main())
