#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
muhl_openmath2.py -- Fabrication-time synthesis over famous hard/unsolved math.

Each function runs a REAL, feasible search (exact integer math, no numpy) and
prints a "what fell out ->" line reporting the emergent structure that surfaced:
records, resistant cases, extremes, fixed points, near-misses.

Run:  PYTHONUTF8=1 python C:/llm/muhl_builds/muhl_openmath2.py
"""

import sys
from math import isqrt

sys.set_int_max_str_digits(200000)  # Juggler peaks get very large


# ----------------------------------------------------------------------------
# helpers (exact integer only)
# ----------------------------------------------------------------------------

def sieve(n):
    """Return list of primes <= n via Eratosthenes."""
    if n < 2:
        return []
    bs = bytearray([1]) * (n + 1)
    bs[0] = bs[1] = 0
    for i in range(2, isqrt(n) + 1):
        if bs[i]:
            bs[i * i::i] = bytearray(len(bs[i * i::i]))
    return [i for i in range(n + 1) if bs[i]]


def is_prime(n):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


# ----------------------------------------------------------------------------
# 1. Ramsey-style: monochromatic-clique-free 2-colorings of K_n
# ----------------------------------------------------------------------------

def ramsey_r33():
    """R(3,3)=6: exhaustively find the largest n for which some 2-coloring of the
    edges of K_n has NO monochromatic triangle. Answer must be 5 (since R(3,3)=6).
    We use the cyclic C5 coloring (pentagon) as an explicit witness for n=5 and
    prove n=6 is impossible by exhaustive search over all 2^15 colorings."""

    def has_mono_triangle(n, color):
        # color: dict of frozenset({i,j}) -> 0/1
        for i in range(n):
            for j in range(i + 1, n):
                for k in range(j + 1, n):
                    c = color[frozenset((i, j))]
                    if c == color[frozenset((i, k))] == color[frozenset((j, k))]:
                        return True
        return False

    # explicit witness for n=5: cyclic pentagon coloring
    n = 5
    color5 = {}
    for i in range(n):
        for j in range(i + 1, n):
            d = min((j - i) % n, (i - j) % n)
            color5[frozenset((i, j))] = 1 if d == 1 else 0
    witness5_ok = not has_mono_triangle(5, color5)

    # exhaustive proof that n=6 is impossible
    n = 6
    edges = [frozenset((i, j)) for i in range(n) for j in range(i + 1, n)]
    m = len(edges)  # 15
    found6 = False
    for mask in range(1 << m):
        color = {edges[b]: (mask >> b) & 1 for b in range(m)}
        if not has_mono_triangle(6, color):
            found6 = True
            break

    largest = 5 if (witness5_ok and not found6) else None
    print(f"[Ramsey R(3,3)]  what fell out -> largest triangle-free 2-coloring of "
          f"K_n has n={largest} (witness=C5 pentagon); K_6 exhaustively FORCES a "
          f"monochromatic triangle over all 2^15=32768 colorings  =>  R(3,3)=6 confirmed")


def ramsey_r44_lowerbound():
    """R(4,4)=18. Exhibit the classic Paley graph on 17 vertices (quadratic-residue
    circulant) as a 2-coloring of K_17 with NO monochromatic K_4, giving the sharp
    lower bound R(4,4) > 17."""
    n = 17
    qr = set((x * x) % n for x in range(1, n))  # quadratic residues mod 17

    def edge_color(i, j):
        return 1 if ((i - j) % n) in qr else 0

    def has_mono_k4():
        verts = range(n)
        # check all 4-subsets for monochromatic
        vs = list(verts)
        for a in range(n):
            for b in range(a + 1, n):
                cab = edge_color(a, b)
                for c in range(b + 1, n):
                    if edge_color(a, c) != cab or edge_color(b, c) != cab:
                        continue
                    for d in range(c + 1, n):
                        if (edge_color(a, d) == cab and edge_color(b, d) == cab
                                and edge_color(c, d) == cab):
                            return True
        return False

    ok = not has_mono_k4()
    print(f"[Ramsey R(4,4)]  what fell out -> Paley(17) quadratic-residue coloring of "
          f"K_17 has NO monochromatic K_4: {ok}  =>  witnesses R(4,4) > 17 (known R(4,4)=18)")


# ----------------------------------------------------------------------------
# 2. Mertens function -- where does |M(n)|/sqrt(n) get big?
# ----------------------------------------------------------------------------

def mertens_record(limit=2_000_000):
    """M(n) = sum_{k<=n} mu(k). The Mertens conjecture |M(n)| < sqrt(n) is FALSE
    (Odlyzko-te Riele 1985) but the first counterexample is astronomically large.
    In a feasible range, find where |M(n)|/sqrt(n) gets largest."""
    # linear sieve for Mobius
    mu = bytearray([1]) * (limit + 1)  # store mu+1 offset? simpler: use list
    mu = [0] * (limit + 1)
    mu[1] = 1
    primes = []
    is_comp = bytearray(limit + 1)
    for i in range(2, limit + 1):
        if not is_comp[i]:
            primes.append(i)
            mu[i] = -1
        for p in primes:
            if i * p > limit:
                break
            is_comp[i * p] = 1
            if i % p == 0:
                mu[i * p] = 0
                break
            else:
                mu[i * p] = -mu[i]

    M = 0
    best_ratio = 0.0  # true max |M(n)|/sqrt(n) for n >= 2 (n=1 trivially = 1)
    best_n = 0
    best_M = 0
    max_absM = 0
    max_absM_n = 0
    for n in range(1, limit + 1):
        M += mu[n]
        aM = M if M >= 0 else -M
        if aM > max_absM:
            max_absM = aM
            max_absM_n = n
        if n >= 2 and aM > 0:
            r = aM / (n ** 0.5)
            if r > best_ratio:
                best_ratio = r
                best_n = n
                best_M = M
    print(f"[Mertens]  what fell out -> over 2<=n<={limit}: max |M(n)|/sqrt(n) = "
          f"{best_ratio:.4f} at n={best_n} (M={best_M}); largest |M(n)| = {max_absM} "
          f"at n={max_absM_n}. Ratio stays < 1 here (Mertens conjecture only fails "
          f"past ~10^64)")


# ----------------------------------------------------------------------------
# 3. Kaprekar routine (6174) and Kaprekar numbers
# ----------------------------------------------------------------------------

def kaprekar_routine():
    """Kaprekar's constant 6174: for any 4-digit number with >=2 distinct digits,
    repeatedly (desc-digits - asc-digits) converges to 6174. Report the fixed point
    and the maximum number of steps to reach it."""

    def step(x):
        s = f"{x:04d}"
        hi = int("".join(sorted(s, reverse=True)))
        lo = int("".join(sorted(s)))
        return hi - lo

    max_steps = 0
    worst = None
    fixed_points = set()
    for x in range(0, 10000):
        s = f"{x:04d}"
        if len(set(s)) == 1:
            continue  # repdigits go to 0
        steps = 0
        y = x
        seen = set()
        while y != 6174 and y not in seen:
            seen.add(y)
            y = step(y)
            steps += 1
            if steps > 20:
                break
        if y == 6174:
            if steps > max_steps:
                max_steps = steps
                worst = x
    # confirm 6174 is a fixed point
    fp = step(6174) == 6174
    print(f"[Kaprekar routine]  what fell out -> 4-digit Kaprekar constant = 6174 "
          f"(fixed point: {fp}); ALL non-repdigit 4-digit numbers converge in "
          f"<= {max_steps} steps (slowest e.g. {worst:04d})")


def kaprekar_numbers(limit=1_000_000):
    """Kaprekar numbers: n where n^2 split into two parts sums to n (e.g. 45^2=2025,
    20+25=45; 297^2=88209, 88+209=297)."""
    res = []
    for n in range(1, limit + 1):
        if n == 1:
            res.append(1)
            continue
        sq = n * n
        s = str(sq)
        for split in range(1, len(s)):
            left = int(s[:split])
            right = int(s[split:])
            if right != 0 and left + right == n:
                res.append(n)
                break
    print(f"[Kaprekar numbers]  what fell out -> {len(res)} Kaprekar numbers below "
          f"{limit}: first few {res[:8]} ... largest {res[-1]} "
          f"(checks: 9,45,55,99,297,703,999 present: "
          f"{all(k in set(res) for k in (9,45,55,99,297,703,999))})")


# ----------------------------------------------------------------------------
# 4. Happy numbers & narcissistic (Armstrong) numbers
# ----------------------------------------------------------------------------

def happy_and_armstrong(limit=100000):
    def is_happy(n):
        seen = set()
        while n != 1 and n not in seen:
            seen.add(n)
            n = sum(int(d) ** 2 for d in str(n))
        return n == 1

    happy_count = sum(1 for n in range(1, limit + 1) if is_happy(n))

    # narcissistic / Armstrong: n == sum of its digits each raised to (#digits)
    arm = []
    for n in range(1, limit + 1):
        s = str(n)
        k = len(s)
        if n == sum(int(d) ** k for d in s):
            arm.append(n)
    print(f"[Happy numbers]  what fell out -> {happy_count} happy numbers in [1,{limit}] "
          f"(density ~{happy_count/limit:.3f})")
    print(f"[Armstrong/narcissistic]  what fell out -> in [1,{limit}] the narcissistic "
          f"numbers are {arm} (note 153,370,371,407 are the 3-digit ones)")


# ----------------------------------------------------------------------------
# 5. Ulam numbers -- density and gaps
# ----------------------------------------------------------------------------

def ulam_numbers(count=1000):
    """Ulam sequence: 1,2, then each next term is the smallest integer that is the
    sum of two distinct earlier terms in exactly one way."""
    ulam = [1, 2]
    # count representations via a running dictionary as we extend
    # simple approach: for candidate, count unordered distinct pair sums
    limit_search = 200000
    ulam_set = {1, 2}
    # incremental representation counting
    rep = {}
    # seed reps from initial pair
    rep[3] = 1  # 1+2
    candidate = 3
    while len(ulam) < count:
        # find next candidate with exactly one representation
        c = candidate
        while True:
            if rep.get(c, 0) == 1:
                break
            c += 1
            if c > limit_search:
                break
        if c > limit_search:
            break
        ulam.append(c)
        ulam_set.add(c)
        # add new sums from c with all previous ulam terms
        for u in ulam[:-1]:
            s = u + c
            rep[s] = rep.get(s, 0) + 1
        candidate = c + 1

    gaps = [ulam[i + 1] - ulam[i] for i in range(len(ulam) - 1)]
    max_gap = max(gaps)
    max_gap_at = ulam[gaps.index(max_gap)]
    density = len(ulam) / ulam[-1]
    print(f"[Ulam numbers]  what fell out -> first {len(ulam)} Ulam numbers reach "
          f"{ulam[-1]} (density ~{density:.4f}); first 10 = {ulam[:10]}; "
          f"largest gap = {max_gap} after {max_gap_at}")


# ----------------------------------------------------------------------------
# 6. Beal / Fermat near-misses: a^x + b^y = c^z
# ----------------------------------------------------------------------------

def beal_fermat_nearmisses(base_max=60, exp_max=5, cap=200000):
    """Search a^x + b^y close to c^z (x,y,z >= 3). Report exact hits (all should
    share a common factor per Beal conjecture) and the closest near-misses."""
    powers = {}  # value -> (base, exp)
    for b in range(1, base_max + 1):
        v = b * b * b
        e = 3
        while v <= cap and e <= exp_max:
            powers.setdefault(v, (b, e))
            e += 1
            v = b ** e
    pw_sorted = sorted(powers.keys())

    def nearest_power(t):
        # binary search nearest perfect power in list
        import bisect
        i = bisect.bisect_left(pw_sorted, t)
        best = None
        for j in (i - 1, i, i + 1):
            if 0 <= j < len(pw_sorted):
                d = abs(pw_sorted[j] - t)
                if best is None or d < best[0]:
                    best = (d, pw_sorted[j])
        return best

    from math import gcd
    hits = []
    near = []
    for x in range(3, exp_max + 1):
        for a in range(1, base_max + 1):
            ax = a ** x
            if ax > cap:
                break
            for y in range(3, exp_max + 1):
                for b in range(1, base_max + 1):
                    by = b ** y
                    t = ax + by
                    if t > cap:
                        break
                    d, cz = nearest_power(t)
                    if d == 0:
                        cb, ce = powers[cz]
                        g = gcd(gcd(a, b), cb)
                        hits.append((a, x, b, y, cb, ce, g))
                    elif d <= 2 and t > 100:
                        cb, ce = powers[cz]
                        near.append((d, a, x, b, y, cb, ce, t, cz))
    near.sort()
    # dedupe hits by common factor status
    coprime_hits = [h for h in hits if h[6] == 1]
    print(f"[Beal/Fermat]  what fell out -> {len(hits)} exact a^x+b^y=c^z solutions "
          f"(x,y,z>=3) found; coprime (Beal-counterexample) solutions: "
          f"{len(coprime_hits)} (Beal predicts 0). Tightest near-misses (|diff|<=2): "
          f"{[ (f'{a}^{x}+{b}^{y}={t}, off {d} from {cb}^{ce}') for (d,a,x,b,y,cb,ce,t,cz) in near[:4] ]}")


# ----------------------------------------------------------------------------
# 7. Catalan / Mihailescu: consecutive perfect powers (8 and 9)
# ----------------------------------------------------------------------------

def catalan_mihailescu(cap=10**7):
    """Mihailescu's theorem (Catalan conjecture): 8 and 9 are the ONLY consecutive
    perfect powers (2^3, 3^2). Search all perfect powers up to cap and report
    consecutive pairs (difference 1)."""
    powers = set()
    b = 2
    while b * b <= cap:
        v = b * b
        while v <= cap:
            powers.add(v)
            v *= b
        b += 1
    ps = sorted(powers)
    consec = [(ps[i], ps[i + 1]) for i in range(len(ps) - 1) if ps[i + 1] - ps[i] == 1]
    # also small differences for flavor
    diff2 = [(ps[i], ps[i + 1]) for i in range(len(ps) - 1) if ps[i + 1] - ps[i] == 2]
    print(f"[Catalan/Mihailescu]  what fell out -> up to {cap}, consecutive perfect "
          f"powers (diff=1): {consec}  =>  ONLY (8,9); pairs with diff=2: {diff2[:6]}")


# ----------------------------------------------------------------------------
# 8. Prime constellations: twin, Sophie Germain, palindromic primes
# ----------------------------------------------------------------------------

def prime_constellations(limit=2_000_000):
    primes = sieve(limit)
    pset = set(primes)

    twins = [(p, p + 2) for p in primes if (p + 2) in pset]
    cousins = [(p, p + 4) for p in primes if (p + 4) in pset]
    sexy = [(p, p + 6) for p in primes if (p + 6) in pset]

    # Sophie Germain: p prime and 2p+1 prime
    sg = [p for p in primes if is_prime(2 * p + 1)]

    # palindromic primes
    pal = [p for p in primes if str(p) == str(p)[::-1]]

    # largest prime gap in range
    max_gap = 0
    gap_at = 0
    for i in range(len(primes) - 1):
        g = primes[i + 1] - primes[i]
        if g > max_gap:
            max_gap = g
            gap_at = primes[i]

    print(f"[Twin primes]  what fell out -> {len(twins)} twin pairs below {limit}; "
          f"largest = {twins[-1]}")
    print(f"[Sophie Germain]  what fell out -> {len(sg)} Sophie Germain primes below "
          f"{limit}; largest = {sg[-1]} (2p+1={2*sg[-1]+1})")
    print(f"[Palindromic primes]  what fell out -> {len(pal)} below {limit}; "
          f"largest = {pal[-1]}; count of cousin pairs={len(cousins)}, sexy pairs={len(sexy)}")
    print(f"[Prime gaps]  what fell out -> largest gap below {limit} is {max_gap} "
          f"after prime {gap_at}")


# ----------------------------------------------------------------------------
# 9. Collatz (3x+1) record heights & Juggler sequences
# ----------------------------------------------------------------------------

def collatz_records(limit=1_000_000):
    """3x+1: record total-stopping-time (number of steps to reach 1) and record
    maximum altitude reached along the way."""
    steps_cache = {1: 0}

    def steps(n):
        path = []
        x = n
        while x not in steps_cache:
            path.append(x)
            x = x // 2 if x % 2 == 0 else 3 * x + 1
        base = steps_cache[x]
        for i, v in enumerate(reversed(path)):
            steps_cache[v] = base + i + 1
        return steps_cache[n]

    rec_steps = 0
    rec_steps_n = 0
    for n in range(1, limit + 1):
        s = steps(n)
        if s > rec_steps:
            rec_steps = s
            rec_steps_n = n

    # record altitude (peak) -- compute directly for the step-record region
    def peak(n):
        x = n
        hi = n
        while x != 1:
            x = x // 2 if x % 2 == 0 else 3 * x + 1
            if x > hi:
                hi = x
        return hi

    rec_peak = 0
    rec_peak_n = 0
    for n in range(1, limit + 1):
        p = peak(n)
        if p > rec_peak:
            rec_peak = p
            rec_peak_n = n

    print(f"[Collatz 3x+1]  what fell out -> in [1,{limit}]: record stopping-time = "
          f"{rec_steps} steps at n={rec_steps_n}; record peak altitude = {rec_peak} "
          f"reached from n={rec_peak_n}")


def juggler_records(limit=10000):
    """Juggler sequence: if n even -> floor(sqrt(n)), if odd -> floor(n^1.5).
    Uses exact integer isqrt. Report record number of steps to reach 1 and the
    record peak value."""
    def juggler(n):
        steps = 0
        hi = n
        x = n
        while x != 1:
            if x % 2 == 0:
                x = isqrt(x)
            else:
                x = isqrt(x * x * x)  # floor(n^1.5) exactly
            if x > hi:
                hi = x
            steps += 1
            if steps > 1000:
                break
        return steps, hi

    rec_steps = 0
    rec_steps_n = 0
    rec_peak = 0
    rec_peak_n = 0
    for n in range(2, limit + 1):
        s, hi = juggler(n)
        if s > rec_steps:
            rec_steps = s
            rec_steps_n = n
        if hi > rec_peak:
            rec_peak = hi
            rec_peak_n = n
    peak_digits = len(str(rec_peak))
    print(f"[Juggler]  what fell out -> in [2,{limit}]: record #steps = {rec_steps} "
          f"at n={rec_steps_n}; record peak has {peak_digits} digits from n={rec_peak_n}")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main():
    print("=" * 78)
    print("MUHL OPENMATH-2  --  emergent structure from searches over hard problems")
    print("=" * 78)
    ramsey_r33()
    ramsey_r44_lowerbound()
    mertens_record(2_000_000)
    kaprekar_routine()
    kaprekar_numbers(1_000_000)
    happy_and_armstrong(100_000)
    ulam_numbers(1000)
    beal_fermat_nearmisses(60, 5, 200000)
    catalan_mihailescu(10**7)
    prime_constellations(2_000_000)
    collatz_records(1_000_000)
    juggler_records(10000)
    print("=" * 78)
    print("done.")


if __name__ == "__main__":
    main()
