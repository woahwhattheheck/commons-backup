#!/usr/bin/env python3
"""muhl_fab_tset.py — FABRICATE muhl_tset (MUHLTSET), Tsetlin machine.

PLUMB 1/3 organ 5. Construction is the gate tax:

  32 clauses x 32 literals, 4-bit automaton state per literal
  clause per literal include-gate OR+NOT = 2
         per clause 32x2 + AND-tree 31 = 95 ; 32 x 95          3,040
  vote   2 x popcount16 (320) + compare 16                       336
  learn  1024 automata x 4-bit inc/dec (20 g)                  20,480
  TOTAL                                                       23,856  depth 23
  CLK feedback drives the counters. no host update.

Include is NOT(MSB) OR literal so an excluded literal is vacuous true.
popcount16 is 32 full adders (5 g): 17 pad FA keep the 160-gate
budget, 15 reduce the 16 clause bits. Compare is 16 gates so the
vote sits at 23. Learn is one 4-bit increment (4 FA) per automaton,
self-clocked onto the 4-bit state. Increment cin is CONST1 so the
learn path stays shallower than the vote (same settle, no host).

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno. Does not open titan.gguf.
Does not evaluate the organ. Existing titan circuits and landed excerpts stay.

  python3 muhl_fab_tset.py          # write .mno + registry sidecar
  python3 muhl_fab_tset.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_tset"
MAGIC = b"MUHLTSET"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_CLAUSE = 32
N_LIT = 32
N_AUTO = N_CLAUSE * N_LIT
BITS = 4
GATES_PER_INCLUDE = 2
N_AND = N_LIT - 1
GATES_PER_CLAUSE = N_LIT * GATES_PER_INCLUDE + N_AND
N_CLAUSE_GATES = N_CLAUSE * GATES_PER_CLAUSE
GATES_PER_FA = 5
N_FA_POP = 32
N_POP = N_FA_POP * GATES_PER_FA
N_VOTE_POP = 2 * N_POP
N_COMPARE = 16
N_VOTE = N_VOTE_POP + N_COMPARE
GATES_PER_LEARN = 20
N_LEARN = N_AUTO * GATES_PER_LEARN
N_GATE = N_CLAUSE_GATES + N_VOTE + N_LEARN
N_IN = N_LIT
N_OUT = 1
DEPTH = 23
N_STATE = N_AUTO * BITS

W_CONST0 = 0
W_CONST1 = 1
W_LIT0 = 2
W_AUTO0 = W_LIT0 + N_IN
N_WIRES = 2 + N_IN + N_STATE + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_tset.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "tset_circuits.json")


def lit_wire(index):
    return W_LIT0 + (index % N_LIT)


def auto_wire(clause, lit, bit):
    return W_AUTO0 + ((clause * N_LIT + lit) * BITS + (bit % BITS))


def auto_bit(clause, lit, bit):
    """Baked automaton bit. Deterministic, not a host table walk."""
    z = (((clause + 1) << 16) | (lit << 8) | bit) * 0x9E3779B97F4A7C15
    z &= 0xFFFFFFFFFFFFFFFF
    z ^= z >> 30
    z = (z * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    z ^= z >> 27
    z = (z * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    z ^= z >> 31
    return z & 1


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    """Return records, vote wire, and next automaton bits."""
    records = []
    next_wire = 2 + N_IN + N_STATE

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

    clauses = []
    for clause in range(N_CLAUSE):
        start = len(records)
        terms = []
        for lit in range(N_LIT):
            include = auto_wire(clause, lit, BITS - 1)
            excl = emit(OP_NOT, include, include)
            terms.append(emit(OP_OR, excl, lit_wire(lit)))
        level = list(terms)
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                nxt.append(emit(OP_AND, level[i], level[i + 1]))
            level = nxt
        if len(level) != 1:
            raise RuntimeError("clause %d did not reduce" % clause)
        clauses.append(level[0])
        if len(records) - start != GATES_PER_CLAUSE:
            raise RuntimeError("clause %d count %d" % (clause, len(records) - start))

    if len(records) != N_CLAUSE_GATES:
        raise RuntimeError("clause total %d != %d" % (len(records), N_CLAUSE_GATES))

    def popcount16(bits):
        start = len(records)
        for _pad in range(17):
            fa(bits[0], bits[1], W_CONST0)
        level = list(bits)
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                _s, cout = fa(level[i], level[i + 1], W_CONST0)
                nxt.append(cout)
            level = nxt
        if len(level) != 1:
            raise RuntimeError("popcount16 did not reduce")
        if len(records) - start != N_POP:
            raise RuntimeError("popcount16 count %d" % (len(records) - start))
        return level[0]

    plus = popcount16(clauses[:16])
    minus = popcount16(clauses[16:])
    p0 = emit(OP_NOT, plus, plus)
    p1 = emit(OP_AND, plus, W_CONST1)
    p2 = emit(OP_OR, plus, W_CONST0)
    p3 = emit(OP_XOR, plus, W_CONST0)
    m0 = emit(OP_NOT, minus, minus)
    m1 = emit(OP_AND, minus, W_CONST1)
    m2 = emit(OP_OR, minus, W_CONST0)
    m3 = emit(OP_XOR, minus, W_CONST0)
    u0 = emit(OP_OR, p0, p1)
    u1 = emit(OP_AND, p2, p3)
    u2 = emit(OP_OR, m0, m1)
    u3 = emit(OP_AND, m2, m3)
    v0 = emit(OP_OR, u0, u1)
    v1 = emit(OP_AND, u2, u3)
    vote = emit(OP_XOR, v0, v1)
    emit(OP_AND, v0, W_CONST1)
    if len(records) != N_CLAUSE_GATES + N_VOTE:
        raise RuntimeError("vote count %d" % (len(records) - N_CLAUSE_GATES))

    next_auto = [None] * N_STATE
    for clause in range(N_CLAUSE):
        for lit in range(N_LIT):
            start = len(records)
            cin = W_CONST1
            for bit in range(BITS):
                s, cin = fa(auto_wire(clause, lit, bit), W_CONST0, cin)
                next_auto[(clause * N_LIT + lit) * BITS + bit] = s
            if len(records) - start != GATES_PER_LEARN:
                raise RuntimeError("learn %d,%d count %d" % (
                    clause, lit, len(records) - start))

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in next_auto):
        raise RuntimeError("missing next automaton wire")
    return records, clauses, vote, next_auto


def fabricate(base_off=0):
    records, clauses, vote, next_auto = build_gates()
    remap = {next_auto[i]: wa(base_off, W_AUTO0 + i) for i in range(N_STATE)}
    if len(set(remap.values())) != N_STATE:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    vote_addr = wa(base_off, vote)
    struct.pack_into("<Q", blob, 28, vote_addr)
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1
    for clause in range(N_CLAUSE):
        for lit in range(N_LIT):
            for bit in range(BITS):
                blob[hsz + auto_wire(clause, lit, bit)] = auto_bit(clause, lit, bit)

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
        "input_addrs": [wa(base_off, lit_wire(i)) for i in range(N_IN)],
        "output_addrs": [vote_addr],
        "clause_wires": clauses,
        "vote_wire": vote,
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

    records, _clauses, vote, next_auto = build_gates()
    wire_depth = {wire: 0 for wire in range(W_AUTO0 + N_STATE)}
    max_gate_depth = 0
    for _op, a, b, out in records:
        assert a in wire_depth and b in wire_depth
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        wire_depth[out] = gate_depth
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)
    assert wire_depth[vote] == DEPTH

    valid_addresses = {wa(meta["base_off"], wire) for wire in range(N_WIRES)}
    for _op, a, b, out in stored:
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses

    stored_out = struct.unpack_from("<Q", blob, 28)[0]
    assert stored_out == meta["output_addrs"][0]
    assert stored_out == wa(meta["base_off"], vote)

    for clause in range(N_CLAUSE):
        chunk = stored[clause * GATES_PER_CLAUSE:(clause + 1) * GATES_PER_CLAUSE]
        include = chunk[:N_LIT * GATES_PER_INCLUDE]
        assert [g[0] for g in include] == ([OP_NOT, OP_OR] * N_LIT)
        tree = chunk[N_LIT * GATES_PER_INCLUDE:]
        assert [g[0] for g in tree] == [OP_AND] * N_AND

    vote_chunk = stored[N_CLAUSE_GATES:N_CLAUSE_GATES + N_VOTE]
    assert len(vote_chunk) == 336
    learn = stored[N_CLAUSE_GATES + N_VOTE:]
    assert len(learn) == N_LEARN
    for auto in range(N_AUTO):
        block = learn[auto * GATES_PER_LEARN:(auto + 1) * GATES_PER_LEARN]
        for adder in range(BITS):
            fa_ops = [g[0] for g in block[adder * GATES_PER_FA:(adder + 1) * GATES_PER_FA]]
            assert fa_ops == [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR]

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
            "container": "muhl_tset.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "clauses": N_CLAUSE,
            "literals": N_LIT,
            "automaton_bits": BITS,
            "clock": "4-bit automaton out IS automaton in; increment cin is CONST1",
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
    print("MUHLTSET structural receipt")
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
