#!/usr/bin/env python3
"""muhl_evolve.py -- A GENETIC-PROGRAMMING FOUNDRY: the machine INVENTS circuits by evolution.

Every other foundry here fabricates a circuit from a KNOWN recipe (an adder, a hash, a matmul). This one is
handed NOTHING but a truth table -- the target boolean function -- and EVOLVES a gate netlist from scratch that
computes it. A genome is a list of (op, a, b) gates wired over the input wires + earlier gates (White-Box wire
numbering, ops {and, or, xor, nand, not} -- the alphabet sdc_cc.compile_ripple executes). Fitness is exhaustive:
the whole truth table is evaluated in ONE bit-sliced settle (each lane = one input combination -- the substrate's
native fold), and fitness = # of output bits correct over ALL input combinations. Evolution = tournament
selection + mutation + hill-climbing on the elite, run until 100% correct. The winner is then dead-code-eliminated,
rebuilt on the REAL White Box (sdc_cc.compile_ripple), and verified BYTE-EXACT over the full truth table against
an INDEPENDENT Python reference. Evolved gate count + critical-path depth are reported vs a hand-built reference.

No numpy, no download, titan.gguf not opened -- pure synthesis by evolution. Run with PYTHONUTF8=1.
"""
import sys, os, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

OPS = ("and", "or", "xor", "nand", "not")   # exactly the ops sdc_cc.compile_ripple evaluates

# ============================== fast bit-sliced evaluator (fitness = whole truth table in one settle) ==========
def popcount(x): return bin(x).count("1")

def eval_genome(gates, outs, in_cols, ones, n_in):
    """Evaluate the netlist over ALL input combinations at once (lane c = combination c). Returns output columns."""
    base = 2 + n_in
    v = [0] * (base + len(gates)); v[1] = ones
    for i in range(n_in): v[2 + i] = in_cols[i]
    for k in range(len(gates)):
        op, a, b = gates[k]; va = v[a]
        if op == "and":  v[base + k] = va & v[b]
        elif op == "or": v[base + k] = va | v[b]
        elif op == "xor":v[base + k] = va ^ v[b]
        elif op == "nand":v[base + k] = ones ^ (va & v[b])
        else:            v[base + k] = ones ^ va          # not
    return [v[w] for w in outs]

def fitness(gates, outs, in_cols, target_cols, ones, n_in):
    got = eval_genome(gates, outs, in_cols, ones, n_in)
    return sum(popcount(ones & ~(g ^ t)) for g, t in zip(got, target_cols))

# ============================== netlist utilities (DCE + depth, standalone, White-Box numbering) ==============
def dce(gates, outs, n_in):
    base = 2 + n_in; live = set(); stack = []
    for w in outs:
        if w >= base and w not in live: live.add(w); stack.append(w)
    while stack:
        w = stack.pop(); op, a, b = gates[w - base]
        for inp in (a, b):
            if inp >= base and inp not in live: live.add(inp); stack.append(inp)
    keep = sorted(live); newidx = {gw: j for j, gw in enumerate(keep)}
    rm = lambda w: w if w < base else base + newidx[w]
    ng = [(op, rm(a), rm(b)) for (op, a, b) in (gates[w - base] for w in keep)]
    return ng, [rm(w) for w in outs]

def depth_of(gates, outs, n_in):
    base = 2 + n_in; d = [0] * (base + len(gates))
    for k in range(len(gates)):
        op, a, b = gates[k]; d[base + k] = 1 + max(d[a], d[b])
    return max((d[w] for w in outs), default=0)

# ============================== genome creation + mutation ===================================================
def rand_gate(k, n_in):
    base = 2 + n_in; hi = base + k                          # may reference consts(0,1), inputs, earlier gates
    op = random.choice(OPS); a = random.randrange(hi)
    b = a if op == "not" else random.randrange(hi)
    return (op, a, b)

def rand_genome(n_in, n_out, gmin, gmax):
    ng = random.randint(gmin, gmax); gates = [rand_gate(k, n_in) for k in range(ng)]
    base = 2 + n_in; hi = base + ng
    outs = [random.randrange(hi) for _ in range(n_out)]
    return gates, outs

