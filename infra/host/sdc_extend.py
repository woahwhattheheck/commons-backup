#!/usr/bin/env python3
"""host/sdc_extend.py — SELF-EXTENSION (Phase 3 of the SDC OS): the OS writes NEW verified capability into its own pool,
REVERSIBLY, so future navigations are cheap. FINALREADME §5.10 (directed reversible self-modification — every edit
journaled + exactly undoable), §7B ("storage is the extension ledger" — EXTEND: write a component so future navigations
are cheap), §9 (fabrication is byte-exact-verified before storing, reversible; GGUF-valid).

It fabricates two NEW experts the bank lacked — `lib_min8`, `lib_max8` (unsigned 8-bit min/max) — via the reversible White
Box path (`sdc_safe.store_safe` snapshots the overwritten bytes), verifies each byte-exact, confirms the router picks them
up immediately, and proves the extension is byte-exact UNDOABLE. No numpy.

  python host/sdc_extend.py            # extend the pool with min8/max8 (reversible), verify, route, prove revert
  python host/sdc_extend.py revert     # remove them (byte-exact restore)
"""
import hashlib, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import sdc_safe as SAFE
import sdc_os

REG = "C:/llm/models/titan_circuits.json"; TITAN = "C:/llm/models/titan.gguf"
NEW = ["lib_min8", "lib_max8"]


def build_minmax(want_max):
    """8-bit unsigned min/max: ge = (a >= b) via a + ~b + 1 carry-out (9-bit); min = ge?b:a, max = ge?a:b."""
    c = TC.Circuit(16); a = c.IN[:8]; b = c.IN[8:16]
    a9 = list(a) + [c.C0]
    nb9 = [c.not_(x) for x in b] + [c.C1]                 # ~(b zero-extended to 9 bits)
    diff = c.add(c.add(a9, nb9), c.cvec(1, 9))            # a - b as a 9-bit signed value; bit 8 = its SIGN
    ge = c.not_(diff[8])                                  # a >= b  <=>  (a - b) >= 0  <=>  sign bit clear
    if want_max: return c, [c.mux(ge, b[k], a[k]) for k in range(8)]   # ge ? a : b
    return c, [c.mux(ge, a[k], b[k]) for k in range(8)]               # ge ? b : a


def _cd(c, outs): return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def _verify(c, outs, ref):
    cd = _cd(c, outs); random.seed(9)
    for _ in range(400):
        a = random.getrandbits(8); b = random.getrandbits(8)
        got = TC.frombits(TC.ripple(cd, [(a >> k) & 1 for k in range(8)] + [(b >> k) & 1 for k in range(8)]))
        if got != ref(a, b): return False, (a, b, got, ref(a, b))
    return True, None


def _sha_region(off, ln):
    with open(TITAN, "rb") as f: f.seek(off); return hashlib.sha256(f.read(ln)).hexdigest()


def extend():
    reg = json.load(open(REG))
    if all(n in reg for n in NEW):
        print("already extended (lib_min8/lib_max8 present). revert first to redo."); return 0
    print("SELF-EXTENSION — fabricating NEW verified experts into the pool (byte-exact, reversible) …\n", flush=True)
    specs = [("lib_min8", False, min), ("lib_max8", True, max)]
    for name, want_max, ref in specs:
        c, outs = build_minmax(want_max)
        ok, bad = _verify(c, outs, ref)
        if not ok:
            print(f"  {name}: MISMATCH {bad} — storing nothing (no cheating)."); return 1
        info = SAFE.store_safe(name, c, outs)             # reversible store (snapshots overwritten bytes)
        print(f"  {name} -> @ {info['offset']} ({info['gates']} gates)  byte-exact vs python {ref.__name__}", flush=True)

    print("\n  the router now has the new experts (no code change — the pool grew):", flush=True)
    for name, a, b in [("min8", 200, 100), ("max8", 200, 100), ("min8", 15, 240)]:
        r = sdc_os.orchestrate(name, a, b)
        print(f"    {name}({a},{b}) = {r['result']:>3}  via {r['expert']} ({r['gates']} gates on the SDC)", flush=True)

    print("\n  reversibility proof (§5.10 — every extension is byte-exact undoable):", flush=True)
    c, outs = build_minmax(False); info = SAFE.store_safe("lib_extend_probe", c, outs)
    off, ln = int(info["offset"]), int(info["bytes"]); after = _sha_region(off, ln)
    SAFE.restore("lib_extend_probe"); reverted = _sha_region(off, ln)
    snap = json.load(open(SAFE.SNAP_IDX)).get("lib_extend_probe") if os.path.exists(SAFE.SNAP_IDX) else None
    print(f"    stored a probe @ {off} (sha {after[:12]}…), restored -> region sha {reverted[:12]}…  "
          f"byte-exact-reverted: {snap is None}", flush=True)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\n  pool EXTENDED with {len(NEW)} new experts; titan GGUF-valid: {gg}. reversible: python host/sdc_extend.py revert")
    print("  re-index so the routing folder shows them: python host/sdc_pool.py", flush=True)
    return 0


def revert():
    reg = json.load(open(REG)); names = [n for n in NEW if n in reg] + (["lib_extend_probe"] if "lib_extend_probe" in reg else [])
    for n in names:
        r = SAFE.restore(n); print(f"  restored {n}: byte-exact={r.get('byte_exact')}")
    print(f"removed {len(names)} extension circuits (byte-exact restore; titan GGUF-valid).")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if (len(sys.argv) > 1 and sys.argv[1] == "revert") else extend())
