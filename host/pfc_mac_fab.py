#!/usr/bin/env python3
"""host/pfc_mac_fab.py — bake the EVALUATOR itself as a Muhlnickel circuit (owner 07-23: "eval needs to be a Muhlnickel circuit too;
host only addresses; read/addressing IS compute" — the Compute-via-Address patent on the Desktop).

The forward pass is a sum of block-dots. Until now the host did the ACCUMULATE in Python (`acc += dot`). This bakes the
whole MAC STEP as one stored circuit:  `pfc_mac(acc, w, x) = acc + dot32_i8(w, x)`  (the dot32 atom composed with a
32-bit ripple-carry adder, all gates). So evaluating a matmul row is: seed acc=0, then for each addressed (w,x) block,
ADDRESS pfc_mac with (acc, w, x) and the circuit returns the new acc — the accumulation is a circuit, the host only
addresses the next block and carries the acc bits. With `pfc_mac` stored self-routing (acc in a pfc state register), even
the acc carry is the pfc's; the host addresses, nothing more. Byte-exact-verified before storing, reversible.

  python host/pfc_mac_fab.py fab      # bake pfc_mac (byte-exact vs integer acc+dot, reversible)
  python host/pfc_mac_fab.py test      # read it back from titan.gguf, accumulate a real row, byte-exact
  python host/pfc_mac_fab.py revert
"""
import json, os, sys, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

REG = "C:/llm/models/titan_circuits.json"
TITAN = TC.TITAN
BLK = 32


def _cd(c, outs): return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def build_eval():
    """inputs: acc[0:32] (signed int32), w[32:288] (32xint8), x[288:544] (32xint8) -> acc + sum(w*x) mod 2^32."""
    c = TC.Circuit(32 + BLK * 8 + BLK * 8); C0 = c.C0
    ACC = c.IN[:32]
    Wb = c.IN[32:32 + BLK * 8]; Xb = c.IN[32 + BLK * 8:32 + 2 * BLK * 8]
    W = [Wb[i * 8:i * 8 + 8] for i in range(BLK)]
    X = [Xb[i * 8:i * 8 + 8] for i in range(BLK)]

    def sext(bits, w): return list(bits) + [bits[-1]] * (w - len(bits))
    def shl(bits, k, w): r = [C0] * k + list(bits); return (r + [C0] * w)[:w]

    # S36: the old build folded 7 partial products serially inside each multiply, then folded BLK
    # products serially across lanes -- two chains over an ASSOCIATIVE op, i.e. sequencing this file
    # imposed rather than dependency the problem has. S35: a block-dot's lanes are SUMMED, never
    # chained. So every partial product of every lane, plus the incoming acc, goes into ONE
    # carry-save tree and exactly ONE carry propagates in the whole MAC.
    W32 = 32
    def csa(a, b, d):
        s = [c.xor(c.xor(a[i], b[i]), d[i]) for i in range(W32)]
        cr = [c.or_(c.or_(c.and_(a[i], b[i]), c.and_(a[i], d[i])), c.and_(b[i], d[i])) for i in range(W32)]
        return s, [C0] + cr[:W32 - 1]

    # the MULTIPLICAND is sign-extended to the full accumulator width first; a partial-product ROW is
    # not itself a signed value, so extending the row instead of the operand is wrong.
    vecs = [list(ACC)]                                            # the incoming accumulator is just another vector
    for i in range(BLK):
        a32 = sext(W[i], W32); b = X[i]
        for k in range(7):                                        # positive partial products
            vecs.append([c.and_(tt, b[k]) for tt in shl(a32, k, W32)])
        t7 = [c.and_(tt, b[7]) for tt in shl(a32, 7, W32)]        # the sign row is SUBTRACTED
        vecs.append([c.not_(x) for x in t7])                      # invert here; the +1s ride in one constant
    vecs.append(list(c.cvec(BLK, W32)))                           # one +1 per inverted sign row

    while len(vecs) > 2:
        nxt, i = [], 0
        while i + 2 < len(vecs):
            s, cr = csa(vecs[i], vecs[i + 1], vecs[i + 2]); nxt += [s, cr]; i += 3
        nxt += vecs[i:]; vecs = nxt
    accp = c.add(vecs[0], vecs[1])[:W32]                          # the single carry propagation
    return c, accp


