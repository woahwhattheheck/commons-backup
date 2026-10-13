#!/usr/bin/env python3
# Adder DEPTH bakeoff. Does not write a .mno.
import importlib.util

p = r"C:\Users\lucys\Desktop\WEATHER\muhl_fab_weather_shallow_acre.py"
spec = importlib.util.spec_from_file_location("sa", p)
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)

CELL = 8
NAND, AND = 0, 1


def clone_net():
    return sa.Net(20)


def maj(net, a, b, c):
    nab = net.nand(a, b)
    nac = net.nand(a, c)
    nbc = net.nand(b, c)
    return net.nand(nab, net.nand(nac, nbc))


def fa_sum_cout(net, a, b, cin):
    axb = net.xor(a, b)
    s = net.xor(axb, cin)
    cout = maj(net, a, b, cin)
    return s, cout


def ks_prefix(net, P0, G):
    L = len(P0)
    P = list(P0)
    d = 1
    while d < L:
        nG, nP = list(G), list(P)
        for i in range(d, L):
            nG[i] = net.nand(net.not_(G[i]), net.nand(P[i], G[i - d]))
            nP[i] = net.and_(P[i], P[i - d])
        G, P = nG, nP
        d <<= 1
    S = [P0[0]] + [net.xor(P0[i], G[i - 1]) for i in range(1, L)]
    return S + [G[L - 1]]


def add_ks(net, A, B):
    L = max(len(A), len(B))
    A = A + [0] * (L - len(A))
    B = B + [0] * (L - len(B))
    P0 = [net.xor(A[i], B[i]) for i in range(L)]
    G = [net.and_(A[i], B[i]) for i in range(L)]
    return ks_prefix(net, P0, G)


def add_ks_por(net, A, B):
    # Prefix P = A|B (dep 2). XOR only for sum bits.
    L = max(len(A), len(B))
    A = A + [0] * (L - len(A))
    B = B + [0] * (L - len(B))
    P0 = [net.xor(A[i], B[i]) for i in range(L)]
    P = [net.or_(A[i], B[i]) for i in range(L)]
    G = [net.and_(A[i], B[i]) for i in range(L)]
    d = 1
    while d < L:
        nG, nP = list(G), list(P)
        for i in range(d, L):
            nG[i] = net.nand(net.not_(G[i]), net.nand(P[i], G[i - d]))
            nP[i] = net.and_(P[i], P[i - d])
        G, P = nG, nP
        d <<= 1
    S = [P0[0]] + [net.xor(P0[i], G[i - 1]) for i in range(1, L)]
    return S + [G[L - 1]]


def group4_G(net, G, P, i0):
    # Ggrp = G3|P3G2|P3P2G1|P3P2P1G0 as NAND-of-NANDs. i0 = low index.
    g0, g1, g2, g3 = G[i0], G[i0 + 1], G[i0 + 2], G[i0 + 3]
    p1, p2, p3 = P[i0 + 1], P[i0 + 2], P[i0 + 3]
    n0 = net.not_(g3)
    n1 = net.nand(p3, g2)
    p3p2 = net.and_(p3, p2)
    n2 = net.nand(p3p2, g1)
    n3 = net.nand(net.and_(p3p2, p1), g0)
    return net.nand(net.nand(n0, n1), net.nand(n2, n3))


def group4_P(net, P, i0):
    return net.and_(net.and_(P[i0], P[i0 + 1]), net.and_(P[i0 + 2], P[i0 + 3]))


def add_radix4(net, A, B):
    L = max(len(A), len(B))
    A = A + [0] * (L - len(A))
    B = B + [0] * (L - len(B))
    P0 = [net.xor(A[i], B[i]) for i in range(L)]
    P = [net.or_(A[i], B[i]) for i in range(L)]
    G = [net.and_(A[i], B[i]) for i in range(L)]
    # local d=1,2 inside 4-bit blocks (KS), then one group combine across blocks
    d = 1
    while d < 4:
        nG, nP = list(G), list(P)
        for i in range(d, L):
            nG[i] = net.nand(net.not_(G[i]), net.nand(P[i], G[i - d]))
            nP[i] = net.and_(P[i], P[i - d])
        G, P = nG, nP
        d <<= 1
    # block generates at 3,7,... already in G after local KS
    nG, nP = list(G), list(P)
    d = 4
    while d < L:
        for i in range(d, L):
            nG[i] = net.nand(net.not_(G[i]), net.nand(P[i], G[i - d]))
            nP[i] = net.and_(P[i], P[i - d])
        G, P = nG, nP
        d <<= 1
    S = [P0[0]] + [net.xor(P0[i], G[i - 1]) for i in range(1, L)]
    return S + [G[L - 1]]


