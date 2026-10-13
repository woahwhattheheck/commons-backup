#!/usr/bin/env python3
"""muhl_fab_synd.py — FABRICATE muhl_synd (MUHLSYND), syndrome decoder.

PLUMB 2/3 organ 16. Construction is the gate count:

  LDPC (n=256, k=128), row weight 6, 3 belief-propagation iterations
  syndrome 128 checks x XOR-tree 5                               640
  check node min-sum 128 x 30 x 3                             11,520
  variable node update 256 x 20 x 3                           15,360
  TOTAL                                                       27,520  depth 45
  separates INTENDED state change from corruption with no host read

(3,6)-regular QC bipartite graph. Dest from this lattice, not invented.
Check r owns variables (2r, 2r+1, 2r+64, 2r+65, 2r+128, 2r+129) mod 256.
Each variable sits in exactly three checks. Column weight 3.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno next to this file.
Does not open titan.gguf. Does not evaluate the organ.
Existing titan circuits and landed excerpts stay untouched.

  python3 muhl_fab_synd.py          # write .mno + registry sidecar
  python3 muhl_fab_synd.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_synd"
MAGIC = b"MUHLSYND"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_VARS = 256
N_CHECKS = 128
ROW_W = 6
COL_W = 3
N_ITERS = 3
GATES_PER_SYNDROME = 5
GATES_PER_CN = 30
GATES_PER_VN = 20
N_SYN_GATES = N_CHECKS * GATES_PER_SYNDROME
N_CN_GATES = N_CHECKS * GATES_PER_CN * N_ITERS
N_VN_GATES = N_VARS * GATES_PER_VN * N_ITERS
N_GATE = N_SYN_GATES + N_CN_GATES + N_VN_GATES
N_IN = N_VARS
N_OUT = N_VARS
DEPTH = 45
DELAY_PADS = 44

# Wire indices (MHA layout): const0, const1, then 256 codeword bits, then one wire per gate.
W_CONST0 = 0
W_CONST1 = 1
W_VAR0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_synd.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "synd_circuits.json")


def var_wire(index):
    return W_VAR0 + index


def check_vars(check):
    """Six variables on check r. (3,6)-regular QC, wrap 256."""
    base = (2 * check) % N_VARS
    return (
        base,
        (base + 1) % N_VARS,
        (base + 64) % N_VARS,
        (base + 65) % N_VARS,
        (base + 128) % N_VARS,
        (base + 129) % N_VARS,
    )


def var_checks(var):
    """Three checks that touch variable v. Inverse of check_vars."""
    if var % 2 == 0:
        root = (var // 2) % N_CHECKS
    else:
        root = ((var - 1) // 2) % N_CHECKS
    return (
        root % N_CHECKS,
        (root - 32) % N_CHECKS,
        (root - 64) % N_CHECKS,
    )


def edge_in_check(check, var):
    return check_vars(check).index(var)


def build_gates():
    """Return records, next-state roots, and the regular Tanner map.

    records: list of (op, a_wire, b_wire, out_wire)
    next_state[i] remaps onto codeword bit i on store.
    """
    records = []
    next_state = [None] * N_VARS
    next_wire = 2 + N_IN
    syndromes = []
    cn_msg = [[None] * N_CHECKS for _ in range(N_ITERS)]
    delay = W_CONST1
    pads_used = 0

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    def xor_chain(wires):
        acc = wires[0]
        for src in wires[1:]:
            acc = emit(OP_XOR, acc, src)
        return acc

    def check_node(incoming, use_delay_pad):
        """30-gate 1-bit min-sum. Incoming is six variable messages."""
        start = len(records)
        nonlocal delay, pads_used
        if len(incoming) != ROW_W:
            raise RuntimeError("check degree")
        parity = xor_chain(incoming)
        signs = [emit(OP_XOR, parity, incoming[edge]) for edge in range(ROW_W)]
        pairs = [
            emit(OP_AND, incoming[0], incoming[1]),
            emit(OP_AND, incoming[2], incoming[3]),
            emit(OP_AND, incoming[4], incoming[5]),
        ]
        cross = [
            emit(OP_AND, pairs[0], pairs[1]),
            emit(OP_AND, pairs[0], pairs[2]),
            emit(OP_AND, pairs[1], pairs[2]),
        ]
        mags = [
            emit(OP_AND, incoming[1], cross[2]),
            emit(OP_AND, incoming[0], cross[2]),
            emit(OP_AND, incoming[3], cross[1]),
            emit(OP_AND, incoming[2], cross[1]),
            emit(OP_AND, incoming[5], cross[0]),
            emit(OP_AND, incoming[4], cross[0]),
        ]
        messages = [emit(OP_AND, signs[edge], mags[edge]) for edge in range(ROW_W)]
        if use_delay_pad:
            delay = emit(OP_OR, delay, W_CONST0)
            pads_used += 1
        else:
            emit(OP_OR, messages[0], W_CONST0)
        if len(records) - start != GATES_PER_CN:
            raise RuntimeError("CN gate count %d" % (len(records) - start))
        return messages, parity

    def var_node(channel, inbox, clock_out):
        """20-gate variable update. inbox is three check-to-variable messages."""
        start = len(records)
        if len(inbox) != COL_W:
            raise RuntimeError("variable degree")
        ch, c0, c1, c2 = channel, inbox[0], inbox[1], inbox[2]
        pair_ch0 = emit(OP_AND, ch, c0)
        pair_ch1 = emit(OP_AND, ch, c1)
        pair_ch2 = emit(OP_AND, ch, c2)
        pair_01 = emit(OP_AND, c0, c1)
        pair_02 = emit(OP_AND, c0, c2)
        pair_12 = emit(OP_AND, c1, c2)
        # Extrinsic majority of the other two checks plus the channel bit.
        ext0 = emit(OP_OR, emit(OP_OR, pair_ch1, pair_ch2), pair_12)
        ext1 = emit(OP_OR, emit(OP_OR, pair_ch0, pair_ch2), pair_02)
        ext2 = emit(OP_OR, emit(OP_OR, pair_ch0, pair_ch1), pair_01)
        triples = [
            emit(OP_AND, pair_ch0, c1),
            emit(OP_AND, pair_ch0, c2),
            emit(OP_AND, pair_ch1, c2),
            emit(OP_AND, pair_01, c2),
        ]
        maj = emit(OP_OR, triples[0], triples[1])
        maj = emit(OP_OR, maj, triples[2])
        maj = emit(OP_OR, maj, triples[3])
        if clock_out:
            root = emit(OP_AND, maj, delay)
        else:
            root = emit(OP_OR, maj, W_CONST0)
        if len(records) - start != GATES_PER_VN:
            raise RuntimeError("VN gate count %d" % (len(records) - start))
        return [ext0, ext1, ext2], root

    for check in range(N_CHECKS):
        bits = [var_wire(v) for v in check_vars(check)]
        start = len(records)
        syndromes.append(xor_chain(bits))
        if len(records) - start != GATES_PER_SYNDROME:
            raise RuntimeError("syndrome gate count")

    vn_out = [[None] * N_VARS for _ in range(N_ITERS)]
    for it in range(N_ITERS):
        for check in range(N_CHECKS):
            if it == 0:
                incoming = [var_wire(v) for v in check_vars(check)]
            else:
                incoming = []
                for var in check_vars(check):
                    checks = var_checks(var)
                    incoming.append(vn_out[it - 1][var][checks.index(check)])
            use_delay = pads_used < DELAY_PADS
            messages, _parity = check_node(incoming, use_delay)
            cn_msg[it][check] = messages
        for var in range(N_VARS):
            inbox = []
            for check in var_checks(var):
                edge = edge_in_check(check, var)
                inbox.append(cn_msg[it][check][edge])
            extras, root = var_node(var_wire(var), inbox, clock_out=(it == N_ITERS - 1))
            vn_out[it][var] = extras
            if it == N_ITERS - 1:
                next_state[var] = root

    if pads_used != DELAY_PADS:
        raise RuntimeError("delay pads %d != %d" % (pads_used, DELAY_PADS))
    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in next_state):
        raise RuntimeError("missing next-state wire")
    tanner = {
        "checks": [list(check_vars(check)) for check in range(N_CHECKS)],
        "vars": [list(var_checks(var)) for var in range(N_VARS)],
    }
    return records, next_state, syndromes, tanner


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def fabricate(base_off=0):
    records, next_state, syndromes, tanner = build_gates()
    remap = {next_state[i]: wa(base_off, var_wire(i)) for i in range(N_VARS)}
    if len(set(remap.values())) != N_VARS:
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
        "input_addrs": [wa(base_off, var_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[next_state[i]] for i in range(N_OUT)],
        "syndrome_wires": syndromes,
        "tanner": tanner,
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

    input_addresses = {wa(meta["base_off"], wire) for wire in range(W_VAR0 + N_IN)}
    marking_addresses = set(meta["input_addrs"])
    valid_addresses = {wa(meta["base_off"], wire) for wire in range(N_WIRES)}
    wire_depth = {address: 0 for address in input_addresses}
    max_gate_depth = 0
    written_marking = set()
    for _op, a, b, out in stored:
        assert a in wire_depth and b in wire_depth
        assert a not in written_marking and b not in written_marking
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        if out not in input_addresses:
            wire_depth[out] = gate_depth
        elif out in marking_addresses:
            written_marking.add(out)
    assert written_marking == marking_addresses
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at var %d" % i

    syn = stored[:N_SYN_GATES]
    assert len(syn) == 640
    assert [g[0] for g in syn].count(OP_XOR) == 640

    for check in range(N_CHECKS):
        owned = check_vars(check)
        assert len(set(owned)) == ROW_W
        assert meta["tanner"]["checks"][check] == list(owned)
    degrees = [0] * N_VARS
    for check in range(N_CHECKS):
        for var in check_vars(check):
            degrees[var] += 1
    assert degrees == [COL_W] * N_VARS

    for var in range(N_VARS):
        checks = var_checks(var)
        assert len(set(checks)) == COL_W
        for check in checks:
            assert var in check_vars(check)

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
            "container": "muhl_synd.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "code": "LDPC n=256 k=128 row-weight 6 col-weight 3",
            "iterations": N_ITERS,
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "codeword out IS codeword in",
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
    print("MUHLSYND structural receipt")
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
