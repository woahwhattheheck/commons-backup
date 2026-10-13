#!/usr/bin/env python3
"""host/pfc_mac_prefix_fab.py — store S37A's REBUILT MAC into titan.gguf.

THE DEFECT (PFC_FINDINGS S37A / S37D / S39, S53E class): S37A rebuilt pfc_mac from two serial folds
(DEPTH 372 / 93,664 gates) to ONE fused carry-save tree (DEPTH 210 / 181,728 gates) and the doc quotes
210 from S37D onward -- but the netlist STORED IN titan.gguf is still the BEFORE. The improvement
lives only in source. This instrument fabricates the AFTER into the parameter bytes.

ADDITIVE: the existing 372-DEPTH `pfc_mac` is NOT touched. The rebuild is stored under `pfc_mac_prefix`.

  python host/pfc_mac_prefix_fab.py measure   # build both, count gates, longest-path DEPTH (no write)
  python host/pfc_mac_prefix_fab.py verify    # independent integer reference + all-zero baseline + MUTANTS
  python host/pfc_mac_prefix_fab.py plan      # four-style occupancy sweep + inertness probe + magic scan
  python host/pfc_mac_prefix_fab.py fab       # journal -> write -> fsync -> re-read from disk -> register
  python host/pfc_mac_prefix_fab.py revert    # replay the genome in reverse, drop the registry entry
"""
import json, os, struct, sys, random, mmap

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import titan_circuit as TC
import pfc_mac_fab as MACFAB                      # S37A's rebuilt builder lives here (build_eval)

TITAN  = TC.TITAN
REG    = TC.REG
IDX    = TC.IDX
GENOME = "C:/llm/models/titan_pfcmac_genome.jsonl"
NAME   = "pfc_mac_prefix"
BLK    = 32

MAGICS = [b"TITANCIR", b"MUHLOSCP", b"NRING2M1", b"MUHLOSCA", b"PFCMEMO1", b"PFCLOOKT", b"TITANBUS",
          b"TITANSDC", b"MUHLPHYS", b"PFCNLST1", b"PFCTYPED", b"TITANBSL", b"TITANMTY", b"PFCEXEC1",
          b"PFCWINMN", b"TITANHDR", b"PFCMMU01", b"PFCSMACH", b"PFCSMCLK", b"PFCNMAP1", b"TITANGEN",
          b"PFCLOAD1", b"MUHLBNK1", b"MUHLJNC1", b"WOF0"]

# ===================================================================================================
# BUILDERS
# ===================================================================================================

def build_new():
    """S37A AFTER: every partial product of every lane PLUS the incoming accumulator into ONE
    carry-save tree; exactly one carry propagates. Delegated to pfc_mac_fab.build_eval so this
    instrument cannot drift from the source the doc describes."""
    return MACFAB.build_eval()


def build_old(mut=None):
    """S37A BEFORE, reconstructed. Verified BYTE-IDENTICAL to the netlist stored at the registry's
    `pfc_mac` offset in titan.gguf (see `measure`): 7 partial products folded serially inside each
    multiply (16-bit), the sign row negated, then the BLK products folded serially across lanes at
    32-bit, the accumulator added last. Positive control only -- never stored."""
    c = TC.Circuit(32 + BLK * 8 + BLK * 8); C0 = c.C0
    ACC = c.IN[:32]
    Wb = c.IN[32:32 + BLK * 8]; Xb = c.IN[32 + BLK * 8:32 + 2 * BLK * 8]
    W = [Wb[i * 8:i * 8 + 8] for i in range(BLK)]
    X = [Xb[i * 8:i * 8 + 8] for i in range(BLK)]
    def sext(b, w): return list(b) + [b[-1]] * (w - len(b))
    def shl(b, k, w): return ([C0] * k + list(b) + [C0] * w)[:w]
    PW = 16
    tot = [C0] * 32
    for i in range(BLK):
        a = sext(W[i], PW); bx = X[i]
        p = [C0] * PW
        for k in range(7):
            p = c.add(p, [c.and_(tt, bx[k]) for tt in shl(a, k, PW)])[:PW]
        inv = [c.not_(z) for z in [c.and_(tt, bx[7]) for tt in shl(a, 7, PW)]]
        neg = c.add(inv, c.cvec(1, PW))[:PW]
        p = c.add(p, neg)[:PW]
        tot = c.add(tot, sext(p, 32))[:32]
    out = c.add(ACC, tot)[:32]
    return c, out


