#!/usr/bin/env python3
"""muhl_fab_chimera_tset_hdvs.py — FABRICATE organ 22 (MUHLCHTH).

PLUMB 3/3 organ 22. Construction is the gate count:

  clause output -> hdvs BIND plane
  12 clause lanes
  double-negation NAND buffer per lane (depth 2, 2 gates)
  TOTAL 24 gates, depth 2

Existing chimera shape (organs 20/21 / ardr_eal): NAND(src,src) then
NAND(tmp,tmp). That is an identity buffer. Dest FROM FILE: tset clause
AND-outs 0..11 and hdvs BIND XOR-outs 0..11, read off the landed .mno
files. Local outs self-clock onto local ins. No titan address is
invented. Landed organs 1–21 stay untouched.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires,
n_in, n_out, depth. Records are <BQQQ> stride 25.
OPS NAND AND OR XOR NOT = 0 1 2 3 4.

  python3 muhl_fab_chimera_tset_hdvs.py          # write .mno + sidecar
  python3 muhl_fab_chimera_tset_hdvs.py --dry    # structural verify only
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_chimera_tset_hdvs"
MAGIC = b"MUHLCHTH"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_LANES = 12
GATES_PER_LANE = 2
N_GATE = N_LANES * GATES_PER_LANE
N_IN = N_LANES
N_OUT = N_LANES
DEPTH = 2

W_CONST0 = 0
W_CONST1 = 1
W_CLAUSE0 = 2
N_TEMP = N_LANES
N_WIRES = 2 + N_IN + N_TEMP

# Landed tset construction: 32 clauses, 32 literals, include 2 + AND-tree 31.
TSET_GATES_PER_CLAUSE = 95
TSET_CLAUSES = 32

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_chimera_tset_hdvs.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "chimera_tset_hdvs_circuits.json")
TSET_REG = os.path.join(EXCERPT_DIR, "tset_circuits.json")
TSET_MNO = os.path.join(EXCERPT_DIR, "muhl_tset.mno")
HDVS_REG = os.path.join(EXCERPT_DIR, "hdvs_circuits.json")
HDVS_MNO = os.path.join(EXCERPT_DIR, "muhl_hdvs.mno")


def clause_wire(index):
    return W_CLAUSE0 + (index % N_LANES)


def temp_wire(index):
    return W_CLAUSE0 + N_IN + (index % N_LANES)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def _read_landed(reg_path, mno_path, key, magic):
    with open(reg_path, encoding="utf-8") as handle:
        row = json.load(handle)[key]
    with open(mno_path, "rb") as handle:
        blob = handle.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != row["sha256"]:
        raise RuntimeError("%s sha256 is not the landed sidecar" % key)
    if blob[:8] != magic:
        raise RuntimeError("%s magic is not the landed file" % key)
    return row, blob


def dests_from_file():
    """Read landed excerpts. Do not invent addresses."""
    tset, tset_blob = _read_landed(TSET_REG, TSET_MNO, "muhl_tset", b"MUHLTSET")
    hdvs, hdvs_blob = _read_landed(HDVS_REG, HDVS_MNO, "muhl_hdvs", b"MUHLHDVS")
    if tset.get("clauses") != TSET_CLAUSES:
        raise RuntimeError("tset sidecar is not the landed 32-clause bank")
    if tset.get("n_out") != 1 or hdvs.get("n_in") != 1024:
        raise RuntimeError("landed sidecars are not tset vote / hdvs D=1024")

    tset_ng, tset_nw, _ni, tset_no, _dp = struct.unpack_from("<IIIII", tset_blob, 8)
    tset_start = 28 + tset_no * 8 + tset_nw
    src = []
    for lane in range(N_LANES):
        off = tset_start + ((lane + 1) * TSET_GATES_PER_CLAUSE - 1) * GATE_STRIDE
        op, _a, _b, out = struct.unpack_from("<BQQQ", tset_blob, off)
        if op != OP_AND:
            raise RuntimeError("tset clause %d last gate is not AND" % lane)
        src.append(out)
    if tset_start + tset_ng * GATE_STRIDE != len(tset_blob):
        raise RuntimeError("tset excerpt length does not match header")

    hdvs_ng, hdvs_nw, _ni, hdvs_no, _dp = struct.unpack_from("<IIIII", hdvs_blob, 8)
    hdvs_start = 28 + hdvs_no * 8 + hdvs_nw
    dst = []
    for lane in range(N_LANES):
        off = hdvs_start + lane * GATE_STRIDE
        op, _a, _b, out = struct.unpack_from("<BQQQ", hdvs_blob, off)
        if op != OP_XOR:
            raise RuntimeError("hdvs BIND gate %d is not XOR" % lane)
        dst.append(out)
    if hdvs_start + hdvs_ng * GATE_STRIDE != len(hdvs_blob):
        raise RuntimeError("hdvs excerpt length does not match header")
    if hdvs.get("bind") != "XOR rotate-1":
        raise RuntimeError("hdvs sidecar is not the landed BIND plane")

    return {
        "src_organ": "muhl_tset",
        "src_plane": "clause AND-outs 0..11",
        "src_addrs": src,
        "dst_organ": "muhl_hdvs",
        "dst_plane": "BIND XOR-outs 0..11",
        "dst_addrs": dst,
        "tset_sha256": tset["sha256"],
        "hdvs_sha256": hdvs["sha256"],
    }


def build_gates():
    records = []
    temps = []
    for lane in range(N_LANES):
        src = clause_wire(lane)
        tmp = temp_wire(lane)
        records.append((OP_NAND, src, src, tmp))
        temps.append(tmp)
    binds = []
    for lane in range(N_LANES):
        tmp = temps[lane]
        out = clause_wire(lane)
        records.append((OP_NAND, tmp, tmp, out))
        binds.append(out)
    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    return records, binds


def fabricate(base_off=0):
    dests = dests_from_file()
    records, binds = build_gates()
    remap = {binds[i]: wa(base_off, clause_wire(i)) for i in range(N_LANES)}
    if len(set(remap.values())) != N_OUT:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[binds[i]])
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
        "input_addrs": [wa(base_off, clause_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[binds[i]] for i in range(N_OUT)],
        "lanes": N_LANES,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "dests": dests,
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
        assert op == OP_NAND, "gate %d must be NAND" % i
        assert o not in writers, "out reused by gates %d and %d" % (writers[o], i)
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at lane %d" % i

    first = stored[:N_LANES]
    second = stored[N_LANES:]
    assert len(first) == N_LANES and len(second) == N_LANES
    for i, (op, a, b, _out) in enumerate(first):
        src = wa(meta["base_off"], clause_wire(i))
        assert op == OP_NAND and a == src and b == src
    for i, (op, a, b, out) in enumerate(second):
        tmp = wa(meta["base_off"], temp_wire(i))
        dest = wa(meta["base_off"], clause_wire(i))
        assert op == OP_NAND and a == tmp and b == tmp and out == dest
    dests = meta["dests"]
    assert dests["src_addrs"][0] == 4260
    assert dests["dst_addrs"][0] == 9246
    assert dests["dst_addrs"] == list(range(9246, 9258))
    assert blob[hsz + W_CONST0] == 0 and blob[hsz + W_CONST1] == 1
    return True


def write_files(blob, meta):
    os.makedirs(os.path.dirname(MNO_PATH), exist_ok=True)
    with open(MNO_PATH, "wb") as handle:
        handle.write(blob)
    dests = meta["dests"]
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
            "container": "muhl_chimera_tset_hdvs.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "lanes": N_LANES,
            "src": "tset clause AND-outs",
            "dst": "hdvs BIND XOR-outs",
            "buffer": "NAND NAND identity, 2 g per lane",
            "src_addrs": dests["src_addrs"],
            "dst_addrs": dests["dst_addrs"],
            "tset_sha256": dests["tset_sha256"],
            "hdvs_sha256": dests["hdvs_sha256"],
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "BIND-plane out IS clause-out in",
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
    print("MUHLCHTH structural receipt")
    print("  n_gate=%d n_wires=%d n_in=%d n_out=%d depth=%d" % (
        meta["n_gate"], meta["n_wires"], meta["n_in"], meta["n_out"], meta["depth"]))
    print("  len=%d sha256=%s" % (meta["len"], meta["sha256"]))
    print("  dest FROM FILE src=%s dst=%s" % (
        meta["dests"]["src_addrs"], meta["dests"]["dst_addrs"]))
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
