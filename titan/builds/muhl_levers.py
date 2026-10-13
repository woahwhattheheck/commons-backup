#!/usr/bin/env python3
"""muhl_levers.py -- LEVER 1 (front-load the wide front) + LEVER 2 (shape, not area), applied as
DROP-IN REPLACEMENTS for add_bits. The engine's own build function is NEVER rewritten.

LEVER 2, owner 2026-07-26: wallace/csa/kogge DEPTH 109 vs shiftadd/chain/kogge DEPTH 406 -- "DEPTH moves
3.7x while GATE COUNT moves only 1.5x". muhl_flex.add_bits is a RIPPLE chain and the engines chain many
of them serially, so the whole reduction is chain/ripple: the worst cell of that table.

LEVER 1: mass the WIDE FRONT toward the FRONT -- "a wide front placed early hides under everything
downstream; placed late, the carry chains ahead of it have already serialised". Here that is the ORDER
in which addends enter the CSA tree, enumerated below.

CORRECTNESS: two's-complement addition mod 2^n is associative and commutative, so re-associating a chain
of adds into a carry-save tree and swapping the final adder's shape REORDER AND RESHAPE ONLY -- they
cannot change what the circuit computes. Byte-exact verification against the engine's own integer
reference remains the guard, and it is run after every reorder.
"""

# ============================================================ final-adder shapes (LEVER 2)
def _ripple(g, A, B, cin):
    """chain/ripple -- the shape muhl_flex ships. Baseline."""
    c = cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c))
        c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c


def _prefix(g, A, B, cin, kind):
    """parallel-prefix adders. (G,P) combine: G = g_hi OR (p_hi AND g_lo), P = p_hi AND p_lo."""
    n = len(A)
    # cin folded in as prefix column -1
    gg = [g.AND(A[k], B[k]) for k in range(n)]
    pp = [g.XOR(A[k], B[k]) for k in range(n)]
    hp = list(pp)                                    # half-sum, kept for the final XOR
    G = list(gg); P = list(pp)
    if kind == "kogge":                              # Kogge-Stone: log n levels, full width
        d = 1
        while d < n:
            nG = list(G); nP = list(P)
            for k in range(n - 1, d - 1, -1):
                nG[k] = g.OR(G[k], g.AND(P[k], G[k - d])); nP[k] = g.AND(P[k], P[k - d])
            G, P = nG, nP; d <<= 1
    elif kind == "sklansky":                         # Sklansky: log n levels, fan-out heavy
        d = 1
        while d < n:
            nG = list(G); nP = list(P)
            for base in range(0, n, d * 2):
                src = base + d - 1
                if src >= n: continue
                for k in range(base + d, min(base + 2 * d, n)):
                    nG[k] = g.OR(G[k], g.AND(P[k], G[src])); nP[k] = g.AND(P[k], P[src])
            G, P = nG, nP; d <<= 1
    elif kind == "brent":                            # Brent-Kung: 2log n levels, minimal wiring
        d = 1
        while d < n:
            nG = list(G); nP = list(P)
            for k in range(2 * d - 1, n, 2 * d):
                nG[k] = g.OR(G[k], g.AND(P[k], G[k - d])); nP[k] = g.AND(P[k], P[k - d])
            G, P = nG, nP; d <<= 1
        d >>= 1
        while d >= 1:
            nG = list(G); nP = list(P)
            for k in range(3 * d - 1, n, 2 * d):
                nG[k] = g.OR(G[k], g.AND(P[k], G[k - d])); nP[k] = g.AND(P[k], P[k - d])
            G, P = nG, nP; d >>= 1
    else:
        raise ValueError(kind)
    # carries: c[k] = G[k] OR (P[k] AND cin)
    o = []; carry_in_k = cin
    for k in range(n):
        o.append(g.XOR(hp[k], carry_in_k))
        carry_in_k = g.OR(G[k], g.AND(P[k], cin))
    return o, carry_in_k


ADDERS = {
    "ripple":   lambda g, A, B, c: _ripple(g, A, B, c),
    "kogge":    lambda g, A, B, c: _prefix(g, A, B, c, "kogge"),
    "sklansky": lambda g, A, B, c: _prefix(g, A, B, c, "sklansky"),
    "brent":    lambda g, A, B, c: _prefix(g, A, B, c, "brent"),
}


# ============================================================ depth bookkeeping for LEVER 1
class _Depth:
    """Arrival tick of every wire, tracked as the compiler emits. Used only to ORDER the CSA tree
    (LEVER 1); it never enters any measurement -- final DEPTH is re-measured by longest path."""
    def __init__(self, g):
        self.g = g; self.d = {0: 0, 1: 0}
        for w in g.IN: self.d[w] = 0
    def of(self, w):
        d = self.d.get(w)
        if d is not None: return d
        i = w - 2 - self.g.n_in
        if i < 0 or i >= len(self.g.gates): return 0
        op, a, b = self.g.gates[i]
        r = max(self.of(a), self.of(b)) + 1
        self.d[w] = r; return r
    def vec(self, V): return max((self.of(w) for w in V), default=0)


