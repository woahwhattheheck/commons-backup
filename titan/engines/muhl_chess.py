#!/usr/bin/env python3
"""muhl_chess.py -- CHESS MOVE-LEGALITY / ATTACK-BITBOARD GENERATOR fabricated on Bryce's Muhlnickel substrate.

Every attack generator is built as NAND/AND/OR/XOR/NOT gates with the White Box compiler
(sdc_cc.CircuitCompiler), DCE'd, rippled, and VERIFIED BYTE-EXACT against an independent pure-Python
reference -- no numpy, no host executor as a runtime, titan.gguf never opened. Fabrication-time synthesis:
prove the logic byte-exact BEFORE it would ever be baked, then the substrate could run it by address.

Board convention: square index s = rank*8 + file, rank 0 = white's home rank, rank 7 = black's home rank.
A "bitboard" is a 64-bit value; bit s (== output/reference wire index s, LSB-first) is set iff square s is
attacked.  All packing LSB-first, matching sdc_cc's `run(inp, 1)` and `rd()`.

Circuits (each verified byte-exact):
  knight   square(6)                 -> attack bitboard(64)   [leaper, exhaustive over all 64 squares]
  king     square(6)                 -> attack bitboard(64)   [leaper, exhaustive]
  rook     square(6) + occupancy(64) -> attack bitboard(64)   [slider, blockers -> ray stops]
  bishop   square(6) + occupancy(64) -> attack bitboard(64)   [slider]
  queen    square(6) + occupancy(64) -> attack bitboard(64)   [rook rays OR bishop rays]
  select   piece(3) + square(6) + occupancy(64) -> bitboard   [one circuit, piece-selectable mux]
  BONUS king-in-check detector: white_king(6) + black {N,K,B,R,Q,P} bitboards + occupancy -> 1 bit,
        covers knight/king/pawn/bishop-or-queen(diag)/rook-or-queen(orth) attacks, byte-exact.
"""
import sys, os, random, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---------- shared White Box helpers (same discipline as muhl_flex.py) ----------
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return run, out2, gates, n_wire

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))   # LSB-first
def setf(inp, base, W, x):
    for b in range(W): inp[base + b] = (x >> b) & 1

RESULTS = []
def record(name, gates, depth, ok, cases, note=""):
    RESULTS.append((name, len(gates), depth, ok, cases, note))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name:8s} {len(gates):>7,} gates  depth {depth:>4}  byte-exact over {cases:>6} cases  {note}", flush=True)

# ======================= chess reference (independent, pure Python) =======================
KNIGHT_D = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
KING_D   = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
ROOK_D   = [(1, 0), (-1, 0), (0, 1), (0, -1)]
BISHOP_D = [(1, 1), (1, -1), (-1, 1), (-1, -1)]

def on(r, f): return 0 <= r < 8 and 0 <= f < 8
def leaper_ref(s, D):
    r, f = divmod(s, 8); bb = 0
    for dr, df in D:
        nr, nf = r + dr, f + df
        if on(nr, nf): bb |= 1 << (nr * 8 + nf)
    return bb
def knight_ref(s): return leaper_ref(s, KNIGHT_D)
def king_ref(s):   return leaper_ref(s, KING_D)
def slider_ref(s, occ, D):
    r, f = divmod(s, 8); bb = 0
    for dr, df in D:
        nr, nf = r + dr, f + df
        while on(nr, nf):
            t = nr * 8 + nf; bb |= 1 << t
            if (occ >> t) & 1: break            # first blocker is included (capturable), ray stops
            nr += dr; nf += df
    return bb
def rook_ref(s, occ):   return slider_ref(s, occ, ROOK_D)
def bishop_ref(s, occ): return slider_ref(s, occ, BISHOP_D)
def queen_ref(s, occ):  return rook_ref(s, occ) | bishop_ref(s, occ)
# squares FROM WHICH a black pawn attacks white square s (black pawns move toward rank 0):
def pawn_attackers_ref(s):
    r, f = divmod(s, 8); bb = 0
    for df in (-1, 1):
        nr, nf = r + 1, f + df
        if on(nr, nf): bb |= 1 << (nr * 8 + nf)
    return bb

