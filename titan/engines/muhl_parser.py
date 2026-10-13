#!/usr/bin/env python3
"""muhl_parser.py -- a PARENTHESIS-BALANCE / BRACKET-MATCHING checker fabricated on Bryce's
Muhlnickel substrate.

The classic "is this bracket string balanced?" is a PUSHDOWN problem -- it needs a stack, the one
thing a finite counter famously cannot do for multiple bracket types. Here it is built as NAND/AND/
OR/XOR/NOT gates with the White Box compiler (sdc_cc.CircuitCompiler), DCE'd, rippled, and VERIFIED
BYTE-EXACT against an independent pure-Python reference -- no numpy, no host executor as runtime, no
touching titan.gguf. Fabrication-time synthesis: the logic is proven byte-exact BEFORE it would ever
be stored, then it is a real gate netlist the substrate could bake and run by address.

Two circuits:
  balance    PUSHDOWN COUNTER over an N-token stream of '(' / ')' / pad. Running two's-complement
             depth counter; flags any underflow (a ')' with depth 0) and requires final depth 0.
             This is the exact automaton that recognises the Dyck language of one bracket type.
             == Python reference over random balanced/unbalanced streams.
  brackets   FULL BRACKET MATCHER over () [] {} -- a real UNROLLED STACK (one-hot stack pointer +
             N type cells, push/pop/compare-top per token). A pure counter CANNOT do this ("([)]"
             must be rejected); the stack can. == Python stack reference, incl. type-mismatch and
             underflow cases.
"""
import sys, os, random, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---------- shared helpers (same idiom as muhl_flex.py) ----------
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

def add_bits(g, A, B, cin=None):
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c
def mux1(g, s, a, b): return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))
def xnor(g, a, b): return g.NOT(g.XOR(a, b))
def orlist(g, xs):
    o = g.C0
    for x in xs: o = g.OR(o, x)
    return o
def andlist(g, xs):
    o = g.C1
    for x in xs: o = g.AND(o, x)
    return o

RESULTS = []
def record(name, gates, depth, ok, cases, note=""):
    RESULTS.append((name, len(gates), depth, ok, cases, note))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name:9s} {len(gates):>8,} gates  depth {depth:>4}  byte-exact over {cases:,} cases  {note}", flush=True)

# ================================ balance: pushdown counter, one bracket type ================================
# token per position = 2 input bits: (open, close). 00=pad/none, 01=open '(', 10=close ')'.
def build_balance(N=32):
    B = max(4, N.bit_length() + 2)                      # two's-complement counter width (range +/- 2^(B-1)-1 >> N)
    g = CC.CircuitCompiler(2 * N); IN = g.IN
    counter = [g.C0] * B
    ever_neg = g.C0
    for t in range(N):
        o = IN[2 * t]; c = IN[2 * t + 1]
        # delta = +1 for open (00..01), -1 for close (11..11), 0 for pad
        delta = [g.OR(o, c)] + [c] * (B - 1)
        counter, _ = add_bits(g, counter, delta)        # ripple add, carry-out discarded
        ever_neg = g.OR(ever_neg, counter[B - 1])        # sign bit set => depth went negative (underflow)
    zero = andlist(g, [g.NOT(x) for x in counter])       # final depth == 0
    balanced = g.AND(g.NOT(ever_neg), zero)
    return g, [balanced], B

def ref_balance(tokens):                                 # tokens: 0=pad, 1=open, 2=close
    d = 0
    for t in tokens:
        if t == 1: d += 1
        elif t == 2:
            d -= 1
            if d < 0: return 0
    return 1 if d == 0 else 0

def test_balance(N=32, cases=4000):
    g, outs, B = build_balance(N)
    run, out2, gates, _ = build_run(g, outs)
    random.seed(110)
    ok = True; ncase = 0
    for _ in range(cases):
        # mix genuinely-balanced strings with fully random ones so both classes are exercised
        if random.random() < 0.5:
            toks = _gen_balanced_single(N)
        else:
            toks = [random.choice((0, 1, 2)) for _ in range(N)]
        inp = [0] * (2 * N)
        for t, tok in enumerate(toks):
            if tok == 1: inp[2 * t] = 1
            elif tok == 2: inp[2 * t + 1] = 1
        got = bit(run(inp, 1), out2[0])
        ncase += 1
        if got != ref_balance(toks): ok = False; break
    record("balance", gates, depth_of(g, gates, out2), ok, ncase, f"N={N}, Dyck-1 pushdown counter")

def _gen_balanced_single(N):
    # random well-formed '()' sequence padded to N (may be truncated -> unbalanced, that's fine, ref decides)
    seq = []; depth = 0
    for _ in range(N):
        if depth == 0: step = random.choice((0, 1))          # pad or open
        else: step = random.choice((0, 1, 2))
        if step == 1: depth += 1
        elif step == 2: depth -= 1
        seq.append(step)
    return seq