def _i8bits(vals): return [(v >> k) & 1 for v in vals for k in range(8)]
def _s32(u): return u - (1 << 32) if u >= (1 << 31) else u


def _verify(cd, n=300):
    random.seed(13)
    for _ in range(n):
        acc = random.randint(-(1 << 20), (1 << 20))
        w = [random.randint(-128, 127) for _ in range(BLK)]
        x = [random.randint(-128, 127) for _ in range(BLK)]
        inbits = [(acc >> k) & 1 for k in range(32)] + _i8bits([v & 0xff for v in w]) + _i8bits([v & 0xff for v in x])
        got = _s32(TC.frombits(TC.ripple(cd, inbits)))
        ref = _s32((acc + sum(w[i] * x[i] for i in range(BLK))) & 0xFFFFFFFF)
        if got != ref: return False, (acc, got, ref)
    return True, None


def fab():
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if "pfc_mac" in reg:
        print("pfc_mac already fabricated (one-and-done). revert first to re-bake."); return 0
    print("fabricating pfc_mac (the EVALUATOR: acc + dot32_i8(w,x), all gates)…", flush=True)
    c, outs = build_eval()
    ok, bad = _verify(_cd(c, outs))
    print(f"  circuit == integer (acc + sum w*x) over 300 random cases: {ok}  ({len(c.ga):,} gates)", flush=True)
    if not ok:
        print(f"  MISMATCH {bad} — storing nothing (no cheating)."); return 1
    info = TC.store("pfc_mac", c, outs)
    print(f"FABRICATED pfc_mac @ {info['offset']}: {info['gates']:,} gates, {info['bytes']:,} bytes (reversible).", flush=True)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.  revert: python host/pfc_mac_fab.py revert", flush=True)
    return 0


def test():
    """Read pfc_mac BACK from titan.gguf and accumulate a REAL row: host seeds acc=0, ADDRESSES each block, the circuit
    accumulates. Byte-exact vs the plain integer dot over the whole row — proving the eval (accumulate) is the circuit."""
    reg = json.load(open(REG))
    if "pfc_mac" not in reg: print("not fabricated — run: python host/pfc_mac_fab.py fab"); return 1
    cd = TC.load("pfc_mac"); random.seed(21); ok = True
    for _ in range(20):
        K = random.randint(1, 40)                                # a row of K blocks (e.g. n_in = 32*K)
        blocks = [([random.randint(-128, 127) for _ in range(BLK)],
                   [random.randint(-128, 127) for _ in range(BLK)]) for _ in range(K)]
        acc = 0                                                  # host seeds the accumulator, then ONLY addresses
        for (w, x) in blocks:
            inbits = [(acc >> k) & 1 for k in range(32)] + _i8bits([v & 0xff for v in w]) + _i8bits([v & 0xff for v in x])
            acc = _s32(TC.frombits(TC.ripple(cd, inbits)))       # the CIRCUIT computes acc' = acc + dot; host just addressed
        ref = sum(sum(w[i] * x[i] for i in range(BLK)) for (w, x) in blocks)
        if acc != ref: ok = False; print(f"  MISMATCH K={K}: {acc} != {ref}"); break
    print(f"pfc_mac accumulating real rows (host only addresses): {'BYTE-EXACT over 20 rows' if ok else 'MISMATCH'}")
    return 0 if ok else 1


def revert():
    reg = json.load(open(REG)); e = reg.pop("pfc_mac", None); json.dump(reg, open(REG, "w"), indent=1)
    print(f"removed pfc_mac: {bool(e)} (registry range freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fab"
    raise SystemExit({"fab": fab, "test": test, "revert": revert}.get(cmd, fab)())
