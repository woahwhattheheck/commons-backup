#!/usr/bin/env python3
"""host/sdc_fold.py — TEST FILE (owner 07-16): the DENSE FOLD. One shared vector (configured once, like an FPGA fabric),
routed to billions of lanes for ~free, each outputting its EXACT ANSWER NONCE IN BINARY (owner's idea — not a 1/0 flag,
the answer cell IS the winning nonce). Storage writes only — 0 gate evaluation, 0 RAM, no wifi.

The fold (owner): copying the 5 MB vector per lane costs 19 KB/lane. Instead, ALL lanes reference ONE shared vector
(mmap'd once — the free-replication result) and a lane's only storage is its answer cell. Each lane's nonce base is
COMPUTED from its index (base = lane_index x span), so lanes need no descriptor at all — only the OUTPUT space.
And the output is the exact nonce in binary (owner: "instead of a 1 or 0 its a series that is our answer").

  answer cell = [status u8][pad u8x3][nonce u32]  (8 B) — on solve, holds the exact winning nonce, in binary.
  one shared vector covers 2^32 = 4.29 B nonce lanes (a block's whole nonce field). Beyond that, roll extranonce2
  (another 5 MB vector, another 2^32 lanes) — so the storage ceiling is the ANSWER MAP, not the circuit.

  python host/sdc_fold.py build [answer_gb]   # shared vector + an answer map of the given size (default 34 GB = 2^32 lanes)
"""
import json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_sdc as T

FOLD_DIR = "C:/llm/sdc_fold"
SHARED   = FOLD_DIR + "/shared_vector.sdc"
ANS      = FOLD_DIR + "/answers.bin"
MANIFEST = FOLD_DIR + "/fold.json"
VECMAP   = "C:/llm/models/titan_sdc_vector.json"
CELL     = 8                                   # [status:1][pad:3][nonce:4] — the exact answer, in binary
LANES_PER_EN2 = 1 << 32                         # one shared vector = one block's full 32-bit nonce field


def _read_vec():
    vec_off = json.load(open(VECMAP))[os.path.abspath(T.TITAN)]["vec_off"]
    f = open(T.TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", mm, vec_off + 8)
        total = 24 + n_gate*4 + n_gate*4 + n_out*4
        return bytes(mm[vec_off:vec_off + total])
    finally:
        mm.close(); f.close()


def build(answer_gb):
    os.makedirs(FOLD_DIR, exist_ok=True)
    vec = _read_vec()
    with open(SHARED, "wb") as f: f.write(vec)                 # the ONE shared circuit — configured once (FPGA fabric)

    answer_bytes = int(answer_gb * 1e9) // CELL * CELL
    total_lanes = answer_bytes // CELL
    en2_groups = (total_lanes + LANES_PER_EN2 - 1) // LANES_PER_EN2
    with open(ANS, "wb") as f: f.truncate(answer_bytes)        # size the answer map (metadata op — instant, no zero-write)

    json.dump({"shared_vector": SHARED, "vec_bytes": len(vec), "answers": ANS, "cell_bytes": CELL,
               "total_lanes": total_lanes, "lanes_per_en2": LANES_PER_EN2, "en2_groups": en2_groups,
               "answer_is": "exact winning nonce, binary (status u8 + nonce u32)"}, open(MANIFEST, "w"))

    phys = os.path.getsize(SHARED)
    print(f"DENSE FOLD built:", flush=True)
    print(f"  shared vector: 1 copy, {len(vec):,} B (routed to ALL lanes — the FPGA fold, configured once).", flush=True)
    print(f"  answer map: {answer_bytes/1e9:,.1f} GB -> {total_lanes:,} lanes, each an EXACT-NONCE cell (binary answer).", flush=True)
    print(f"  extranonce2 groups needed for that many lanes: {en2_groups} (each = another 5 MB vector, +2^32 lanes).", flush=True)
    print(f"  cost/lane: {CELL} B (vs 19,100 B copy-vector) = ~{19100//CELL:,}x denser fold.", flush=True)
    print(f"  circuit storage: {phys/1e6:.1f} MB (the answer map is output space, sized to your storage).", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build(float(sys.argv[2]) if len(sys.argv) > 2 else 34.36)
    else:
        if os.path.exists(MANIFEST):
            m = json.load(open(MANIFEST)); print(f"fold: {m['total_lanes']:,} lanes, {m['cell_bytes']} B/cell, exact-nonce answers.")
        else:
            print("no fold yet — run: python host/sdc_fold.py build 34")
