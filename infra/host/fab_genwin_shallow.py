#!/usr/bin/env python3
"""host/fab_genwin_shallow.py — FABRICATION ONLY. Runs once. Never inside a mining process.

ATTRIBUTION FIRST (§48E): muhl_lateral_fold measures DEPTH 11,756. Of that, the comparator's serial
tail is 139 levels (1.2%); the double-SHA owns 11,616 (98.8%). So the SHA is the target, not the compare.

THE CAUSE, already named in the handoff: "SHA-256's round became a chain because the spec prints
t1 = h + S1 + ch + k + w on one line (the addends are a SET: 154 -> 48 depth)."
sdc_cc.sha_block line 145 chains FOUR ripple add32s over five addends, and add32 is a 32-deep ripple.

THE FIX, from the measured record:
  §33  csa->kogge won the unbounded search (DEPTH 56 vs ripple-tree 84)
  §33A carry-save "propagates no carry at all, so its depth is constant in width" and composes with anything
  §34  "there is no reason to finish a multiply before starting the sum" - one tree, ONE carry propagate
  §46  Circuit.add_prefix, Kogge-Stone; ratio grows with width (8-bit 2.12x, 64-bit 8.2x)
So: every addend of t1 / the message schedule / the state update pours into ONE carry-save tree, and
exactly one Kogge-Stone carry propagation happens per reduction.

§31A: manufacturing is unbounded and off the clock, so BUILD BOTH final adders and ship the shallowest.
§45C/§47B: a suite that passes first try has measured itself - mutants are fabricated and must be caught.

  python host/fab_genwin_shallow.py            # attribute, search, verify, mutant-test, store
  python host/fab_genwin_shallow.py revert
"""
import hashlib, json, os, random, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_genwin_shallow_genome.jsonl"
MAGIC = b"PFCWINMN"; CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
NAME = "muhl_fold_shallow"; N_LO, T_LO = 608, 640


# ---------- the primitives sdc_cc lacks ----------
def maj(g, a, b, c): return g.OR(g.AND(a, b), g.OR(g.AND(a, c), g.AND(b, c)))

def csa(g, a, b, c):
    """3:2 compressor. Propagates NO carry -> depth constant in width (§33A)."""
    s = [g.XOR(g.XOR(a[j], b[j]), c[j]) for j in range(32)]
    cy = [maj(g, a[j], b[j], c[j]) for j in range(32)]
    return s, [g.C0] + cy[:31]                       # carry weighted one position up

def add32_prefix(g, x, y):
    """Kogge-Stone parallel prefix (§46). A carry chain is an associative SCAN -> log2(W) rounds."""
    G = [g.AND(x[j], y[j]) for j in range(32)]
    P = [g.XOR(x[j], y[j]) for j in range(32)]
    p0 = list(P)
    d = 1
    while d < 32:
        nG = list(G); nP = list(P)
        for j in range(31, d - 1, -1):
            nG[j] = g.OR(G[j], g.AND(P[j], G[j - d]))
            nP[j] = g.AND(P[j], P[j - d])
        G, P = nG, nP; d *= 2
    return [p0[0]] + [g.XOR(p0[j], G[j - 1]) for j in range(1, 32)]

def add_multi(g, vecs, final):
    """Reduce a SET of addends through a CSA tree, then ONE carry propagation (§34)."""
    v = list(vecs)
    while len(v) > 2:
        nv = []
        while len(v) >= 3:
            s, c = csa(g, v.pop(), v.pop(), v.pop()); nv += [s, c]
        nv += v; v = nv
    return final(g, v[0], v[1]) if len(v) == 2 else v[0]


