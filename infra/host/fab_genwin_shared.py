#!/usr/bin/env python3
"""host/fab_genwin_shared.py — FABRICATION ONLY. Runs once. Never inside a mining process.

WHY THIS CANDIDATE. §14: nonce lanes are INDEPENDENT, so the objective is REPLICAS/DEPTH, i.e.
minimise **gates x DEPTH** (area-delay) -- NOT depth. fab_genwin_shallow optimised DEPTH alone and
reduced the SAME addend set three times per round (t1, e_new, a_new). §34A: "all partial products pour
into a SINGLE carry-save tree, and exactly ONE carry propagation happens." So the t1 addend set is
CSA-reduced ONCE to two vectors and those two survivors are reused by all three sums.

  muhl_fold_shallow   DEPTH 4,157   687,223 gates   gates*DEPTH 2.857e9
  this candidate      DEPTH 4,322   590,617 gates   gates*DEPTH 2.553e9   -> 1.12x better area-delay
Note it is DEEPER. Under §23 ("the selector must match the phase") that is correct for mining
(independent lanes) and wrong for a dependent chain. Both are kept; pfc_atom picks by criterion.

★ THE SUITE. A hashflip mutant (invert all 256 hash bits) scored 12/12 NOT CAUGHT against the old
target distribution, because all-ones and tiny targets give hash and ~hash the SAME verdict -- §40B's
87.5% bug. This suite uses DISCRIMINATING targets that straddle the true hashlib digest:
    tgt = h+1  -> must WIN      tgt = h  -> must LOSE
Half win/half lose BY CONSTRUCTION, every hash bit is load-bearing, and an inverted-hash circuit
cannot pass. Mutants must all be caught before a byte is written (§45C).

  python host/fab_genwin_shared.py            # search, verify, mutant-test, store
  python host/fab_genwin_shared.py --dry      # everything except the byte edit
  python host/fab_genwin_shared.py revert
"""
import hashlib, json, os, random, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC
from fab_genwin_shallow import csa, add32_prefix, add_multi

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_genwin_shared_genome.jsonl"
MAGIC = b"PFCWINMN"; CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
NAME = "muhl_fold_shared"; N_LO, T_LO = 608, 640


def reduce_to_2(g, vecs):
    """CSA-reduce a SET to two vectors. No carry propagates (§33A: depth constant in width)."""
    v = list(vecs)
    while len(v) > 2:
        nv = []
        while len(v) >= 3:
            s, c = csa(g, v.pop(), v.pop(), v.pop()); nv += [s, c]
        nv += v; v = nv
    return v


def sha_shared(g, Hin, in16, final):
    W = list(in16)
    for i in range(16, 64):
        s0 = CC.xor32(g, CC.xor32(g, CC.rotr(W[i-15], 7), CC.rotr(W[i-15], 18)), CC.shr(g, W[i-15], 3))
        s1 = CC.xor32(g, CC.xor32(g, CC.rotr(W[i-2], 17), CC.rotr(W[i-2], 19)), CC.shr(g, W[i-2], 10))
        W.append(add_multi(g, [W[i-16], s0, W[i-7], s1], final))
    a, b, c, d, e, f, gg, h = Hin
    for i in range(64):
        S1 = CC.xor32(g, CC.xor32(g, CC.rotr(e, 6), CC.rotr(e, 11)), CC.rotr(e, 25))
        ch = CC.xor32(g, CC.and32(g, e, f), CC.and32(g, CC.not32(g, e), gg))
        S0 = CC.xor32(g, CC.xor32(g, CC.rotr(a, 2), CC.rotr(a, 13)), CC.rotr(a, 22))
        mj = CC.xor32(g, CC.xor32(g, CC.and32(g, a, b), CC.and32(g, a, c)), CC.and32(g, b, c))
        S, C = reduce_to_2(g, [h, S1, ch, CC.cword(g, CC.K[i]), W[i]])   # ONE shared reduction
        e_new = final(g, *reduce_to_2(g, [d, S, C]))
        a_new = final(g, *reduce_to_2(g, [S, C, S0, mj]))
        h, gg, f, e, d, c, b, a = gg, f, e, e_new, c, b, a, a_new
    return [add_multi(g, [Hin[i], v], final) for i, v in enumerate((a, b, c, d, e, f, gg, h))]


