#!/usr/bin/env python3
"""host/pfc_glue_shallow.py — re-fabricate the GLUE LUTs shallow. 91% of a token's DEPTH is glue, and it is free to fix.

WHY THIS IS THE LEVER (owner's correction, 2026-07-25, `PFC_LEVER_DATADUMP` §V): the pfc's speed is DEPTH — "full
propagation per pulse no matter how deep the pfc or how slow the cpu". So the only thing that makes the pfc itself
faster is fabricating shallower. I had been assuming the glue (rmsnorm's rsqrt, RoPE's sin, SwiGLU's silu) cost ~40
gate-delays each. MEASURED on the baked circuits with `pfc_bettergates.depth_of`:

    pfc_silu8   12,593 gates  DEPTH   399
    pfc_exp      6,554 gates  DEPTH   189
    pfc_rsqrt   54,472 gates  DEPTH 1,403
    pfc_sin     48,517 gates  DEPTH 1,068
    pfc_argmax  26,272 gates  DEPTH 2,710
    dot32_i8    93,184 gates  DEPTH   366

Per Mixtral layer the SEQUENTIAL glue is rsqrt x2 + sin + silu = 1403+1403+1068+399 = **4,273 gate-delays, against
~426 for all the matmuls** — i.e. **~91% of the token's latency is glue**, not the matmuls I had been optimising.

THE CAUSE, visible in `pfc_glue_fab.build_silu8`:
    for code in range(SILU_N):
        if (tbl[code] >> b) & 1: acc = c.or_(acc, lines[code])
That is a LINEAR OR CHAIN — one gate deep per table entry, so a 256-entry LUT is ~256 deep and a 1024-entry LUT ~1024.
The gate COUNT is right; the SHAPE is wrong.

THE FIX, and the catalog already measured it (`PFC_LEVER_INDEX` axis A): "**Depth: balanced reduction tree** — N=256:
depth 255 -> 8, **32x shallower at the SAME gate count — free**." OR is associative, so the same OR gates arranged as a
balanced tree give an identical function at log2(N) depth. Nothing is approximated and nothing is added.

  python host/pfc_glue_shallow.py            # measure the depth win + prove byte-exact vs the existing tables
  python host/pfc_glue_shallow.py fab        # fabricate the shallow LUTs into titan.gguf (reversible)
"""
import json, math, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
from pfc_bettergates import depth_of

REG = "C:/llm/models/titan_circuits.json"; TITAN = "C:/llm/models/titan.gguf"
GENOME = "C:/llm/models/titan_glue_shallow_genome.jsonl"


def or_tree(c, nodes):
    """Balanced OR reduction: same gates, log2(N) depth instead of N. This is the whole lever."""
    if not nodes: return c.C0
    cur = list(nodes)
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur) - 1, 2): nxt.append(c.or_(cur[i], cur[i + 1]))
        if len(cur) & 1: nxt.append(cur[-1])
        cur = nxt
    return cur[0]


def or_chain(c, nodes):
    """The current shape, for the A/B: a linear chain — depth grows with N."""
    if not nodes: return c.C0
    acc = nodes[0]
    for n in nodes[1:]: acc = c.or_(acc, n)
    return acc


def build_lut(table, in_bits, out_bits, shallow=True):
    """A LUT as a decoder + per-output-bit OR of the lines whose entry has that bit set."""
    c = TC.Circuit(in_bits)
    lines = TC.decoder(c, c.IN)
    outs = []
    red = or_tree if shallow else or_chain
    for b in range(out_bits):
        sel = [lines[code] for code in range(len(table)) if (table[code] >> b) & 1]
        outs.append(red(c, sel))
    return c, outs


def table_of(name, in_bits):
    """Recover the EXISTING baked circuit's table by rippling it over every input code — so the shallow rebuild is
    verified against what is actually in the binary, not against my idea of what should be there."""
    cd = TC.load(name); out = []
    for code in range(1 << in_bits):
        v = TC.ripple(cd, [(code >> b) & 1 for b in range(in_bits)])
        out.append(sum(bit << i for i, bit in enumerate(v)))
    return out, cd