def build_mutant(kind):
    """Deliberately broken variants of the NEW circuit. The suite MUST catch every one of these."""
    c = TC.Circuit(32 + BLK * 8 + BLK * 8); C0 = c.C0
    ACC = c.IN[:32]
    Wb = c.IN[32:32 + BLK * 8]; Xb = c.IN[32 + BLK * 8:32 + 2 * BLK * 8]
    W = [Wb[i * 8:i * 8 + 8] for i in range(BLK)]
    X = [Xb[i * 8:i * 8 + 8] for i in range(BLK)]
    def sext(b, w): return list(b) + [b[-1]] * (w - len(b))
    def shl(b, k, w): r = [C0] * k + list(b); return (r + [C0] * w)[:w]
    W32 = 32
    def csa(a, b, d):
        s = [c.xor(c.xor(a[i], b[i]), d[i]) for i in range(W32)]
        cr = [c.or_(c.or_(c.and_(a[i], b[i]), c.and_(a[i], d[i])), c.and_(b[i], d[i])) for i in range(W32)]
        return s, [C0] + cr[:W32 - 1]
    vecs = [list(ACC)]
    for i in range(BLK):
        a32 = sext(W[i], W32); b = X[i]
        rng = range(7) if not (kind == "truncate_high_pp" and i == 0) else range(6)   # MUTANT B
        for k in rng:
            vecs.append([c.and_(tt, b[k]) for tt in shl(a32, k, W32)])
        t7 = [c.and_(tt, b[7]) for tt in shl(a32, 7, W32)]
        vecs.append([c.not_(x) for x in t7])
    vecs.append(list(c.cvec(BLK, W32)))
    while len(vecs) > 2:
        nxt, i = [], 0
        while i + 2 < len(vecs):
            s, cr = csa(vecs[i], vecs[i + 1], vecs[i + 2]); nxt += [s, cr]; i += 3
        nxt += vecs[i:]; vecs = nxt
    if kind == "drop_carry_half":                                                    # MUTANT A
        accp = _add_broken_carry(c, vecs[0], vecs[1], cut=16)[:W32]
    else:
        accp = c.add(vecs[0], vecs[1])[:W32]
    return c, accp


def _add_broken_carry(c, xs, ys, cut):
    """ripple-carry adder with the carry INTO bit `cut` forced to 0 -- the two halves stop talking."""
    out = []; carry = c.C0
    for i in range(len(xs)):
        if i == cut: carry = c.C0
        axb = c.xor(xs[i], ys[i]); out.append(c.xor(axb, carry))
        carry = c.or_(c.and_(xs[i], ys[i]), c.and_(axb, carry))
    return out


def cd_of(c, outs): return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def depth_of(cd):
    """longest path over the netlist, in TICKS (one tick = one NAND settle). Graph property --
    independent of emission order and of any host."""
    n = cd["n_in"]; ga = cd["ga"]; gb = cd["gb"]
    d = [0] * (2 + n + len(ga))
    base = 2 + n
    for k in range(len(ga)):
        a = d[ga[k]]; b = d[gb[k]]
        d[base + k] = 1 + (a if a > b else b)
    return max(d[x] for x in cd["outs"])


# ===================================================================================================
# INDEPENDENT REFERENCE + MUTANT SUITE
# ===================================================================================================

def _i8bits(vals): return [(v >> k) & 1 for v in vals for k in range(8)]
def _s32(u): return u - (1 << 32) if u >= (1 << 31) else u


def ref_mac(acc, w, x):
    """the INDEPENDENT reference: plain Python integer multiply-accumulate. No gate path, no circuit,
    no reuse of anything being replaced."""
    return _s32((acc + sum(w[i] * x[i] for i in range(BLK))) & 0xFFFFFFFF)


