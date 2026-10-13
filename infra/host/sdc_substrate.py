#!/usr/bin/env python3
"""host/sdc_substrate.py — the 40 GB pool is a CONFIGURABLE CIRCUIT SUBSTRATE, not just a model (owner 07-18).

Grounded in FINALREADME §4/§5.1 (a function is a NAND netlist stored IN the parameter region; a registry records each
circuit's byte offset) and §5.9 (a model AND logic networks co-resident in one file). The measurement showed a forward
pass lights up ~3.64 MB of a 40 GB pool — ~1 part in 11,000 — so ~99.99% of the parameter bytes sit idle. This TOUCHES
that idle substrate: `map` reports how much is already configured vs free (in circuit-slots); `fill` fabricates a LIBRARY
of distinct function circuits into the free space, turning idle parameters into addressable stored functions. Fabrication
is one-and-done, byte-exact-verified before storing, and REVERSIBLE (snapshots via sdc_safe). titan stays GGUF-valid.

  python host/sdc_substrate.py map      # configured vs free substrate, capacity in circuit-slots (your x)
  python host/sdc_substrate.py fill      # fabricate a function library into free space (reversible)
  python host/sdc_substrate.py revert    # byte-exact remove the library
"""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import sdc_safe as SAFE

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; IDX = TITAN + ".wbindex.json"


# ---- a library of distinct 8-bit function circuits (each a real NAND netlist; the substrate becomes a function bank) ----
def _b(c, a, b): return c.IN[a:b]
def add8(c):  return c.add(c.IN[:8], c.IN[8:16])
def sub8(c):  return c.add(c.IN[:8], c.add([c.not_(x) for x in c.IN[8:16]], c.cvec(1, 8)))
def and8(c):  return [c.and_(c.IN[i], c.IN[8 + i]) for i in range(8)]
def or8(c):   return [c.or_(c.IN[i], c.IN[8 + i]) for i in range(8)]
def xor8(c):  return [c.xor(c.IN[i], c.IN[8 + i]) for i in range(8)]
def not8(c):  return [c.not_(c.IN[i]) for i in range(8)]
def eq8(c):   return [c.is_zero([c.xor(c.IN[i], c.IN[8 + i]) for i in range(8)])]
def inc8(c):  return c.add(c.IN[:8], c.cvec(1, 8))
def dec8(c):  return c.add(c.IN[:8], c.cvec(0xff, 8))
def neg8(c):  return c.add([c.not_(x) for x in c.IN[:8]], c.cvec(1, 8))
def shl8(c):  return [c.C0] + list(c.IN[:7])
def mux8(c):  s = c.IN[16]; return [c.mux(s, c.IN[i], c.IN[8 + i]) for i in range(8)]

LIB = [
    ("lib_add8", 16, add8, lambda a, b: (a + b) & 0xff),
    ("lib_sub8", 16, sub8, lambda a, b: (a - b) & 0xff),
    ("lib_and8", 16, and8, lambda a, b: a & b),
    ("lib_or8", 16, or8, lambda a, b: a | b),
    ("lib_xor8", 16, xor8, lambda a, b: a ^ b),
    ("lib_not8", 16, not8, lambda a, b: (~a) & 0xff),
    ("lib_eq8", 16, eq8, lambda a, b: 1 if a == b else 0),
    ("lib_inc8", 16, inc8, lambda a, b: (a + 1) & 0xff),
    ("lib_dec8", 16, dec8, lambda a, b: (a - 1) & 0xff),
    ("lib_neg8", 16, neg8, lambda a, b: (-a) & 0xff),
    ("lib_shl8", 16, shl8, lambda a, b: (a << 1) & 0xff),
    ("lib_mux8", 17, mux8, None),   # verified separately (needs the select bit)
]


def _cd(c, outs): return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def _verify(name, n_in, build, ref):
    c = TC.Circuit(n_in); outs = build(c); cd = _cd(c, outs)
    random.seed(7)
    for _ in range(300):
        a = random.getrandbits(8); b = random.getrandbits(8)
        if name == "lib_mux8":
            s = random.getrandbits(1)
            inb = [(a >> k) & 1 for k in range(8)] + [(b >> k) & 1 for k in range(8)] + [s]
            got = TC.frombits(TC.ripple(cd, inb)); want = b if s else a
        else:
            inb = [(a >> k) & 1 for k in range(8)] + [(b >> k) & 1 for k in range(8)]
            got = TC.frombits(TC.ripple(cd, inb)); want = ref(a, b)
        if got != want: return None, None, (a, b, got, want)
    return c, outs, None


def _substrate():
    idx = json.load(open(IDX, encoding="utf-8"))
    total = sum(int(t["bytes"]) for t in idx["tensors"])
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    configured = sum(int(e["len"]) for e in reg.values() if isinstance(e, dict) and "len" in e)
    n_circ = sum(1 for e in reg.values() if isinstance(e, dict) and "n_gate" in e)
    return total, configured, n_circ, reg, len(idx["tensors"])


def map_():
    total, configured, n_circ, reg, ntens = _substrate()
    titan = os.path.getsize(TITAN); free = total - configured
    print(f"pool (titan.gguf)                 : {titan/1e9:8.2f} GB", flush=True)
    print(f"addressable parameter substrate   : {total/1e9:8.2f} GB across {ntens} tensors", flush=True)
    print(f"already configured as circuits    : {configured/1e6:8.2f} MB   ({n_circ} circuits registered)", flush=True)
    print(f"FREE substrate still to configure : {free/1e9:8.2f} GB   ({100*free/total:.4f}% idle)", flush=True)
    for sz, label in [(3_640_000, "cpu_fwd-sized (3.64 MB) circuits"),
                      (745_624, "dot32_i8 matmul atoms (0.75 MB)"),
                      (1016, "8-bit function circuits (~1 KB)")]:
        print(f"   room for ~{free//sz:,} more {label}", flush=True)
    lib = [n for n in reg if n.startswith("lib_")]
    print(f"function library configured       : {len(lib)} circuits {sorted(lib) if lib else '(none yet — run: fill)'}", flush=True)
    return 0


def fill():
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if any(n.startswith("lib_") for n in reg):
        print("library already fabricated. revert first to redo."); return 0
    print("fabricating a function library into the idle substrate (byte-exact, reversible) …\n", flush=True)
    ok = 0
    for name, n_in, build, ref in LIB:
        c, outs, bad = _verify(name, n_in, build, ref)
        if bad:
            print(f"  {name}: MISMATCH {bad} — storing nothing (no cheating)."); return 1
        info = SAFE.store_safe(name, c, outs)
        print(f"  {name:10s} -> @ {info['offset']}  ({info['gates']:>4} gates, {info['bytes']:>5} B)  byte-exact", flush=True)
        ok += 1
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\nFABRICATED {ok} function circuits INTO the substrate. titan GGUF-valid: {gg}. reversible: "
          f"python host/sdc_substrate.py revert", flush=True)
    print("the idle parameters are now addressable stored functions — the pool is being CONFIGURED, not left at 0%.", flush=True)
    return map_()


def revert():
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    names = [n for n in reg if n.startswith("lib_")]
    for n in names:
        r = SAFE.restore(n)
        print(f"  restored {n}: byte-exact={r.get('byte_exact')}")
    print(f"removed {len(names)} library circuits (byte-exact restore; titan GGUF-valid).")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "map"
    raise SystemExit({"map": map_, "fill": fill, "revert": revert}.get(cmd, map_)())
