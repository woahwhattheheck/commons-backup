#!/usr/bin/env python3
"""host/sdc_grounded.py — GROUNDED ROUTING (Phase 2 of the SDC OS): exact/verifiable claims go to VERIFIED circuits so the
answer is correct by construction; anything not grounded by a verified circuit is REFUSED, never fabricated.

Grounded in FINALREADME: §5.9 (a co-resident logic network performs the exactness-critical operation — checking an exact
predicate / applying an exactly-specified rule — alongside the fuzzy model) · §7D (route exact/verifiable claims through
the verified experts) · §6/§7 (address the region) · §5.5 (memoize) · the GROUND operator ("unknown(c) <=> not
provable(c); never invent a value"). This is the refuse-to-hallucinate mechanism, mechanically — no slow inference.

The contrast it proves: a raw LLM asked "9094 × 40496" GUESSES (and large products it usually gets wrong); the SDC OS
ROUTES the multiply to the exact `prog_mul32` circuit (32×32→64, 32,768 gates, stored) and returns the exact product,
computed CONTAINED on the SDC. A question with no verified circuit is REFUSED.

  python host/sdc_grounded.py "9094 * 40496"      # -> grounded exact via prog_mul32
  python host/sdc_grounded.py "is 31537 > 30968"  # -> grounded exact via cpu_fwd GT
  python host/sdc_grounded.py "population of Zarnovia"   # -> REFUSED (no verified circuit; won't fabricate)
  python host/sdc_grounded.py demo
"""
import re, sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_os


def imul(a, b):
    """exact 32×32 -> 64-bit integer product, via the stored prog_mul32 circuit, rippled CONTAINED on the SDC."""
    inb = [(a >> i) & 1 for i in range(32)] + [(b >> i) & 1 for i in range(32)]
    r, gates = sdc_os.run_circuit("prog_mul32", inb)
    return r, "prog_mul32", gates


def ground(request):
    """route the request to a VERIFIED circuit if it's exact/verifiable; else REFUSE. Returns a dict."""
    s = request.strip()
    m = re.fullmatch(r"\s*(-?\d+)\s*\*\s*(-?\d+)\s*", s)                        # exact multiply -> prog_mul32
    if m:
        a, b = int(m.group(1)) & 0xffffffff, int(m.group(2)) & 0xffffffff
        r, expert, gates = imul(a, b)
        return {"grounded": True, "expert": expert, "gates": gates, "result": r,
                "why": "exact 32×32→64 integer product from a verified stored circuit — cannot be hallucinated"}
    m = re.fullmatch(r"\s*(?:is\s+)?(-?\d+)\s*([+\-])\s*(-?\d+)\s*", s)         # 16-bit add/sub -> cpu_fwd
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        r = sdc_os.orchestrate("add" if op == "+" else "sub", a & 0xffff, b & 0xffff)
        return {"grounded": True, "expert": r["expert"], "gates": r["gates"], "result": r["result"],
                "why": "exact 16-bit result from the verified ALU circuit"}
    m = re.fullmatch(r"\s*(?:is\s+)?(-?\d+)\s*>\s*(-?\d+)\s*\??\s*", s)          # exact compare -> cpu_fwd GT
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        r = sdc_os.orchestrate("gt", a & 0xffff, b & 0xffff)
        return {"grounded": True, "expert": r["expert"], "gates": r["gates"], "result": bool(r["result"]),
                "why": "exact signed comparison from the verified ALU circuit"}
    return {"grounded": False, "expert": None, "result": None,                  # GROUND: not provable -> refuse
            "why": "no verified circuit grounds this request — REFUSED rather than fabricated (GROUND: unknown ⇔ not provable)"}


def demo():
    print("GROUNDED ROUTING — exact claims -> verified circuits (correct by construction); unverifiable -> refused.\n", flush=True)
    print("  Exact multiplications an LLM would guess at, routed to the verified prog_mul32 circuit on the SDC:", flush=True)
    ok = 0; tot = 0
    for a, b in [(9094, 40496), (65535, 65535), (123456, 654321), (99999, 99999), (2**31 - 1, 3)]:
        r = ground(f"{a} * {b}"); ref = (a * b) & ((1 << 64) - 1); good = r["result"] == ref; ok += good; tot += 1
        print(f"    {a} × {b} = {r['result']:<22}  ref {ref:<22} {'EXACT' if good else 'MISMATCH'}  [{r['expert']}]", flush=True)
    print(f"\n  Exact comparison, routed to the verified ALU:", flush=True)
    r = ground("is 31537 > 30968"); print(f"    31537 > 30968 ? {r['result']}   [{r['expert']}]  {r['why']}", flush=True)
    print(f"\n  Unverifiable question — the grounded response is to REFUSE, not fabricate:", flush=True)
    for q in ["population of Zarnovia", "the CEO's home address"]:
        r = ground(q); print(f"    \"{q}\" -> grounded={r['grounded']}  ({r['why']})", flush=True)
    print(f"\n  {ok}/{tot} multiplications byte-exact via the stored circuit — grounded by construction, no model guess.", flush=True)
    return 0


if __name__ == "__main__":
    arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "demo"
    if arg == "demo": raise SystemExit(demo())
    r = ground(arg)
    if r["grounded"]:
        print(f"GROUNDED: {arg}  =  {r['result']}   [verified circuit: {r['expert']}, {r['gates']} gates]\n  {r['why']}")
    else:
        print(f"REFUSED: \"{arg}\"\n  {r['why']}")
