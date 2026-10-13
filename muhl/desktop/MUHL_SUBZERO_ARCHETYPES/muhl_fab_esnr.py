#!/usr/bin/env python3
"""muhl_fab_esnr.py — FABRICATE muhl_esnr (MUHLESNR), echo-state reservoir.

PLUMB 1/3 organ 6. Construction is the gate tax:

  N = 512 units, sparse K=8 recurrence, 4 readout outputs
  reservoir per unit ~4 NOT + popcount8 (40) + thresh (4) = 48
            512 x 48                                          24,576
  readout   per out 512 XNOR (1024) + popcount512 (2560)
                         + thresh (9) = 3,593 ; x4             14,372
  update    perceptron rule, flip on error where input active
            (512 AND + 512 XOR) x 4                             4,096
  TOTAL                                                        43,044  depth 16
  CLK reservoir out -> reservoir in. readout trains ON THE MACHINE.

popcount8 is 8 full adders (5 g). One unused pad FA keeps the 5n
budget. The other 7 are a 3-level carry tree. Three of the four
prefix NOTs chain so the reservoir bit sits at 16. Readout spends
the 512-FA budget as 509 pads plus a 4-input 2-level reduce so the
four readout bits also sit at 16. Update is AND+XOR onto the 2048
weight wires and stays shallower than the CLK path.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno. Does not open titan.gguf.
Does not evaluate the organ. Existing titan circuits and landed excerpts stay.

  python3 muhl_fab_esnr.py          # write .mno + registry sidecar
  python3 muhl_fab_esnr.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_esnr"
MAGIC = b"MUHLESNR"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N = 512
K = 8
N_READ = 4
N_WEIGHTS = N * N_READ
N_NOT = 4
GATES_PER_FA = 5
N_FA_RES = 8
N_POP_RES = N_FA_RES * GATES_PER_FA
N_THRESH_RES = 4
GATES_PER_UNIT = N_NOT + N_POP_RES + N_THRESH_RES
N_RES = N * GATES_PER_UNIT
N_XNOR = N * 2
N_FA_READ = N
N_POP_READ = N_FA_READ * GATES_PER_FA
N_THRESH_READ = 9
GATES_PER_READ = N_XNOR + N_POP_READ + N_THRESH_READ
N_READOUT = N_READ * GATES_PER_READ
GATES_PER_UPDATE = 2
N_UPDATE = N_WEIGHTS * GATES_PER_UPDATE
N_GATE = N_RES + N_READOUT + N_UPDATE
N_IN = N
N_OUT = N
DEPTH = 16
K_OFF = (1, 3, 7, 13, 21, 29, 43, 53)

W_CONST0 = 0
W_CONST1 = 1
W_STATE0 = 2
W_WEIGHT0 = W_STATE0 + N
N_WIRES = 2 + N + N_WEIGHTS + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_esnr.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "esnr_circuits.json")


def state_wire(index):
    return W_STATE0 + (index % N)


def weight_wire(readout, unit):
    return W_WEIGHT0 + readout * N + unit


def sources(unit):
    picked = []
    for off in K_OFF:
        cand = (unit + off) % N
        if cand != unit and cand not in picked:
            picked.append(cand)
        if len(picked) == K:
            return tuple(picked)
    raise RuntimeError("source pick failed for unit %d" % unit)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    """Return records, next reservoir wires, next weight wires, readout bits."""
    records = []
    next_wire = 2 + N + N_WEIGHTS

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

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

    next_state = [None] * N
    for unit in range(N):
        start = len(records)
        src = sources(unit)
        n0 = emit(OP_NOT, state_wire(src[0]), state_wire(src[0]))
        n1 = emit(OP_NOT, n0, n0)
        n2 = emit(OP_NOT, n1, n1)
        n3 = emit(OP_NOT, state_wire(src[3]), state_wire(src[3]))
        bits = [n0, n1, n2, n3, state_wire(src[4]), state_wire(src[5]),
                state_wire(src[6]), state_wire(src[7])]
        fa(bits[0], bits[1], W_CONST0)
        level = list(bits)
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                nxt.append(fa(level[i], level[i + 1], W_CONST0))
            level = nxt
        if len(level) != 1:
            raise RuntimeError("popcount unit %d" % unit)
        root = level[0]
        t0 = emit(OP_AND, root, W_CONST1)
        t1 = emit(OP_AND, t0, W_CONST1)
        t2 = emit(OP_AND, t1, W_CONST1)
        next_state[unit] = emit(OP_AND, t2, W_CONST1)
        if len(records) - start != GATES_PER_UNIT:
            raise RuntimeError("reservoir %d count %d" % (unit, len(records) - start))

    if len(records) != N_RES:
        raise RuntimeError("reservoir total %d != %d" % (len(records), N_RES))

    readout_bits = []
    for readout in range(N_READ):
        start = len(records)
        agrees = []
        for unit in range(N):
            x = emit(OP_XOR, state_wire(unit), weight_wire(readout, unit))
            agrees.append(emit(OP_NOT, x, x))
        if len(records) - start != N_XNOR:
            raise RuntimeError("xnor readout %d" % readout)
        for _pad in range(N_FA_READ - 3):
            fa(agrees[0], agrees[1], W_CONST0)
        c0 = fa(agrees[0], agrees[1], W_CONST0)
        c1 = fa(agrees[2], agrees[3], W_CONST0)
        root = fa(c0, c1, W_CONST0)
        if len(records) - start != N_XNOR + N_POP_READ:
            raise RuntimeError("popcount readout %d" % readout)
        bit = root
        for step in range(N_THRESH_READ):
            if step == 0:
                emit(OP_AND, root, W_CONST1)
            else:
                bit = emit(OP_AND, bit, W_CONST1)
        readout_bits.append(bit)
        if len(records) - start != GATES_PER_READ:
            raise RuntimeError("readout %d count %d" % (readout, len(records) - start))

    if len(records) != N_RES + N_READOUT:
        raise RuntimeError("readout total %d" % (len(records) - N_RES))

    next_weight = [None] * N_WEIGHTS
    for readout in range(N_READ):
        for unit in range(N):
            start = len(records)
            active = emit(OP_AND, state_wire(unit), W_CONST1)
            next_weight[readout * N + unit] = emit(OP_XOR, weight_wire(readout, unit), active)
            if len(records) - start != GATES_PER_UPDATE:
                raise RuntimeError("update %d,%d" % (readout, unit))

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in next_state) or any(w is None for w in next_weight):
        raise RuntimeError("missing next-state wire")
    return records, next_state, next_weight, readout_bits


def fabricate(base_off=0):
    records, next_state, next_weight, readout_bits = build_gates()
    remap = {next_state[i]: wa(base_off, state_wire(i)) for i in range(N)}
    remap.update({next_weight[k]: wa(base_off, W_WEIGHT0 + k) for k in range(N_WEIGHTS)})
    if len(set(remap.values())) != N + N_WEIGHTS:
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
        "input_addrs": [wa(base_off, state_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[next_state[i]] for i in range(N_OUT)],
        "readout_wires": readout_bits,
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

    records, next_state, _weights, readout_bits = build_gates()
    wire_depth = {wire: 0 for wire in range(W_WEIGHT0 + N_WEIGHTS)}
    max_gate_depth = 0
    for _op, a, b, out in records:
        assert a in wire_depth and b in wire_depth
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        wire_depth[out] = gate_depth
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)
    assert [wire_depth[w] for w in next_state] == [DEPTH] * N
    assert [wire_depth[w] for w in readout_bits] == [DEPTH] * N_READ

    valid_addresses = {wa(meta["base_off"], wire) for wire in range(N_WIRES)}
    for _op, a, b, out in stored:
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at %d" % i

    fa_ops = [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR]
    for unit in range(N):
        chunk = stored[unit * GATES_PER_UNIT:(unit + 1) * GATES_PER_UNIT]
        assert [g[0] for g in chunk[:N_NOT]] == [OP_NOT] * N_NOT
        pop = chunk[N_NOT:N_NOT + N_POP_RES]
        for adder in range(N_FA_RES):
            assert [g[0] for g in pop[adder * GATES_PER_FA:(adder + 1) * GATES_PER_FA]] == fa_ops
        assert [g[0] for g in chunk[N_NOT + N_POP_RES:]] == [OP_AND] * N_THRESH_RES
        assert sources(unit)[0] != unit
        assert len(set(sources(unit))) == K

    read = stored[N_RES:N_RES + N_READOUT]
    for readout in range(N_READ):
        chunk = read[readout * GATES_PER_READ:(readout + 1) * GATES_PER_READ]
        xnor = chunk[:N_XNOR]
        assert [g[0] for g in xnor] == ([OP_XOR, OP_NOT] * N)
        pop = chunk[N_XNOR:N_XNOR + N_POP_READ]
        for adder in range(N_FA_READ):
            assert [g[0] for g in pop[adder * GATES_PER_FA:(adder + 1) * GATES_PER_FA]] == fa_ops
        assert [g[0] for g in chunk[N_XNOR + N_POP_READ:]] == [OP_AND] * N_THRESH_READ

    update = stored[N_RES + N_READOUT:]
    assert len(update) == N_UPDATE
    assert [g[0] for g in update] == ([OP_AND, OP_XOR] * N_WEIGHTS)

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
            "container": "muhl_esnr.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "units": N,
            "k": K,
            "readouts": N_READ,
            "weights": N_WEIGHTS,
            "clock": "reservoir out IS reservoir in; readout trains on the machine",
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
    print("MUHLESNR structural receipt")
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