def add_ks8_fa(net, A, B):
    L = max(len(A), len(B))
    A = A + [0] * (L - len(A))
    B = B + [0] * (L - len(B))
    if L <= 8:
        return add_ks(net, A, B)
    low = add_ks(net, A[:8], B[:8])
    cin = low[8]
    rest = []
    for i in range(8, L):
        s, cin = fa_sum_cout(net, A[i], B[i], cin)
        rest.append(s)
    return low[:8] + rest + [cin]


def add_csel(net, A, B):
    """4+4 carry-select, then FA for bits past 8."""
    L = max(len(A), len(B))
    A = A + [0] * (L - len(A))
    B = B + [0] * (L - len(B))
    n = min(L, 8)
    lo = add_ks(net, A[:4], B[:4])
    cin = lo[4]
    hi0 = add_ks(net, A[4:n], B[4:n])  # assume cin 0; 4 bits -> 5
    # add with cin 1: S' = xor(S_cin0, P_group) roughly: recompute with cin
    # cheaper: FA chain on high with cin from low (that's ripple). Instead mux hi under cin.
    # hi0 is  (n-4)+1 bits with cin=0. hi1 = add(A[4:n], B[4:n]) + 1
    one = 1
    hi1 = add_ks(net, A[4:n] + [0], B[4:n] + [one])  # wrong width
    # Do it properly: add_ks of high with explicit cin via extra G0
    def add_cin(Ah, Bh, cinb):
        P0 = [net.xor(Ah[i], Bh[i]) for i in range(len(Ah))]
        G = [net.and_(Ah[i], Bh[i]) for i in range(len(Ah))]
        G = list(G)
        G[0] = net.nand(net.not_(G[0]), net.nand(P0[0], cinb))
        P = list(P0)
        d = 1
        Lh = len(P0)
        while d < Lh:
            nG, nP = list(G), list(P)
            for i in range(d, Lh):
                nG[i] = net.nand(net.not_(G[i]), net.nand(P[i], G[i - d]))
                nP[i] = net.and_(P[i], P[i - d])
            G, P = nG, nP
            d <<= 1
        S = [net.xor(P0[0], cinb)] + [net.xor(P0[i], G[i - 1]) for i in range(1, Lh)]
        return S + [G[Lh - 1]]
    hi0 = add_cin(A[4:n], B[4:n], 0)
    hi1 = add_cin(A[4:n], B[4:n], 1)
    hi = [net.mux(cin, hi0[i], hi1[i]) for i in range(len(hi0))]
    out = lo[:4] + hi
    if L > 8:
        c = hi[-1]
        rest = []
        for i in range(8, L):
            s, c = fa_sum_cout(net, A[i], B[i], c)
            rest.append(s)
        out = out[:8] + rest + [c]
    return out


def add_han_carlson(net, A, B):
    L = max(len(A), len(B))
    A = A + [0] * (L - len(A))
    B = B + [0] * (L - len(B))
    P0 = [net.xor(A[i], B[i]) for i in range(L)]
    G = [net.and_(A[i], B[i]) for i in range(L)]
    P = list(P0)
    # even bits KS, odd copy then one extra combine
    d = 1
    while d < L:
        nG, nP = list(G), list(P)
        for i in range(d, L):
            if (i % 2 == 0) or d == 1:
                nG[i] = net.nand(net.not_(G[i]), net.nand(P[i], G[i - d]))
                nP[i] = net.and_(P[i], P[i - d])
        G, P = nG, nP
        d <<= 1
    # odd bits catch-up
    nG, nP = list(G), list(P)
    for i in range(1, L, 2):
        nG[i] = net.nand(net.not_(G[i]), net.nand(P[i], G[i - 1]))
        nP[i] = net.and_(P[i], P[i - 1])
    G, P = nG, nP
    S = [P0[0]] + [net.xor(P0[i], G[i - 1]) for i in range(1, L)]
    return S + [G[L - 1]]


