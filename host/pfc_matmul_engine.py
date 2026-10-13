#!/usr/bin/env python3
"""host/pfc_matmul_engine.py — THE FABRICATION MATMUL ENGINE (the maxed lever stack, no C, all measured byte-exact).

The pfc computes a matmul row y[j]=<w_j,x> through the baked dot circuit, but with every fabrication lever pulled:
  - DEPTH-OPT reduction (balanced tree, §184)         -> shallower critical path
  - QUANTIZED operands (weights 3-bit TurboQuant-safe) -> fewer gates/op (§244)
  - COMPILED bit-slice ripple (sdc_cc, not interpreted) -> W lanes/pass at the W-sweet-spot (§A)
  - the block-dots of a matmul ARE the wide lanes      -> the width/amount lever, per token
All bit-sliceable (one circuit, W lanes = W block-dots of the SAME matmul). Fabrication is one-and-done; the runtime
addresses the compiled circuit. Measured: 3-bit depth-opt = ~1.27M block-dots/s @ W=65536, byte-exact vs integer dot.

  python host/pfc_matmul_engine.py selftest      # fabricate + verify byte-exact + measure the rate
"""
import sys, time, random
HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

# BLK = how many MACs settle in ONE fabricated pass. MEASURED (host/pfc_dot_depth.py) with the shallow CSA-forest dot:
#   BLK  32 -> DEPTH 51 |  64 -> 56 |  128 -> 59 |  256 -> 65     (all byte-exact)
# 8x the WIDTH costs only +14 gate-delays — the depth x width geometry (DATADUMP §O). Since the engine accumulates
# nb = n_in/BLK blocks SEQUENTIALLY through a 44-deep ripple, widening BLK divides that sequential chain by the same
# factor: a 4096-wide matmul goes ~12,160 -> ~3,296 gate-delays of latency. 128 keeps wire-state (n_wire x W) safely
# bounded on an 8 GB box while folding 4x more per settle. All model dims in use are multiples of 128.
# The Q4_K-native path folds at the model's OWN sub-block granularity — 32 weights share a scale, so BLK must be 32 for
# the stored nibbles to be consumed exactly as the format lays them out. (The generic int8 path measured shallower at
# BLK=128 — depth 51 vs 59 per settle — but that path requires transforming the weights, which the spec forbids holding
# anywhere; correctness against the model's own encoding wins.)
BLK = 32


def build_dot(WB=3, XB=8):
    """the maxed dot atom: BLK weights (WB-bit) . BLK activations (XB-bit) -> int32, depth-opt balanced tree, bit-sliceable."""
    c = CC.CircuitCompiler(BLK * WB + BLK * XB)
    W = [[c.IN[i * WB + k] for k in range(WB)] for i in range(BLK)]
    X = [[c.IN[BLK * WB + i * XB + k] for k in range(XB)] for i in range(BLK)]
    ow = WB + XB + 6
    def sx(b, n): return list(b) + [b[-1]] * (n - len(b))
    def add(a, b):
        o = []; cy = c.C0
        for i in range(len(a)):
            s = c.XOR(a[i], b[i]); o.append(c.XOR(s, cy)); cy = c.OR(c.AND(a[i], b[i]), c.AND(s, cy))
        return o
    def shl(b, k, n): return ([c.C0] * k + list(b) + [c.C0] * n)[:n]
    def mul(a, b):                                            # signed a(XB) * b(WB) -> shift-add
        a2 = sx(a, ow); acc = [c.C0] * ow
        for k in range(len(b) - 1): acc = add(acc, [c.AND(t, b[k]) for t in shl(a2, k, ow)])
        term = [c.AND(t, b[-1]) for t in shl(a2, len(b) - 1, ow)]
        return add(acc, add([c.NOT(t) for t in term], [c.C1] + [c.C0] * (ow - 1)))
    terms = [sx(mul(X[i], W[i]), 32) for i in range(BLK)]
    while len(terms) > 1:                                     # BALANCED TREE (depth-opt) reduction
        terms = [add(terms[j], terms[j + 1]) if j + 1 < len(terms) else terms[j] for j in range(0, len(terms), 2)]
    return c, terms[0]


