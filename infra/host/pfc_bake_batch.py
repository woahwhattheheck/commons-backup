#!/usr/bin/env python3
"""host/pfc_bake_batch.py — BAKE THE REMAINING BATCH at once (owner 07-19: "build them all at once then test, trust but
verify"): big-integer/modular arithmetic + a wider 32-bit ALU. Build all, verify all byte-exact vs references, bake all.

  mul16      16x16 -> 32 shift-add multiplier            (bignum multiply)
  modadd32   (a + b) mod m, 32-bit                        (modular arithmetic — RSA/DH/ECC foundation)
  alu32      32-bit ALU, op-select over add/sub/and/or/xor/not/shl/shr/lt/eq   (the wider ALU, go-wide)

  python host/pfc_bake_batch.py           # build all + verify all + bake all (reversible)
  python host/pfc_bake_batch.py revert
"""
import json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_batch_genome.jsonl"
CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}


# ---------- gate helpers ----------
def add_co(g, x, y, cin=None):
    o = []; c = g.C0 if cin is None else cin
    for i in range(len(x)):
        axb = g.XOR(x[i], y[i]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(x[i], y[i]), g.AND(axb, c))
    return o, c
def sub_bo(g, x, y):
    ny = [g.NOT(w) for w in y]; o, c = add_co(g, x, ny, g.C1); return o, g.NOT(c)   # borrow = not carry
def onehot(g, addr, N):
    out = []
    for i in range(N):
        m = g.C1
        for j in range(len(addr)): m = g.AND(m, addr[j] if (i >> j) & 1 else g.NOT(addr[j]))
        out.append(m)
    return out
def mux_oh(g, sel, vals):
    acc = g.C0
    for i in range(len(sel)): acc = g.OR(acc, g.AND(sel[i], vals[i]))
    return acc
def shl_barrel(g, a, amt):
    cur = list(a)
    for k in range(len(amt)):
        sh = 1 << k; shifted = [g.C0] * sh + cur[:32 - sh]
        cur = [g.OR(g.AND(amt[k], shifted[i]), g.AND(g.NOT(amt[k]), cur[i])) for i in range(32)]
    return cur
def shr_barrel(g, a, amt):
    cur = list(a)
    for k in range(len(amt)):
        sh = 1 << k; shifted = cur[sh:] + [g.C0] * sh
        cur = [g.OR(g.AND(amt[k], shifted[i]), g.AND(g.NOT(amt[k]), cur[i])) for i in range(32)]
    return cur


# ---------- circuits ----------
def build_mul16(g):
    a = list(g.IN[:16]); b = list(g.IN[16:32]); acc = [g.C0] * 32
    for i in range(16):
        part = [g.AND(b[i], a[j - i]) if 0 <= j - i < 16 else g.C0 for j in range(32)]
        acc, _ = add_co(g, acc, part)
    return acc
def ref_mul16(x): a = x & 0xffff; b = (x >> 16) & 0xffff; return (a * b) & 0xffffffff

def build_modadd32(g):
    a = list(g.IN[:32]); b = list(g.IN[32:64]); m = list(g.IN[64:96])
    s, cout = add_co(g, a, b); s33 = s + [cout]; m33 = m + [g.C0]
    d, borrow = sub_bo(g, s33, m33); ge = g.NOT(borrow)
    return [g.OR(g.AND(ge, d[i]), g.AND(g.NOT(ge), s[i])) for i in range(32)]
def ref_modadd32(x):
    a = x & 0xffffffff; b = (x >> 32) & 0xffffffff; m = (x >> 64) & 0xffffffff
    if m == 0: m = 1
    a %= m; b %= m; return (a + b) % m

def build_alu32(g):
    op = list(g.IN[:4]); a = list(g.IN[4:36]); b = list(g.IN[36:68])
    add_r, _ = add_co(g, a, b); sub_r, bor = sub_bo(g, a, b)
    R = [add_r, sub_r, [g.AND(a[i], b[i]) for i in range(32)], [g.OR(a[i], b[i]) for i in range(32)],
         [g.XOR(a[i], b[i]) for i in range(32)], [g.NOT(a[i]) for i in range(32)],
         shl_barrel(g, a, b[:5]), shr_barrel(g, a, b[:5]), [bor] + [g.C0] * 31, None]
    eq = g.C1
    for i in range(32): eq = g.AND(eq, g.NOT(g.XOR(a[i], b[i])))
    R[9] = [eq] + [g.C0] * 31
    while len(R) < 16: R.append(add_r)
    sel = onehot(g, op, 16)
    return [mux_oh(g, sel, [R[k][i] for k in range(16)]) for i in range(32)]