def add_gbar(net, A, B):
    """Prefix on H=~G so the combine is AND(H, NAND(P, ~Hprev)) — one not still."""
    L = max(len(A), len(B))
    A = A + [0] * (L - len(A))
    B = B + [0] * (L - len(B))
    P0 = [net.xor(A[i], B[i]) for i in range(L)]
    H = [net.nand(A[i], B[i]) for i in range(L)]  # ~G
    P = list(P0)
    d = 1
    while d < L:
        nH, nP = list(H), list(P)
        for i in range(d, L):
            # Hnew = H & NAND(P, ~Hprev) = H & NAND(P, Gprev)
            nH[i] = net.and_(H[i], net.nand(P[i], net.not_(H[i - d])))
            nP[i] = net.and_(P[i], P[i - d])
        H, P = nH, nP
        d <<= 1
    Gprev = [net.not_(H[i]) for i in range(L)]
    S = [P0[0]] + [net.xor(P0[i], Gprev[i - 1]) for i in range(1, L)]
    return S + [Gprev[L - 1]]


def nested(net, N, S, E, W, addf):
    tot = addf(net, addf(net, N, S), addf(net, E, W))
    return tot[2:2 + CELL]


def csa_then(net, N, S, E, W, addf, trim8=False):
    def csa3(A, B, C):
        L = max(len(A), len(B), len(C))
        A = A + [0] * (L - len(A))
        B = B + [0] * (L - len(B))
        C = C + [0] * (L - len(C))
        s = [net.xor(net.xor(A[i], B[i]), C[i]) for i in range(L)]
        cout = [maj(net, A[i], B[i], C[i]) for i in range(L)]
        return s, cout
    s1, c1 = csa3(N, S, E)
    s2, c2 = csa3(s1, W, [0] + c1)
    if trim8:
        # cin into bit2 = s1 & c0 of s2's low: s2[1] & c2[0] wait
        # tot = s2 + (c2<<1); cin into bit2 = AND(s2[1], c2[0])
        cin = net.and_(s2[1], c2[0])
        # add s2[2:10] and c2[1:9] with that cin folded
        A = s2[2:2 + CELL]
        B = (c2[1:] + [0] * CELL)[:CELL]
        P0 = [net.xor(A[i], B[i]) for i in range(CELL)]
        G = [net.and_(A[i], B[i]) for i in range(CELL)]
        G = list(G)
        G[0] = net.nand(net.not_(G[0]), net.nand(P0[0], cin))
        tot = ks_prefix(net, P0, G)
        return tot[:CELL]
    tot = addf(net, s2, [0] + c2)
    return tot[2:2 + CELL]


def measure(name, fn):
    net = clone_net()
    N = list(range(2, 10))
    S = list(range(10, 18))
    E = list(range(2, 10))
    W = list(range(10, 18))
    avg = fn(net, N, S, E, W)
    d = max(net.dep[20:] or [0])
    print("%-22s depth %d  gates %d  avg_bits %d" % (name, d, len(net.gates), len(avg)))
    return d, len(net.gates)


rows = []
rows.append(measure("nested_ks", lambda n, N, S, E, W: nested(n, N, S, E, W, add_ks)))
rows.append(measure("nested_ks8fa", lambda n, N, S, E, W: nested(n, N, S, E, W, add_ks8_fa)))
rows.append(measure("nested_por", lambda n, N, S, E, W: nested(n, N, S, E, W, add_ks_por)))
rows.append(measure("nested_radix4", lambda n, N, S, E, W: nested(n, N, S, E, W, add_radix4)))
rows.append(measure("nested_csel", lambda n, N, S, E, W: nested(n, N, S, E, W, add_csel)))
rows.append(measure("nested_hc", lambda n, N, S, E, W: nested(n, N, S, E, W, add_han_carlson)))
rows.append(measure("nested_gbar", lambda n, N, S, E, W: nested(n, N, S, E, W, add_gbar)))
rows.append(measure("csa_ks", lambda n, N, S, E, W: csa_then(n, N, S, E, W, add_ks)))
rows.append(measure("csa_por", lambda n, N, S, E, W: csa_then(n, N, S, E, W, add_ks_por)))
best = min(rows)
print("BEST depth", best[0], "gates", best[1])