def test_vectors():
    """balanced random + edge cases: zero, all-ones, max/min operands, sign boundaries, acc overflow."""
    V = []
    z = [0] * BLK
    V.append((0, z, z))                                                    # zero
    V.append((0, [-128] * BLK, [-128] * BLK))                              # -128 x -128 (the S37A case)
    V.append((0, [127] * BLK, [127] * BLK))                                # +max x +max
    V.append((0, [-128] * BLK, [127] * BLK))                               # sign boundary
    V.append((0, [127] * BLK, [-128] * BLK))
    V.append((0, [-1] * BLK, [-1] * BLK))                                  # all-ones (two's complement)
    V.append((-1, [-1] * BLK, [-1] * BLK))
    V.append(((1 << 31) - 1, [127] * BLK, [127] * BLK))                    # accumulator overflow, +side
    V.append((-(1 << 31), [-128] * BLK, [127] * BLK))                      # accumulator overflow, -side
    V.append((0, [1] + z[1:], [1] + z[1:]))                                # single lane
    V.append((0, z[:-1] + [-128], z[:-1] + [-128]))                        # last lane only
    V.append((12345678, [k - 128 for k in range(BLK)], [127 - k for k in range(BLK)]))
    V.append((-12345678, [0, -128, 127, -1, 1] + [0] * (BLK - 5), [-128, 0, -1, 127, 1] + [0] * (BLK - 5)))
    rnd = random.Random(20260801)
    for _ in range(120):                                                   # balanced random
        V.append((rnd.randint(-(1 << 31), (1 << 31) - 1),
                  [rnd.randint(-128, 127) for _ in range(BLK)],
                  [rnd.randint(-128, 127) for _ in range(BLK)]))
    for _ in range(60):                                                    # random over extremes only
        V.append((rnd.choice([0, -1, 1, (1 << 31) - 1, -(1 << 31)]),
                  [rnd.choice([-128, -1, 0, 1, 127]) for _ in range(BLK)],
                  [rnd.choice([-128, -1, 0, 1, 127]) for _ in range(BLK)]))
    return V


def score(cd, V):
    """fraction of the test set on which the netlist byte-matches the independent integer reference."""
    hit = 0
    for (acc, w, x) in V:
        ib = [(acc >> k) & 1 for k in range(32)] + _i8bits([v & 0xff for v in w]) + _i8bits([v & 0xff for v in x])
        if _s32(TC.frombits(TC.ripple(cd, ib))) == ref_mac(acc, w, x): hit += 1
    return hit


def zero_baseline(V):
    """what a DEGENERATE all-zero circuit would score. If a 'pass' is near this, the pass is fake."""
    return sum(1 for (acc, w, x) in V if ref_mac(acc, w, x) == 0)


# ===================================================================================================
# ALLOCATION — four span styles + inertness probe + magic scan (spec 8; TC._alloc is blind to (c))
# ===================================================================================================

OFFISH = ("offset", "off", "addr", "start", "at", "base")
GUARD = 4096                     # conservative band around bare point-addresses in the registry


def _int(v):
    if isinstance(v, bool): return None
    if isinstance(v, int): return v
    return None