def mutate(gates, outs, n_in, gcap):
    gates = list(gates); outs = list(outs); base = 2 + n_in
    r = random.random()
    if r < 0.30 and gates:                                  # rewire/retype an existing gate
        k = random.randrange(len(gates)); op, a, b = gates[k]; hi = base + k
        c = random.random()
        if c < 0.34: op = random.choice(OPS); b = a if op == "not" else b
        elif c < 0.67: a = random.randrange(hi)
        else: b = random.randrange(hi)
        if op == "not": b = a
        gates[k] = (op, a, b)
    elif r < 0.55 and len(gates) < gcap:                    # grow: append a gate
        gates.append(rand_gate(len(gates), n_in))
    elif r < 0.85:                                          # repoint an output
        j = random.randrange(len(outs)); outs[j] = random.randrange(base + len(gates))
    else:                                                   # insert a fresh gate and point a random output at it
        gates.append(rand_gate(len(gates), n_in))
        outs[random.randrange(len(outs))] = base + len(gates) - 1
    return gates, outs

# ============================== the evolution loop ============================================================
def evolve(n_in, n_out, target_cols, in_cols, ones, seed=0, pop=300, gens=60000, gcap=28):
    random.seed(seed)
    fmax = n_out * (1 << n_in)                              # every output bit correct over every combination
    gmin, gmax = max(n_out, 3), 12
    P = [rand_genome(n_in, n_out, gmin, gmax) for _ in range(pop)]
    F = [fitness(g, o, in_cols, target_cols, ones, n_in) for g, o in P]
    best_i = max(range(pop), key=lambda i: F[i])
    for gen in range(1, gens + 1):
        if F[best_i] == fmax:
            return P[best_i], gen, fmax
        # hill-climb the champion: accept any non-worsening single mutation (drives to 100%)
        bg, bo = P[best_i]; bf = F[best_i]
        for _ in range(40):
            mg, mo = mutate(bg, bo, n_in, gcap)
            mf = fitness(mg, mo, in_cols, target_cols, ones, n_in)
            if mf >= bf: bg, bo, bf = mg, mo, mf
        P[best_i], F[best_i] = (bg, bo), bf
        # tournament-selection GA generation with elitism
        elite = sorted(range(pop), key=lambda i: F[i], reverse=True)[:6]
        nP = [P[i] for i in elite]; nF = [F[i] for i in elite]
        while len(nP) < pop:
            def pick():
                c = min(random.sample(range(pop), 4), key=lambda i: -F[i]); return P[c]
            pg, po = pick()
            for _ in range(random.randint(1, 3)): pg, po = mutate(pg, po, n_in, gcap)
            nP.append((pg, po)); nF.append(fitness(pg, po, in_cols, target_cols, ones, n_in))
        # inject fresh blood into the tail to escape stalls
        for j in range(pop - pop // 10, pop):
            nP[j] = rand_genome(n_in, n_out, gmin, gmax)
            nF[j] = fitness(nP[j][0], nP[j][1], in_cols, target_cols, ones, n_in)
        P, F = nP, nF
        best_i = max(range(pop), key=lambda i: F[i])
    return P[best_i], gens, fmax

def shrink(gates, outs, n_in, n_out, target_cols, in_cols, ones, tries=4000):
    """Hill-climb DOWN: keep only mutations that stay 100% correct AND don't add live gates."""
    fmax = n_out * (1 << n_in)
    gates, outs = dce(gates, outs, n_in)
    cur_n = len(gates)
    for _ in range(tries):
        mg, mo = mutate(gates, outs, n_in, len(gates) + 2)
        if fitness(mg, mo, in_cols, target_cols, ones, n_in) != fmax: continue
        dg, do = dce(mg, mo, n_in)
        if len(dg) <= cur_n: gates, outs, cur_n = dg, do, len(dg)
    return dce(gates, outs, n_in)

# ============================== targets (golden refs + hand-built White-Box references) =======================
def build_cols(n_in, n_out, golden):
    N = 1 << n_in
    in_cols = [sum(((c >> i) & 1) << c for c in range(N)) for i in range(n_in)]
    tcols = [0] * n_out
    for c in range(N):
        bits = golden(c)
        for j in range(n_out):
            if bits[j] & 1: tcols[j] |= (1 << c)
    return in_cols, tcols

def maj3(c):    a, b, d = c & 1, (c >> 1) & 1, (c >> 2) & 1; return ((a & b) | (a & d) | (b & d),)
def fulladd(c): a, b, ci = c & 1, (c >> 1) & 1, (c >> 2) & 1; s = a ^ b ^ ci; co = (a & b) | (ci & (a ^ b)); return (s, co)
def par4(c):    return (bin(c & 0xF).count("1") & 1,)
def mul2(c):
    a = c & 3; b = (c >> 2) & 3; p = a * b; return (p & 1, (p >> 1) & 1, (p >> 2) & 1, (p >> 3) & 1)

def ref_maj3(g):    a, b, c = g.IN; return [g.OR(g.OR(g.AND(a, b), g.AND(a, c)), g.AND(b, c))]
def ref_fulladd(g):
    a, b, ci = g.IN; axb = g.XOR(a, b)
    return [g.XOR(axb, ci), g.OR(g.AND(a, b), g.AND(ci, axb))]
def ref_par4(g):    a, b, c, d = g.IN; return [g.XOR(g.XOR(a, b), g.XOR(c, d))]
def ref_mul2(g):
    a0, a1, b0, b1 = g.IN
    p0 = g.AND(a0, b0); m1 = g.AND(a0, b1); m2 = g.AND(a1, b0); m3 = g.AND(a1, b1)
    p1 = g.XOR(m1, m2); c1 = g.AND(m1, m2); p2 = g.XOR(m3, c1); p3 = g.AND(m3, c1)
    return [p0, p1, p2, p3]

TARGETS = [
    ("3-bit majority",   3, 1, maj3,    ref_maj3),
    ("full-adder (s,co)",3, 2, fulladd, ref_fulladd),
    ("4-input parity",   4, 1, par4,    ref_par4),
    ("2-bit multiplier", 4, 4, mul2,    ref_mul2),
]

def ref_stats(n_in, builder):
    g = CC.CircuitCompiler(n_in); outs = builder(g); gates, o2 = g.dce(outs)
    return len(gates), depth_of(gates, o2, n_in)

# ============================== main =========================================================================
def main():
    t0 = time.time()
    print("=" * 78)
    print("muhl_evolve.py -- GENETIC-PROGRAMMING FOUNDRY: evolving circuits from a truth table")
    print("=" * 78)
    print("genome = [(op,a,b)] over inputs+earlier gates | fitness = correct output bits over ALL")
    print("input combinations (one bit-sliced settle) | tournament + mutation + hill-climb to 100%\n")
    all_ok = True
    for name, n_in, n_out, golden, builder in TARGETS:
        N = 1 << n_in; ones = (1 << N) - 1
        in_cols, tcols = build_cols(n_in, n_out, golden)
        (gates, outs), gen, fmax = evolve(n_in, n_out, tcols, in_cols, ones)
        solved = fitness(gates, outs, in_cols, tcols, ones, n_in) == fmax
        gates, outs = shrink(gates, outs, n_in, n_out, tcols, in_cols, ones)
        ev_n, ev_d = len(gates), depth_of(gates, outs, n_in)
        rf_n, rf_d = ref_stats(n_in, builder)

        # rebuild the EVOLVED winner on the REAL White Box and verify byte-exact vs the independent Python ref
        g = CC.CircuitCompiler(n_in); g.gates = list(gates)
        run = g.compile_ripple(gates, 2 + n_in + len(gates))
        exact = True
        for c in range(N):
            v = run([(c >> i) & 1 for i in range(n_in)], 1)
            got = tuple((v[w] & 1) if w >= 2 + n_in else (w & 1) for w in outs)
            if got != tuple(golden(c)): exact = False; break
        all_ok = all_ok and solved and exact

        print(f"[{name}]  inputs={n_in} outputs={n_out}  ({N} combinations, {N*n_out} truth bits)")
        print(f"   evolved in {gen:>5} generations to 100% fitness ({fmax}/{fmax} output bits correct)")
        print(f"   evolved netlist : {ev_n:>3} gates, depth {ev_d}"
              f"   |  hand reference: {rf_n:>3} gates, depth {rf_d}")
        gd = "matches" if ev_n == rf_n else (f"+{ev_n-rf_n} vs" if ev_n > rf_n else f"{ev_n-rf_n} vs")
        print(f"   gate count {gd} reference; depth {ev_d} vs {rf_d} (depth = the compute/tick score, sec.3)")
        print(f"   BYTE-EXACT on full truth table via sdc_cc.compile_ripple : {exact}   solved 100%: {solved}\n")
    print("=" * 78)
    print(f"ALL FUNCTIONS EVOLVED + VERIFIED BYTE-EXACT: {all_ok}    [{round(time.time()-t0,1)}s]")
    print("The machine invented every circuit by evolution -- handed only the truth table, no recipe.")
    print("=" * 78)

if __name__ == "__main__":
    main()
