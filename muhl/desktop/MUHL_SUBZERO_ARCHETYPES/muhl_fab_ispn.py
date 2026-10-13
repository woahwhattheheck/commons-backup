#!/usr/bin/env python3
"""muhl_fab_ispn.py — FABRICATE muhl_ispn (MUHLISPN), Ising annealer.

PLUMB 2/3 organ 11. Construction is the gate count:

  N = 256 spins, 4-neighbour
  per spin 4 XNOR (8) + popcount4 (20) + temp threshold (6) = 34
  256 x 34 = 8,704
  16-bit anneal counter, 16 FA = 80
  TOTAL 8,784 gates, depth 12
  CLK spin out -> spin in. temperature descends in gates.
  NO host schedule.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno next to this file.
Does not open titan.gguf. Does not evaluate the organ.
Existing 19 titan circuits and organ 7 stay untouched.

  python3 muhl_fab_ispn.py          # write .mno + registry sidecar
  python3 muhl_fab_ispn.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_ispn"
MAGIC = b"MUHLISPN"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_SPINS = 256
GRID = 16
N_CNT = 16
GATES_PER_SPIN = 34
N_SPIN_GATES = N_SPINS * GATES_PER_SPIN
N_CNT_GATES = N_CNT * 5
N_GATE = N_SPIN_GATES + N_CNT_GATES
N_IN = N_SPINS
N_OUT = N_SPINS
DEPTH = 12

# Wire indices: const0, const1, 256 spins, 16 counter bits, then one wire per gate.
W_CONST0 = 0
W_CONST1 = 1
W_SPIN0 = 2
W_CNT0 = W_SPIN0 + N_SPINS
N_WIRES = 2 + N_SPINS + N_CNT + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_ispn.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "ispn_circuits.json")


def spin_wire(i):
    return W_SPIN0 + i


def cnt_wire(i):
    return W_CNT0 + i


def neighbors(i):
    """4-neighbour wrap on 16x16. Dest from this lattice, not invented."""
    r, c = divmod(i, GRID)
    return (
        r * GRID + (c + 1) % GRID,
        r * GRID + (c - 1) % GRID,
        ((r + 1) % GRID) * GRID + c,
        ((r - 1) % GRID) * GRID + c,
    )


def build_gates():
    """Return (records, next_spin, next_cnt).

    records: list of (op, a_wire, b_wire, out_wire)
    next_spin[i] / next_cnt[i] remapped onto the matching state wires on store.
    """
    records = []
    next_spin = [None] * N_SPINS
    next_cnt = [None] * N_CNT
    next_wire = 2 + N_SPINS + N_CNT

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    def fa(a, b, cin):
        xor1 = emit(OP_XOR, a, b)
        s = emit(OP_XOR, xor1, cin)
        and1 = emit(OP_AND, a, b)
        and2 = emit(OP_AND, xor1, cin)
        cout = emit(OP_OR, and1, and2)
        return s, cout

    # 16 FA decrementer: cnt + 0xFFFF = cnt - 1. High bits start hot after wrap.
    carry = W_CONST0
    for bit in range(N_CNT):
        s, carry = fa(cnt_wire(bit), W_CONST1, carry)
        next_cnt[bit] = s

    # Temperature is current counter high bits. They descend as the counter does.
    t2 = cnt_wire(15)
    t1 = cnt_wire(14)

    for node in range(N_SPINS):
        me = spin_wire(node)
        agrees = []
        for nb in neighbors(node):
            x = emit(OP_XOR, me, spin_wire(nb))
            agrees.append(emit(OP_NOT, x, x))
        a, b, c, d = agrees
        # popcount4 as 4 FA = 20. FA(d,0,0) copies the fourth agree bit.
        ps, pc = fa(a, b, c)
        ds, dc = fa(d, W_CONST0, W_CONST0)
        sum0, c0 = fa(ps, ds, W_CONST0)
        sum1, sum2 = fa(pc, dc, c0)
        del sum0
        # temp threshold (6): flip when hot and not fully / strongly aligned.
        n2 = emit(OP_NOT, sum2, sum2)
        n1 = emit(OP_NOT, sum1, sum1)
        hot_mis = emit(OP_AND, t2, n2)
        warm_low = emit(OP_AND, t1, n1)
        should_flip = emit(OP_OR, hot_mis, warm_low)
        next_spin[node] = emit(OP_XOR, me, should_flip)

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in next_spin) or any(w is None for w in next_cnt):
        raise RuntimeError("missing next-state wire")
    return records, next_spin, next_cnt


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def fabricate(base_off=0):
    records, next_spin, next_cnt = build_gates()
    remap = {next_spin[i]: wa(base_off, spin_wire(i)) for i in range(N_SPINS)}
    remap.update({next_cnt[i]: wa(base_off, cnt_wire(i)) for i in range(N_CNT)})
    if len(set(remap.values())) != N_SPINS + N_CNT:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[next_spin[i]])
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
        "input_addrs": [wa(base_off, spin_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[next_spin[i]] for i in range(N_OUT)],
        "counter_addrs": [wa(base_off, cnt_wire(i)) for i in range(N_CNT)],
        "neighbors": [list(neighbors(i)) for i in range(N_SPINS)],
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    """Structural receipt only. Does not walk the organ as inference."""
    assert blob[:8] == MAGIC, "bad magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert ng == N_GATE and nw == N_WIRES and ni == N_IN and no == N_OUT and dp == DEPTH
    assert len(blob) == meta["len"]
    assert meta["n_gate"] == N_GATE
    assert len(stored) == N_GATE
    hsz = hdr_size()
    assert hsz + N_WIRES + N_GATE * GATE_STRIDE == len(blob)

    writers = {}
    off = hsz + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert op == eop and a == ea and b == eb and o == eo, "gate %d record" % i
        assert op in (OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT), "gate %d op" % i
        assert o not in writers, "out reused by gates %d and %d" % (writers[o], i)
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at spin %d" % i

    cnt_chunk = stored[:N_CNT_GATES]
    assert len(cnt_chunk) == 80
    assert [g[0] for g in cnt_chunk].count(OP_XOR) == 32
    assert [g[0] for g in cnt_chunk].count(OP_AND) == 32
    assert [g[0] for g in cnt_chunk].count(OP_OR) == 16

    for node in range(N_SPINS):
        chunk = stored[N_CNT_GATES + node * GATES_PER_SPIN:
                       N_CNT_GATES + (node + 1) * GATES_PER_SPIN]
        ops = [g[0] for g in chunk]
        assert len(chunk) == GATES_PER_SPIN
        assert ops.count(OP_XOR) == 13, "spin %d XOR" % node
        assert ops.count(OP_NOT) == 6, "spin %d NOT" % node
        assert ops.count(OP_AND) == 10, "spin %d AND" % node
        assert ops.count(OP_OR) == 5, "spin %d OR" % node

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
            "container": "muhl_ispn.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "spin out IS spin in; anneal counter self-clocks",
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
    print("MUHLISPN structural receipt")
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
