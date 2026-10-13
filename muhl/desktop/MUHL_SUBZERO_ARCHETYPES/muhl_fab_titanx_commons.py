#!/usr/bin/env python3
"""muhl_fab_titanx_commons.py — FABRICATE organ 31 (MUHLTITX).

PLUMB 3/3 organ 31. Construction is the gate count:

  wires 12 existing + 19 new + 9 chimeras
  300 dest-FROM-FILE lanes x NAND NAND identity (2 g) = 600
  depth 2
  to= routing IS address collision. No new routing mechanism.

Hops (lanes) — dest FROM FILE only:
  hdvs identity                 43
  sdmk + hopf memory            16 + 16
  immn non-self (DOOR OPEN)      1
  pdap envelope                 16
  stig rank                     16
  flow thread                   32
  byzq quorum                   16
  rgcg compress                  4
  synd corruption               16
  vscf court                    16
  cgat cause                    16
  hpc shape                     16
  mha metabolism                16
  eal clock                     16
  dmb bloom                     10
  awcg bloom                    16
  9 chimeras x 2                18

Local outs self-clock onto local ins. titan NOT_WRITTEN.
Organs 1-30 stay.

  python3 muhl_fab_titanx_commons.py          # write .mno + sidecar
  python3 muhl_fab_titanx_commons.py --dry    # structural verify only
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys

NAME = "muhl_titanx_commons"
MAGIC = b"MUHLTITX"
GATE_STRIDE = 25
OP_NAND = 0

HOPS = (
    {"name": "hdvs_identity", "src": "muhl_hdvs", "kind": "out", "lanes": 43},
    {"name": "sdmk_memory", "src": "muhl_sdmk", "kind": "out", "lanes": 16},
    {"name": "hopf_memory", "src": "muhl_hopf", "kind": "out", "lanes": 16},
    {"name": "immn_nonself", "src": "muhl_immn", "kind": "out", "lanes": 1},
    {"name": "pdap_envelope", "src": "muhl_pdap", "kind": "out", "lanes": 16},
    {"name": "stig_rank", "src": "muhl_stig", "kind": "out", "lanes": 16},
    {"name": "flow_thread", "src": "muhl_flow", "kind": "out", "lanes": 32},
    {"name": "byzq_quorum", "src": "muhl_byzq", "kind": "out", "lanes": 16},
    {"name": "rgcg_compress", "src": "muhl_rgcg", "kind": "out", "lanes": 4},
    {"name": "synd_corrupt", "src": "muhl_synd", "kind": "out", "lanes": 16},
    {"name": "vscf_court", "src": "muhl_vscf", "kind": "census", "lanes": 16},
    {"name": "cgat_cause", "src": "muhl_cgat", "kind": "census", "lanes": 16},
    {"name": "hpc_shape", "src": "muhl_hpc", "kind": "census", "lanes": 16},
    {"name": "mha_metabolism", "src": "muhl_mha", "kind": "census", "lanes": 16},
    {"name": "eal_clock", "src": "muhl_eal", "kind": "census", "lanes": 16},
    {"name": "dmb_bloom", "src": "muhl_dmb", "kind": "census", "lanes": 10},
    {"name": "awcg_bloom", "src": "muhl_awcg", "kind": "census", "lanes": 16},
    {"name": "chih_wire", "src": "muhl_chimera_immn_hdvs", "kind": "out", "lanes": 2},
    {"name": "chhs_wire", "src": "muhl_chimera_hopf_sdmk", "kind": "out", "lanes": 2},
    {"name": "chth_wire", "src": "muhl_chimera_tset_hdvs", "kind": "out", "lanes": 2},
    {"name": "chgs_wire", "src": "muhl_chimera_grbn_socr", "kind": "out", "lanes": 2},
    {"name": "chss_wire", "src": "muhl_chimera_socr_stig", "kind": "out", "lanes": 2},
    {"name": "chfs_wire", "src": "muhl_chimera_flow_stig", "kind": "out", "lanes": 2},
    {"name": "chpd_wire", "src": "muhl_chimera_pots_dmb", "kind": "out", "lanes": 2},
    {"name": "chpr_wire", "src": "muhl_chimera_pred_rgcg", "kind": "out", "lanes": 2},
    {"name": "chls_wire", "src": "muhl_chimera_lvin_synd", "kind": "out", "lanes": 2},
)
N_LANES = sum(hop["lanes"] for hop in HOPS)
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
CENSUS_PATH = os.path.join(REPO_ROOT, "ground", "SUBZERO_CENSUS.md")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_titanx_commons.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "titanx_commons_circuits.json")

LANDED = {
    "muhl_hdvs": {
        "reg": os.path.join(EXCERPT_DIR, "hdvs_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_hdvs.mno"),
        "magic": b"MUHLHDVS",
    },
    "muhl_sdmk": {
        "reg": os.path.join(EXCERPT_DIR, "sdmk_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_sdmk.mno"),
        "magic": b"MUHLSDMK",
    },
    "muhl_hopf": {
        "reg": os.path.join(EXCERPT_DIR, "hopf_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_hopf.mno"),
        "magic": b"MUHLHOPF",
    },
    "muhl_immn": {
        "reg": os.path.join(EXCERPT_DIR, "immn_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_immn.mno"),
        "magic": b"MUHLIMMN",
    },
    "muhl_pdap": {
        "reg": os.path.join(EXCERPT_DIR, "pdap_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_pdap.mno"),
        "magic": b"MUHLPDAP",
    },
    "muhl_stig": {
        "reg": os.path.join(EXCERPT_DIR, "stig_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_stig.mno"),
        "magic": b"MUHLSTIG",
    },
    "muhl_flow": {
        "reg": os.path.join(EXCERPT_DIR, "flow_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_flow.mno"),
        "magic": b"MUHLFLOW",
    },
    "muhl_byzq": {
        "reg": os.path.join(EXCERPT_DIR, "byzq_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_byzq.mno"),
        "magic": b"MUHLBYZQ",
    },
    "muhl_rgcg": {
        "reg": os.path.join(EXCERPT_DIR, "rgcg_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_rgcg.mno"),
        "magic": b"MUHLRGCG",
    },
    "muhl_synd": {
        "reg": os.path.join(EXCERPT_DIR, "synd_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_synd.mno"),
        "magic": b"MUHLSYND",
    },
    "muhl_chimera_immn_hdvs": {
        "reg": os.path.join(EXCERPT_DIR, "chimera_immn_hdvs_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_chimera_immn_hdvs.mno"),
        "magic": b"MUHLCHIH",
    },
    "muhl_chimera_hopf_sdmk": {
        "reg": os.path.join(EXCERPT_DIR, "chimera_hopf_sdmk_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_chimera_hopf_sdmk.mno"),
        "magic": b"MUHLCHHS",
    },
    "muhl_chimera_tset_hdvs": {
        "reg": os.path.join(EXCERPT_DIR, "chimera_tset_hdvs_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_chimera_tset_hdvs.mno"),
        "magic": b"MUHLCHTH",
    },
    "muhl_chimera_grbn_socr": {
        "reg": os.path.join(EXCERPT_DIR, "chimera_grbn_socr_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_chimera_grbn_socr.mno"),
        "magic": b"MUHLCHGS",
    },
    "muhl_chimera_socr_stig": {
        "reg": os.path.join(EXCERPT_DIR, "chimera_socr_stig_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_chimera_socr_stig.mno"),
        "magic": b"MUHLCHSS",
    },
    "muhl_chimera_flow_stig": {
        "reg": os.path.join(EXCERPT_DIR, "chimera_flow_stig_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_chimera_flow_stig.mno"),
        "magic": b"MUHLCHFS",
    },
    "muhl_chimera_pots_dmb": {
        "reg": os.path.join(EXCERPT_DIR, "chimera_pots_dmb_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_chimera_pots_dmb.mno"),
        "magic": b"MUHLCHPD",
    },
    "muhl_chimera_pred_rgcg": {
        "reg": os.path.join(EXCERPT_DIR, "chimera_pred_rgcg_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_chimera_pred_rgcg.mno"),
        "magic": b"MUHLCHPR",
    },
    "muhl_chimera_lvin_synd": {
        "reg": os.path.join(EXCERPT_DIR, "chimera_lvin_synd_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_chimera_lvin_synd.mno"),
        "magic": b"MUHLCHLS",
    },
}

CENSUS_FIRST = {
    "muhl_vscf": ("VSCF", "muhl_vscf", "input[0]", 93709728614),
    "muhl_cgat": ("CGAT", "muhl_cgat", "input_U", 93709782976),
    "muhl_hpc": ("HPC", "muhl_hpc", "input[0]", 93709884814),
    "muhl_mha": ("MHA", "muhl_mha", "input[0]", 93709824030),
    "muhl_eal": ("EAL", "muhl_eal", "attractor_select", 93709785846),
    "muhl_dmb": ("DMB", "muhl_dmb", "input", 93709782657),
    "muhl_awcg": ("AWCG", "muhl_awcg", "input", 93709781888),
}


def lane_wire(index):
    return W_LANE0 + (index % N_LANES)


def temp_wire(index):
    return W_LANE0 + N_IN + (index % N_LANES)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def _read_landed(key):
    spec = LANDED[key]
    with open(spec["reg"], encoding="utf-8") as handle:
        row = json.load(handle)[key]
    with open(spec["mno"], "rb") as handle:
        blob = handle.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != row["sha256"]:
        raise RuntimeError("%s sha256 is not the landed sidecar" % key)
    if blob[:8] != spec["magic"]:
        raise RuntimeError("%s magic is not the landed file" % key)
    return row, digest


def census_text():
    with open(CENSUS_PATH, encoding="utf-8") as handle:
        return handle.read()


def census_first(key):
    """Read documented first dest FROM FILE. Do not invent the titan dest."""
    family, name, label, expected = CENSUS_FIRST[key]
    text = census_text()
    if key == "muhl_vscf":
        match = re.search(r"\| `muhl_vscf` \| 149 \| 17 \| `MUHLVSCF` \| input\[0\] `(\d+)` \|", text)
    elif key == "muhl_cgat":
        match = re.search(r"\| `muhl_cgat` \| 97 \| 6 \| `MUHLCGAT` \| input_U `(\d+)` \|", text)
    elif key == "muhl_hpc":
        match = re.search(r"\| `muhl_hpc` \| 26480 \| 421 \| `MUHLHPC0` \| input\[0\] `(\d+)` \|", text)
    elif key == "muhl_mha":
        match = re.search(r"\| `muhl_mha` \| 2328 \| 44 \| `MUHLMHA0` \| input\[0\] `(\d+)`", text)
    elif key == "muhl_eal":
        match = re.search(r"\| `muhl_eal` \| 1456 \| 66 \| `MUHLEAL0` \| attractor_select `(\d+)` \|", text)
    elif key == "muhl_dmb":
        match = re.search(r"\| `muhl_dmb` \| 10 \| 3 \| `MUHLDMB1` \| input `(\d+)` \|", text)
    elif key == "muhl_awcg":
        match = re.search(r"\| `muhl_awcg` \| 27 \| 2 \| `MUHLAWCG` \| input `(\d+)` \|", text)
    else:
        raise RuntimeError("no census reader for %s" % key)
    if not match:
        raise RuntimeError("SUBZERO_CENSUS.md missing %s %s dest" % (name, label))
    first = int(match.group(1))
    if first != expected:
        raise RuntimeError("%s census dest is not the measured land" % key)
    return first


def planes_from_file():
    planes = {}
    sha = {}
    for key in LANDED:
        row, digest = _read_landed(key)
        planes[key] = {
            "ins": list(row["input_addrs"]),
            "outs": list(row["output_addrs"]),
        }
        sha[key] = digest
    for key in CENSUS_FIRST:
        first = census_first(key)
        addrs = list(range(first, first + 32))
        planes[key] = {"ins": addrs, "outs": addrs}
        sha[key] = "CENSUS"
    return planes, sha


def hop_dests(planes):
    hops = []
    for spec in HOPS:
        n = spec["lanes"]
        src = spec["src"]
        src_addrs = planes[src]["outs"][:n]
        if len(src_addrs) != n:
            raise RuntimeError("%s dests FROM FILE are short" % spec["name"])
        hops.append({
            "name": spec["name"],
            "src_organ": src,
            "dst_organ": NAME,
            "lanes": n,
            "src_addrs": src_addrs,
            "dst_kind": "local commons bit plane",
        })
    return hops


def dests_from_file():
    planes, sha = planes_from_file()
    hops = hop_dests(planes)
    src_addrs = []
    for hop in hops:
        src_addrs.extend(hop["src_addrs"])
    if len(src_addrs) != N_LANES:
        raise RuntimeError("commons dests FROM FILE are not 300 lanes")
    expected = {
        "hdvs_identity": planes["muhl_hdvs"]["outs"][:43],
        "sdmk_memory": planes["muhl_sdmk"]["outs"][:16],
        "hopf_memory": list(range(542, 558)),
        "immn_nonself": [29636],
        "pdap_envelope": list(range(286, 302)),
        "stig_rank": list(range(6174, 6190)),
        "flow_thread": list(range(16414, 16446)),
        "byzq_quorum": planes["muhl_byzq"]["outs"][:16],
        "rgcg_compress": planes["muhl_rgcg"]["outs"][:4],
        "synd_corrupt": list(range(2078, 2094)),
        "vscf_court": list(range(93709728614, 93709728630)),
        "cgat_cause": list(range(93709782976, 93709782992)),
        "hpc_shape": list(range(93709884814, 93709884830)),
        "mha_metabolism": list(range(93709824030, 93709824046)),
        "eal_clock": list(range(93709785846, 93709785862)),
        "dmb_bloom": list(range(93709782657, 93709782667)),
        "awcg_bloom": list(range(93709781888, 93709781904)),
        "chih_wire": planes["muhl_chimera_immn_hdvs"]["outs"][:2],
        "chhs_wire": planes["muhl_chimera_hopf_sdmk"]["outs"][:2],
        "chth_wire": planes["muhl_chimera_tset_hdvs"]["outs"][:2],
        "chgs_wire": planes["muhl_chimera_grbn_socr"]["outs"][:2],
        "chss_wire": planes["muhl_chimera_socr_stig"]["outs"][:2],
        "chfs_wire": planes["muhl_chimera_flow_stig"]["outs"][:2],
        "chpd_wire": planes["muhl_chimera_pots_dmb"]["outs"][:2],
        "chpr_wire": planes["muhl_chimera_pred_rgcg"]["outs"][:2],
        "chls_wire": planes["muhl_chimera_lvin_synd"]["outs"][:2],
    }
    if expected["hdvs_identity"][:3] != [10274, 10279, 10284]:
        raise RuntimeError("hdvs outs are not the landed sidecar plane")
    if expected["sdmk_memory"][:3] != [1188, 1963, 2738]:
        raise RuntimeError("sdmk outs are not the landed sidecar plane")
    for hop in hops:
        if hop["src_addrs"] != expected[hop["name"]]:
            raise RuntimeError("%s dests are not the landed planes" % hop["name"])
    return {
        "hops": hops,
        "src_addrs": src_addrs,
        "sha": sha,
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
    assert ng == 600
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
    assert dests["src_addrs"][:3] == [10274, 10279, 10284]
    assert [29636] in [hop["src_addrs"] for hop in dests["hops"]]
    hops = {hop["name"]: hop for hop in dests["hops"]}
    assert hops["chls_wire"]["src_addrs"] == [118, 119]
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
            "container": "muhl_titanx_commons.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "lanes": N_LANES,
            "src": "12 existing + named 19-new planes + 9 chimeras",
            "dst": "local commons bit plane",
            "buffer": "NAND NAND identity, 2 g per lane, 26 hops",
            "hops": dests["hops"],
            "src_addrs": dests["src_addrs"],
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "local out IS local in; commons bit plane only",
            "door": "impersonation flags non-self. DOOR STAYS OPEN.",
            "requested_offset_band": "OWNER_LOCAL_ALLOCATOR; not chosen in public tree",
            "titan": "NOT_WRITTEN",
        }
    }
    for key, digest in dests["sha"].items():
        sidecar[NAME][key.replace("muhl_", "") + "_sha256"] = digest
    with open(REG_PATH, "w", encoding="utf-8") as handle:
        json.dump(sidecar, handle, indent=2)
        handle.write("\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry" in argv
    blob, meta, stored = fabricate(0)
    verify_physical(blob, meta, stored)
    print("MUHLTITX structural receipt")
    print("  n_gate=%d n_wires=%d depth=%d len=%d" % (
        meta["n_gate"], meta["n_wires"], meta["depth"], meta["len"]))
    print("  sha256=%s" % meta["sha256"])
    print("  hops=%s" % ",".join(hop["name"] for hop in meta["dests"]["hops"]))
    print("  dest FROM FILE lanes=%d" % meta["lanes"])
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