def _points(obj, out):
    """recursive conservative sweep: every plausible ADDRESS anywhere in the registry entry."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            n = _int(v)
            if n is not None and n > (1 << 20) and any(str(k).lower().endswith(s) or str(k).lower() == s for s in OFFISH):
                out.append(n)
            else:
                _points(v, out)
    elif isinstance(obj, list):
        for v in obj: _points(v, out)


def occupancy(reg):
    """(a) offset+len  (b) gates_offset+gates_len  (c) gate_table_off + n_gate*gate_stride
       (d) segments[]  (e) conservative point sweep with a guard band."""
    iv = []
    for name, e in reg.items():
        if not isinstance(e, dict): continue
        o = _int(e.get("offset")); L = _int(e.get("len"))
        if o is not None and L is not None: iv.append((o, o + L, name, "a"))
        go = _int(e.get("gates_offset")); gl = _int(e.get("gates_len"))
        if go is not None and gl is not None: iv.append((go, go + gl, name, "b"))
        gt = _int(e.get("gate_table_off"))
        if gt is not None:
            ng = _int(e.get("n_gate")) or _int(e.get("gates")) or _int(e.get("gates_measured")) or 0
            st = _int(e.get("gate_stride")) or _int(e.get("gate_bytes")) or _int(e.get("record_bytes")) or 9
            iv.append((gt, gt + max(ng * st, GUARD), name, "c"))
        segs = e.get("segments")
        if isinstance(segs, list):
            for s in segs:
                if isinstance(s, dict):
                    so = _int(s.get("offset")) or _int(s.get("off")) or _int(s.get("start"))
                    sl = _int(s.get("len")) or _int(s.get("bytes")) or _int(s.get("length"))
                    if so is not None: iv.append((so, so + (sl or GUARD), name, "d"))
                elif isinstance(s, (list, tuple)) and len(s) >= 2 and _int(s[0]) is not None:
                    iv.append((int(s[0]), int(s[0]) + int(s[1]), name, "d"))
        pts = []; _points(e, pts)
        for p in pts: iv.append((p - GUARD, p + GUARD, name, "e"))
    return iv


def _merge(iv):
    s = sorted((a, b) for a, b, _, _ in iv); out = []
    for a, b in s:
        if out and a <= out[-1][1]: out[-1][1] = max(out[-1][1], b)
        else: out.append([a, b])
    return out


CHUNK = 65536


def _struct_hi(b):
    """LIVENESS DISCRIMINATOR. Every stored netlist body here is a stream of 4-byte <i wire ids whose
    values are < n_wire (< 2^24 for anything in this file), so byte 3 of every record is ZERO. Q4/Q8
    weight bytes are near-uniform, so that byte is zero ~1/256 of the time. Returns the MAX over 64 KiB
    chunks of the fraction of position-3-mod-4 bytes that are zero. A live netlist reads ~1.0 here even
    if its magic sits outside the window; weight data reads ~0.004."""
    worst = 0.0; worst_at = -1
    for s in range(0, len(b), CHUNK):
        ch = b[s:s + CHUNK]
        if len(ch) < 4096: break
        hi = ch[3::4]
        f = hi.count(0) / len(hi)
        if f > worst: worst, worst_at = f, s
    return worst, worst_at


def probe(off, n):
    """read exactly the declared span (bounded read, spec 11) and report inertness + magic + structure."""
    with open(TITAN, "rb") as f:
        f.seek(off); b = f.read(n)
    zeros = b.count(0)
    inert_zero = (zeros == len(b))
    inert_wof = (len(set(b[i:i + 4] for i in range(0, len(b) - 3, 4))) == 1 and b[:4] == b"WOF0")
    hits = []
    for m in MAGICS:
        i = b.find(m)
        if i >= 0: hits.append((m.decode("latin1"), off + i))
    sh, sat = _struct_hi(b)
    return {"zeros": zeros, "len": len(b), "inert_zero": inert_zero, "inert_wof": inert_wof,
            "magics": hits, "struct_hi": sh, "struct_at": (off + sat) if sat >= 0 else None,
            "longest_zero_run": _lzr(b)}


def _lzr(b):
    import re
    return max((len(m.group(0)) for m in re.finditer(b"\x00+", b)), default=0)


def allocate(need, reg, verbose=True):
    a = json.load(open(IDX, encoding="utf-8"))
    tensors = sorted(a["tensors"], key=lambda t: -int(t["bytes"]))
    reserved = tensors[0]["name"] if tensors else None            # the miner's region — never touched
    occ = _merge(occupancy(reg))
    if verbose:
        print(f"  occupancy sweep: {len(occ):,} merged intervals from {len(reg):,} registry entries "
              f"(styles a/b/c/d + conservative point band {GUARD})")
    pad = 4096
    cands = []
    for t in tensors:
        if t["name"] == reserved: continue
        ts = int(t["offset"]); te = ts + int(t["bytes"])
        cursor = ts
        for o0, o1 in occ:
            if o1 <= cursor or o0 >= te: continue
            if o0 - cursor >= need + 2 * pad: cands.append((cursor + pad, t["name"]))
            cursor = max(cursor, o1)
        if te - cursor >= need + 2 * pad: cands.append((cursor + pad, t["name"]))
    if verbose:
        print(f"  {len(cands):,} candidate windows clear of ALL four span styles + the point band")
    scanned = []
    for cand, tn in cands:
        pr = probe(cand, need + 8)
        scanned.append((cand, tn, pr))
        if (pr["inert_zero"] or pr["inert_wof"]) and not pr["magics"] and pr["struct_hi"] <= 0.25:
            pr["clearance"] = "sentinel-inert (all-zero or WOF0 fill), no magic, no netlist structure"
            return cand, tn, pr
    if verbose:
        bz = max(p["zeros"] for _, _, p in scanned); br = max(p["longest_zero_run"] for _, _, p in scanned)
        print(f"  SENTINEL-INERTNESS PROBE, all {len(scanned):,} windows: 0 are all-zero or WOF0-filled.")
        print(f"    best window holds {bz:,} zero bytes of {need + 8:,}; longest zero RUN found: {br} bytes.")
        print(f"    MEASUREMENT: no span in this file is sentinel fill; unclaimed spans are Q4 weight bytes.")
        print(f"  Both remaining liveness tests must still pass, and BOTH are kept, not relaxed:")
        print(f"    (i)  no known circuit magic anywhere in the window")
        print(f"    (ii) struct_hi = max over 64 KiB chunks of P(byte at 4k+3 == 0) must stay under 0.25.")
        print(f"         A stored netlist body reads ~1.000 here (every wire id < 2^24, so byte 3 is 0),")
        print(f"         so (ii) detects a live netlist overlapping the window even with its magic outside it.")
    for cand, tn, pr in scanned:
        if pr["magics"]:
            if verbose: print(f"    reject {cand}: magic {pr['magics'][:2]}")
            continue
        if pr["struct_hi"] > 0.25:
            if verbose: print(f"    reject {cand}: struct_hi {pr['struct_hi']:.3f} at {pr['struct_at']}")
            continue
        pr["clearance"] = ("clear of all four registry span styles + point band; no known magic in window; "
                           "struct_hi %.4f (netlist reads ~1.0)" % pr["struct_hi"])
        return cand, tn, pr
    raise RuntimeError("no unclaimed, magic-free, structure-free span found")


# ===================================================================================================
# GENOME — every write journaled and reversible (spec 9; pattern from muhl_fab_fold_latch.py)
# ===================================================================================================

def _journal(off, n):
    with open(TITAN, "rb") as f:
        f.seek(off); orig = f.read(n)
    with open(GENOME, "a") as g:
        g.write(json.dumps({"off": int(off), "orig": orig.hex()}) + "\n")
        g.flush(); os.fsync(g.fileno())
    return orig


def _write(off, blob):
    _journal(off, len(blob))
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob); f.flush(); os.fsync(f.fileno())


def revert():
    n = 0
    if os.path.exists(GENOME):
        recs = [json.loads(l) for l in open(GENOME) if l.strip()]
        for e in reversed(recs):
            with open(TITAN, "r+b") as f:
                f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"])); f.flush(); os.fsync(f.fileno())
            n += 1
        os.remove(GENOME)
    if os.path.exists(REG):
        reg = json.load(open(REG)); gone = reg.pop(NAME, None)
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"registry: dropped {NAME}: {bool(gone)}  (pfc_mac untouched: {'pfc_mac' in reg})")
    with open(TITAN, "rb") as f: ok = f.read(4) == b"GGUF"
    print(f"reverted {n} journaled span(s); GGUF-valid: {ok}")
    return 0


# ===================================================================================================
# COMMANDS
# ===================================================================================================

def measure():
    print("=" * 96)
    print("MEASURE — built in-process, gates counted, DEPTH = longest path over the netlist (ticks)")
    cn, on = build_new(); dn = cd_of(cn, on)
    co, oo = build_old(); do = cd_of(co, oo)
    gn, dpn = len(cn.ga), depth_of(dn)
    go, dpo = len(co.ga), depth_of(do)
    print(f"  S37A AFTER  (fused CSA tree, pfc_mac_fab.build_eval): gates {gn:,}  DEPTH {dpn}"
          f"  muhl {gn/dpn:.1f}   doc says 181,728 / 210 -> "
          f"{'MATCH' if (gn, dpn) == (181728, 210) else 'DIVERGENCE'}")
    print(f"  S37A BEFORE (two serial folds, reconstructed)       : gates {go:,}  DEPTH {dpo}"
          f"  muhl {go/dpo:.1f}   doc says  93,664 / 372 -> "
          f"{'MATCH' if (go, dpo) == (93664, 372) else 'DIVERGENCE'}")
    reg = json.load(open(REG)); e = reg.get("pfc_mac")
    if e:
        with open(TITAN, "rb") as f:
            f.seek(int(e["offset"])); stored = f.read(int(e["len"]))
        n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", stored, 8)
        cdz = TC.load("pfc_mac")
        print(f"  STORED pfc_mac read back from titan.gguf @ {e['offset']}: magic {stored[:8].decode('latin1')}"
              f"  n_gate {ng:,}  DEPTH {depth_of(cdz)}")
        print(f"  positive control BYTE-IDENTICAL to stored bytes: {TC.serialize(co, oo) == stored}")
    return 0


def verify():
    V = test_vectors()
    zb = zero_baseline(V)
    print("=" * 96)
    print(f"VERIFY — independent reference: plain Python integer acc + sum(w*x), no gate path.")
    print(f"  test set: {len(V)} vectors (edge cases + balanced random + extremes)")
    print(f"  ALL-ZERO-CIRCUIT BASELINE: {zb}/{len(V)}  ({100.0*zb/len(V):.1f}%) — a fake pass looks like this")
    cn, on = build_new(); dn = cd_of(cn, on)
    s = score(dn, V)
    print(f"  S37A AFTER  (to be stored): {s}/{len(V)}   DEPTH {depth_of(dn)}  gates {len(cn.ga):,}")
    co, oo = build_old(); do = cd_of(co, oo)
    so = score(do, V)
    print(f"  S37A BEFORE (control)     : {so}/{len(V)}   DEPTH {depth_of(do)}  gates {len(co.ga):,}")
    caught = True
    for kind in ("drop_carry_half", "truncate_high_pp"):
        cm, om = build_mutant(kind); dm = cd_of(cm, om)
        sm = score(dm, V)
        ok = sm < len(V)
        caught &= ok
        print(f"  MUTANT {kind:<18}: {sm}/{len(V)}  -> {'CAUGHT' if ok else 'NOT CAUGHT — SUITE IS BLIND'}")
    passed = (s == len(V)) and (so == len(V)) and caught
    print(f"  SUITE VERDICT: {'PASS' if passed else 'FAIL — WRITE NOTHING'}")
    return 0 if passed else 1


def plan(verbose=True):
    cn, on = build_new()
    blob = TC.serialize(cn, on)
    need = len(blob)
    body_law = 24 + len(cn.ga) * 8 + len(on) * 4
    print("=" * 96)
    print(f"PLAN — blob {need:,} bytes; TITANCIR body law 24 + n_gate*8 + n_out*4 = {body_law:,} -> "
          f"{'OK' if body_law == need else 'MISMATCH'}")
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    ctl = reg.get("pfc_mac")
    if ctl:                                   # CONTROL for the liveness discriminator: a KNOWN live netlist
        cp = probe(int(ctl["offset"]), int(ctl["len"]))
        print(f"  discriminator control — the KNOWN LIVE pfc_mac body @ {ctl['offset']}: "
              f"struct_hi {cp['struct_hi']:.4f}, magics {[m[0] for m in cp['magics']]}")
        cp2 = probe(int(ctl["offset"]) + 300000, need + 8)   # mid-body, magic OUT of the window
        print(f"    same body probed 300,000 bytes in (magic outside the window): "
              f"struct_hi {cp2['struct_hi']:.4f} -> discriminator still fires: {cp2['struct_hi'] > 0.25}")
    off, tname, pr = allocate(need, reg, verbose=verbose)
    print(f"  ALLOCATED {off} in tensor {tname}")
    print(f"    inertness probe over {pr['len']:,} bytes: zeros {pr['zeros']:,}  all-zero {pr['inert_zero']}  "
          f"WOF0-fill {pr['inert_wof']}  magic hits {pr['magics']}  struct_hi {pr['struct_hi']:.4f}")
    print(f"    clearance: {pr['clearance']}")
    return off, tname, pr, blob, cn, on


def fab():
    if verify() != 0:
        print("verification failed — WRITING NOTHING."); return 1
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if NAME in reg:
        print(f"{NAME} already fabricated (one-and-done). revert first."); return 0
    off, tname, pr, blob, cn, on = plan()
    dpn = depth_of(cd_of(cn, on))
    print("=" * 96)
    print(f"FABRICATING {NAME} -> {len(blob):,} bytes at {off} (journaled to {GENOME})")
    _write(off, blob)
    # RE-READ FROM DISK — the binary is the authority, not what we think we wrote
    with open(TITAN, "rb") as f:
        f.seek(off); back = f.read(len(blob))
    assert back[:8] == TC.MAGIC, "stored bytes do not carry TITANCIR"
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", back, 8)
    fq = open(TITAN, "rb"); mm = mmap.mmap(fq.fileno(), 0, access=mmap.ACCESS_READ)
    ga = list(struct.unpack_from("<%di" % ng, mm, off + 24))
    gb = list(struct.unpack_from("<%di" % ng, mm, off + 24 + ng * 4))
    outs = list(struct.unpack_from("<%di" % n_out, mm, off + 24 + ng * 8))
    mm.close(); fq.close()
    cdz = {"n_in": n_in, "n_wire": n_wire, "ga": ga, "gb": gb, "outs": outs}
    d_disk = depth_of(cdz)
    V = test_vectors(); s_disk = score(cdz, V)
    n_node = n_in + ng + 2
    print(f"  READ BACK FROM DISK: n_in {n_in}  n_wire {n_wire}  n_gate {ng:,}  n_out {n_out}")
    print(f"    n_node law (n_in + n_gate + 2 = {n_node:,}) vs n_wire {n_wire:,} -> "
          f"{'OK' if n_node == n_wire else 'MISMATCH'}")
    print(f"    DEPTH from the STORED bytes: {d_disk}  (in-process: {dpn}) -> "
          f"{'OK' if d_disk == dpn else 'MISMATCH'}")
    print(f"    stored netlist vs independent integer reference: {s_disk}/{len(V)}")
    if not (ng == 181728 and d_disk == dpn and s_disk == len(V) and n_node == n_wire):
        print("  STORED BYTES DID NOT VERIFY — reverting."); revert(); return 1
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "tensor": tname, "offset": off, "len": len(blob), "magic": "TITANCIR",
        "n_in": n_in, "n_out": n_out, "n_gate": ng, "n_wire": n_wire,
        "depth": d_disk, "gates_measured": ng, "muhl_rating": round(ng / d_disk, 3),
        "depth_source": "longest path over the netlist read back from titan.gguf",
        "build": "PFC_FINDINGS S37A rebuild — one fused carry-save tree over every partial product of "
                 "every lane PLUS the incoming accumulator; exactly one carry propagates in the whole MAC",
        "supersedes": "pfc_mac",
        "note": "ADDITIVE. pfc_mac (DEPTH 372 / 93,664 gates, the S37A BEFORE) is left intact at its own "
                "offset. S37A's table gives after = DEPTH 210 / 181,728 gates; the improvement existed "
                "only in host/pfc_mac_fab.py source until this fabrication (S53E class defect).",
        "source": "host/pfc_mac_fab.py::build_eval, fabricated by host/pfc_mac_prefix_fab.py",
        "verified_by": "independent Python integer acc+sum(w*x) over %d vectors; all-zero baseline %d/%d; "
                       "mutants drop_carry_half + truncate_high_pp both CAUGHT"
                       % (len(V), zero_baseline(V), len(V)),
        "mutant_caught": ["drop_carry_half", "truncate_high_pp"],
        "genome": GENOME, "reversible": True,
    }
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"  REGISTERED {NAME} (additive; pfc_mac still present: {'pfc_mac' in reg}).  GGUF-valid: {gg}")
    print(f"  revert: python host/pfc_mac_prefix_fab.py revert")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "measure"
    raise SystemExit({"measure": measure, "verify": verify,
                      "plan": lambda: (plan() and 0) or 0,
                      "fab": fab, "revert": revert}.get(cmd, measure)())