def ref_alu32(x):
    op = x & 0xf; a = (x >> 4) & 0xffffffff; b = (x >> 36) & 0xffffffff; sh = b & 31
    if op == 0: r = (a + b) & 0xffffffff
    elif op == 1: r = (a - b) & 0xffffffff
    elif op == 2: r = a & b
    elif op == 3: r = a | b
    elif op == 4: r = a ^ b
    elif op == 5: r = (~a) & 0xffffffff
    elif op == 6: r = (a << sh) & 0xffffffff
    elif op == 7: r = a >> sh
    elif op == 8: r = 1 if a < b else 0
    elif op == 9: r = 1 if a == b else 0
    else: r = (a + b) & 0xffffffff
    return r

def gen_mul16(r): x = r.getrandbits(32); return x, ref_mul16(x)
def gen_alu32(r): x = r.getrandbits(68); return x, ref_alu32(x)
def gen_modadd32(r):                                              # mod-add contract: inputs are residues a,b < m
    m = r.randrange(1, 1 << 32); a = r.randrange(m); b = r.randrange(m)
    return a | (b << 32) | (m << 64), (a + b) % m
CIRCUITS = [
    ("mul16", 32, 32, build_mul16, gen_mul16, "16x16->32 multiplier (bignum)"),
    ("modadd32", 96, 32, build_modadd32, gen_modadd32, "(a+b) mod m, 32-bit (modular arithmetic)"),
    ("alu32", 68, 32, build_alu32, gen_alu32, "32-bit ALU: add/sub/and/or/xor/not/shl/shr/lt/eq"),
]


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG))
    for n, *_ in CIRCUITS: reg.pop(n, None)
    json.dump(reg, open(REG, "w"), indent=1); print("reverted — titan byte-exact; batch removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    # BUILD ALL
    built = []
    print("building the batch (all at once) …", flush=True)
    for name, n_in, n_out, builder, gen, desc in CIRCUITS:
        g = CC.CircuitCompiler(n_in); outs = builder(g); gates, out2 = g.dce(outs)
        built.append((name, n_in, n_out, g, gates, out2, gen, desc))
        print(f"  {name:<10} {len(gates):>6,} gates  ({desc})", flush=True)
    # VERIFY ALL
    print("\nverifying all byte-exact vs references (300 random each) …", flush=True)
    allok = True
    for name, n_in, n_out, g, gates, out2, gen, desc in built:
        n_wire = 2 + n_in + len(gates); ok = True; rng = random.Random(hash(name) & 0xffff)
        for _ in range(300):
            x, expect = gen(rng)
            v = CC.ripple_typed(g, gates, n_wire, [(x >> i) & 1 for i in range(n_in)], 1)
            got = sum((v[out2[j]] if out2[j] >= 2 else out2[j]) << j for j in range(n_out))
            if got != expect: ok = False; break
        print(f"  {name:<10} byte-exact: {ok}", flush=True); allok = allok and ok
    if not allok:
        print("\n  a circuit MISMATCHED — baking NOTHING (no cheating)."); return 1
    # BAKE ALL
    print("\nall byte-exact — baking all permanent …", flush=True)
    reg = json.load(open(REG))
    for name, n_in, n_out, g, gates, out2, ref, desc in built:
        if name in reg: print(f"  {name} already baked, skipping."); continue
        n_wire = 2 + n_in + len(gates)
        body = b"".join(struct.pack("<Bii", CODE[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in out2)
        blob = b"PFCTYPED" + struct.pack("<IIII", n_in, n_wire, len(gates), len(out2)) + body
        off, tn = TC._alloc(len(blob), reg); backup_and_write(off, blob)
        reg = json.load(open(REG))
        reg[name] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": n_in, "n_wire": n_wire,
                     "n_gate": len(gates), "n_out": n_out, "format": "typed", "role": desc}
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"  BAKED {name} @ {off} ({len(gates):,} gates).", flush=True)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\n  titan GGUF-valid: {gg}. bignum + modular + wider ALU baked permanent. revert: python host/pfc_bake_batch.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
