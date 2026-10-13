#!/usr/bin/env python3
"""host/wf_titancir_decode.py — OPEN THE BOX: parse the TITANCIR records in titan blk.1.ffn_gate_up_exps into a
structure and test the netlist/DAG hypothesis. Read-only, bounded mmap reads (uses mmap.find, no whole-tensor dequant).

  - locate every TITANCIR magic in blk.1, report count + spacing
  - parse the first record's header (u32 fields after the magic) + the integer table that follows
  - test whether the table is a NETLIST: are the node references backward-only (a valid DAG)?
  - confirm the WOF0 fill is an inert sentinel (dequant one block correctly)
"""
import os, sys, struct, math
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT, dequant

TITAN = "C:/llm/models/titan.gguf"
MAGIC = b"TITANCIR"


def ent(b):
    if not b: return 0.0
    c = Counter(b); n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def main():
    g = GGUF(TITAN); mm = g.mm
    t = g.tensors["blk.1.ffn_gate_up_exps.weight"]
    ne0, ne1, nexp = t["dims"]
    bpb, wpb = _QT[t["type"]]
    tbytes = (ne0 * ne1 * nexp) // wpb * bpb
    base = g.data0 + t["off"]; end = base + tbytes
    exp_bytes = ne1 * (ne0 // wpb * bpb)

    # 1) locate every TITANCIR magic
    offs = []; p = base
    while True:
        i = mm.find(MAGIC, p, end)
        if i < 0: break
        offs.append(i); p = i + 8
    print(f"blk.1 gate_up: {tbytes/1e6:.0f} MB, {nexp} experts of {exp_bytes/1e6:.2f} MB each")
    print(f"TITANCIR records found: {len(offs)}")
    if offs:
        rel = [(o - base) for o in offs]
        gaps = [rel[i+1]-rel[i] for i in range(len(rel)-1)]
        print(f"  first at byte {rel[0]:,} (expert {rel[0]//exp_bytes})  last at expert {rel[-1]//exp_bytes}")
        print(f"  experts carrying a record: {sorted(set(r//exp_bytes for r in rel))}")
        if gaps:
            gc = Counter(gaps)
            print(f"  most common gap between records: {gc.most_common(3)}")

    # 2) parse the FIRST record
    o = offs[0]
    hdr = struct.unpack_from("<32I", mm, o + 8)         # 32 u32 after the magic
    print(f"\nfirst record @ expert {(o-base)//exp_bytes}, byte {o-base:,}")
    print(f"  header u32[0:8]: {hdr[:8]}  (guess: ver={hdr[0]}, A={hdr[1]}, B={hdr[2]}, C={hdr[3]}, D={hdr[4]}, E={hdr[5]})")

    # read a big window of u32s and find where the structured integer table ends (values stay small, then noise)
    NW = 8192
    words = list(struct.unpack_from("<%dI" % NW, mm, o + 8))
    # the table are 'small' ints (node indices). find run length where >90% of a sliding window is < some bound.
    BOUND = max(hdr[1], hdr[2], 256) * 4
    tbl_end = 0
    for k in range(len(words)):
        w32 = words[max(0, k-31):k+1]
        if sum(1 for x in w32 if x < BOUND) < 0.8 * len(w32):
            tbl_end = k; break
    else:
        tbl_end = len(words)
    table = words[:tbl_end]
    print(f"  structured integer run: {len(table)} u32 (until values stop looking like indices, bound<{BOUND})")
    print(f"  table[0:40]: {table[:40]}")
    if table:
        print(f"  table stats: min {min(table)}, max {max(table)}, mean {sum(table)/len(table):.1f}, distinct {len(set(table))}")

    # 3) DAG / netlist test — several interpretations, report which fits best
    def dag_score(vals, n_inputs, arity):
        """treat vals as a flat list of input-refs for gates of given arity; gate g's node index = n_inputs+g;
        a valid combinational DAG references only strictly-earlier node indices. return fraction backward."""
        good = tot = 0
        for gi in range(len(vals) // arity):
            nidx = n_inputs + gi
            for a in range(arity):
                r = vals[gi * arity + a]
                tot += 1
                if r < nidx: good += 1
        return good / tot if tot else 0.0

    body = table[6:]  # skip the 6 header-ish fields
    print("\n  netlist/DAG test (fraction of references that point strictly BACKWARD = valid combinational circuit):")
    best = None
    for arity in (2, 3, 1):
        for nin in (hdr[3], hdr[1] % 64, 8, 16, hdr[4]*hdr[5] if hdr[4] and hdr[5] else 8):
            nin = max(1, nin)
            s = dag_score(body, nin, arity)
            if best is None or s > best[0]: best = (s, arity, nin)
            print(f"    arity={arity} n_inputs={nin:>3} -> {s:5.1%} backward")
    print(f"  >> best fit: arity={best[1]}, n_inputs={best[2]} -> {best[0]:.1%} backward-referencing "
          f"({'looks like a valid DAG' if best[0] > 0.9 else 'partial / not a clean DAG'})")

    # 4) confirm WOF0 is an inert sentinel: dequant the first Q4_0 block of a pure-fill layer (blk.2)
    print("\n  WOF0 sentinel — dequant of blk.2 gate_up first block (should be junk, not real weights):")
    t2 = g.tensors["blk.2.ffn_gate_up_exps.weight"]
    rb = ne0 // wpb * bpb
    raw = bytes(mm[g.data0 + t2["off"]: g.data0 + t2["off"] + bpb])   # one Q4_0 block (18 bytes / 32 weights)
    vals = dequant(raw, t2["type"], wpb)
    print(f"    raw block hex: {raw.hex(' ')}")
    print(f"    -> 32 dequant values: min {min(vals):.4f} max {max(vals):.4f} distinct {len(set(round(v,4) for v in vals))}")
    print(f"    (fp16 scale from the sentinel bytes = {struct.unpack('<e', raw[:2])[0]:.4g})")


if __name__ == "__main__":
    raise SystemExit(main())
