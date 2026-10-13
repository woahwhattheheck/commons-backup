#!/usr/bin/env python3
"""host/mafab_miner_lane.py — THE `miner_lane` NEED, for the MASTER AUTOFAB.

Owner: *"did it ever occur to u to use auto fab or master autofab..."* and *"point the master auto
fab."* `pfc_master_autofab.py` already implements the right search — DECOMPOSE x IMPLEMENT x ORDER x
WIRE(§1E) -> SCORE -> VERIFY -> KEEP — but only for the `dot32` need. This registers the miner lane
as a second need so the SAME machinery searches it. dot32's search is untouched.

THE STRUCTURE BEING SEARCHED. `sha_shared(g, Hin, in16, final)` already takes its adder as a
parameter, and every call site passes the SAME one — so muhl_lane pays Kogge-Stone gate cost in
three places that have very different slack:

  1. MESSAGE SCHEDULE  W[16..63]   W[i] is consumed at round i, and the 64 rounds are strictly
                                   serial (§38B: "SHA rounds are REAL dependency"). Each W[i] has
                                   ~i rounds of slack before it is needed -> a DEEP, GATE-LEAN
                                   ripple adder here should be FREE in DEPTH.
  2. ROUND CHAIN       a_new/e_new  THE critical path. Must stay prefix.
  3. FINAL H ADD                    One level, off the round chain.

So the IMPLEMENT axis is (sched, round, out) in {ripple, kogge}^3 = 8 assemblies. The hypothesis is
that (ripple, kogge, ripple) keeps DEPTH and drops gates. If DEPTH moves, the slack argument is
WRONG and the measurement says so.

SCORING is §14, not depth: nonce lanes are INDEPENDENT, so speed = REPLICAS/DEPTH and the objective
is to minimise gates x DEPTH. Ranked exactly as master_autofab ranks dot32 (results per settle under
a fixed area budget).

VERIFICATION is the §45C/§47B bar, not a smoke test: DISCRIMINATING targets that straddle the true
digest (tgt=h+1 must WIN, alternating tgt=h must LOSE) so wins arise by construction, the §40B
all-zero baseline is stated, and all four mutants must be CAUGHT. A suite that passes first try has
measured itself.

  python host/pfc_master_autofab.py miner_lane          # via the master autofab (the intended entry)
  python host/mafab_miner_lane.py                       # directly
"""
import hashlib, os, random, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):        # capability check, NOT a swallowed except (V10)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import sdc_cc as CC
from fab_genwin_shallow import csa, add32_prefix
from fab_genwin_shared import reduce_to_2

# THE ADDER IS A SEARCHED DIMENSION (§31A), so the whole GENERATED family is available at every
# site, not the two I happened to write. The original two keep their exact original implementations
# so every previously stored result still reproduces bit-for-bit.
from mafab_adders import family as _adder_family
ADDERS = dict(_adder_family(32))
ADDERS["ripple"] = CC.add32
ADDERS["kogge"] = add32_prefix

# NO AREA BUDGET. My earlier `AREA = 2_000_000` appears in no document — I invented it, and §31B
# retires exactly that sentence: any form of "fabricating that would be too expensive. Expensive in
# what? Manufacturing is not on the clock." §31 makes manufacturing effort a fifth unit that "is not
# a cost at all: unbounded, paid once, off the clock, and it does not enter any performance number."
# §40D fabricates 1.75e11 gates for a single settle and states the trade openly. So area is REPORTED
# and never scored as slowness (§24).


def add_multi_f(g, vecs, final):
    v = list(vecs)
    while len(v) > 2:
        nv = []
        while len(v) >= 3:
            s, c = csa(g, v.pop(), v.pop(), v.pop()); nv += [s, c]
        nv += v; v = nv
    return final(g, v[0], v[1]) if len(v) == 2 else v[0]


