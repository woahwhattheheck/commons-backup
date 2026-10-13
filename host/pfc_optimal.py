#!/usr/bin/env python3
"""host/pfc_optimal.py — THE OPTIMAL-IMPLEMENTATION SELECTOR (owner 07-19: "the same problem can be solved with multiple
implementations, pfc should always choose the most optimal").

A smarter fabricator: for a function, it takes several candidate circuit implementations, VERIFIES they're all
byte-exact equivalent, MEASURES each (gates after fold/CSE/DCE, and critical-path depth), and picks the OPTIMAL — fewest
gates (throughput is gate-count-bound on the bit-slice engine; depth reported as the tiebreaker / FPGA metric). This is
how every future bake gets the leanest circuit automatically, instead of me hand-choosing.

  python host/pfc_optimal.py
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC


def depth(gates, n_in):
    base = 2 + n_in; dep = [0] * len(gates)
    dof = lambda w: dep[w - base] if w >= base else 0
    for k, (op, a, b) in enumerate(gates): dep[k] = 1 + max(dof(a), dof(b))
    return max(dep) if dep else 0


def select(fname, n_in, n_out, candidates, ref_fn, ntest=300):
    """build + DCE each candidate, verify all equal ref, measure gates+depth, pick fewest gates."""
    built = []
    for cname, builder in candidates:
        g = CC.CircuitCompiler(n_in); outs = builder(g)
        gates, out2 = g.dce(outs); built.append((cname, g, gates, out2, len(gates), depth(gates, n_in)))
    random.seed(hash(fname) & 0xffff)
    for _ in range(ntest):
        x = random.getrandbits(n_in); expect = ref_fn(x)
        for cname, g, gates, out2, ng, dp in built:
            v = CC.ripple_typed(g, gates, 2 + n_in + len(gates), [(x >> i) & 1 for i in range(n_in)], 1)
            got = sum((v[out2[j]] if out2[j] >= 2 else out2[j]) << j for j in range(n_out))
            if got != expect:
                print(f"  {fname}: candidate '{cname}' NOT equivalent — skipping this function."); return None
    winner = min(built, key=lambda r: r[4])
    print(f"  {fname} ({len(candidates)} implementations, all byte-exact equivalent):", flush=True)
    for cname, g, gates, out2, ng, dp in built:
        mark = "  <= OPTIMAL" if cname == winner[0] else ""
        print(f"     {cname:<22} {ng:>5} gates   depth {dp:>3}{mark}", flush=True)
    best = winner[4]; worst = max(r[4] for r in built)
    print(f"     => Muhlnickel picks '{winner[0]}' ({best} gates); saves {worst-best} gates ({100*(worst-best)/worst:.0f}%) vs the naive impl.\n", flush=True)
    return winner


# ===== candidate implementations (same function, different circuits) =====
def ch_naive(g):   e, f, gg = g.IN[:32], g.IN[32:64], g.IN[64:96]; return [g.XOR(g.AND(e[j], f[j]), g.AND(g.NOT(e[j]), gg[j])) for j in range(32)]
def ch_min(g):     e, f, gg = g.IN[:32], g.IN[32:64], g.IN[64:96]; return [g.XOR(gg[j], g.AND(e[j], g.XOR(f[j], gg[j]))) for j in range(32)]
def maj_naive(g):  a, b, c = g.IN[:32], g.IN[32:64], g.IN[64:96]; return [g.XOR(g.XOR(g.AND(a[j], b[j]), g.AND(a[j], c[j])), g.AND(b[j], c[j])) for j in range(32)]
def maj_min(g):    a, b, c = g.IN[:32], g.IN[32:64], g.IN[64:96]; return [g.OR(g.AND(a[j], b[j]), g.AND(c[j], g.XOR(a[j], b[j]))) for j in range(32)]

def pop_chain(g):  # popcount of 8 bits, naive: sum via chained 4-bit adds
    x = g.IN[:8]; s = [g.C0] * 4
    for b in x: s = CC.add32(g, s + [g.C0] * 28, [b] + [g.C0] * 31)[:4]
    return s
def pop_tree(g):   # popcount of 8 bits, tree: (a+b)+(c+d) ... balanced
    x = list(g.IN[:8])
    def add(p, q): return CC.add32(g, p + [g.C0] * (32 - len(p)), q + [g.C0] * (32 - len(q)))[:max(len(p), len(q)) + 1]
    pairs = [add([x[i]], [x[i + 1]]) for i in range(0, 8, 2)]      # 4 x 2-bit
    q1 = add(pairs[0], pairs[1]); q2 = add(pairs[2], pairs[3])     # 2 x 3-bit
    return (add(q1, q2) + [g.C0] * 4)[:4]                          # 4-bit


def main():
    print("Muhlnickel OPTIMAL-IMPLEMENTATION SELECTOR — same function, multiple circuits, pick the leanest.\n", flush=True)
    def ch_ref(x):
        e, f, gg = x & 0xffffffff, (x >> 32) & 0xffffffff, (x >> 64) & 0xffffffff
        return (e & f) ^ ((~e & 0xffffffff) & gg)
    def maj_ref(x):
        a, b, c = x & 0xffffffff, (x >> 32) & 0xffffffff, (x >> 64) & 0xffffffff
        return (a & b) ^ (a & c) ^ (b & c)
    select("SHA ch(e,f,g)", 96, 32, [("naive (e&f)^(~e&g)", ch_naive), ("minimal g^(e&(f^g))", ch_min)], ch_ref)
    select("SHA maj(a,b,c)", 96, 32, [("naive 3-AND-2-XOR", maj_naive), ("minimal (a&b)|(c&(a^b))", maj_min)], maj_ref)
    select("popcount(8)", 8, 4, [("naive chained adds", pop_chain), ("balanced tree", pop_tree)], lambda x: bin(x & 0xff).count("1"))

    print("  => the selector is the fabricator picking the optimal implementation, measured. Every future bake (AES,", flush=True)
    print("     bignum, wider ALU) routes through this so the Muhlnickel always stores the leanest circuit for the job.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