# ======================= gate builders =======================
def decode6(g, b6):                                   # 6-bit index -> 64 one-hot select wires
    sel = []
    for s in range(64):
        m = g.C1
        for j in range(6):
            m = g.AND(m, b6[j] if (s >> j) & 1 else g.NOT(b6[j]))
        sel.append(m)
    return sel

def leaper_circuit(g, sel, ref_fn):                   # out[t] = OR over source s (t in attacks(s)) of sel[s]
    outs = []
    for t in range(64):
        acc = g.C0
        for s in range(64):
            if (ref_fn(s) >> t) & 1: acc = g.OR(acc, sel[s])
        outs.append(acc)
    return outs

def slider_source(g, s, occ, D):                      # per-source attack wires as a function of occupancy
    att = [g.C0] * 64
    r, f = divmod(s, 8)
    for dr, df in D:
        blocked = g.C0; nr, nf = r + dr, f + df
        while on(nr, nf):
            t = nr * 8 + nf
            att[t] = g.NOT(blocked)                    # attacked iff ray not blocked before reaching t
            blocked = g.OR(blocked, occ[t])            # occupied square stops the ray beyond it
            nr += dr; nf += df
    return att

def slider_circuit(g, sel, occ, D):                   # out[t] = OR over s of (sel[s] AND att_s[t])
    outs = [g.C0] * 64
    for s in range(64):
        att = slider_source(g, s, occ, D)
        for t in range(64):
            outs[t] = g.OR(outs[t], g.AND(sel[s], att[t]))
    return outs

# ======================= per-piece fabrication + verification =======================
def fab_leaper(name, ref_fn):
    g = CC.CircuitCompiler(6)
    sel = decode6(g, [g.IN[i] for i in range(6)])
    outs = leaper_circuit(g, sel, ref_fn)
    run, out2, gates, _ = build_run(g, outs)
    ok = True
    for s in range(64):                                # EXHAUSTIVE over all 64 squares
        inp = [0] * 6; setf(inp, 0, 6, s)
        if rd(run(inp, 1), out2) != ref_fn(s): ok = False; break
    record(name, gates, depth_of(g, gates, out2), ok, 64, "square->bitboard (exhaustive)")