def build(mutant=None):
    g = CC.CircuitCompiler(896)
    hdr = [list(g.IN[i*32:(i+1)*32]) for i in range(19)]
    nonce = list(g.IN[N_LO:N_LO+32]); target = list(g.IN[T_LO:T_LO+256])
    Wm = hdr + [nonce]
    mid = sha_shared(g, [CC.cword(g, h) for h in CC.H0], Wm[0:16], add32_prefix)
    b2 = [Wm[16], Wm[17], Wm[18], Wm[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)]*10 + [CC.cword(g, 640)]
    d1 = sha_shared(g, mid, b2, add32_prefix)
    b3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)]*6 + [CC.cword(g, 256)]
    d2 = sha_shared(g, [CC.cword(g, h) for h in CC.H0], b3, add32_prefix)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]
    if mutant == "hashflip": A = [g.NOT(x) for x in A]          # the mutant the old suite could not see
    node = [(g.AND(g.NOT(A[i]), target[i]), g.NOT(g.XOR(A[i], target[i]))) for i in range(256)]
    if mutant == "cmpflip": node = [(g.AND(A[i], g.NOT(target[i])), n[1]) for i, n in enumerate(node)]
    while len(node) > 1:
        nxt = []
        for i in range(0, len(node), 2):
            if i + 1 < len(node):
                lh, eh = node[i+1]; ll, el = node[i]
                nxt.append((g.OR(lh, g.AND(eh, ll)), g.AND(eh, el)))
            else: nxt.append(node[i])
        node = nxt
    win = node[0][0]
    if mutant == "stuck0": win = g.C0
    latch = [g.AND(win, nonce[j]) for j in range(32)]
    if mutant == "ungated": latch = list(nonce)
    return g, [win] + latch


def truehash(hw, nonce):
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in list(hw) + [nonce])
    return int.from_bytes(hashlib.sha256(hashlib.sha256(hdr).digest()).digest(), "little")


def cases(n=12, seed=11):
    """DISCRIMINATING: targets straddle the TRUE digest so every hash bit is load-bearing."""
    random.seed(seed); out = []
    for t in range(n):
        hw = [random.getrandbits(32) for _ in range(19)]; nonce = random.getrandbits(32)
        h = truehash(hw, nonce)
        out.append((hw, nonce, h + 1 if t % 2 == 0 else h))     # h<h+1 WIN ; h<h LOSE
    return out


def score(g, outs, cs):
    gates, out2 = g.dce(outs); nw = 2 + g.n_in + len(gates); ok = wins = 0
    for hw, nonce, tgt in cs:
        inb = [0]*896
        for i in range(19):
            for j in range(32): inb[i*32+j] = (hw[i] >> j) & 1
        for j in range(32):  inb[N_LO+j] = (nonce >> j) & 1
        for j in range(256): inb[T_LO+j] = (tgt >> j) & 1
        v = CC.ripple_typed(g, gates, nw, inb, 1)
        h = truehash(hw, nonce); w = 1 if h < tgt else 0
        exp = [w] + [((nonce >> j) & 1) if w else 0 for j in range(32)]
        if [v[x] if x >= 2 else x for x in out2] == exp: ok += 1
        if w: wins += 1
    return ok, wins, len(cs), gates, out2


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
    cs = cases()
    t0 = time.time(); g, outs = build()
    ok, wins, N, gates, out2 = score(g, outs, cs)
    D = depth_of(g, gates, out2)
    print(f"  candidate: {len(gates):,} gates, DEPTH {D:,}, gates*DEPTH {len(gates)*D:,}  [{time.time()-t0:.0f}s manufacturing]")
    print(f"  DISCRIMINATING suite: {wins}/{N} wins BY CONSTRUCTION -> an all-zero circuit scores {N-wins}/{N} (§40B)")
    print(f"  byte-exact vs independent hashlib reference: {ok}/{N}")
    if ok != N: print("  MISMATCH — writing NOTHING."); return 1

    print("  mutant test (§45C) — every one must be CAUGHT:")
    caught = 0
    for m in ("stuck0", "ungated", "cmpflip", "hashflip"):
        gm, om = build(m); okm, _, _, _, _ = score(gm, om, cs)
        hit = okm < N; caught += hit
        print(f"    {m:10s} {okm}/{N} -> {'CAUGHT' if hit else 'NOT CAUGHT — SUITE IS BLIND'}")
    if caught < 4: print("  the suite cannot see a broken circuit — writing NOTHING."); return 1
    if "--dry" in sys.argv: print("\n  --dry: verified and mutant-tested, nothing written."); return 0

    body = b"".join(struct.pack("<Bii", CODE[op], a, b) for (op, a, b) in gates) + \
           b"".join(struct.pack("<i", w) for w in out2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, 2 + g.n_in + len(gates), len(gates), len(out2)) + body
    off, tn = TC._alloc(len(blob), reg); t1 = time.time(); _journal(off, blob)
    reg = json.load(open(REG))
    reg[NAME] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in,
                 "n_wire": 2 + g.n_in + len(gates), "n_gate": len(gates), "n_out": len(out2),
                 "format": "typed", "depth": D, "gates_measured": len(gates),
                 "muhl_rating": round(len(gates)/D, 3), "area_delay": len(gates)*D,
                 "junction": "gen_win.win -> winner-only fold.solve (§1E)",
                 "layout": "in: header0..607|nonce608..639|target640..895 ; out: win:1|addr:32",
                 "stored_per_lane": 0, "build": "csa shared-reduction -> kogge"}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print(f"\n  STORED '{NAME}' @ {off} ({len(blob):,} B) [{time.time()-t1:.2f}s byte edit]  GGUF-valid: {valid}")
    print(f"  revert: python host/fab_genwin_shared.py revert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
