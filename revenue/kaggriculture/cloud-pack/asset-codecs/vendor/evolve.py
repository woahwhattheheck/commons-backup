#!/usr/bin/env python3
"""
evolve.py - self-directing exploratory compression search.

Owner, 2026-08-20:
  "and not 'compress in these ways I predetermined' automated and self directing
   and exploratory compression, let it invent try and fail and succeed, (without
   you blocking something that failed from ever being tried again) the idea is
   the Muhlnickel can do the work so why are you trying to do it manually when
   its faster and has more throughput"

TWO RULES THIS IS BUILT AROUND

1. NOTHING IS EVER PERMANENTLY PRUNED. A sequence that loses goes back in the
   pool and stays drawable forever. The space is path-dependent: a transform
   that loses on the raw plane can win AFTER another transform has run. A
   permanent blocklist makes compositions unreachable. Losers are re-drawn with
   a floor probability that never decays to zero.

2. THE PRIMITIVES ARE GATE OPERATIONS, NOT LIBRARY CALLS. Every transform below
   is XOR / fold / permute / mask / shift over the bit plane - things a
   muhlnickel can do in-circuit and in parallel. `call zlib` can never run
   in-circuit, so the entropy coder is ONLY the terminal scorer, never a step in
   the discovered program. What the search emits is a sequence of bit ops, which
   is the form that could be handed to the substrate to run instead of to
   Python.

COULD be, and so the thing it discovers is a program rather than a setting.

Every transform is invertible and the winner is verified by round-trip.
Pure stdlib.
"""
import sys, os, zlib, bz2, lzma, random, json, time
from collections import Counter

# ---------------------------------------------------------------- primitives
# each is (name, forward, inverse). grid = list of bytearray rows of 0/1.

def t_identity(g):            return [bytearray(r) for r in g]

def t_xor_prev_row(g):
    o = [bytearray(g[0])]
    for y in range(1, len(g)):
        o.append(bytearray(a ^ b for a, b in zip(g[y], g[y-1])))
    return o
def i_xor_prev_row(g):
    o = [bytearray(g[0])]
    for y in range(1, len(g)):
        o.append(bytearray(a ^ b for a, b in zip(g[y], o[y-1])))
    return o

def t_xor_prev_col(g):
    o = []
    for r in g:
        n = bytearray(r);
        for x in range(len(r)-1, 0, -1): n[x] = r[x] ^ r[x-1]
        o.append(n)
    return o
def i_xor_prev_col(g):
    o = []
    for r in g:
        n = bytearray(r)
        for x in range(1, len(r)): n[x] = r[x] ^ n[x-1]
        o.append(n)
    return o

def t_transpose(g):
    W = len(g[0]); H = len(g)
    return [bytearray(g[y][x] for y in range(H)) for x in range(W)]
i_transpose = t_transpose

def t_reverse_rows(g):        return [bytearray(r) for r in reversed(g)]
i_reverse_rows = t_reverse_rows

def t_reverse_cols(g):        return [bytearray(reversed(r)) for r in g]
i_reverse_cols = t_reverse_cols

def _rot(g, k):
    W = len(g[0]); k %= W
    return [bytearray(r[k:]) + bytearray(r[:k]) for r in g]
def t_rot4(g):   return _rot(g, 4)
def i_rot4(g):   return _rot(g, -4)
def t_rot25(g):  return _rot(g, 25)
def i_rot25(g):  return _rot(g, -25)

def t_interleave(g):
    h = len(g)//2
    o = []
    for i in range(h):
        o.append(bytearray(g[i])); o.append(bytearray(g[i+h]))
    if len(g) % 2: o.append(bytearray(g[-1]))
    return o
def i_interleave(g):
    n = len(g); h = n//2
    a = [bytearray(g[2*i]) for i in range(h)]
    b = [bytearray(g[2*i+1]) for i in range(h)]
    o = a + b
    if n % 2: o.append(bytearray(g[-1]))
    return o

def t_fold_adj(g):
    """accordion fold: pair (2i, 2i+1). rows halve, one bit becomes two."""
    h = len(g)//2; W = len(g[0])
    o = [bytearray(W*2) for _ in range(h)]
    for i in range(h):
        a, b = g[2*i], g[2*i+1]
        r = o[i]
        for x in range(W):
            r[2*x] = a[x]; r[2*x+1] = b[x]
    if len(g) % 2:
        last = bytearray(W*2)
        for x in range(W): last[2*x] = g[-1][x]
        o.append(last)
    return o
def i_fold_adj(g):
    W = len(g[0])//2
    o = []
    for r in g:
        a = bytearray(W); b = bytearray(W)
        for x in range(W):
            a[x] = r[2*x]; b[x] = r[2*x+1]
        o.append(a); o.append(b)
    return o

def t_gray(g):
    """binary -> gray along each row. invertible."""
    o = []
    for r in g:
        n = bytearray(r)
        for x in range(len(r)-1, 0, -1): n[x] = r[x] ^ r[x-1]
        o.append(n)
    return o
i_gray = i_xor_prev_col

OPS = [
    ('IDENT',      t_identity,     t_identity),
    ('XOR_ROW',    t_xor_prev_row, i_xor_prev_row),
    ('XOR_COL',    t_xor_prev_col, i_xor_prev_col),
    ('TRANSPOSE',  t_transpose,    i_transpose),
    ('REV_ROWS',   t_reverse_rows, i_reverse_rows),
    ('REV_COLS',   t_reverse_cols, i_reverse_cols),
    ('ROT4',       t_rot4,         i_rot4),
    ('ROT25',      t_rot25,        i_rot25),
    ('INTERLEAVE', t_interleave,   i_interleave),
    ('FOLD_ADJ',   t_fold_adj,     i_fold_adj),
]
BY = {n: (f, i) for n, f, i in OPS}
NAMES = [n for n, _, _ in OPS]