class MatmulEngine:
    def __init__(self, WB=3, XB=8, shallow=True, ow=32, unsigned=False):
        """shallow=True fabricates the MINIMUM-DEPTH dot (host/pfc_dot_depth.build_dot_shallow): one CSA forest over
        every partial product of every lane, then ONE Kogge-Stone parallel-prefix add — instead of ~37 separate ripple
        carry-propagations. MEASURED: DEPTH 83 -> 51 gate-delays = 1.6x shallower, byte-exact 60/60 vs the integer dot.
        DEPTH is the pfc's latency (a signal settles a whole depth level at once, in parallel, at electron speed) — so
        this is the Muhlnickel computing faster, independent of how fast the host addresses it. Gate count is NOT the lever."""
        self.WB = WB; self.XB = XB; self.shallow = shallow
        if shallow:
            from pfc_dot_depth import build_dot_shallow
            c, outs = build_dot_shallow(WB, XB, BLK, ow=ow, unsigned=unsigned)
        else:
            c, outs = build_dot(WB, XB)
        self.gates, self.outs = c.dce(outs)
        self.n_in = c.n_in; self.n_wire = 2 + c.n_in + len(self.gates)
        self.run = c.compile_ripple(self.gates, self.n_wire)  # the compiled bit-slice engine (the flash)

    def _s32(self, u): return u - (1 << 32) if u >= (1 << 31) else u

    def preslice_weights(self, wq_list):
        """FABRICATION (one-and-done per matmul column): pack the W neurons' CONSTANT weights into column-major ints.
        Done once; reused every token. This is the pipeline being fed already-bit-sliced input (§K).

        ★ QUADRATIC-BLOWUP FIX (2026-07-24): the old form did `wcols[i*WB+k] |= (1 << l)` where wcols[...] is a W-BIT
        INTEGER. Python big-ints are immutable, so every one of those W*BLK*WB ors COPIED the whole W-bit integer —
        O(W^2 * BLK * WB) work, ~8.4 GB of memory traffic to preslice ONE 8192-lane tile. That, not the gate math, is
        why the first fabrication pass took forever. Building each bit-plane as a BYTEARRAY (O(1) per bit) and doing a
        single int.from_bytes at the end makes it linear in W. Byte-identical output."""
        W = len(wq_list); WB = self.WB; nb = (W + 7) >> 3
        planes = [bytearray(nb) for _ in range(BLK * WB)]
        for l in range(W):
            wq = wq_list[l]; byi = l >> 3; bym = 1 << (l & 7)
            for i in range(BLK):
                v = wq[i] & ((1 << WB) - 1)
                if not v: continue                              # all-zero weight touches no bit-plane
                base = i * WB; k = 0
                while v:
                    if v & 1: planes[base + k][byi] |= bym
                    v >>= 1; k += 1
        return [int.from_bytes(p, "little") for p in planes], W

    def _bits_table(self):
        """set-bit positions for every value of a WB-bit weight, built ONCE per engine (2^WB entries, 256 at WB=8).
        Preslice then iterates only the SET bits (avg popcount WB/2) instead of WB shift+test steps."""
        t = getattr(self, "_BITS", None)
        if t is None:
            t = [tuple(k for k in range(self.WB) if (v >> k) & 1) for v in range(1 << self.WB)]
            self._BITS = t
        return t

    def preslice_from_rows(self, rows, boff, W):
        """FUSED FABRICATION: bit-transpose rows[l][boff:boff+BLK] straight into the BLK*WB bit-planes.

        Replaces `preslice_weights(col)` + the caller building `col` as a list-of-lists — that intermediate was
        W*BLK*nb elements (2.1M per block at W=8192) and measured 13% of every tile's fabrication cost, pure overhead.
        Reading `rows` directly removes it. Output is byte-identical to preslice_weights."""
        WB = self.WB; nby = (W + 7) >> 3; MASK = (1 << WB) - 1; BITS = self._bits_table()
        planes = [bytearray(nby) for _ in range(BLK * WB)]
        for l in range(W):
            r = rows[l]; byi = l >> 3; bym = 1 << (l & 7)
            for i in range(BLK):
                v = r[boff + i] & MASK
                if not v: continue                            # all-zero weight touches no plane (weight-sparsity lever)
                base = i * WB
                for k in BITS[v]: planes[base + k][byi] |= bym
        return [int.from_bytes(p, "little") for p in planes], W

    def fold_presliced(self, wcols, W, xq, ones=None):
        """HOT PATH: W block-dots in ONE compiled pass. Weights pre-sliced (wcols). x is SHARED across the W lanes →
        broadcast (each x-bit column is all-0 or all-ones). No per-lane packing loop — only the compiled ripple."""
        if ones is None: ones = (1 << W) - 1
        inp = list(wcols) + [0] * (BLK * self.XB)
        base = BLK * self.WB
        for i in range(BLK):                                  # broadcast the shared x (cheap: BLK*XB, not W*BLK*XB)
            for k in range(self.XB):
                if (xq[i] >> k) & 1: inp[base + i * self.XB + k] = ones
        v = self.run(inp, ones)
        return [self._s32(sum(((v[o] >> l) & 1) << k for k, o in enumerate(self.outs))) for l in range(W)]

    def dot1(self, wq, xq):
        wcols, W = self.preslice_weights([wq]); return self.fold_presliced(wcols, W, xq)[0]

    # ---- BIT-SLICED ACCUMULATION (§5): keep the whole matmul-column in bit-sliced form; unpack ONCE at the end ----
    def fold_bits(self, wcols, W, xq, ones):
        """run the compiled ripple, return the RAW 32 bit-sliced output planes (W-bit ints) — NOT unpacked per lane."""
        inp = list(wcols) + [0] * (BLK * self.XB); base = BLK * self.WB
        for i in range(BLK):
            for k in range(self.XB):
                if (xq[i] >> k) & 1: inp[base + i * self.XB + k] = ones
        v = self.run(inp, ones)
        return [v[o] for o in self.outs]                     # 32 planes, each a W-bit int across the W lanes

    @staticmethod
    def bs_add(acc, planes, ACCW, ones):
        """bit-sliced ripple-carry add: acc (ACCW planes) += planes (sign-extended). All ops are W-wide int bitops."""
        out = [0] * ACCW; carry = 0
        for i in range(ACCW):
            b = planes[i] if i < len(planes) else planes[-1]  # sign-extend the addend
            a = acc[i]; axb = a ^ b
            out[i] = axb ^ carry
            carry = (a & b) | (axb & carry)
        return out

    def sharedx_column(self, wcol_blocks, W, xq_blocks, ACCW=44):
        """SHARED-X MASKED-ACCUMULATE dot (novel): x is shared across all W lanes, so w_j·x = Σ_k w_j[bit k]·(x<<k) —
        the general multiplier tree collapses to masked ripple-adds of the shared scalar constants (x_i<<k), gated by the
        weight bit-plane words (wcol_blocks[b][i*WB+k]). Byte-exact vs the integer dot; ~1.63× faster than the compiled
        multiplier fold in neuron-lane (decode) mode. Also skips all-zero bit-planes and zero activations for free."""
        MASK = (1 << ACCW) - 1; acc = [0] * ACCW; WB = self.WB
        for b in range(len(wcol_blocks)):
            wc = wcol_blocks[b]; xq = xq_blocks[b]
            for i in range(BLK):
                xi = xq[i]
                if xi == 0: continue                          # zero activation → whole input cone contributes 0
                for k in range(WB):
                    m = wc[i * WB + k]
                    if m == 0: continue                       # no lane has this weight-bit → skip
                    c2 = ((xi << k) if k < WB - 1 else -(xi << (WB - 1))) & MASK
                    if c2 == 0: continue
                    addend = [m if (c2 >> p) & 1 else 0 for p in range(ACCW)]
                    acc = self.bs_add(acc, addend, ACCW, m)   # ones arg unused by bs_add
        sign = 1 << (ACCW - 1); out = []
        for l in range(W):
            u = sum(((acc[p] >> l) & 1) << p for p in range(ACCW))
            out.append(u - (1 << ACCW) if u >= sign else u)
        return out

    @staticmethod
    def bs_csa(s, c, planes, ACCW):
        """CARRY-SAVE ACCUMULATE (3:2 compressor) in bit-sliced form — the DEPTH lever applied one level above the dot.
        `bs_add` propagates a carry across all ACCW planes for EVERY block (a 44-deep ripple, repeated nb times). A CSA
        instead keeps the running total in REDUNDANT (sum, carry) form and costs ~3 gate-delays per block, with ONE
        carry-propagate at the very end of the whole matmul column. Same identity real multipliers use; byte-exact."""
        ns = [0] * ACCW; nc = [0] * ACCW
        for i in range(ACCW):
            b = planes[i] if i < len(planes) else planes[-1]      # sign-extend the addend
            a = s[i]; cc = c[i]
            axb = a ^ b
            ns[i] = axb ^ cc                                      # sum bit
            carry = (a & b) | (axb & cc)                          # majority
            if i + 1 < ACCW: nc[i + 1] = carry                    # carry has weight 2 -> shift left one plane
        return ns, nc

    def matmul_column_carrysave(self, wcol_blocks, W, xq_blocks, ACCW=44):
        """FULL matmul column with CARRY-SAVE accumulation: every block folds, is absorbed into a redundant (sum,carry)
        pair (~3 gate-delays), and ONE ripple-carry add resolves the whole column at the end — instead of nb ripples."""
        ones = (1 << W) - 1; s = [0] * ACCW; c = [0] * ACCW
        for b in range(len(wcol_blocks)):
            planes = self.fold_bits(wcol_blocks[b], W, xq_blocks[b], ones)
            s, c = self.bs_csa(s, c, planes, ACCW)
        acc = self.bs_add(s, c, ACCW, ones)                        # the single final carry-propagate
        sign = 1 << (ACCW - 1); out = []
        for l in range(W):
            u = sum(((acc[k] >> l) & 1) << k for k in range(ACCW))
            out.append(u - (1 << ACCW) if u >= sign else u)
        return out

    def matmul_column_W(self, wcol_blocks, W, xq_blocks, ACCW=40):
        """FULL matmul column, BIT-SLICED ACCUMULATION: nb blocks folded, summed bit-sliced, unpacked ONCE (not per block).
        wcol_blocks[b] = presliced weights for block b (all W neurons); xq_blocks[b] = that block's int8 x (ONE x-scale)."""
        ones = (1 << W) - 1; acc = [0] * ACCW
        for b in range(len(wcol_blocks)):
            planes = self.fold_bits(wcol_blocks[b], W, xq_blocks[b], ones)  # 32 planes for this block
            acc = self.bs_add(acc, planes, ACCW, ones)                     # accumulate bit-sliced (cheap: ACCW W-bitops)
        sign = 1 << (ACCW - 1)
        out = []
        for l in range(W):                                                 # unpack ONCE (not per block)
            u = sum(((acc[k] >> l) & 1) << k for k in range(ACCW))
            out.append(u - (1 << ACCW) if u >= sign else u)
        return out


