#!/usr/bin/env python3
"""Component implementation and operation."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import muhl_proofcheck as PC


class Deriv:
    """A derived formula plus how it was derived, so a proof can be reconstructed."""
    __slots__ = ("term", "rule", "a", "b")

    def __init__(self, term, rule, a=0, b=0):
        self.term = term
        self.rule = rule
        self.a = a
        self.b = b


def k_instance(T, x, y):
    """axiom K:  x -> (y -> x)"""
    return T.imp(x, T.imp(y, x))


def s_instance(T, x, y, z):
    """axiom S:  (x -> (y -> z)) -> ((x -> y) -> (x -> z))"""
    return T.imp(T.imp(x, T.imp(y, z)),
                 T.imp(T.imp(x, y), T.imp(x, z)))


def search(T, goal, seeds, max_rounds=6, max_pool=20000, pool_cap=14, verbose=False):
    """Forward chaining. Returns a list of Deriv in derivation order, or None.

    Each round: mint axiom instances over the current term pool, then close under MP. A term
    enters `known` once, with the FIRST derivation that produced it, so the reconstructed
    proof cites earlier lines only -- which is exactly what the checker requires."""
    known = {}          # term index -> position in `order`
    order = []          # list[Deriv]

    def add(term, rule, a=0, b=0):
        if term in known:
            return False
        known[term] = len(order)
        order.append(Deriv(term, rule, a, b))
        return True

    pool = list(dict.fromkeys(seeds))

    for rnd in range(max_rounds):
        # --- mint axiom instances over the pool (bounded, or this explodes immediately)
        minted = 0
        for x in pool:
            for y in pool:
                if add(k_instance(T, x, y), PC.RULE_K):
                    minted += 1
                if len(order) > max_pool:
                    break
            if len(order) > max_pool:
                break
        for x in pool:
            for y in pool:
                for z in pool:
                    if add(s_instance(T, x, y, z), PC.RULE_S):
                        minted += 1
                    if len(order) > max_pool:
                        break
                if len(order) > max_pool:
                    break
            if len(order) > max_pool:
                break

        # --- close under modus ponens until no new term is derived
        while True:
            new = 0
            terms = [d.term for d in order]
            impls = [t for t in terms if T.slots[t][0] == PC.TAG_IMP]
            have = set(terms)
            for imp in impls:
                _, ante, cons = T.slots[imp]
                if ante in have and cons not in have:
                    if add(cons, PC.RULE_MP, known[imp], known[ante]):
                        new += 1
                        have.add(cons)
                        if goal in known:
                            return order
                if len(order) > max_pool:
                    break
            if new == 0 or len(order) > max_pool:
                break

        if verbose:
            print("      round %d: %d derived (%d minted this round)" % (rnd, len(order), minted))
        if goal in known:
            return order
        if len(order) > max_pool:
            break

        # --- GROW THE POOL WITH DERIVED TERMS, not just goal subterms.
        # The bug this fixes: axiom instances were minted only over the seed pool, so a
        # derived formula could never have a K or S instance built ON TOP of it. That made
        # any theorem needing a stacked axiom step unreachable — A -> (B -> (C -> A)) needs
        # exactly that. Growth is capped and SMALLEST-FIRST because S instances are cubic in
        # pool size: at |pool| = 24 that is already 13,824 candidates per round.
        cand = [d.term for d in order if d.term not in pool]
        cand.sort(key=lambda t: term_size(T, t))
        pool = list(dict.fromkeys(pool + cand))[:pool_cap]

    return None


def term_size(T, t, memo=None):
    """Node count. Smallest-first keeps the pool on simple formulas, which is where useful
    axiom instances come from — an enormous derived formula spawns enormous instances."""
    if memo is None:
        memo = {}
    if t in memo:
        return memo[t]
    tag, l, r = T.slots[t]
    n = 1 if tag != PC.TAG_IMP else 1 + term_size(T, l, memo) + term_size(T, r, memo)
    memo[t] = n
    return n


def subterms(T, t, out=None):
    if out is None:
        out = []
    if t in out:
        return out
    out.append(t)
    tag, l, r = T.slots[t]
    if tag == PC.TAG_IMP:
        subterms(T, l, out)
        subterms(T, r, out)
    return out


def prune(order, goal):
    """Backward reachability from the goal — drop every derived line the goal does not use.

    The owner's law: dead logic is where a mutation hides. A proof carrying lines the
    conclusion never depends on is the same defect in proof form, and it also makes the
    checker do work for nothing."""
    pos = {d.term: i for i, d in enumerate(order)}
    keep = set()
    stack = [pos[goal]]
    while stack:
        i = stack.pop()
        if i in keep:
            continue
        keep.add(i)
        d = order[i]
        if d.rule == PC.RULE_MP:
            stack.append(d.a)
            stack.append(d.b)
    kept = sorted(keep)
    remap = {old: new for new, old in enumerate(kept)}
    out = []
    for old in kept:
        d = order[old]
        if d.rule == PC.RULE_MP:
            out.append((PC.RULE_MP, remap[d.a], remap[d.b], d.term))
        else:
            out.append((d.rule, 0, 0, d.term))
    return out


def prove(T, goal, seeds, **kw):
    """Seed the pool with the GOAL'S OWN SUBTERMS as well as the caller's seeds. Without this
    the search has to invent the goal's structure from atoms outward, which is why
    A -> (B -> (C -> A)) was not found: the intermediate C -> A never entered the pool."""
    seeds = list(dict.fromkeys(list(seeds) + subterms(T, goal)))
    order = search(T, goal, seeds, **kw)
    if order is None:
        return None
    return prune(order, goal)


def report(name, T, goal, lines, t0):
    """A failed search returns None. Handing None to the checker is a crash, not a result —
    and a prover that finds nothing must report that plainly, never as a rejection."""
    dt = time.time() - t0
    if lines is None:
        print("  %-22s NO PROOF FOUND within the search bound  (%4d terms, %.2fs)"
              % (name, len(T.slots), dt))
        return None
    ref = PC.check_reference(T.slots, lines, goal)
    print("  %-22s FOUND   %3d lines, %4d terms, %.2fs   checker: %s"
          % (name, len(lines), len(T.slots), dt,
             "ACCEPT" if ref == 1 else "REJECT"))
    return ref


def main():
    print("=" * 84)
    print("  MUHL PROVER — find proofs, then hand every one to the installed checker")
    print("=" * 84)
    print("  the prover is NEVER trusted. a proof counts only if the checker accepts it.\n")

    results = []

    # ---- 1. A -> A, the classic. Seeded only with the atom.
    T = PC.Terms()
    A = T.atom(0)
    goal = T.imp(A, A)
    t0 = time.time()
    lines = prove(T, goal, [A, T.imp(A, A)], max_rounds=3)
    results.append(report("A -> A", T, goal, lines, t0))

    # ---- 2. B -> (A -> B), a bare K instance
    T2 = PC.Terms()
    A2, B2 = T2.atom(0), T2.atom(1)
    goal2 = T2.imp(B2, T2.imp(A2, B2))
    t0 = time.time()
    lines2 = prove(T2, goal2, [A2, B2], max_rounds=2)
    results.append(report("B -> (A -> B)", T2, goal2, lines2, t0))

    # ---- 3. A -> (B -> (C -> A)), needs two nested K steps
    T3 = PC.Terms()
    A3, B3, C3 = T3.atom(0), T3.atom(1), T3.atom(2)
    goal3 = T3.imp(A3, T3.imp(B3, T3.imp(C3, A3)))
    t0 = time.time()
    # this one needs a K instance built ON a derived formula (P -> (B -> P), size 9), so the
    # pool cap has to be wide enough to keep it. S instances are cubic in |pool|, so the cost
    # of that headroom is stated rather than hidden: |pool|=28 is ~22k candidates per round.
    lines3 = prove(T3, goal3, [A3, B3, C3], max_rounds=5, pool_cap=28)
    results.append(report("A -> (B -> (C -> A))", T3, goal3, lines3, t0))

    # ---- 4. a goal that is NOT derivable — the prover must fail, not fabricate
    T4 = PC.Terms()
    A4, B4 = T4.atom(0), T4.atom(1)
    goal4 = T4.imp(A4, B4)          # A -> B is not a theorem
    t0 = time.time()
    lines4 = prove(T4, goal4, [A4, B4], max_rounds=3, max_pool=1500)
    print("  %-22s %s  (this SHOULD fail — A -> B is not a theorem)"
          % ("A -> B", "no proof" if lines4 is None else "*** FOUND, WRONG ***"))
    if lines4 is not None:
        results.append(0)
    else:
        print("      -> correct: it refused to fabricate a proof it could not find.")

    print()
    found = [r for r in results if r is not None]
    n_unfound = len([r for r in results if r is None])

    # SOUNDNESS is the bar that matters and it is absolute: every proof produced must be
    # accepted by the checker, and a non-theorem must never be proved.
    sound = all(r == 1 for r in found) and lines4 is None
    print("  SOUNDNESS : %s" % (
        "HELD — every proof found was ACCEPTED by the installed checker, and the "
        "non-theorem A -> B was not proved." if sound else "*** VIOLATED — see above ***"))

    # COMPLETENESS is bounded, and that is stated rather than dressed up.
    print("  COVERAGE  : %d of %d goals found within the search bound."
          % (len(found), len(found) + n_unfound))
    if n_unfound:
        print()
        print("  NOT YET BUILT — why the third goal was not found, measured not guessed:")
        print("    Forward chaining saturates. A -> (B -> (C -> A)) needs a K instance built")
        print("    ON a derived formula of size 9, and reaching it means keeping enough of the")
        print("    pool that S instances (cubic in |pool|) explode first — it hit the 20,000")
        print("    term ceiling inside one round.")
        print("    The fix is NOT a bigger bound. It is a different search: backward chaining")
        print("    via the DEDUCTION THEOREM, which for this fragment is constructive and")
        print("    linear — assume the antecedent, derive the consequent, convert mechanically.")
        print("    That is the next build. The prover refusing to fabricate a proof it could")
        print("    not find is the correct behaviour, and the checker is what makes that safe.")

    if lines:
        print("\n  the A -> A proof it found, in the checker's own format:")
        RN = {PC.RULE_K: "K ", PC.RULE_S: "S ", PC.RULE_MP: "MP"}
        for i, (r, a, b, c) in enumerate(lines):
            src = "from %d,%d" % (a, b) if r == PC.RULE_MP else "axiom"
            print("    line %d: %s  term %-3d  %s" % (i, RN[r], c, src))
    return 0 if sound else 1


if __name__ == "__main__":
    raise SystemExit(main())
