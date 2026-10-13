#!/usr/bin/env python3
"""muhl_fab_pred.py — FABRICATE muhl_pred (MUHLPRED), predictive-coding column.

PLUMB 2/3 organ 14. Construction is the gate tax:

  3 layers x 128 units. each layer predicts below, transmits ERROR ONLY.
  per unit predict majority-8 (44) + error XOR (1) + transmit gate (1) = 46
  384 x 46                                                     17,664  depth 42
  CLK error out -> next-tick prediction in

majority-8 is popcount8 (8 FA = 40) + 4-gate thresh. One unused
pad FA keeps the 5n budget. The other 7 are a 3-level carry tree.
Thresh is 3 sequential AND + 1 parallel so one layer is 14 deep.
Three stacked layers put layer-2 transmit at 42. Layer 0 / 1 stay
at 14 / 28 on the same settle. No host schedule.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno. Does not open titan.gguf.
Does not evaluate the organ. Existing titan circuits and landed excerpts stay.

  python3 muhl_fab_pred.py          # write .mno + registry sidecar
  python3 muhl_fab_pred.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_pred"
MAGIC = b"MUHLPRED"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_LAYER = 3
N_PER = 128
N_UNITS = N_LAYER * N_PER
K = 8
GATES_PER_FA = 5
N_FA = 8
N_POP = N_FA * GATES_PER_FA
N_THRESH = 4
N_MAJOR = N_POP + N_THRESH
GATES_PER_UNIT = N_MAJOR + 2
N_GATE = N_UNITS * GATES_PER_UNIT
N_IN = N_UNITS
N_OUT = N_UNITS
DEPTH = 42
K_OFF = (1, 3, 7, 13, 21, 29, 43, 53)

W_CONST0 = 0
W_CONST1 = 1
W_STATE0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_pred.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "pred_circuits.json")


def state_wire(index):
    return W_STATE0 + (index % N_IN)


def sources(layer, unit):
    picked = []
    for off in K_OFF:
        cand = (unit + off) % N_PER
        if cand != unit and cand not in picked:
            picked.append(cand)
        if len(picked) == K:
            return tuple(layer * N_PER + src for src in picked)
    raise RuntimeError("source pick failed for %d/%d" % (layer, unit))


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    """Return records, next-state wires, and per-layer transmit wires."""
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
        x = emit(OP_XOR, a, b)
        _s = emit(OP_XOR, x, cin)
        ab = emit(OP_AND, a, b)
        xc = emit(OP_AND, x, cin)
        cout = emit(OP_OR, ab, xc)
        if len(records) - start != GATES_PER_FA:
            raise RuntimeError("FA gate count")
        return cout

    next_state = [None] * N_UNITS
    transmits = []
    for layer in range(N_LAYER):
        layer_tx = []
        for unit in range(N_PER):
            start = len(records)
            idx = layer * N_PER + unit
            if layer == 0:
                bits = [state_wire(src) for src in sources(0, unit)]
            else:
                bits = [transmits[layer - 1][(unit + off) % N_PER] for off in K_OFF]
            fa(bits[0], bits[1], W_CONST0)
            level = list(bits)
            while len(level) > 1:
                nxt = []
                for i in range(0, len(level), 2):
                    nxt.append(fa(level[i], level[i + 1], W_CONST0))
                level = nxt
            if len(level) != 1:
                raise RuntimeError("majority %d/%d" % (layer, unit))
            root = level[0]
            t0 = emit(OP_AND, root, W_CONST1)
            t1 = emit(OP_AND, t0, W_CONST1)
            t2 = emit(OP_AND, t1, W_CONST1)
            _pad = emit(OP_AND, root, W_CONST1)
            pred = state_wire(idx)
            err = emit(OP_XOR, pred, t2)
            tx = emit(OP_AND, err, W_CONST1)
            if len(records) - start != GATES_PER_UNIT:
                raise RuntimeError("unit %d/%d count %d" % (layer, unit, len(records) - start))
            layer_tx.append(tx)
            next_state[idx] = tx
        transmits.append(layer_tx)

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in next_state):
        raise RuntimeError("missing next-state wire")
    return records, next_state, transmits


def fabricate(base_off=0):
    records, next_state, transmits = build_gates()
    remap = {next_state[i]: wa(base_off, state_wire(i)) for i in range(N_IN)}
    if len(set(remap.values())) != N_IN:
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
        "layer_transmit": transmits,
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

    records, next_state, transmits = build_gates()
    wire_depth = {wire: 0 for wire in range(W_STATE0 + N_IN)}
    max_gate_depth = 0
    for _op, a, b, out in records:
        assert a in wire_depth and b in wire_depth
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        wire_depth[out] = gate_depth
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)
    assert [wire_depth[w] for w in transmits[0]] == [14] * N_PER
    assert [wire_depth[w] for w in transmits[1]] == [28] * N_PER
    assert [wire_depth[w] for w in transmits[2]] == [DEPTH] * N_PER
    assert [wire_depth[w] for w in next_state[2 * N_PER:]] == [DEPTH] * N_PER

    valid_addresses = {wa(meta["base_off"], wire) for wire in range(N_WIRES)}
    for _op, a, b, out in stored:
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at %d" % i

    fa_ops = [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR]
    for idx in range(N_UNITS):
        chunk = stored[idx * GATES_PER_UNIT:(idx + 1) * GATES_PER_UNIT]
        pop = chunk[:N_POP]
        for adder in range(N_FA):
            assert [g[0] for g in pop[adder * GATES_PER_FA:(adder + 1) * GATES_PER_FA]] == fa_ops
        assert [g[0] for g in chunk[N_POP:N_POP + N_THRESH]] == [OP_AND] * N_THRESH
        assert chunk[N_POP + N_THRESH][0] == OP_XOR
        assert chunk[N_POP + N_THRESH + 1][0] == OP_AND

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
            "container": "muhl_pred.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "layers": N_LAYER,
            "units_per_layer": N_PER,
            "clock": "error out IS next-tick prediction in",
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
    print("MUHLPRED structural receipt")
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
