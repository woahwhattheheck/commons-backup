#!/usr/bin/env python3
"""muhl_fab_chimera_pots_dmb.py — FABRICATE organ 26 (MUHLCHPD).

PLUMB 3/3 organ 26. Construction is the gate count:

  DMB L-system -> Potts IDs (dmb EXISTS)
  10 L-system rewrite dests (gens 1–3; axiom stays inject)
  double-negation NAND buffer per lane (depth 2, 2 gates)
  TOTAL 20 gates, depth 2

Dest FROM FILE: DMB offset + wire map from the public census and
muhl_fab_dmb.py; pots input_addrs[0:10] from pots_circuits.json.
Local outs self-clock onto local ins. titan NOT_WRITTEN.
Landed organs 1–25 stay untouched.

  python3 muhl_fab_chimera_pots_dmb.py          # write .mno + sidecar
  python3 muhl_fab_chimera_pots_dmb.py --dry    # structural verify only
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys

NAME = "muhl_chimera_pots_dmb"
MAGIC = b"MUHLCHPD"
GATE_STRIDE = 25
OP_NAND = 0

N_LANES = 10
N_GATE = N_LANES * 2
N_IN = N_LANES
N_OUT = N_LANES
DEPTH = 2
W_CONST0 = 0
W_CONST1 = 1
W_LSYS0 = 2
N_WIRES = 2 + N_IN + N_LANES

# FROM FILE muhl_fab_dmb.py — axiom wire 1; rewrite dests wires 2..11
DMB_GEN_OFF = [1, 2, 4, 7]
DMB_GEN_SIZES = [1, 2, 3, 5]
DMB_REWRITE_WIRES = []
for gen, size in enumerate(DMB_GEN_SIZES):
    if gen == 0:
        continue
    start = DMB_GEN_OFF[gen]
    DMB_REWRITE_WIRES.extend(range(start, start + size))

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
CENSUS_PATH = os.path.join(REPO_ROOT, "ground", "SUBZERO_CENSUS.md")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_chimera_pots_dmb.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "chimera_pots_dmb_circuits.json")
POTS_REG = os.path.join(EXCERPT_DIR, "pots_circuits.json")


def lsys_wire(index):
    return W_LSYS0 + (index % N_LANES)


def temp_wire(index):
    return W_LSYS0 + N_IN + (index % N_LANES)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def dmb_offset_from_census():
    """Read the live-twelve DMB row. Do not invent the titan offset."""
    with open(CENSUS_PATH, encoding="utf-8") as handle:
        text = handle.read()
    match = re.search(
        r"\| DMB \| `muhl_dmb` \| \*\*IN titan\.gguf\*\* \| (\d+) \|",
        text,
    )
    if not match:
        raise RuntimeError("SUBZERO_CENSUS.md missing DMB offset row")
    offset = int(match.group(1))
    inject = re.search(r"\| `muhl_dmb` \| 10 \| 3 \| `MUHLDMB1` \| input `(\d+)` \|", text)
    if not inject:
        raise RuntimeError("SUBZERO_CENSUS.md missing DMB inject dest")
    inject_addr = int(inject.group(1))
    if inject_addr != offset + DMB_GEN_OFF[0]:
        raise RuntimeError("census inject is not offset + axiom wire")
    if DMB_REWRITE_WIRES != list(range(2, 12)):
        raise RuntimeError("DMB rewrite dests are not the 10 L-system writes")
    return offset, inject_addr


def dests_from_file():
    offset, inject = dmb_offset_from_census()
    src = [offset + wire for wire in DMB_REWRITE_WIRES]
    with open(POTS_REG, encoding="utf-8") as handle:
        pots = json.load(handle)["muhl_pots"]
    dst = list(pots["input_addrs"][:N_LANES])
    if len(src) != N_LANES or len(dst) != N_LANES:
        raise RuntimeError("census or pots sidecar missing L-system or ID dests")
    if pots.get("n_in") != 1024:
        raise RuntimeError("pots sidecar is not the landed 1024-bit ID field")
    if pots.get("sha256") != "ac8e7473739af617f3231d027d679aceb4ed809f2cf0b5f2900add38e85aae71":
        raise RuntimeError("pots sidecar sha is not the landed excerpt")
    return {
        "src_organ": "muhl_dmb",
        "src_plane": "L-system rewrite dests gens 1-3 (wires 2..11)",
        "src_addrs": src,
        "dst_organ": "muhl_pots",
        "dst_plane": "Potts ID ins 0..9",
        "dst_addrs": dst,
        "dmb_offset": offset,
        "dmb_inject": inject,
        "pots_sha256": pots["sha256"],
    }


def build_gates():
    records = []
    temps = []
    for lane in range(N_LANES):
        src = lsys_wire(lane)
        tmp = temp_wire(lane)
        records.append((OP_NAND, src, src, tmp))
        temps.append(tmp)
    ids = []
    for lane in range(N_LANES):
        out = lsys_wire(lane)
        records.append((OP_NAND, temps[lane], temps[lane], out))
        ids.append(out)
    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    return records, ids


def fabricate(base_off=0):
    dests = dests_from_file()
    records, ids = build_gates()
    remap = {ids[i]: wa(base_off, lsys_wire(i)) for i in range(N_LANES)}
    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[ids[i]])
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1
    stored = []
    off = gate_start
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
        "input_addrs": [wa(base_off, lsys_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[ids[i]] for i in range(N_OUT)],
        "lanes": N_LANES,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "dests": dests,
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    assert blob[:8] == MAGIC
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert (ng, nw, ni, no, dp) == (N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    assert len(blob) == meta["len"] == hdr_size() + N_WIRES + N_GATE * GATE_STRIDE
    writers = {}
    off = hdr_size() + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert (op, a, b, o) == (eop, ea, eb, eo)
        assert op == OP_NAND and o not in writers
        writers[o] = i
        off += GATE_STRIDE
    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i] == meta["input_addrs"][i]
    dests = meta["dests"]
    assert dests["src_addrs"] == list(range(93709782658, 93709782668))
    assert dests["dst_addrs"] == list(range(8222, 8232))
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
            "container": "muhl_chimera_pots_dmb.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "lanes": N_LANES,
            "src": "dmb L-system rewrite dests",
            "dst": "pots ID ins",
            "buffer": "NAND NAND identity, 2 g per lane",
            "src_addrs": dests["src_addrs"],
            "dst_addrs": dests["dst_addrs"],
            "dmb_offset": dests["dmb_offset"],
            "dmb_inject": dests["dmb_inject"],
            "pots_sha256": dests["pots_sha256"],
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "Potts ID out IS L-system in",
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
    print("MUHLCHPD structural receipt")
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