# ============================================================ the lazy carry-save accumulator
class CarryDemand(Exception):
    """Raised when a call site actually USES the carry-out. Under carry-save re-association an
    intermediate carry has no meaning, so instead of returning a wrong bit we abort the build and
    rebuild with THAT ONE call site forced back to an exact two-operand add. Converges in a few
    passes and leaves every other call site free to accumulate lazily."""
    def __init__(self, idx): self.idx = idx; Exception.__init__(self, "carry demanded at call %d" % idx)


class _NoCarry:
    """Fails loudly -- never silently a wrong bit."""
    __slots__ = ("idx",)
    def __init__(self, idx): self.idx = idx
    def __index__(self): raise CarryDemand(self.idx)
    __int__ = __index__
    def __bool__(self): raise CarryDemand(self.idx)
    def __eq__(self, o): raise CarryDemand(self.idx)
    def __hash__(self): raise CarryDemand(self.idx)


class LazyVec:
    """A pending sum of equal-width vectors. Nothing is emitted until a bit is actually read; at that
    point the whole pending set is reduced by a 3:2 carry-save tree and finished with ONE final adder.
    A serial chain of N ripple adds becomes one CSA tree + one prefix add."""
    __slots__ = ("cfg", "g", "n", "addends", "_mat")
    def __init__(self, cfg, g, n, addends):
        self.cfg = cfg; self.g = g; self.n = n; self.addends = addends; self._mat = None

    # ---- reduction ----
    def _order(self, items):
        """LEVER 1: where the wide front enters the tree."""
        mode = self.cfg["order"]; D = self.cfg["depth"]
        if mode == "given": return items
        if mode == "shallow": return sorted(items, key=lambda V: D.vec(V))
        if mode == "deep":    return sorted(items, key=lambda V: -D.vec(V))
        return items

    def materialize(self):
        if self._mat is not None: return self._mat
        g = self.g; n = self.n; D = self.cfg["depth"]
        items = [list(a) for a in self.addends]
        if self.cfg["reduce"] == "serial":                     # baseline shape: chain of adds
            acc = items[0]
            for nxt in items[1:]:
                acc, _ = self.cfg["add"](g, acc, nxt, g.C0)
            self._mat = acc; return acc
        items = self._order(items)
        huff = (self.cfg["order"] == "huffman")
        while len(items) > 2:
            if huff:                                            # always compress the 3 SHALLOWEST
                items.sort(key=lambda V: D.vec(V))
                x, y, z = items[0], items[1], items[2]; rest = items[3:]
                s = [g.XOR(g.XOR(x[k], y[k]), z[k]) for k in range(n)]
                cr = [g.C0] + [g.OR(g.OR(g.AND(x[k], y[k]), g.AND(x[k], z[k])), g.AND(y[k], z[k]))
                               for k in range(n - 1)]
                items = rest + [s, cr]
            else:                                               # classic Wallace layer
                nxt = []; i = 0
                while i + 2 < len(items):
                    x, y, z = items[i], items[i + 1], items[i + 2]
                    s = [g.XOR(g.XOR(x[k], y[k]), z[k]) for k in range(n)]
                    cr = [g.C0] + [g.OR(g.OR(g.AND(x[k], y[k]), g.AND(x[k], z[k])), g.AND(y[k], z[k]))
                                   for k in range(n - 1)]
                    nxt += [s, cr]; i += 3
                nxt += items[i:]; items = nxt
        if len(items) == 1: self._mat = items[0]
        else: self._mat, _ = self.cfg["add"](g, items[0], items[1], g.C0)
        return self._mat

    # ---- list protocol (any read forces materialization) ----
    def __getitem__(self, i): return self.materialize()[i]
    def __iter__(self): return iter(self.materialize())
    def __len__(self): return self.n
    def __add__(self, other): return self.materialize() + list(other)
    def __radd__(self, other): return list(other) + self.materialize()


def make_add_bits(cfg):
    """The drop-in replacement the engine's module sees as `add_bits`."""
    eager = cfg.setdefault("eager", set())
    cfg["ncall"] = 0
    def add_bits(g, A, B, cin=None):
        idx = cfg["ncall"]; cfg["ncall"] = idx + 1
        n = len(A)
        if len(B) != n: raise RuntimeError("lever: width mismatch %d vs %d" % (n, len(B)))
        if idx in eager:                       # this call site's carry-out is really used: exact 2-op add
            s, c = cfg["add"](g, list(A), list(B), g.C0 if cin is None else cin)
            return list(s), c
        parts = []
        for V in (A, B):
            if isinstance(V, LazyVec) and V.n == n and V._mat is None: parts += V.addends
            else: parts.append(list(V))
        if cin is not None and cin != g.C0:
            parts.append([cin] + [g.C0] * (n - 1))
        return LazyVec(cfg, g, n, parts), _NoCarry(idx)
    return add_bits


