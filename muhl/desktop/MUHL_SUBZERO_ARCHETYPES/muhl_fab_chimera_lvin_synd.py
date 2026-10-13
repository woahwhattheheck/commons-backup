#!/usr/bin/env python3
"""muhl_fab_chimera_lvin_synd.py — FABRICATE organ 28 (MUHLCHLS).

12-lane NAND NAND identity. Dest FROM FILE: pred next-tick outs 0..11
and synd codeword ins 0..11, read off the landed excerpts.
Local outs self-clock onto local ins. titan NOT_WRITTEN. Organs 1-26 stay.

  python3 muhl_fab_chimera_lvin_synd.py
  python3 muhl_fab_chimera_lvin_synd.py --dry
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_chimera_lvin_synd"
MAGIC = b"MUHLCHLS"
GATE_STRIDE = 25
OP_NAND = 0

N_LANES = 11
N_GATE = N_LANES * 2
N_IN = N_LANES
N_OUT = N_LANES
DEPTH = 2

W_CONST0 = 0
W_CONST1 = 1
W_LANE0 = 2
N_WIRES = 2 + N_IN + N_LANES

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_chimera_lvin_synd.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "chimera_lvin_synd_circuits.json")
LVIN_REG = os.path.join(EXCERPT_DIR, "lvin_circuits.json")
LVIN_MNO = os.path.join(EXCERPT_DIR, "muhl_lvin.mno")
SYND_REG = os.path.join(EXCERPT_DIR, "synd_circuits.json")
SYND_MNO = os.path.join(EXCERPT_DIR, "muhl_synd.mno")


def lane_wire(index):
    return W_LANE0 + (index % N_LANES)


def temp_wire(index):
    return W_LANE0 + N_IN + (index % N_LANES)


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
    pred, _pred_blob = _read_landed(LVIN_REG, LVIN_MNO, "muhl_lvin", b"MUHLLVIN")
    rgcg, _rgcg_blob = _read_landed(SYND_REG, SYND_MNO, "muhl_synd", b"MUHLSYND")
    src = list(pred["output_addrs"][:N_LANES])
    dst = list(rgcg["input_addrs"][:N_LANES])
    if len(src) != N_LANES or len(dst) != N_LANES:
        raise RuntimeError("lvin/synd sidecars do not expose 11 dests FROM FILE")
    if src != list(range(542, 542 + N_LANES)):
        raise RuntimeError("lvin outs 0..10 are not the landed tape plane")
    if dst != list(range(2078, 2078 + N_LANES)):
        raise RuntimeError("synd ins 0..10 are not the landed codeword plane")
    return {
        "src_organ": "muhl_lvin",
        "src_plane": "tape outs 0..10",
        "src_addrs": src,
        "dst_organ": "muhl_synd",
        "dst_plane": "codeword ins 0..10",
        "dst_addrs": dst,
        "lvin_sha256": pred["sha256"],
        "synd_sha256": rgcg["sha256"],
    }


def build_gates():
    records = []
    for lane in range(N_LANES):
        src = lane_wire(lane)
        tmp = temp_wire(lane)
        records.append((OP_NAND, src, src, tmp))
    for lane in range(N_LANES):
        tmp = temp_wire(lane)
        out = lane_wire(lane)
        records.append((OP_NAND, tmp, tmp, out))
    return records


def fabricate(base_off=0):
    dests = dests_from_file()
    records = build_gates()
    remap = {lane_wire(i): wa(base_off, lane_wire(i)) for i in range(N_LANES)}
    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[lane_wire(i)])
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1
    stored = []
    off = gate_start
    for op, a, b, out_w in records:
        a_addr = wa(base_off, a)
        b_addr = wa(base_off, b)
        out_addr = remap.get(out_w, wa(base_off, out_w))
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
        "input_addrs": [remap[lane_wire(i)] for i in range(N_IN)],
        "output_addrs": [remap[lane_wire(i)] for i in range(N_OUT)],
        "lanes": N_LANES,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "dests": dests,
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    assert blob[:8] == MAGIC
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert (ng, nw, ni, no, dp) == (N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    assert len(blob) == meta["len"]
    hsz = hdr_size()
    writers = {}
    off = hsz + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert (op, a, b, o) == (eop, ea, eb, eo)
        assert o not in writers
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE
    dests = meta["dests"]
    assert dests["src_addrs"] == list(range(542, 553))
    assert dests["dst_addrs"] == list(range(2078, 2089))
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
            "container": "muhl_chimera_lvin_synd.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "lanes": N_LANES,
            "src": "lvin tape outs",
            "dst": "synd codeword ins",
            "buffer": "NAND NAND identity, 2 g per lane",
            "src_addrs": dests["src_addrs"],
            "dst_addrs": dests["dst_addrs"],
            "lvin_sha256": dests["lvin_sha256"],
            "synd_sha256": dests["synd_sha256"],
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "rgcg majority-plane in IS pred next-tick out",
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
    print("MUHLCHLS structural receipt")
    print("  n_gate=%d n_wires=%d depth=%d len=%d" % (
        meta["n_gate"], meta["n_wires"], meta["depth"], meta["len"]))
    print("  sha256=%s" % meta["sha256"])
    print("  dest FROM FILE src=%s" % meta["dests"]["src_addrs"])
    print("  dest FROM FILE dst=%s" % meta["dests"]["dst_addrs"])
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