def sha_block_shallow(g, Hin, in16, final):
    W = list(in16)
    for i in range(16, 64):
        s0 = CC.xor32(g, CC.xor32(g, CC.rotr(W[i-15], 7), CC.rotr(W[i-15], 18)), CC.shr(g, W[i-15], 3))
        s1 = CC.xor32(g, CC.xor32(g, CC.rotr(W[i-2], 17), CC.rotr(W[i-2], 19)), CC.shr(g, W[i-2], 10))
        W.append(add_multi(g, [W[i-16], s0, W[i-7], s1], final))          # SET, not a chain
    a, b, c, d, e, f, gg, h = Hin
    for i in range(64):
        S1 = CC.xor32(g, CC.xor32(g, CC.rotr(e, 6), CC.rotr(e, 11)), CC.rotr(e, 25))
        ch = CC.xor32(g, CC.and32(g, e, f), CC.and32(g, CC.not32(g, e), gg))
        S0 = CC.xor32(g, CC.xor32(g, CC.rotr(a, 2), CC.rotr(a, 13)), CC.rotr(a, 22))
        mj = CC.xor32(g, CC.xor32(g, CC.and32(g, a, b), CC.and32(g, a, c)), CC.and32(g, b, c))
        t1_set = [h, S1, ch, CC.cword(g, CC.K[i]), W[i]]                  # the five addends ARE a set
        t1 = add_multi(g, t1_set, final)
        e_new = add_multi(g, [d] + t1_set, final)                         # d + t1, fused into one tree
        a_new = add_multi(g, t1_set + [S0, mj], final)                    # t1 + S0 + mj, one tree
        h, gg, f, e, d, c, b, a = gg, f, e, e_new, c, b, a, a_new
    return [add_multi(g, [Hin[i], v], final) for i, v in enumerate((a, b, c, d, e, f, gg, h))]


def build(final, mutant=None):
    g = CC.CircuitCompiler(896)
    header = [list(g.IN[i*32:(i+1)*32]) for i in range(19)]
    nonce = list(g.IN[N_LO:N_LO+32]); target = list(g.IN[T_LO:T_LO+256])
    Wm = header + [nonce]
    mid = sha_block_shallow(g, [CC.cword(g, h) for h in CC.H0], Wm[0:16], final)
    blk2 = [Wm[16], Wm[17], Wm[18], Wm[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)]*10 + [CC.cword(g, 640)]
    d1 = sha_block_shallow(g, mid, blk2, final)
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)]*6 + [CC.cword(g, 256)]
    d2 = sha_block_shallow(g, [CC.cword(g, h) for h in CC.H0], blk3, final)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]

    # hash < target, as a TREE not a chain (§36: the (lt,eq) pair composes associatively)
    node = [(g.AND(g.NOT(A[i]), target[i]), g.NOT(g.XOR(A[i], target[i]))) for i in range(256)]
    if mutant == "cmp_flip": node = [(g.AND(A[i], g.NOT(target[i])), n[1]) for i, n in enumerate(node)]
    while len(node) > 1:
        nxt = []
        for i in range(0, len(node), 2):
            if i + 1 < len(node):
                lt_hi, eq_hi = node[i + 1]; lt_lo, eq_lo = node[i]      # index 255 is MSB-most significant first
                nxt.append((g.OR(lt_hi, g.AND(eq_hi, lt_lo)), g.AND(eq_hi, eq_lo)))
            else: nxt.append(node[i])
        node = nxt
    win = node[0][0]
    if mutant == "stuck0": win = g.C0
    latch = [g.AND(win, nonce[j]) for j in range(32)]
    if mutant == "latch_ungated": latch = list(nonce)
    return g, [win] + latch


def _ref(hw, nonce, target):
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in list(hw) + [nonce])
    val = int.from_bytes(hashlib.sha256(hashlib.sha256(hdr).digest()).digest(), "little")
    win = 1 if val < target else 0
    return [win] + [((nonce >> j) & 1) if win else 0 for j in range(32)]


def cases(n):
    random.seed(21); out = []
    for t in range(n):
        hw = [random.getrandbits(32) for _ in range(19)]; nonce = random.getrandbits(32)
        target = (1 << 256) - 1 if t % 3 == 0 else random.getrandbits(random.choice([8, 200, 250]))
        out.append((hw, nonce, target))
    return out