def fab_slider(name, ref_fn, D, cases=64 * 40):
    g = CC.CircuitCompiler(6 + 64)
    b6 = [g.IN[i] for i in range(6)]; occ = [g.IN[6 + i] for i in range(64)]
    sel = decode6(g, b6)
    outs = slider_circuit(g, sel, occ, D)
    run, out2, gates, _ = build_run(g, outs)
    ok = True; n = 0
    for s in range(64):                                # every square x random occupancies (incl. self-square set)
        for _ in range(cases // 64):
            occv = random.getrandbits(64)
            inp = [0] * (6 + 64); setf(inp, 0, 6, s); setf(inp, 6, 64, occv)
            if rd(run(inp, 1), out2) != ref_fn(s, occv): ok = False; break
            n += 1
        if not ok: break
    record(name, gates, depth_of(g, gates, out2), ok, n, "square+occupancy->bitboard")

def fab_queen(cases=64 * 40):
    g = CC.CircuitCompiler(6 + 64)
    b6 = [g.IN[i] for i in range(6)]; occ = [g.IN[6 + i] for i in range(64)]
    sel = decode6(g, b6)
    rook = slider_circuit(g, sel, occ, ROOK_D)
    bish = slider_circuit(g, sel, occ, BISHOP_D)
    outs = [g.OR(rook[t], bish[t]) for t in range(64)]  # queen = rook rays OR bishop rays
    run, out2, gates, _ = build_run(g, outs)
    ok = True; n = 0
    for s in range(64):
        for _ in range(cases // 64):
            occv = random.getrandbits(64)
            inp = [0] * (6 + 64); setf(inp, 0, 6, s); setf(inp, 6, 64, occv)
            if rd(run(inp, 1), out2) != queen_ref(s, occv): ok = False; break
            n += 1
        if not ok: break
    record("queen", gates, depth_of(g, gates, out2), ok, n, "square+occupancy->bitboard")

# ======================= piece-selectable single circuit =======================
# piece codes: 0 knight, 1 king, 2 rook, 3 bishop, 4 queen
def fab_select(cases=4000):
    g = CC.CircuitCompiler(3 + 6 + 64)
    p3 = [g.IN[i] for i in range(3)]
    b6 = [g.IN[3 + i] for i in range(6)]
    occ = [g.IN[9 + i] for i in range(64)]
    sel = decode6(g, b6)
    kn = leaper_circuit(g, sel, knight_ref)
    kg = leaper_circuit(g, sel, king_ref)
    rk = slider_circuit(g, sel, occ, ROOK_D)
    bs = slider_circuit(g, sel, occ, BISHOP_D)
    qn = [g.OR(rk[t], bs[t]) for t in range(64)]
    pieces = [kn, kg, rk, bs, qn]
    psel = []
    for p in range(5):                                  # decode the 3-bit piece code
        m = g.C1
        for j in range(3): m = g.AND(m, p3[j] if (p >> j) & 1 else g.NOT(p3[j]))
        psel.append(m)
    outs = []
    for t in range(64):
        acc = g.C0
        for p in range(5): acc = g.OR(acc, g.AND(psel[p], pieces[p][t]))
        outs.append(acc)
    run, out2, gates, _ = build_run(g, outs)
    reffns = [lambda s, o: knight_ref(s), lambda s, o: king_ref(s), rook_ref, bishop_ref, queen_ref]
    ok = True
    for _ in range(cases):
        p = random.randrange(5); s = random.randrange(64); occv = random.getrandbits(64)
        inp = [0] * (3 + 6 + 64); setf(inp, 0, 3, p); setf(inp, 3, 6, s); setf(inp, 9, 64, occv)
        if rd(run(inp, 1), out2) != reffns[p](s, occv): ok = False; break
    record("select", gates, depth_of(g, gates, out2), ok, cases, "piece+square+occ->bitboard (mux)")

# ======================= BONUS: king-in-check detector =======================
# inputs: white king sq(6) + black bitboards N,K,B,R,Q,P (64 each) + full occupancy(64)
def in_check_ref(ksq, bn, bk, bbi, br, bq, bp, occ):
    if knight_ref(ksq) & bn: return 1
    if king_ref(ksq) & bk: return 1
    if bishop_ref(ksq, occ) & (bbi | bq): return 1
    if rook_ref(ksq, occ) & (br | bq): return 1
    if pawn_attackers_ref(ksq) & bp: return 1
    return 0

def fab_incheck(cases=3000):
    NB = 64
    g = CC.CircuitCompiler(6 + 7 * NB)
    ksq = [g.IN[i] for i in range(6)]
    off = 6
    def band(k): return [g.IN[off + k * NB + i] for i in range(NB)]
    bn, bk, bbi, br, bq, bp = band(0), band(1), band(2), band(3), band(4), band(5)
    occ = band(6)
    sel = decode6(g, ksq)
    kn_att   = leaper_circuit(g, sel, knight_ref)
    kg_att   = leaper_circuit(g, sel, king_ref)
    pawn_att = leaper_circuit(g, sel, pawn_attackers_ref)
    rk_att   = slider_circuit(g, sel, occ, ROOK_D)
    bs_att   = slider_circuit(g, sel, occ, BISHOP_D)
    def any_and(A, B):
        acc = g.C0
        for t in range(64): acc = g.OR(acc, g.AND(A[t], B[t]))
        return acc
    diag = [g.OR(bbi[t], bq[t]) for t in range(64)]     # bishops or queens
    orth = [g.OR(br[t], bq[t]) for t in range(64)]      # rooks or queens
    chk = g.OR(any_and(kn_att, bn),
          g.OR(any_and(kg_att, bk),
          g.OR(any_and(pawn_att, bp),
          g.OR(any_and(bs_att, diag),
               any_and(rk_att, orth)))))
    run, out2, gates, _ = build_run(g, [chk])
    ok = True; n_chk = 0
    for _ in range(cases):
        ks = random.randrange(64)
        def rndbb(n):                                    # sparse random piece set, never on the king square
            bb = 0
            for _ in range(n):
                q = random.randrange(64)
                if q != ks: bb |= 1 << q
            return bb
        bn_, bk_, bbi_, br_, bq_, bp_ = (rndbb(2), rndbb(1), rndbb(2), rndbb(2), rndbb(1), rndbb(4))
        occv = bn_ | bk_ | bbi_ | br_ | bq_ | bp_        # realistic: rays block on the real pieces
        inp = [0] * (6 + 7 * NB); setf(inp, 0, 6, ks)
        for k, bbv in enumerate((bn_, bk_, bbi_, br_, bq_, bp_, occv)):
            setf(inp, 6 + k * NB, NB, bbv)
        exp = in_check_ref(ks, bn_, bk_, bbi_, br_, bq_, bp_, occv)
        n_chk += exp
        if (rd(run(inp, 1), out2) & 1) != exp: ok = False; break
    record("in_check", gates, depth_of(g, gates, out2), ok, cases, f"white king attacked? ({n_chk} were in check)")

# ======================= demo: print a couple of attack boards =======================
def show_board(bb, mark, tag):
    print(f"    {tag}:")
    for r in range(7, -1, -1):
        row = "      "
        for f in range(8):
            s = r * 8 + f
            row += (mark if (bb >> s) & 1 else ".") + " "
        print(row, flush=True)

def demo():
    print("\n  --- sample attack boards (o = attacked, N/K/etc = piece) ---", flush=True)
    ks = 6 * 8 + 3            # d7-ish
    nb = knight_ref(ks); nb |= 1 << ks
    show_board(nb, "o", f"knight on square {ks} (rank {ks//8}, file {ks%8})")
    rs = 3 * 8 + 3           # d4
    occ = (1 << (3 * 8 + 6)) | (1 << (5 * 8 + 3)) | (1 << (3 * 8 + 1))  # a few blockers
    rb = rook_ref(rs, occ)
    show_board(rb | occ | (1 << rs), "o", f"rook on {rs} with blockers (ray stops at first blocker)")

def main():
    random.seed(1789)
    print("\n  MUHLNICKEL CHESS FABRICATOR -- attack generators as gates, each byte-exact vs an independent reference\n", flush=True)
    for fn, args in ((fab_leaper, ("knight", knight_ref)),
                     (fab_leaper, ("king", king_ref)),
                     (fab_slider, ("rook", rook_ref, ROOK_D)),
                     (fab_slider, ("bishop", bishop_ref, BISHOP_D)),
                     (fab_queen, ()),
                     (fab_select, ()),
                     (fab_incheck, ())):
        t = time.time()
        try:
            fn(*args); print(f"        ({time.time()-t:.1f}s)", flush=True)
        except Exception as ex:
            import traceback; traceback.print_exc()
            print(f"  [ERR ] {fn.__name__}: {type(ex).__name__}: {ex}", flush=True)
    npass = sum(1 for r in RESULTS if r[3]); tot = sum(r[1] for r in RESULTS)
    print(f"\n  === {npass}/{len(RESULTS)} chess circuits byte-exact  |  {tot:,} total gates fabricated ===", flush=True)
    demo()

if __name__ == "__main__":
    main()