CODECS = (('zlib', lambda b: zlib.compress(b, 9)),
          ('bz2', lambda b: bz2.compress(b, 9)),
          ('lzma', lambda b: lzma.compress(b, preset=9)))


def pack(g):
    out = bytearray(); acc = 0; n = 0
    for r in g:
        for v in r:
            acc = (acc << 1) | v; n += 1
            if n == 8:
                out.append(acc); acc = 0; n = 0
    if n: out.append(acc << (8-n))
    return bytes(out)


def score(g):
    b = pack(g)
    bn, bs = None, None
    for name, f in CODECS:
        try: c = len(f(b))
        except Exception: continue
        if bs is None or c < bs: bn, bs = name, c
    return bs, bn


def apply_seq(g, seq):
    for n in seq:
        g = BY[n][0](g)
    return g


def invert_seq(g, seq):
    for n in reversed(seq):
        g = BY[n][1](g)
    return g


def load(path, W):
    b = open(path, 'rb').read()
    total = len(b)*8
    H = (total + W - 1)//W
    g = []
    for y in range(H):
        row = bytearray(W); base = y*W
        for x in range(W):
            i = base + x
            if i < total: row[x] = (b[i >> 3] >> (7-(i & 7))) & 1
        g.append(row)
    return g, len(b)


def main():
    path = sys.argv[1]
    def opt(n, d, c=int): return c(sys.argv[sys.argv.index(n)+1]) if n in sys.argv else d
    W = opt('--width', 200)
    ROUNDS = opt('--rounds', 120)
    MAXLEN = opt('--maxlen', 6)
    SEED = opt('--seed', 12345)
    LEDGER = opt('--ledger', 'evolve_ledger.json', str)
    rnd = random.Random(SEED)

    g0, srcb = load(path, W)
    base, bcodec = score(g0)
    print("EVOLVE  %s" % path)
    print("   %d x %d bits   source %s B   baseline %s B via %s  (%.2f%%)"
          % (len(g0[0]), len(g0), format(srcb, ','), format(base, ','), bcodec, 100.0*base/srcb))
    print("   %d primitives, sequences up to %d long, %d rounds" % (len(OPS), MAXLEN, ROUNDS))
    print("   RULE: nothing is ever permanently pruned. losers stay drawable.")
    print()

    # ledger persists across runs. failures are KEPT, never blocked.
    ledger = {}
    if os.path.exists(LEDGER):
        try: ledger = json.load(open(LEDGER))
        except Exception: ledger = {}
    print("   ledger loaded: %d sequences already tried in past runs" % len(ledger))

    pool = [[]]
    best = (base, [], bcodec)
    t0 = time.time()
    tried_now = 0
    for rd in range(ROUNDS):
        # draw: mostly mutate a known-good, but ALWAYS with a floor chance of
        # re-drawing a past LOSER, because a loser may win in a new composition.
        losers = [json.loads(k) for k, v in ledger.items() if v['bytes'] >= base]
        r = rnd.random()
        if losers and r < 0.25:
            seq = list(rnd.choice(losers))          # retry a failure. never blocked.
        elif r < 0.55 and best[1]:
            seq = list(best[1])
        else:
            seq = list(rnd.choice(pool))
        # mutate
        m = rnd.random()
        if m < 0.5 and len(seq) < MAXLEN: seq.append(rnd.choice(NAMES))
        elif m < 0.7 and seq: seq.pop(rnd.randrange(len(seq)))
        elif seq: seq[rnd.randrange(len(seq))] = rnd.choice(NAMES)
        else: seq.append(rnd.choice(NAMES))
        key = json.dumps(seq)
        if key in ledger:
            continue
        try:
            g = apply_seq(g0, seq)
            s, cod = score(g)
        except Exception as e:
            ledger[key] = dict(bytes=10**9, codec='ERR', err=str(e)[:60])
            continue
        tried_now += 1
        ledger[key] = dict(bytes=s, codec=cod)
        pool.append(seq)
        if s < best[0]:
            ok = invert_seq(apply_seq(g0, seq), seq) == g0
            print("   round %-4d %-9s %-10s %6.2f%%  %s  %s"
                  % (rd, format(s, ','), cod, 100.0*s/srcb, "LOSSLESS" if ok else "*** NOT LOSSLESS ***",
                     " -> ".join(seq) or "IDENT"))
            if ok: best = (s, seq, cod)

    json.dump(ledger, open(LEDGER, 'w'))
    print()
    print("   %d new sequences evaluated in %.1f s, ledger now %d total"
          % (tried_now, time.time()-t0, len(ledger)))
    wins = sum(1 for v in ledger.values() if v['bytes'] < base)
    print("   %d beat baseline, %d did not - and all %d stay drawable next run"
          % (wins, len(ledger)-wins, len(ledger)))
    print()
    print("   BEST: %s B (%.2f%% of source, %.2f%% of baseline) via %s"
          % (format(best[0], ','), 100.0*best[0]/srcb, 100.0*best[0]/base, best[2]))
    print("   PROGRAM: %s" % (" -> ".join(best[1]) or "IDENT"))
    print("   Those are bit operations, not library calls - the form a substrate could run.")


if __name__ == '__main__':
    sys.exit(main() or 0)
