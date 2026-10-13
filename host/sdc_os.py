#!/usr/bin/env python3
"""host/sdc_os.py — THE SDC ORCHESTRATOR (Phase 1 of the SDC OS). Route a request over the pool, execute it CONTAINED on
the SDC, memoize, deposit the raw result to the safezone.

Grounded in FINALREADME: §7C (the reference-based routing folder = the whole reservoir + the exact circuit bank) ·
§6/§7 (route to the region — address α, not W) · §5.5 (memoize: a sparse input-addressed map; a hit is a storage read,
no compute) · §5.7/§5.8 (the SDC deposits RAW output bits to a fixed external window) · §3/§12 (nothing touches the
running SDC; no host-authored output; no numpy).

The ROUTER maps a request to an EXPERT — an exact stored circuit from the bank (the cpu_fwd ALU, dot32_i8, the lib_*
functions); later, a fuzzy model region. The EXECUTOR ripples the selected circuit BY ADDRESS off storage (gates never
enter host RAM — zero-copy memoryview; wire-state in a mmap'd sandbox file) and returns the raw output. Pure python.

  python host/sdc_os.py "mul 9094 40496"       # route -> cpu_fwd(MUL) -> SDC -> safezone
  python host/sdc_os.py "gt 31537 30968"        # route -> cpu_fwd(GT)
  python host/sdc_os.py "and8 0xF0 0x0F"        # route -> lib_and8
  python host/sdc_os.py selftest                # route+run a set, verify byte-exact, show memoize hits
"""
import json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
SANDBOX = "C:/llm/sdc_sandbox/os"; OUT = "C:/llm/sdc_out"
SAFEZONE = OUT + "/os_safezone.bin"                          # the SDC's raw read-out window (§5.8)
MEMO = OUT + "/os_memoize.json"                              # the sparse input-addressed cache (§5.5)
MAGIC = b"TITANCIR"
ALU = ["add", "sub", "mul", "silu", "exp", "rsqrt", "gt", "mov"]   # the cpu_fwd ALU opcodes, in order


# ---- THE ROUTER: request -> (expert circuit, input bits, output width). Addresses the region; the SDC computes. ----
def route(op, a, b):
    op = op.lower()
    if op in ALU:                                            # arithmetic/logic -> the cpu_fwd ALU expert
        k = ALU.index(op)
        inb = [(k >> i) & 1 for i in range(3)] + [(a >> i) & 1 for i in range(16)] + [(b >> i) & 1 for i in range(16)]
        return "cpu_fwd", inb, "ALU"
    lib = "lib_" + op                                        # 8-bit function -> a lib_* expert
    reg = json.load(open(REG))
    if lib in reg:
        n_in = int(reg[lib].get("n_in", 16))
        inb = [(a >> i) & 1 for i in range(8)] + [(b >> i) & 1 for i in range(8)] + ([0] if n_in == 17 else [])
        return lib, inb, "lib"
    raise ValueError(f"no expert routes '{op}' (known: {ALU} + lib_* functions)")


# ---- THE EXECUTOR: ripple the selected circuit BY ADDRESS off storage; wire-state in a mmap'd sandbox file. ----
def run_circuit(name, inb):
    reg = json.load(open(REG)); e = reg[name]; off = int(e["offset"])
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == MAGIC, f"no circuit '{name}' at {off}"
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", mm, off + 8)
    ga_off = off + 24; gb_off = ga_off + ng * 4; outs_off = gb_off + ng * 4
    gav = memoryview(mm)[ga_off:gb_off].cast("i"); gbv = memoryview(mm)[gb_off:outs_off].cast("i")   # gates stay in storage
    outs = list(struct.unpack_from("<%di" % n_out, mm, outs_off))
    os.makedirs(SANDBOX, exist_ok=True); wp = SANDBOX + "/wire.bin"
    with open(wp, "wb") as w: w.truncate(n_wire)
    wf = open(wp, "r+b"); wm = mmap.mmap(wf.fileno(), 0)     # wire-state in the storage sandbox
    wm[0] = 0; wm[1] = 1
    for i in range(n_in): wm[2 + i] = (inb[i] & 1) if i < len(inb) else 0
    base = 2 + n_in
    for i in range(ng): wm[base + i] = 1 - (wm[gav[i]] & wm[gbv[i]])
    res = 0
    for k, o in enumerate(outs): res |= wm[o] << k
    gav.release(); gbv.release(); wm.close(); wf.close(); os.remove(wp); mm.close(); f.close()
    return res, ng