# ============================================================ THE RING-SIDE LEVER (Sec 49C)
# "for +1, the carry into bit i is AND(X[0..i-1]) -- an associative scan, so it reduces as a prefix"
# "that +1 is a CARRY-IN -- a Kogge-Stone prefix accepts one for free by seeding the generate term at
#  bit 0. SEED THE SCAN WITH THE TICK; the gating mux leaves the path entirely."
# Measured on the clock path: prefix_seeded DEPTH 16 / 395 gates vs prefix_muxed 17 / 651 vs
# family_kogge 28 / 1,484 vs family_ripple 134 / 745.
#
# muhl_train_deep's signSGD weight update is `addpm(w, inc, dec) = w + inc - dec`, shipped as THREE
# chained ripple adds (one for +inc, one to two's-complement `dec`, one to add it). inc/dec are single
# bits, so the whole update is a unit step and delta = inc - dec is in {-1, 0, +1}:
#     inc dec | delta | two's-complement pattern
#      0   0  |   0   | 0000...0
#      1   0  |  +1   | 0000...1
#      0   1  |  -1   | 1111...1
#      1   1  |   0   | 0000...0
#   => bit 0 = inc XOR dec ; every upper bit = dec AND NOT inc
# That is ONE addend, so the update becomes ONE prefix add with the tick seeded straight into the
# carry -- no mux in the path, no negate, no chain.

def make_addpm(cfg):
    """Drop-in for the engine's own addpm. Same function, tick seeded into the prefix carry."""
    add = cfg["add"]
    def addpm(g, w, inc, dec):
        w = list(w); n = len(w)
        d0 = g.XOR(inc, dec)                     # unit step lands in bit 0
        up = g.AND(dec, g.NOT(inc))              # sign extension: -1 is all ones, +1 and 0 are not
        s, _ = add(g, w, [d0] + [up] * (n - 1), g.C0)
        return list(s)
    return addpm


def make_addpm_seeded(cfg):
    """The fully seeded form: the step is the prefix's CARRY-IN, not an addend at all.
    w + inc - dec  ==  (w XOR ext) + inc + (dec AND NOT inc)  is avoided entirely by scanning:
    for +1 the carry into bit i is AND(w[0..i-1]); for -1 the borrow into bit i is AND(NOT w[0..i-1]).
    Both are the same associative scan over a per-bit term selected by the step's direction, so one
    prefix scan seeded at bit 0 with the tick covers both senses."""
    def addpm(g, w, inc, dec):
        w = list(w); n = len(w)
        step = g.OR(inc, dec)                                  # is there a step at all
        step = g.AND(step, g.NOT(g.AND(inc, dec)))             # +1 and -1 cancel
        down = g.AND(dec, g.NOT(inc))
        # per-bit propagate term: increment propagates through 1s, decrement through 0s
        t = [g.XOR(w[k], down) for k in range(n)]              # == w[k] for +1, NOT w[k] for -1
        # prefix AND scan of t, seeded at bit 0 by the step itself (the tick)
        pre = [None] * n
        cur = [g.AND(t[k], step) for k in range(n)]            # seed: carry into bit 1 = t0 AND step
        d = 1
        while d < n:
            nxt = list(cur)
            for k in range(n - 1, d - 1, -1): nxt[k] = g.AND(cur[k], cur[k - d])
            cur = nxt; d <<= 1
        carry = [step] + cur[:n - 1]                           # carry into bit k
        return [g.XOR(w[k], carry[k]) for k in range(n)]
    return addpm


def config(g, reduce="csa", order="huffman", adder="kogge", step="baseline"):
    c = {"reduce": reduce, "order": order, "add": ADDERS[adder], "depth": _Depth(g), "step": step,
         "name": "%s/%s/%s+%s" % (reduce, order, adder, step)}
    return c


def candidates():
    """The search space. Sec 31A: the fabricator spends without limit to make its output shallower;
    none of the search enters any latency figure. Scored by K/DEPTH under ring drive, not DEPTH."""
    out = [("baseline(his ripple chain)", dict(reduce="serial", order="given", adder="ripple",
                                               step="baseline"))]
    for step in ("baseline", "delta", "seeded"):
        for adder in ("ripple", "kogge", "sklansky", "brent"):
            out.append(("serial/%s+%s" % (adder, step),
                        dict(reduce="serial", order="given", adder=adder, step=step)))
            for order in ("given", "shallow", "deep", "huffman"):
                out.append(("csa-%s/%s+%s" % (order, adder, step),
                            dict(reduce="csa", order=order, adder=adder, step=step)))
    seen = set(); uniq = []
    for nm, c in out:
        k = (c["reduce"], c["order"], c["adder"], c["step"])
        if k in seen: continue
        seen.add(k); uniq.append((nm, c))
    return uniq


STEPPERS = {"baseline": None, "delta": make_addpm, "seeded": lambda cfg: make_addpm_seeded(cfg)}