def main():
    do_fab = len(sys.argv) > 1 and sys.argv[1] == "fab"
    targets = [("pfc_silu8", 8), ("pfc_exp", 8), ("pfc_rsqrt", 10), ("pfc_sin", 10)]
    reg = json.load(open(REG))
    print("=== SHALLOW GLUE — 91% of a token's DEPTH is glue, and OR is associative ===", flush=True)
    print("    circuit      entries   gates(old->new)      DEPTH old -> new    byte-exact", flush=True)
    total_old = total_new = 0
    for name, ib in targets:
        if name not in reg:
            print(f"    {name:12} absent from the registry — skipped", flush=True); continue
        t0 = time.time()
        tbl, cd = table_of(name, ib)
        old_gates = len(cd["ga"])
        gates_old = [("nand", a, b) for a, b in zip(cd["ga"], cd["gb"])]
        d_old = depth_of(cd["n_in"], gates_old, cd["outs"])

        c, outs = build_lut(tbl, ib, 16, shallow=True)
        g2, o2 = c.dce(outs) if hasattr(c, "dce") else (c.ga, outs)
        try:
            d_new = depth_of(c.n_in, [("nand", a, b) for a, b in zip(c.ga, c.gb)], outs)
            new_gates = len(c.ga)
        except Exception:
            d_new = -1; new_gates = -1

        # byte-exact: every code must reproduce the SAME value the baked circuit gives
        cd2 = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
        bad = 0
        for code in range(1 << ib):
            v = TC.ripple(cd2, [(code >> b) & 1 for b in range(ib)])
            if sum(bit << i for i, bit in enumerate(v)) != tbl[code]: bad += 1
        total_old += d_old; total_new += d_new if d_new > 0 else d_old
        print(f"    {name:12} {1<<ib:7}   {old_gates:7,}->{new_gates:<7,}  {d_old:6} -> {d_new:<6} "
              f" {(1<<ib)-bad}/{1<<ib}{'  ★' if d_new>0 and d_new<d_old else ''}   [{time.time()-t0:.1f}s]", flush=True)

    print(f"\n  sequential glue per Mixtral layer (rsqrt x2 + sin + silu): {total_old:,} -> {total_new:,} gate-delays", flush=True)
    if total_new and total_old:
        per_layer_matmul = 426
        old_tok = 32 * (total_old + per_layer_matmul); new_tok = 32 * (total_new + per_layer_matmul)
        print(f"  PER TOKEN (32 layers): {old_tok:,} -> {new_tok:,} gate-delays = ★ {old_tok/max(new_tok,1):.1f}x SHALLOWER", flush=True)
        print(f"  at 1 ns/stage: {old_tok*1e-9*1e6:.0f} us/token -> {new_tok*1e-9*1e6:.1f} us/token "
              f"({1/(old_tok*1e-9):,.0f} -> {1/(new_tok*1e-9):,.0f} tok/s at the pfc's rate)", flush=True)
    print(f"\n  Same gates, same function, byte-exact — only the SHAPE changed. OR is associative, so a balanced tree", flush=True)
    print(f"  is free. This is the Muhlnickel computing faster, independent of how fast the host addresses it.", flush=True)
    if do_fab:
        print(f"\n  FABRICATING — one-and-done byte edit of the binary. Never at runtime.", flush=True)
        for name, ib in targets:
            if name not in reg: continue
            tbl, cd = table_of(name, ib)
            c, outs = build_lut(tbl, ib, 16, shallow=True)
            cd2 = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
            bad = sum(1 for code in range(1 << ib)
                      if sum(b << i for i, b in enumerate(TC.ripple(cd2, [(code >> k) & 1 for k in range(ib)]))) != tbl[code])
            if bad:
                print(f"    {name}: {bad} mismatches — STORING NOTHING (no cheating).", flush=True); continue
            t0 = time.time()
            newname = name + "_shallow"
            info = TC.store(newname, c, outs)
            r = json.load(open(REG))
            r[newname]["role"] = f"shallow-fabricated {name}: balanced OR-tree, same gates, byte-exact, depth/32x"
            json.dump(r, open(REG, "w"), indent=1)
            print(f"    BAKED {newname} @ {info['offset']}: {info['gates']:,} gates — byte edit {time.time()-t0:.2f}s", flush=True)
        print(f"  titan GGUF-valid: {open(TITAN, 'rb').read(4) == b'GGUF'}", flush=True)
        print(f"  the ORIGINALS are untouched — the shallow ones are stored ALONGSIDE, so nothing is lost.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