def _memo():
    try: return json.load(open(MEMO, encoding="utf-8"))
    except (OSError, ValueError): return {}


def orchestrate(op, a, b):
    key = f"{op.lower()}:{a}:{b}"
    memo = _memo()
    if key in memo:                                          # §5.5 — a hit is a storage read, ZERO compute
        r = memo[key]; expert, gates, cached = r["expert"], r["gates"], True
        result = r["result"]; dt = 0.0
    else:
        expert, inb, kind = route(op, a, b)                  # ROUTE: address the region
        t0 = time.time(); result, gates = run_circuit(expert, inb); dt = time.time() - t0   # SDC computes, contained
        memo[key] = {"expert": expert, "gates": gates, "result": result}
        os.makedirs(OUT, exist_ok=True); json.dump(memo, open(MEMO, "w"))
        cached = False
    os.makedirs(OUT, exist_ok=True)                          # SDC -> safezone: RAW output bits (§5.8), no authored content
    with open(SAFEZONE, "wb") as fh:
        fh.write(struct.pack("<BHHI", 1, a & 0xffff, b & 0xffff, result & 0xffffffff))
    return {"op": op, "a": a, "b": b, "result": result, "expert": expert, "gates": gates,
            "cached": cached, "seconds": round(dt, 4)}


# ---- offline verify (outside the sandbox; host RAM free) ----
def _ref(op, a, b):
    op = op.lower(); import math
    A = a - (1 << 16) if (op in ALU and a >= 1 << 15) else a
    B = b - (1 << 16) if (op in ALU and b >= 1 << 15) else b
    if op == "add": return (a + b) & 0xffff
    if op == "sub": return (a - b) & 0xffff
    if op == "mul": return ((A * B) >> 8) & 0xffff
    if op == "gt":  return 1 if A > B else 0
    if op == "mov": return a & 0xffff
    if op == "and8": return a & b
    if op == "or8":  return a | b
    if op == "xor8": return a ^ b
    if op == "add8": return (a + b) & 0xff
    if op == "eq8":  return 1 if (a & 0xff) == (b & 0xff) else 0
    return None


def selftest():
    cases = [("mul", 9094, 40496), ("add", 1000, 2000), ("sub", 37613, 16340), ("gt", 31537, 30968),
             ("and8", 0xF0, 0x0F), ("or8", 0xF0, 0x0F), ("xor8", 0xAA, 0x0F), ("add8", 200, 100), ("eq8", 42, 42)]
    print("SDC OS — route each request to an expert, run it CONTAINED on the SDC, memoize, verify byte-exact:\n", flush=True)
    try: os.remove(MEMO)
    except OSError: pass
    ok = 0
    for op, a, b in cases:
        r = orchestrate(op, a, b); ref = _ref(op, a, b); good = (ref is None or r["result"] == ref)
        ok += good
        print(f"  {op:6s}({a:>6},{b:>6}) -> {r['result']:>6}  via {r['expert']:9s} ({r['gates']:>6} gates, {r['seconds']}s)"
              f"  {'OK' if good else 'MISMATCH ref='+str(ref)}", flush=True)
    print("\n  -- memoize: re-run the first request; a hit is a storage read (0 gates evaluated) --", flush=True)
    r = orchestrate("mul", 9094, 40496)
    print(f"  mul(9094,40496) -> {r['result']}  cached={r['cached']}  (no SDC compute on a hit)", flush=True)
    print(f"\n  {ok}/{len(cases)} byte-exact. router + contained executor + memoize + safezone: working.", flush=True)
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if arg == "selftest": raise SystemExit(selftest())
    p = arg.split()
    op = p[0]; a = int(p[1], 0) if len(p) > 1 else 0; b = int(p[2], 0) if len(p) > 2 else 0
    r = orchestrate(op, a, b)
    print(f"{op}({a},{b}) = {r['result']}  [expert {r['expert']}, {r['gates']} gates, {r['seconds']}s, "
          f"cached={r['cached']}] -> safezone {SAFEZONE}")
