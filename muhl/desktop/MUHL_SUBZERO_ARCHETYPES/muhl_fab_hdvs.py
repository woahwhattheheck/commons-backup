#!/usr/bin/env python3
"""muhl_fab_hdvs.py — FABRICATE muhl_hdvs (MUHLHDVS), hyperdimensional vectors.

PLUMB 1/3 organ 1. Construction is the gate count:

  D = 1024-bit hypervectors. bind=XOR bundle=majority sequence=permute
  BIND 1024 XOR                                                1,024
  BUNDLE majority-3 per bit, 5 g                               5,120
  PERMUTE address remap                                            0
  SIM XOR 1024 + popcount(1024) 5x1024                         6,144
  TOTAL 12,288  depth 34

Sequence is a rotate. Zero gates. Dest from this lattice, not invented.
Bind XORs bit i with rotate-1. Bundle majority of (A, rotate-3, rotate-17).
Sim XORs the bundled vector with the bound vector, then a 10-level carry
tree of 1024 full adders (5 g, depth 3) reduces the 1024 difference bits.
Carry-out is the reduction bit so each level adds 3 and the last carry sits at 34.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno next to this file.
Does not open titan.gguf. Does not evaluate the organ.
Existing titan circuits and landed excerpts stay untouched.

  python3 muhl_fab_hdvs.py          # write .mno + registry sidecar
  python3 muhl_fab_hdvs.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_hdvs"
MAGIC = b"MUHLHDVS"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

D = 1024
N_BIND = D
GATES_PER_MAJ = 5
N_BUNDLE = D * GATES_PER_MAJ
N_SIM_XOR = D
GATES_PER_FA = 5
N_FA = D
N_POP = N_FA * GATES_PER_FA
N_GATE = N_BIND + N_BUNDLE + N_SIM_XOR + N_POP
N_IN = D
N_OUT = D
DEPTH = 34
PERM_BIND = 1
PERM_BUNDLE_A = 3
PERM_BUNDLE_B = 17

W_CONST0 = 0
W_CONST1 = 1
W_VEC0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_hdvs.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "hdvs_circuits.json")


def vec_wire(index):
    return W_VEC0 + (index % D)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    """Return records and the 1024 bundled result wires.

    records: list of (op, a_wire, b_wire, out_wire)
    """
    records = []
    next_wire = 2 + N_IN

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    def majority3(a, b, c):
        start = len(records)
        ab = emit(OP_AND, a, b)
        ac = emit(OP_AND, a, c)
        bc = emit(OP_AND, b, c)
        t = emit(OP_OR, ab, ac)
        bit = emit(OP_OR, t, bc)
        if len(records) - start != GATES_PER_MAJ:
            raise RuntimeError("majority gate count")
        return bit

    def fa(a, b, cin):
        start = len(records)
        x = emit(OP_XOR, a, b)
        _s = emit(OP_XOR, x, cin)
        ab = emit(OP_AND, a, b)
        xc = emit(OP_AND, x, cin)
        cout = emit(OP_OR, ab, xc)
        if len(records) - start != GATES_PER_FA:
            raise RuntimeError("FA gate count")
        return cout

    bound = []
    for i in range(D):
        bound.append(emit(OP_XOR, vec_wire(i), vec_wire(i + PERM_BIND)))
    if len(records) != N_BIND:
        raise RuntimeError("bind count %d" % len(records))

    bundled = []
    for i in range(D):
        bundled.append(majority3(
            vec_wire(i),
            vec_wire(i + PERM_BUNDLE_A),
            vec_wire(i + PERM_BUNDLE_B),
        ))
    if len(records) != N_BIND + N_BUNDLE:
        raise RuntimeError("bundle count %d" % len(records))

    sim = []
    for i in range(D):
        sim.append(emit(OP_XOR, bundled[i], bound[i]))
    if len(records) != N_BIND + N_BUNDLE + N_SIM_XOR:
        raise RuntimeError("sim xor count %d" % len(records))

    # One unused pad FA keeps the 5n budget at 1024 adders. Reduction uses
    # the other 1023: 512 + 256 + 128 + 64 + 32 + 16 + 8 + 4 + 2 + 1.
    fa(sim[0], sim[1], W_CONST0)
    level = list(sim)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            nxt.append(fa(level[i], level[i + 1], W_CONST0))
        level = nxt
    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if len(level) != 1:
        raise RuntimeError("popcount did not reduce to one carry")
    return records, bundled, level[0]


def fabricate(base_off=0):
    records, bundled, pop_root = build_gates()
    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    out_addrs = [wa(base_off, w) for w in bundled]
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
        "input_addrs": [wa(base_off, vec_wire(i)) for i in range(N_IN)],
        "output_addrs": out_addrs,
        "pop_root_addr": wa(base_off, pop_root),
        "perm_bind": PERM_BIND,
        "perm_bundle": (PERM_BUNDLE_A, PERM_BUNDLE_B),
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

    input_addresses = {wa(meta["base_off"], wire) for wire in range(W_VEC0 + N_IN)}
    valid_addresses = {wa(meta["base_off"], wire) for wire in range(N_WIRES)}
    wire_depth = {address: 0 for address in input_addresses}
    max_gate_depth = 0
    for _op, a, b, out in stored:
        assert a in wire_depth and b in wire_depth
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        wire_depth[out] = gate_depth
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]

    bind = stored[:N_BIND]
    assert [g[0] for g in bind] == [OP_XOR] * N_BIND
    bundle = stored[N_BIND:N_BIND + N_BUNDLE]
    for i in range(D):
        chunk = bundle[i * GATES_PER_MAJ:(i + 1) * GATES_PER_MAJ]
        ops = [g[0] for g in chunk]
        assert ops == [OP_AND, OP_AND, OP_AND, OP_OR, OP_OR], "maj %d" % i
    sim = stored[N_BIND + N_BUNDLE:N_BIND + N_BUNDLE + N_SIM_XOR]
    assert [g[0] for g in sim] == [OP_XOR] * N_SIM_XOR
    pop = stored[N_BIND + N_BUNDLE + N_SIM_XOR:]
    assert len(pop) == N_POP
    for i in range(N_FA):
        chunk = pop[i * GATES_PER_FA:(i + 1) * GATES_PER_FA]
        ops = [g[0] for g in chunk]
        assert ops == [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR], "fa %d" % i

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
            "container": "muhl_hdvs.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "bind": "XOR rotate-1",
            "bundle": "majority-3 of A, rotate-3, rotate-17",
            "sequence": "address remap, 0 gates",
            "sim": "bundled XOR bound plus 1024-FA carry tree",
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
    print("MUHLHDVS structural receipt")
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
    raise SystemExit(main())