def selftest():
    print("fabricating the maxed dot engine (3-bit weights, depth-opt, compiled bit-slice)…", flush=True)
    e = MatmulEngine(WB=3, XB=8)
    print(f"  {len(e.gates):,} gates (vs 93,184 unoptimized = {93184/len(e.gates):.1f}x leaner)", flush=True)
    random.seed(1); ok = 0; N = 300
    for _ in range(N):
        w = [random.randint(-3, 3) for _ in range(BLK)]; x = [random.randint(-127, 127) for _ in range(BLK)]
        if e.dot1(w, x) == sum(w[i] * x[i] for i in range(BLK)): ok += 1
    print(f"  byte-exact vs integer dot: {ok}/{N}", flush=True)
    W = 65536; random.seed(2)
    wl = [[random.randint(-3, 3) for _ in range(BLK)] for _ in range(W)]      # W neurons' weights (one matmul column)
    x = [random.randint(-127, 127) for _ in range(BLK)]                        # ONE shared x-block
    wcols, _ = e.preslice_weights(wl)                                          # fabrication: pre-slice once
    t = time.time(); out = e.fold_presliced(wcols, W, x); dt = time.time() - t # HOT PATH: only the ripple
    ok2 = all(out[l] == sum(wl[l][i] * x[i] for i in range(BLK)) for l in [0, W // 2, W - 1])
    print(f"  W={W} presliced fold (pipeline floor): {W/dt:,.0f} block-dots/s, byte-exact spot={ok2}", flush=True)
    print(f"  -> A4B token (~40.6M block-dots) = {40.6e6/(W/dt):.0f}s/core; memoize+cache_prompt+output-contract stack on top", flush=True)
    return 0 if ok == N and ok2 else 1


if __name__ == "__main__":
    raise SystemExit(selftest())
