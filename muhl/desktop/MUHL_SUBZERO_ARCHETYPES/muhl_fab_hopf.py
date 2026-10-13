#!/usr/bin/env python3
"""muhl_fab_hopf.py — FABRICATE muhl_hopf (MUHLHOPF), Hopfield + Hebbian store.

PLUMB 1/3 organ 3. Construction is the gate tax:

  N = 64 bipolar neurons, full connect, 1-bit sign weights
  recall per neuron 64 XNOR (128) + popcount64 (320) + thresh (6) = 454
         64 x 454                                             29,056
  store  w_ij |= XNOR(s_i,s_j), 4096 weight cells x 2 g        8,192
  TOTAL                                                       37,248  depth 24
  CLK state out -> state in. store path is one settle, no host.

popcount64 is 64 full adders (5 g). One unused pad FA keeps the 5n
budget. The other 63 are a 6-level carry tree. Threshold is 6 gates
so declared depth stays 24. Store is XOR+NOT remapped onto weight
wires (one settle).

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno. Does not open titan.gguf.
Does not evaluate the organ. Existing titan circuits and landed excerpts stay.

  python3 muhl_fab_hopf.py          # write .mno + registry sidecar
  python3 muhl_fab_hopf.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_hopf"
MAGIC = b"MUHLHOPF"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N = 64
N_WEIGHTS = N * N
XNOR_PER_NEURON = N * 2
GATES_PER_FA = 5
N_FA = N
N_POP = N_FA * GATES_PER_FA
N_THRESH = 6
GATES_PER_RECALL = XNOR_PER_NEURON + N_POP + N_THRESH
N_RECALL = N * GATES_PER_RECALL
GATES_PER_STORE = 2
N_STORE = N_WEIGHTS * GATES_PER_STORE
N_GATE = N_RECALL + N_STORE
N_IN = N
N_OUT = N
DEPTH = 24

W_CONST0 = 0
W_CONST1 = 1
W_STATE0 = 2
W_WEIGHT0 = W_STATE0 + N
N_WIRES = 2 + N + N_WEIGHTS + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_hopf.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "hopf_circuits.json")


def state_wire(index):
    return W_STATE0 + (index % N)


def weight_wire(i, j):
    return W_WEIGHT0 + i * N + j


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    """Return records, next neuron wires, next weight wires."""
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
    for neuron in range(N):
        start = len(records)
        agrees = []
        for src in range(N):
            x = emit(OP_XOR, state_wire(src), weight_wire(neuron, src))
            agrees.append(emit(OP_NOT, x, x))
        fa(agrees[0], agrees[1], W_CONST0)
        level = list(agrees)
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                nxt.append(fa(level[i], level[i + 1], W_CONST0))
            level = nxt
        if len(level) != 1:
            raise RuntimeError("popcount neuron %d" % neuron)
        root = level[0]
        t0 = emit(OP_NOT, root, root)
        t1 = emit(OP_AND, root, W_CONST1)
        u0 = emit(OP_OR, t0, t1)
        u1 = emit(OP_AND, t0, t1)
        v = emit(OP_OR, u0, u1)
        next_state[neuron] = emit(OP_AND, v, W_CONST1)
        if len(records) - start != GATES_PER_RECALL:
            raise RuntimeError("recall %d count %d" % (neuron, len(records) - start))

    next_weight = [None] * N_WEIGHTS
    for i in range(N):
        for j in range(N):
            start = len(records)
            x = emit(OP_XOR, state_wire(i), state_wire(j))
            next_weight[i * N + j] = emit(OP_NOT, x, x)
            if len(records) - start != GATES_PER_STORE:
                raise RuntimeError("store %d,%d" % (i, j))

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in next_state) or any(w is None for w in next_weight):
        raise RuntimeError("missing next-state wire")
    return records, next_state, next_weight


def fabricate(base_off=0):
    records, next_state, next_weight = build_gates()
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

    records, next_state, _weights = build_gates()
    wire_depth = {wire: 0 for wire in range(W_WEIGHT0 + N_WEIGHTS)}
    max_gate_depth = 0
    for _op, a, b, out in records:
        assert a in wire_depth and b in wire_depth
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        wire_depth[out] = gate_depth
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)
    assert [wire_depth[w] for w in next_state] == [DEPTH] * N

    valid_addresses = {wa(meta["base_off"], wire) for wire in range(N_WIRES)}
    for _op, a, b, out in stored:
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at %d" % i

    for neuron in range(N):
        chunk = stored[neuron * GATES_PER_RECALL:(neuron + 1) * GATES_PER_RECALL]
        xnor = chunk[:XNOR_PER_NEURON]
        assert [g[0] for g in xnor] == ([OP_XOR, OP_NOT] * N)
        pop = chunk[XNOR_PER_NEURON:XNOR_PER_NEURON + N_POP]
        for adder in range(N_FA):
            fa_ops = [g[0] for g in pop[adder * GATES_PER_FA:(adder + 1) * GATES_PER_FA]]
            assert fa_ops == [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR]
        thresh = chunk[XNOR_PER_NEURON + N_POP:]
        assert [g[0] for g in thresh] == [OP_NOT, OP_AND, OP_OR, OP_AND, OP_OR, OP_AND]
    store = stored[N_RECALL:]
    assert len(store) == N_STORE
    assert [g[0] for g in store] == ([OP_XOR, OP_NOT] * N_WEIGHTS)

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
            "container": "muhl_hopf.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "neurons": N,
            "weights": N_WEIGHTS,
            "clock": "state out IS state in; store is one settle",
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
    print("MUHLHOPF structural receipt")
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
