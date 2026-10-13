#!/usr/bin/env python3
"""muhl_fab_grbn.py — FABRICATE muhl_grbn (MUHLGRBN), Kauffman RBN.

PLUMB 1/3 organ 7. Construction is the gate count:

  N = 256 nodes, K = 3, truth table baked at fab
  per node 3-to-8 decoder (3 NOT + 8 AND2 = 19) + 8 table AND + OR-tree 7 = 34
  256 x 34 = 8,704 gates, depth 7
  CLK node state out -> node state in. one update = one settle.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno next to this file.
Does not open titan.gguf. Does not evaluate the organ.
Existing 19 titan circuits stay untouched.

  python3 muhl_fab_grbn.py          # write .mno + registry sidecar
  python3 muhl_fab_grbn.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_grbn"
MAGIC = b"MUHLGRBN"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_NODES = 256
K = 3
GATES_PER_NODE = 34
N_GATE = N_NODES * GATES_PER_NODE
N_IN = N_NODES
N_OUT = N_NODES
DEPTH = 7

# Wire indices (MHA layout): const0, const1, then 256 state bits, then one wire per gate.
W_CONST0 = 0
W_CONST1 = 1
W_STATE0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_grbn.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "grbn_circuits.json")


def state_wire(node):
    return W_STATE0 + node


def sources(node):
    """K=3 NK inputs. Distinct, not self, deterministic."""
    a = (node + 1) % N_NODES
    b = (node + 17) % N_NODES
    c = (node + 41) % N_NODES
    picked = [a]
    for cand in (b, c, (node + 67) % N_NODES, (node + 97) % N_NODES):
        if cand != node and cand not in picked:
            picked.append(cand)
        if len(picked) == K:
            return tuple(picked)
    raise RuntimeError("source pick failed for node %d" % node)


def table_byte(node):
    """Baked 8-bit truth table. NK landscape, one byte per node."""
    x = (node * 0x45D9F3B) ^ 0xA5A5A5
    x = (x ^ (x >> 8)) & 0xFF
    return x


def build_gates():
    """Return (records, next_state_wires).

    records: list of (op, a_wire, b_wire, out_wire)
    next_state_wires[i] is the OR-root wire for node i (remapped to state i on store).
    """
    records = []
    next_state = [None] * N_NODES
    next_wire = 2 + N_IN

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    for node in range(N_NODES):
        s0, s1, s2 = (state_wire(s) for s in sources(node))
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
        tbl = table_byte(node)
        terms = []
        for t in range(8):
            const = W_CONST1 if ((tbl >> t) & 1) else W_CONST0
            terms.append(emit(OP_AND, minterms[t], const))
        level = terms
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                nxt.append(emit(OP_OR, level[i], level[i + 1]))
            level = nxt
        next_state[node] = level[0]

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in next_state):
        raise RuntimeError("missing next-state wire")
    return records, next_state


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def fabricate(base_off=0):
    records, next_state = build_gates()
    remap = {next_state[i]: wa(base_off, state_wire(i)) for i in range(N_NODES)}
    if len(set(remap.values())) != N_NODES:
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
        "sources": [list(sources(i)) for i in range(N_NODES)],
        "tables": [table_byte(i) for i in range(N_NODES)],
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
        assert stored_out == meta["input_addrs"][i], "self-clock broken at node %d" % i

    # 34 gates per node, ops split as 3 NOT + 16 decoder AND + 8 table AND + 7 OR
    for node in range(N_NODES):
        chunk = stored[node * GATES_PER_NODE:(node + 1) * GATES_PER_NODE]
        ops = [g[0] for g in chunk]
        assert ops.count(OP_NOT) == 3, "node %d NOT" % node
        assert ops.count(OP_AND) == 24, "node %d AND" % node
        assert ops.count(OP_OR) == 7, "node %d OR" % node
        assert len(chunk) == GATES_PER_NODE

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
            "container": "muhl_grbn.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "state out IS state in",
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
    print("MUHLGRBN structural receipt")
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