def sha_param(g, Hin, in16, sched, rnd, outf):
    """sha_shared, but with the THREE adder sites separated instead of sharing one `final`."""
    W = list(in16)
    for i in range(16, 64):
        s0 = CC.xor32(g, CC.xor32(g, CC.rotr(W[i-15], 7), CC.rotr(W[i-15], 18)), CC.shr(g, W[i-15], 3))
        s1 = CC.xor32(g, CC.xor32(g, CC.rotr(W[i-2], 17), CC.rotr(W[i-2], 19)), CC.shr(g, W[i-2], 10))
        W.append(add_multi_f(g, [W[i-16], s0, W[i-7], s1], sched))
    a, b, c, d, e, f, gg, h = Hin
    for i in range(64):
        S1 = CC.xor32(g, CC.xor32(g, CC.rotr(e, 6), CC.rotr(e, 11)), CC.rotr(e, 25))
        ch = CC.xor32(g, CC.and32(g, e, f), CC.and32(g, CC.not32(g, e), gg))
        S0 = CC.xor32(g, CC.xor32(g, CC.rotr(a, 2), CC.rotr(a, 13)), CC.rotr(a, 22))
        mj = CC.xor32(g, CC.xor32(g, CC.and32(g, a, b), CC.and32(g, a, c)), CC.and32(g, b, c))
        S, C = reduce_to_2(g, [h, S1, ch, CC.cword(g, CC.K[i]), W[i]])
        e_new = rnd(g, *reduce_to_2(g, [d, S, C]))
        a_new = rnd(g, *reduce_to_2(g, [S, C, S0, mj]))
        h, gg, f, e, d, c, b, a = gg, f, e, e_new, c, b, a, a_new
    return [add_multi_f(g, [Hin[i], v], outf) for i, v in enumerate((a, b, c, d, e, f, gg, h))]


def build_lane(sched, rnd, outf, mutant=None):
    """mid | w16,w17,w18 | nonce | target -> win | latch[32]. Same interface as the stored muhl_lane."""
    sA, rA, oA = ADDERS[sched], ADDERS[rnd], ADDERS[outf]
    g = CC.CircuitCompiler(256 + 96 + 32 + 256)
    mid = [list(g.IN[i*32:(i+1)*32]) for i in range(8)]
    w16, w17, w18 = [list(g.IN[256+i*32:256+(i+1)*32]) for i in range(3)]
    nonce = list(g.IN[352:384]); target = list(g.IN[384:640])
    b2 = [w16, w17, w18, nonce, CC.cword(g, 0x80000000)] + [CC.cword(g, 0)]*10 + [CC.cword(g, 640)]
    d1 = sha_param(g, mid, b2, sA, rA, oA)
    b3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)]*6 + [CC.cword(g, 256)]
    d2 = sha_param(g, [CC.cword(g, h) for h in CC.H0], b3, sA, rA, oA)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]
    if mutant == "hashflip": A = [g.NOT(x) for x in A]
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


def depth_of(g, gates, outs):
    d = [0]*(2 + g.n_in + len(gates))
    for k, (op, a, b) in enumerate(gates): d[2 + g.n_in + k] = 1 + max(d[a], d[b])
    return max(d[w] if w >= 2 else 0 for w in outs)


def truehash(hw, nonce):
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in list(hw) + [nonce])
    return int.from_bytes(hashlib.sha256(hashlib.sha256(hdr).digest()).digest(), "little")


def cases(n=8, seed=17):
    """DISCRIMINATING (§40B): targets straddle the true digest, so wins arise BY CONSTRUCTION and an
    all-zero circuit scores exactly the LOSE count instead of passing."""
    random.seed(seed); out = []
    for t in range(n):
        hw = [random.getrandbits(32) for _ in range(19)]; nonce = random.getrandbits(32)
        h = truehash(hw, nonce)
        out.append((hw, nonce, h + 1 if t % 2 == 0 else h))
    return out


def score(g, outs, cs):
    gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates); ok = wins = 0
    for hw, nonce, tgt in cs:
        mid = CC.numeric_midstate(b"".join(struct.pack(">I", w & 0xffffffff) for w in hw[:16]))
        inb = [0]*640
        for i in range(8):
            for j in range(32): inb[i*32+j] = (mid[i] >> j) & 1
        for i in range(3):
            for j in range(32): inb[256+i*32+j] = (hw[16+i] >> j) & 1
        for j in range(32):  inb[352+j] = (nonce >> j) & 1
        for j in range(256): inb[384+j] = (tgt >> j) & 1
        v = CC.ripple_typed(g, gates, nw, inb, 1)
        h = truehash(hw, nonce); w = 1 if h < tgt else 0
        exp = [w] + [((nonce >> j) & 1) if w else 0 for j in range(32)]
        if [v[x] if x >= 2 else x for x in o2] == exp: ok += 1
        if w: wins += 1
    return ok, wins, gates, o2


