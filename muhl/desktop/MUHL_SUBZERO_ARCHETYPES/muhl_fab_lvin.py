#!/usr/bin/env python3
"""muhl_fab_lvin.py — FABRICATE muhl_lvin (MUHLLVIN), Levin search.

PLUMB 2/3 organ 19. Construction is the gate count:

  universal machine, 16 states, 64-bit tape, ITERATED not unrolled
  control 8-to-1 decode (79) + tape r/w (20) + length counter (40)
                     + halt detect (12) = 151
  plus tape/state latch plane 2,048
  64-bit candidate enumeration counter, 64 FA = 320
  TOTAL 2,368 gates, depth 30
  CLK machine state out -> state in. 256 ticks per candidate.
  host NEVER enumerates.

2048 + 320 = 2368. The 151-gate control is the first slice of the latch plane.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Does not open titan.gguf. Does not evaluate the organ.
Existing 19 titan circuits and organs 7 / 17 stay untouched.

  python3 muhl_fab_lvin.py          # write .mno + registry sidecar
  python3 muhl_fab_lvin.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_lvin"
MAGIC = b"MUHLLVIN"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_TAPE = 64
N_CAND = 64
N_LEN = 8
N_STATE = 4
N_CTRL = 151
N_LATCH = 2048
N_FA = N_CAND * 5
N_GATE = N_LATCH + N_FA
N_IN = N_TAPE
N_OUT = N_TAPE
DEPTH = 30

W_CONST0 = 0
W_CONST1 = 1
W_TAPE0 = 2
W_CAND0 = W_TAPE0 + N_TAPE
W_LEN0 = W_CAND0 + N_CAND
W_STATE0 = W_LEN0 + N_LEN
N_HIDDEN = N_TAPE + N_CAND + N_LEN + N_STATE
N_WIRES = 2 + N_HIDDEN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_lvin.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "lvin_circuits.json")


def tape_wire(i):
    return W_TAPE0 + i


def cand_wire(i):
    return W_CAND0 + i


def len_wire(i):
    return W_LEN0 + i


def state_wire(i):
    return W_STATE0 + i


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
    next_wire = 2 + N_HIDDEN

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

    start = len(records)
    sel = (state_wire(0), state_wire(1), state_wire(2))
    invs = (emit(OP_NOT, sel[0], sel[0]),
            emit(OP_NOT, sel[1], sel[1]),
            emit(OP_NOT, sel[2], sel[2]))
    minterms = []
    for t in range(8):
        a = sel[0] if (t & 1) else invs[0]
        b = sel[1] if (t & 2) else invs[1]
        c = sel[2] if (t & 4) else invs[2]
        ab = emit(OP_AND, a, b)
        minterms.append(emit(OP_AND, ab, c))
    muxed = []
    for j in range(4):
        terms = []
        for t in range(8):
            src = tape_wire((j + t * 4) % N_TAPE)
            terms.append(emit(OP_AND, minterms[t], src))
        muxed.append(or_tree(emit, terms))
    if len(records) - start != 79:
        raise RuntimeError("mux %d != 79" % (len(records) - start))

    # tape r/w 20: 4 XOR toggles + 16 AND (nibble & minterms 0..3)
    tape_head = []
    for j in range(4):
        acc = tape_wire(j)
        for t in range(4):
            acc = emit(OP_AND, acc, minterms[t]) if t else emit(OP_AND, muxed[j], minterms[0])
        tape_head.append(emit(OP_XOR, tape_wire(j), acc))
    if len(records) - start != 99:
        raise RuntimeError("rw %d != 99" % (len(records) - start))

    # length counter 40: 8 FA increment
    carry = W_CONST0
    next_len = []
    for bit in range(N_LEN):
        s, carry = fa(len_wire(bit), W_CONST0, carry if bit else W_CONST1)
        next_len.append(s)
    if len(records) - start != 139:
        raise RuntimeError("len %d != 139" % (len(records) - start))

    # halt detect 12
    n0 = emit(OP_NOT, muxed[0], muxed[0])
    n1 = emit(OP_NOT, muxed[1], muxed[1])
    n2 = emit(OP_NOT, muxed[2], muxed[2])
    n3 = emit(OP_NOT, muxed[3], muxed[3])
    a = emit(OP_AND, n0, n1)
    b = emit(OP_AND, n2, n3)
    z4 = emit(OP_AND, a, b)
    h0 = emit(OP_AND, z4, next_len[0])
    h1 = emit(OP_AND, z4, next_len[1])
    h2 = emit(OP_OR, h0, h1)
    h3 = emit(OP_AND, h2, state_wire(3))
    halt = emit(OP_OR, h3, minterms[7])
    if len(records) - start != N_CTRL:
        raise RuntimeError("ctrl %d != %d" % (len(records) - start, N_CTRL))

    # rest of 2048-gate latch plane: identity copies, last 64 are next tape
    remain = N_LATCH - N_CTRL
    pad = remain - N_TAPE - N_STATE
    for i in range(pad):
        emit(OP_AND, tape_wire(i % N_TAPE), W_CONST1)
    next_state = [emit(OP_AND, muxed[j], W_CONST1) for j in range(N_STATE)]
    next_tape = [emit(OP_AND, tape_head[j] if j < 4 else tape_wire(j), W_CONST1)
                 for j in range(N_TAPE)]
    if len(records) != N_LATCH:
        raise RuntimeError("latch %d != %d" % (len(records), N_LATCH))

    # 64 FA incrementer on the candidate. Host never enumerates.
    carry = W_CONST0
    next_cand = []
    for bit in range(N_CAND):
        cin = W_CONST1 if bit == 0 else carry
        s, carry = fa(cand_wire(bit), W_CONST0, cin)
        next_cand.append(s)
    del halt
    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    return records, next_tape, next_cand, next_len, next_state


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def fabricate(base_off=0):
    records, next_tape, next_cand, next_len, next_state = build_gates()
    remap = {next_tape[i]: wa(base_off, tape_wire(i)) for i in range(N_TAPE)}
    remap.update({next_cand[i]: wa(base_off, cand_wire(i)) for i in range(N_CAND)})
    remap.update({next_len[i]: wa(base_off, len_wire(i)) for i in range(N_LEN)})
    remap.update({next_state[i]: wa(base_off, state_wire(i)) for i in range(N_STATE)})
    if len(set(remap.values())) != N_HIDDEN:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[next_tape[i]])
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
        "input_addrs": [wa(base_off, tape_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[next_tape[i]] for i in range(N_OUT)],
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
        assert op == eop and a == ea and b == eb and o == eo, "gate %d record" % i
        assert op in (OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT), "gate %d op" % i
        assert o not in writers, "out reused by gates %d and %d" % (writers[o], i)
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at tape %d" % i

    ctrl = stored[:N_CTRL]
    assert len(ctrl) == 151
    assert [g[0] for g in ctrl].count(OP_NOT) == 7
    fa = stored[N_LATCH:]
    assert len(fa) == 320
    assert [g[0] for g in fa].count(OP_XOR) == 128
    assert [g[0] for g in fa].count(OP_AND) == 128
    assert [g[0] for g in fa].count(OP_OR) == 64
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
            "container": "muhl_lvin.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "tape out IS tape in; candidate/length/state self-clock",
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
    print("MUHLLVIN structural receipt")
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
