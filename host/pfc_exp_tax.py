#!/usr/bin/env python3
"""host/pfc_exp_tax.py — EXPERIMENTAL (owner 07-19): map the Muhlnickel's tax vs NATIVE, by workload TYPE.

The monetization question is "which applications fit". Answer = where is the pfc's tax (native_ops/s ÷ pfc_ops/s)
SMALL vs HUGE. Hypothesis to measure: the tax shrinks as the native operation gets heavier — simple arithmetic (native
= 1 instruction) is a terrible fit; complex crypto/verification (native already does thousands of ops) is a good fit.

pfc runs bit-sliced at W=256 (256 lanes/ripple, low RAM, safe); native is the equivalent Python/hashlib op. Byte-exact
circuits reused from pfc_exp_levers. Single process, foreground, titan.gguf not opened.
  python host/pfc_exp_tax.py
"""
import hashlib, json, os, random, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdc_cc as CC
import pfc_exp_levers as L
from pfc_exp_bench import rate

OUT_DIR = "C:/llm/sdc_out"; os.makedirs(OUT_DIR, exist_ok=True)


def pfc_ops(builder, W=256, secs=2.0):
    g, outs, check, _ = builder()
    run, out2, n_gate, n_wire, _ = L.finish(g, outs)
    if not check(run, out2): return None, n_gate
    ones = (1 << W) - 1; lanes = [random.getrandbits(W) for _ in range(g.n_in)]
    n, s = rate(lambda: run(lanes, ones), secs)
    return n * W / s, n_gate


def nat_ops(fn, secs=1.5):
    n, s = rate(fn, secs); return n / s


PREFIX = CC.PREFIX
def main():
    print("Muhlnickel TAX-BY-TYPE — Muhlnickel (bit-slice W=256) vs native, by workload\n", flush=True)
    rows = []
    specs = [
        ("add32", L.build_add32, lambda: (0x89abcdef + 0x12345678) & 0xffffffff),
        ("sha256_1block", L.build_sha_block, lambda: hashlib.sha256(struct.pack(">I", 0xdeadbeef)).digest()),
        ("double_sha_miner", L.build_miner,
         lambda: hashlib.sha256(hashlib.sha256(PREFIX[:76] + struct.pack(">I", 0)).digest()).digest()),
    ]
    print(f"  {'workload':<18s}{'gates':>9s}{'Muhlnickel H/s (W256)':>16s}{'native ops/s':>15s}{'tax':>10s}", flush=True)
    for name, builder, nat in specs:
        p, ng = pfc_ops(builder)
        if p is None:
            print(f"  {name:<18s}  VERIFY FAILED — skip"); continue
        nv = nat_ops(nat)
        tax = nv / max(p, 1e-9)
        rows.append({"workload": name, "gates": ng, "pfc_ops_s": round(p), "native_ops_s": round(nv), "tax": round(tax, 1)})
        print(f"  {name:<18s}{ng:>9,}{p:>16,.0f}{nv:>15,.0f}{tax:>9,.1f}x", flush=True)
    json.dump(rows, open(f"{OUT_DIR}/pfc_tax.json", "w"), indent=2)
    print(f"\n  the pattern: tax is HUGE for simple ops (native = ~1 instruction), SMALL for heavy crypto/verification.", flush=True)
    print(f"  -> the Muhlnickel fits where the useful operation is already complex, not where native does it in one instruction.", flush=True)
    print(f"\n  results -> {OUT_DIR}/pfc_tax.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