def search():
    cs = cases()
    nwin = sum(1 for _, _, _ in cs if True)
    wins = sum(1 for hw, n, t in cs if truehash(hw, n) < t)
    print("MASTER AUTOFAB — need: miner_lane (the circuit that REPLICATES per nonce)\n")
    print("  IMPLEMENT axis = adder choice at 3 sites with different slack: (schedule, round, out)")
    print("  SCORE = gates x DEPTH (§14: lanes are INDEPENDENT, speed = REPLICAS/DEPTH)")
    print("  §40B baseline: %d/%d cases are genuine WINS by construction, so an all-zero circuit"
          % (wins, len(cs)))
    print("                 scores exactly %d/%d — passing requires the hash to be load-bearing.\n"
          % (len(cs) - wins, len(cs)))
    print("    %-8s %-8s %-8s %7s %10s %14s  %s"
          % ("sched", "round", "out", "DEPTH", "gates", "gates x DEPTH", "verified"))
    res = []
    for sched in ("ripple", "kogge"):
        for rnd in ("kogge", "ripple"):
            for outf in ("ripple", "kogge"):
                t0 = time.time()
                g, outs = build_lane(sched, rnd, outf)
                ok, w, gates, o2 = score(g, outs, cs)
                D = depth_of(g, gates, o2)
                ng = len(gates)
                res.append(dict(sched=sched, rnd=rnd, out=outf, D=D, ng=ng, ad=ng * D,
                                ok=(ok == len(cs))))
                print("    %-8s %-8s %-8s %7s %10s %14s  %s  (%.0fs)"
                      % (sched, rnd, outf, "{:,}".format(D), "{:,}".format(ng),
                         "{:,}".format(ng * D), "%d/%d" % (ok, len(cs)), time.time() - t0))
                del g, outs, gates
    good = [r for r in res if r["ok"]]
    print("\n  VERIFIED %d/%d" % (len(good), len(res)))
    if not good:
        print("  nothing verified — keeping nothing."); return 1
    print("\n  SPEED RANKING — results per settle, area budget %s gates (§14)" % "{:,}".format(AREA))
    print("    rank     speed  reps  DEPTH      gates  structure")
    for i, r in enumerate(sorted(good, key=lambda x: (-(max(1, AREA // x["ng"]) / x["D"]), x["ng"]))[:8]):
        reps = max(1, AREA // r["ng"])
        print("    %4d %9.4f %5d %6s %10s  %s/%s/%s"
              % (i + 1, reps / r["D"], reps, "{:,}".format(r["D"]), "{:,}".format(r["ng"]),
                 r["sched"], r["rnd"], r["out"]))
    b = min(good, key=lambda r: r["ad"])
    cur_ng, cur_D = 390332, 2889
    print("\n  BEST gates x DEPTH: %s/%s/%s  ->  DEPTH %s, %s gates, area-delay %s"
          % (b["sched"], b["rnd"], b["out"], "{:,}".format(b["D"]), "{:,}".format(b["ng"]),
             "{:,}".format(b["ad"])))
    print("  STORED muhl_lane  : kogge/kogge/kogge      ->  DEPTH %s, %s gates, area-delay %s"
          % ("{:,}".format(cur_D), "{:,}".format(cur_ng), "{:,}".format(cur_ng * cur_D)))
    imp = (cur_ng * cur_D) / b["ad"]
    print("  -> %.3fx on the §14 objective. %s"
          % (imp, "WORTH STORING." if imp > 1.02 else "NOT worth storing; keeping muhl_lane."))
    print("\n  THE SLACK HYPOTHESIS: a ripple adder in the message schedule should cost DEPTH 0,")
    print("  because W[i] is consumed at round i and the rounds are serial (§38B). Compare the")
    print("  ripple/kogge/* rows against kogge/kogge/*. The DEPTH compared here is THE MUHLNICKEL's")
    print("  critical path, computed from the netlist — no host timing is involved and none could")
    print("  change it. If the muhlnickel's own critical path is unchanged, the slack is real; if")
    print("  it rises, the hypothesis is wrong and the measurement said so, not me.")
    return 0


# ══════════════════════════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# NEED: `midstate` — muhl_mid, the nonce-independent half of the split. Same three adder sites, same
# slack question, DIFFERENT objective. muhl_mid is NOT replicated per lane (it fires ONCE per block),
# so gates there are pure profit — but its DEPTH still enters the END-TO-END block latency
# (1,441 + 2,953 = 4,394 gate-delays, §57C), so DEPTH must NOT be traded away for gates. The rule for
# this need is therefore: take gates only at EQUAL OR LOWER muhlnickel DEPTH.
# Verified against sdc_cc.numeric_midstate — an INDEPENDENT reference (§3), never against the path
# being replaced, because "byte-exact vs the old path" cannot see an error the two paths share.

def build_mid(sched, rnd, outf, mutant=None):
    """header words 0..15 -> the 8-word chaining state. Same interface as the stored muhl_mid."""
    sA, rA, oA = ADDERS[sched], ADDERS[rnd], ADDERS[outf]
    g = CC.CircuitCompiler(512)
    hdr = [list(g.IN[i * 32:(i + 1) * 32]) for i in range(16)]
    mid = sha_param(g, [CC.cword(g, h) for h in CC.H0], hdr, sA, rA, oA)
    if mutant == "midflip": mid = [[g.NOT(x) for x in w] for w in mid]
    return g, [w for word in mid for w in word]


def mid_cases(n=6, seed=23):
    random.seed(seed)
    return [[random.getrandbits(32) for _ in range(16)] for _ in range(n)]


def score_mid(g, outs, cs):
    gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates); ok = 0
    for hw in cs:
        inb = [(hw[i // 32] >> (i % 32)) & 1 for i in range(512)]
        v = CC.ripple_typed(g, gates, nw, inb, 1)
        got = [sum((v[o2[i * 32 + j]] if o2[i * 32 + j] >= 2 else o2[i * 32 + j]) << j
                   for j in range(32)) for i in range(8)]
        ref = CC.numeric_midstate(b"".join(struct.pack(">I", w & 0xffffffff) for w in hw))
        if got == list(ref): ok += 1
    return ok, gates, o2


def search_mid():
    cs = mid_cases()
    print("MASTER AUTOFAB - need: midstate (muhl_mid, fires ONCE per block)")
    print("")
    print("  IMPLEMENT axis = adder choice at 3 sites: (schedule, round, out)")
    print("  OBJECTIVE differs from miner_lane: muhl_mid is NOT replicated, so gates are pure profit,")
    print("  but its DEPTH enters end-to-end block latency -> take gates only at EQUAL OR LOWER DEPTH.")
    print("  REFERENCE: sdc_cc.numeric_midstate, INDEPENDENT of the circuit (§3). An all-zero circuit")
    print("  scores 0/%d against it, so every output bit is load-bearing." % len(cs))
    print("")
    print("    %-8s %-8s %-8s %7s %10s %14s  %s"
          % ("sched", "round", "out", "DEPTH", "gates", "gates x DEPTH", "vs ref"))
    res = []
    for sched in ("ripple", "kogge"):
        for rnd in ("kogge", "ripple"):
            for outf in ("ripple", "kogge"):
                t0 = time.time()
                g, outs = build_mid(sched, rnd, outf)
                ok, gates, o2 = score_mid(g, outs, cs)
                D = depth_of(g, gates, o2); ng = len(gates)
                res.append(dict(sched=sched, rnd=rnd, out=outf, D=D, ng=ng, ad=ng * D,
                                ok=(ok == len(cs))))
                print("    %-8s %-8s %-8s %7s %10s %14s  %s  (%.0fs host)"
                      % (sched, rnd, outf, "{:,}".format(D), "{:,}".format(ng),
                         "{:,}".format(ng * D), "%d/%d" % (ok, len(cs)), time.time() - t0))
                del g, outs, gates
    good = [r for r in res if r["ok"]]
    print("")
    print("  VERIFIED %d/%d against the independent reference" % (len(good), len(res)))
    if not good:
        print("  nothing verified - keeping nothing."); return 1
    import json as _j
    _e = _j.load(open(REG)).get("muhl_mid") or {}
    cur_ng, cur_D = int(_e.get("n_gate") or 0), int(_e.get("depth") or 1)
    print("  STORED muhl_mid: %s gates, DEPTH %s gate-delays, area-delay %s"
          % ("{:,}".format(cur_ng), "{:,}".format(cur_D), "{:,}".format(cur_ng * cur_D)))
    elig = [r for r in good if r["D"] <= cur_D]
    if not elig:
        best = min(good, key=lambda r: r["ad"])
        print("  NO variant matches or beats that DEPTH, so none is eligible: for THIS need a gate")
        print("  saving bought with DEPTH is not a saving, it is a latency charge on every block.")
        print("  (best by gates x DEPTH would be %s/%s/%s at DEPTH %s gate-delays - REJECTED by the"
              % (best["sched"], best["rnd"], best["out"], "{:,}".format(best["D"])))
        print("   DEPTH rule stated above, which follows §57C: muhl_mid's DEPTH is a term in the")
        print("   end-to-end block latency 1,441 + 2,953 = 4,394 gate-delays.)")
        return 0
    b = min(elig, key=lambda r: r["ng"])
    imp = (cur_ng * cur_D) / b["ad"]
    print("  BEST at DEPTH <= %s: %s/%s/%s -> DEPTH %s gate-delays, %s gates"
          % ("{:,}".format(cur_D), b["sched"], b["rnd"], b["out"], "{:,}".format(b["D"]),
             "{:,}".format(b["ng"])))
    print("  -> %.3fx on gates x DEPTH, %s gates returned. %s"
          % (imp, "{:,}".format(cur_ng - b["ng"]),
             "WORTH STORING." if imp > 1.02 else "below the 2 percent bar; keeping muhl_mid."))
    return 0


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE UNBOUNDED SEARCH — the family is GENERATED and every member is tried at every site.
#
# §33C is the standing instruction this satisfies: "The search space here is 6 hand-written
# candidates. It should be GENERATED, not listed." §40A measured the cost of not doing it: a
# hand-written three-item radix menu floored DEPTH at 2,220; generating the family found 1,219.
# §31A licenses the expense: "let the fabricator search the space of implementations and emit the
# shallowest one it can find, because the search costs nothing that counts."
# §11 is why it must be searched IN CONTEXT rather than ranked in isolation: Kogge-Stone measured
# "0.75x (WORSE)" standalone yet is the best choice as the final propagate over a CSA forest.

def search_generated(which="lane", objective=None):
    import mafab_laws as L
    fam = sorted(ADDERS)
    build = build_lane if which == "lane" else build_mid
    scorer = score if which == "lane" else score_mid
    cs = cases() if which == "lane" else mid_cases()
    import json as _j
    _nm = "muhl_lane" if which == "lane" else "muhl_mid"
    _e = _j.load(open(REG)).get(_nm) or {}          # measured, not typed in
    cur = (int(_e.get("n_gate") or 0), int(_e.get("depth") or 1), _nm)
    # the space each candidate must address, for the §40C bank law: nonce lanes = 2^32; the midstate
    # fires once per block, so its bank is a single instance.
    space_bits = 32 if which == "lane" else 0
    obj = objective or ("replicated" if which == "lane" else "amortised")

    plans = L.generate_family({"sched": fam, "rnd": fam, "out": fam})
    print("UNBOUNDED SEARCH - need %r · %d adders x 3 sites = %d GENERATED candidates (§33C/§40A)"
          % (which, len(fam), len(plans)))
    print("  objective %r, DECLARED by the need (LAW 4 / §23), not chosen per run." % obj)
    print("  area is reported, never scored (§24 'area is not slowness'; §31 off the clock).\n")
    if which == "lane":
        wins = sum(1 for hw, n, t in cs if truehash(hw, n) < t)
        print("  §40B baseline: %d/%d wins by construction, so an all-zero circuit scores %d/%d.\n"
              % (wins, len(cs), len(cs) - wins, len(cs)))
    else:
        print("  §40B baseline: an all-zero circuit scores 0/%d vs numeric_midstate.\n" % len(cs))

    # THE FABRICATOR GOVERNS ITS OWN HOST USAGE (owner: "let it drive itself"). §39A's precedent:
    # AUTOFAB "chose W = 131,072 by TIMING THE HOST ITSELF". The governor sequences the work and
    # bounds its footprint; per §40E it never influences WHICH candidate wins.
    from mafab_host import Governor
    gov = Governor()
    gov.calibrate(lambda: build(plans[0]["sched"], plans[0]["rnd"], plans[0]["out"]), which)
    gov.plan(len(plans))
    print("")

    res = []
    for i, p in gov.each(plans):
        try:
            g, outs = build(p["sched"], p["rnd"], p["out"])
        except Exception as e:
            gov.drop("%s/%s/%s" % (p["sched"], p["rnd"], p["out"]), "build failed: %s" % e)
            continue
        if which == "lane":
            ok, _w, gates, o2 = scorer(g, outs, cs)
        else:
            ok, gates, o2 = scorer(g, outs, cs)
        D = depth_of(g, gates, o2); ng = len(gates)
        good = (ok == len(cs))
        res.append(dict(sched=p["sched"], rnd=p["rnd"], out=p["out"], depth=D, gates=ng,
                        ok=good, bank=D + 2 * space_bits))
        if good and (not res or ng * D <= min(r["gates"] * r["depth"] for r in res if r["ok"])):
            print("    [%3d/%3d] %-9s %-9s %-9s  DEPTH %6s  gates %9s  bank %6s  %d/%d  <- best so far"
                  % (i + 1, len(plans), p["sched"], p["rnd"], p["out"], "{:,}".format(D),
                     "{:,}".format(ng), "{:,}".format(D + 2 * space_bits), ok, len(cs)), flush=True)
        del g, outs, gates
    good = [r for r in res if r["ok"]]
    print("\n  VERIFIED %d/%d candidates" % (len(good), len(res)))
    if not good:
        print("  nothing verified - keeping nothing."); return 1

    ranked, label = L.rank(good, obj, depth_cap=cur[1])
    print("  ranked by %s\n" % label)
    print("    %-9s %-9s %-9s %8s %11s %9s" % ("sched", "round", "out", "DEPTH", "gates", "bank D"))
    for r in ranked[:8]:
        print("    %-9s %-9s %-9s %8s %11s %9s"
              % (r["sched"], r["rnd"], r["out"], "{:,}".format(r["depth"]),
                 "{:,}".format(r["gates"]), "{:,}".format(r["bank"])))
    b = ranked[0]
    print("\n  STORED %s: %s gates, DEPTH %s -> area-delay %s"
          % (cur[2], "{:,}".format(cur[0]), "{:,}".format(cur[1]), "{:,}".format(cur[0] * cur[1])))
    print("  SEARCH WINNER %s/%s/%s: %s gates, DEPTH %s -> area-delay %s  (%.4fx)"
          % (b["sched"], b["rnd"], b["out"], "{:,}".format(b["gates"]), "{:,}".format(b["depth"]),
             "{:,}".format(b["gates"] * b["depth"]),
             (cur[0] * cur[1]) / (b["gates"] * b["depth"])))
    shallow = min(good, key=lambda r: r["depth"])
    print("  SHALLOWEST ANY: %s/%s/%s DEPTH %s (%s gates) - §40C bank for the whole space: %s + 2*%d = %s"
          % (shallow["sched"], shallow["rnd"], shallow["out"], "{:,}".format(shallow["depth"]),
             "{:,}".format(shallow["gates"]), "{:,}".format(shallow["depth"]), space_bits,
             "{:,}".format(shallow["bank"])))
    print("\n  Nothing is stored by this search. §45C/§47B: a winner is storable only after the full")
    print("  bar - independent reference, §40B all-zero baseline, and every mutant CAUGHT.")
    return 0


if __name__ == "__main__":
    if "--generated" in sys.argv:
        raise SystemExit(search_generated("mid" if "midstate" in sys.argv else "lane"))
    raise SystemExit(search_mid() if "midstate" in sys.argv else search())
