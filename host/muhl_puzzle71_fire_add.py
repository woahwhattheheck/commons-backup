#!/usr/bin/env python3
"""host/muhl_puzzle71_fire_add.py — the puzzle-71 routing button (additive). Inject, fire, die. Surface separate.

Offsets come ONLY from C:/llm/models/muhl_puzzle71.circuits.json (written by muhl_puzzle71_organs_add.py).
Fail closed if any name or offset is missing. Never guess a dest.

  --go       : for every ring, cell 0 of fwd and of rev: new = old | 0x01 (both senses; foundry_acre pattern).
               The fire is a WRITE that raises a bit, never a read. Then the button dies.
  --surface  : bounded read of tick, win, latch (70 B), every ring's fwd/rev/carry/pub and clock bank. Bits, not hex.
               The host does not solve and does not check: the assembled candidate is printed; the wallet judges.
  (no args)  : print the plan from the registry. Write nothing.
"""
from __future__ import annotations
import json, os, sys

PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
REG = PFC_ROOT + "/models/muhl_puzzle71.circuits.json"
NAME = "muhl_puzzle71"
N_BITS = 70

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def bits(b):
    return " ".join(format(x, "08b") for x in b)


def load():
    if not os.path.isfile(REG):
        return None, "registry missing: %s (fabricate first: host/muhl_puzzle71_organs_add.py --fab)" % REG
    reg = json.load(open(REG, encoding="utf-8"))
    e = reg.get(NAME)
    if not isinstance(e, dict):
        return None, "%s not in registry" % NAME
    cont = e.get("container")
    if not cont or not os.path.isfile(cont):
        return None, "container missing: %s" % cont
    ram = e.get("ram") or {}
    for k in ("cand_off", "tick_off", "latch_off", "win_off"):
        if not isinstance(ram.get(k), int):
            return None, "registry ram.%s missing" % k
    rings = e.get("rings")
    if not isinstance(rings, list) or not rings:
        return None, "registry rings missing"
    size = os.path.getsize(cont)
    for r in rings:
        for k in ("fwd", "rev", "carry", "pub"):
            if not isinstance(r.get(k), int) or r[k] >= size:
                return None, "ring %s offset missing or past EOF" % k
    return {"e": e, "cont": cont, "ram": ram, "rings": rings, "size": size}, None


def _read(cont, off, n):
    with open(cont, "rb", buffering=0) as f:
        f.seek(off)
        return f.read(n)


def print_plan(p):
    e, ram = p["e"], p["ram"]
    print("\nMUHL PUZZLE-71 FIRE (routing button)")
    print("  container : %s (%s B)" % (p["cont"], f"{p['size']:,}"))
    print("  gates     : %s decision + %s organs = %s" % (f"{e.get('n_gate_decision', 0):,}", f"{e.get('n_gate_organs', 0):,}", f"{e.get('n_gate', 0):,}"))
    print("  rings     : %d x %d cells, both senses, %d clocks each ; pubs OR-treed -> tick@%d" % (e.get("n_rings", 0), e.get("cells", 0), e.get("n_clocks_per_ring", 0), ram["tick_off"]))
    d = e.get("declaration") or {}
    print("  fold      : addr_bits %s base %s bytes/lane %s winner_only %s" % (d.get("addr_bits"), d.get("base"), d.get("bytes_per_lane"), d.get("winner_only")))
    print("  FIRE      : new=old|0x01 at cell 0 fwd+rev of every ring, then die")
    print("  SURFACE   : tick@%d win@%d latch@%d (%d B) + ring state + clock bank" % (ram["tick_off"], ram["win_off"], ram["latch_off"], N_BITS))
    print()


def go(p):
    print_plan(p)
    cont = p["cont"]
    lit = 0
    with open(cont, "r+b") as f:
        for r in p["rings"]:
            for sense in ("fwd", "rev"):
                off = r[sense]
                f.seek(off); old = f.read(1)[0]
                new = old | 0x01
                f.seek(off); f.write(bytes([new]))
                lit += 1
        f.flush(); os.fsync(f.fileno())
    print("  FIRED: %d cell-0 bytes ORed with 00000001 across %d rings, both senses. Button dies." % (lit, len(p["rings"])))
    print("  surface is a separate act: python host/muhl_puzzle71_fire_add.py --surface\n")
    return 0


def surface(p):
    print_plan(p)
    cont, ram = p["cont"], p["ram"]
    tick = _read(cont, ram["tick_off"], 1)
    win = _read(cont, ram["win_off"], 1)
    latch = _read(cont, ram["latch_off"], N_BITS)
    cand = _read(cont, ram["cand_off"], N_BITS)
    print("SURFACE — bounded read. Host does not solve; it reads.\n")
    print("  tick  @%-12d %s" % (ram["tick_off"], bits(tick)))
    print("  win   @%-12d %s" % (ram["win_off"], bits(win)))
    print("  cand  @%-12d ones=%d" % (ram["cand_off"], sum(b & 1 for b in cand)))
    print("  latch @%-12d ones=%d" % (ram["latch_off"], sum(b & 1 for b in latch)))
    for i in range(0, N_BITS, 10):
        print("        bits %2d..%2d  %s" % (i, min(i + 9, N_BITS - 1), bits(latch[i:i + 10])))
    c = sum((latch[j] & 1) << j for j in range(N_BITS))
    print("  assembled candidate (LSB-first) = 0x%x ; key = 2^70 + candidate = 0x%x" % (c, (1 << 70) + c))
    print("  (the wallet / address judges; this button computes nothing)\n")
    for i, r in enumerate(p["rings"]):
        fwd = _read(cont, r["fwd"], r.get("cells", 32)); rev = _read(cont, r["rev"], r.get("cells", 32))
        carry = _read(cont, r["carry"], 1); pub = _read(cont, r["pub"], 1)
        clk = _read(cont, r["clocks"][0], len(r["clocks"])) if r.get("clocks") else b""
        print("  ring %2d  fwd ones %2d  rev ones %2d  carry %s  pub %s  clocks ones %d/%d" % (
            i, sum(b & 1 for b in fwd), sum(b & 1 for b in rev), bits(carry), bits(pub), sum(b & 1 for b in clk), len(clk)))
    print()
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    p, err = load()
    if err:
        return _fail(err)
    if "--go" in a and "--surface" in a:
        return _fail("pass --go or --surface, not both (surface is a separate act)")
    if "--go" in a:
        return go(p)
    if "--surface" in a:
        return surface(p)
    print_plan(p)
    print("  (no fire performed; pass --go)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