def check(g, outs, cs):
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    ok = 0
    for hw, nonce, target in cs:
        inb = [0]*896
        for i in range(19):
            for j in range(32): inb[i*32+j] = (hw[i] >> j) & 1
        for j in range(32):  inb[N_LO+j] = (nonce >> j) & 1
        for j in range(256): inb[T_LO+j] = (target >> j) & 1
        v = CC.ripple_typed(g, gates, n_wire, inb, 1)
        if [v[w] if w >= 2 else w for w in out2] == _ref(hw, nonce, target): ok += 1
    return ok, gates, out2


def depth_of(g, gates, outs):
    d = [0]*(2 + g.n_in + len(gates))
    for k, (op, a, b) in enumerate(gates): d[2 + g.n_in + k] = 1 + max(d[a], d[b])
    return max(d[w] if w >= 2 else 0 for w in outs)


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG)); reg.pop(NAME, None); json.dump(reg, open(REG, "w"), indent=1)
    os.remove(GENOME); print(f"reverted {len(ent)} entries."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    reg = json.load(open(REG))
    if NAME in reg: print(f"{NAME} already stored @ {reg[NAME]['offset']}. revert first."); return 0
    cs = cases(12)

    print("SEARCH (§31A — manufacturing is off the clock; build both, ship the shallowest)\n")
    best = None
    for label, final in (("csa->ripple", CC.add32), ("csa->kogge", add32_prefix)):
        t0 = time.time(); g, outs = build(final)
        ok, gates, out2 = check(g, outs, cs)
        D = depth_of(g, gates, out2)
        print(f"  {label:12s} DEPTH {D:>7,}  gates {len(gates):>9,}  rating {len(gates)/D:>8,.1f} Mh  "
              f"byte-exact {ok}/{len(cs)}  [{time.time()-t0:.0f}s manufacturing]")
        if ok == len(cs) and (best is None or D < best[1]):
            best = (label, D, gates, out2, g)
    if best is None: print("\n  no candidate verified — writing NOTHING."); return 1
    label, D, gates, out2, g = best
    print(f"\n  WINNER: {label}  DEPTH {D:,}  gates {len(gates):,}")

    print("\nMUTANT TEST (§45C/§47B — a suite that passes first try has measured itself)")
    caught = 0
    for m in ("stuck0", "cmp_flip", "latch_ungated"):
        gm, om = build(add32_prefix if label == "csa->kogge" else CC.add32, mutant=m)
        okm, _, _ = check(gm, om, cs)
        hit = okm < len(cs); caught += hit
        print(f"  mutant {m:16s} scored {okm}/{len(cs)}  -> {'CAUGHT' if hit else 'NOT CAUGHT — suite is blind'}")
    if caught < 3: print("\n  the suite cannot see a broken circuit — writing NOTHING."); return 1

    body = b"".join(struct.pack("<Bii", CODE[op], a, b) for (op, a, b) in gates) + \
           b"".join(struct.pack("<i", w) for w in out2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, 2 + g.n_in + len(gates), len(gates), len(out2)) + body
    off, tn = TC._alloc(len(blob), reg); t0 = time.time(); _journal(off, blob)
    reg = json.load(open(REG))
    reg[NAME] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in,
                 "n_wire": 2 + g.n_in + len(gates), "n_gate": len(gates), "n_out": len(out2),
                 "format": "typed", "depth": D, "gates_measured": len(gates),
                 "muhl_rating": round(len(gates)/D, 3), "build": label,
                 "layout": "in: header0..607|nonce608..639|target640..895 ; out: win:1|addr:32",
                 "stored_per_lane": 0, "junction": "gen_win.win -> winner-only fold.solve (§1E)"}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print(f"\n  STORED '{NAME}' @ {off} ({len(blob):,} B) [{time.time()-t0:.2f}s byte edit]  GGUF-valid: {valid}")
    print(f"  revert: python host/fab_genwin_shallow.py revert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