# ================================ brackets: full matcher, () [] {} via an unrolled stack ================================
# token per position = 3 input bits encoding 0..6:
#   0 pad   1 '('   2 ')'   3 '['   4 ']'   5 '{'   6 '}'
# type ids: 1='()' 2='[]' 3='{}'.  a close is valid iff stack top is the same type id.
def build_brackets(N=12):
    g = CC.CircuitCompiler(3 * N); IN = g.IN
    def cbits(x, n): return [g.C1 if (x >> k) & 1 else g.C0 for k in range(n)]
    # stack: N cells, each a 2-bit type id (0=empty slot); sp = one-hot over 0..N
    cells = [list(cbits(0, 2)) for _ in range(N)]
    sp = [g.C1] + [g.C0] * N                              # sp_oh[0]=1 -> stack pointer at 0
    err = g.C0
    for t in range(N):
        b0, b1, b2 = IN[3 * t], IN[3 * t + 1], IN[3 * t + 2]
        def eq(x):
            return andlist(g, [b if (x >> k) & 1 else g.NOT(b) for k, b in enumerate((b0, b1, b2))])
        open1, close1 = eq(1), eq(2)
        open2, close2 = eq(3), eq(4)
        open3, close3 = eq(5), eq(6)
        is_open = orlist(g, [open1, open2, open3])
        is_close = orlist(g, [close1, close2, close3])
        otype0 = g.OR(open1, open3);  otype1 = g.OR(open2, open3)     # id of the opener (1,2,3)
        ctype0 = g.OR(close1, close3); ctype1 = g.OR(close2, close3)  # id the closer expects
        # --- read top-of-stack = cell[sp-1], and whether the stack is non-empty ---
        top0 = orlist(g, [g.AND(sp[k], cells[k - 1][0]) for k in range(1, N + 1)])
        top1 = orlist(g, [g.AND(sp[k], cells[k - 1][1]) for k in range(1, N + 1)])
        nonempty = g.NOT(sp[0])
        match = andlist(g, [nonempty, xnor(g, top0, ctype0), xnor(g, top1, ctype1)])
        # errors: a close that doesn't match the top (incl. empty stack), or an overflow push at sp==N
        err = g.OR(err, g.AND(is_close, g.NOT(match)))
        err = g.OR(err, g.AND(is_open, sp[N]))
        # --- push: on open, write opener id into cell[sp] ---
        pushhere = [g.AND(is_open, sp[j]) for j in range(N)]
        cells = [[mux1(g, pushhere[j], otype0, cells[j][0]),
                  mux1(g, pushhere[j], otype1, cells[j][1])] for j in range(N)]
        # --- stack-pointer update (one-hot). push=+1, pop(valid close)=-1, else hold. mutually exclusive. ---
        do_push = is_open
        do_pop = g.AND(is_close, nonempty)
        hold = g.NOT(g.OR(do_push, do_pop))
        newsp = []
        for k in range(N + 1):
            up = g.AND(do_push, sp[k - 1]) if k - 1 >= 0 else g.C0
            dn = g.AND(do_pop, sp[k + 1]) if k + 1 <= N else g.C0
            hd = g.AND(hold, sp[k])
            newsp.append(orlist(g, [up, dn, hd]))
        sp = newsp
    balanced = g.AND(g.NOT(err), sp[0])                   # no error AND stack empty at end
    return g, [balanced]

def ref_brackets(tokens):                                # tokens: 0 pad,1 '(',2 ')',3 '[',4 ']',5 '{',6 '}'
    openmap = {1: 1, 3: 2, 5: 3}; closemap = {2: 1, 4: 2, 6: 3}
    st = []
    for t in tokens:
        if t in openmap: st.append(openmap[t])
        elif t in closemap:
            if not st or st[-1] != closemap[t]: return 0
            st.pop()
    return 1 if not st else 0

def test_brackets(N=12, cases=4000):
    g, outs = build_brackets(N)
    run, out2, gates, _ = build_run(g, outs)
    random.seed(77)
    OPENS = {1: 2, 3: 4, 5: 6}                            # opener token -> its matching closer token
    ok = True; ncase = 0
    for _ in range(cases):
        r = random.random()
        if r < 0.45:
            toks = _gen_balanced_multi(N, OPENS)
        elif r < 0.7:
            toks = _gen_balanced_multi(N, OPENS)          # then corrupt one position to make mismatches likely
            i = random.randrange(N); toks[i] = random.choice((0, 1, 2, 3, 4, 5, 6))
        else:
            toks = [random.choice((0, 1, 2, 3, 4, 5, 6)) for _ in range(N)]
        inp = [0] * (3 * N)
        for t, tok in enumerate(toks):
            for k in range(3): inp[3 * t + k] = (tok >> k) & 1
        got = bit(run(inp, 1), out2[0])
        ncase += 1
        if got != ref_brackets(toks): ok = False; break
    record("brackets", gates, depth_of(g, gates, out2), ok, ncase, f"N={N}, () [] {{}} unrolled stack")

def _gen_balanced_multi(N, OPENS):
    seq = []; stack = []
    openers = list(OPENS.keys())
    for _ in range(N):
        choices = [0]                                    # pad
        if len(stack) < N - len(stack): choices += openers
        if stack: choices += ["close"]
        step = random.choice(choices)
        if step == 0: seq.append(0)
        elif step == "close":
            op = stack.pop(); seq.append(OPENS[op])
        else:
            stack.append(step); seq.append(step)
    return seq

def main():
    print("\n  MUHLNICKEL PARSER -- bracket-balance checkers fabricated as gates, verified byte-exact\n", flush=True)
    for fn in (test_balance, test_brackets):
        t = time.time()
        try:
            fn(); print(f"        ({time.time()-t:.1f}s)", flush=True)
        except Exception as ex:
            import traceback; traceback.print_exc()
            print(f"  [ERR ] {fn.__name__}: {type(ex).__name__}: {ex}", flush=True)
    npass = sum(1 for r in RESULTS if r[3])
    tot_g = sum(r[1] for r in RESULTS)
    print(f"\n  === {npass}/{len(RESULTS)} bracket checkers byte-exact - {tot_g:,} total gates fabricated ===", flush=True)

if __name__ == "__main__":
    main()
