#!/usr/bin/env python3
"""muhl_proofcheck.py -- THE PROOF CHECKER, AS SOFTWARE FOR THE MUHLNICKEL.

Owner, 2026-08-06: "whatever that is just put it in the muhlnickel recreate it as logic
dont install it thats dumb muhlnickel has better specs than host" and, correcting me
when I read the no-recreate rule too widely: "DONT RECREATE DOESNT MEAN DONT PUT IT IN
THE SUBSTRATE".

So: not installed on the host, and not hand-etched as a gate clone. It is SOFTWARE and
the muhlnickel is the COMPUTER -- exactly the pfc_load.py pattern, where a model is
referenced and wired rather than recreated. The substrate already holds a real RV32I CPU
as gates (`pfc_riscv_rv32i_v2__phys`, 67,348 gates, DEPTH 74 ticks/instruction), so the
checker is RV32I machine code that runs ON it.

WHAT IT CHECKS
  Hilbert-style propositional calculus, implicational fragment -- a real, sound formal
  system, the same shape of object a kernel checks:
      axiom K :  A -> (B -> A)
      axiom S :  (A -> (B -> C)) -> ((A -> B) -> (A -> C))
      rule MP :  from  P  and  P -> Q  infer  Q
  A proof is a list of lines; each line is an axiom instance or an MP step citing two
  EARLIER lines. The checker accepts iff every line is justified and the last line is the
  goal. Terms are a hash-consed (interned) graph, so structural equality is index equality
  -- which is how a real kernel makes definitional equality cheap, not a shortcut.

  SOUNDNESS DETAILS THAT ARE EASY TO GET WRONG, AND ARE HANDLED:
    - MP premises must cite STRICTLY EARLIER lines (no circular justification).
    - Every term index is bounds-checked; an out-of-range index REJECTS rather than
      reading whatever bytes are next door.
    - An unknown rule code REJECTS.

This module holds the program source, an INDEPENDENT Python reference for the same
semantics, and a proof generator for verification. Fabrication tooling only -- it stores
nothing. `muhl_fab_proofcheck.py` does the storing, and only after this verifies.
"""

# ------------------------------------------------------------------ memory map (bytes)
CODE_BASE  = 0x0000
DATA_BASE  = 0x1000        # n_terms(0) n_lines(4) goal(8) result(12)
TERMS_BASE = 0x0001_0000   # n_terms x 3 words: tag, left, right
LINES_BASE = 0x0400_0000   # n_lines x 4 words: rule, a, b, concl
# The first scaling wall (2026-08-06) was MINE, not the machine's: TERMS/LINES were 4,096 B
# apart, so 448 terms overran the line table at 320 proof lines. Widened to 64 MB of term
# space (~5.6M terms). The program did not change -- only two immediates. Recorded as an
# assistant layout error, per the owner's rule that a limit must be proven and attributed.

TAG_ATOM = 0
TAG_IMP  = 1
RULE_K, RULE_S, RULE_MP = 0, 1, 2

RESULT_ADDR = DATA_BASE + 12
NO_VERDICT  = 0xDEADBEEF    # what the result word holds before the program writes a verdict


# ------------------------------------------------------------------ the program
PROGRAM = """
        li   s0, %(DATA)d
        li   s1, %(TERMS)d
        li   s2, %(LINES)d
        lw   s3, 4(s0)              # n_lines
        li   s5, 1                  # ok = 1
        li   s4, 0                  # i  = 0

loop:   bge  s4, s3, done
        slli t0, s4, 4
        add  t0, t0, s2
        lw   s6, 0(t0)              # rule
        lw   s7, 4(t0)              # premise a
        lw   s8, 8(t0)              # premise b
        lw   s9, 12(t0)             # conclusion term index

        li   t6, 1
        beq  s6, zero, chk_k
        addi t5, zero, 1
        beq  s6, t5, chk_s
        addi t5, zero, 2
        beq  s6, t5, chk_mp
        li   s5, 0                  # unknown rule -> reject
        jal  zero, next

# ---- axiom K :  concl = IMP(x, IMP(y, x))
chk_k:  add  a0, s9, zero
        jal  ra, term
        bne  a1, t6, bad
        add  t1, a2, zero           # x = left(concl)
        add  a0, a3, zero           # n1 = right(concl)
        jal  ra, term
        bne  a1, t6, bad
        bne  a3, t1, bad            # right(n1) == x
        jal  zero, next

# ---- axiom S :  concl = IMP( IMP(A,IMP(B,C)) , IMP( IMP(A,B), IMP(A,C) ) )
chk_s:  add  a0, s9, zero
        jal  ra, term
        bne  a1, t6, bad
        add  t5, a2, zero           # P
        add  t4, a3, zero           # Q
        add  a0, t5, zero
        jal  ra, term
        bne  a1, t6, bad
        add  t1, a2, zero           # A
        add  t5, a3, zero           # R
        add  a0, t5, zero
        jal  ra, term
        bne  a1, t6, bad
        add  t2, a2, zero           # B
        add  t3, a3, zero           # C
        add  a0, t4, zero
        jal  ra, term
        bne  a1, t6, bad
        add  t4, a2, zero           # U
        add  t5, a3, zero           # V
        add  a0, t4, zero
        jal  ra, term
        bne  a1, t6, bad
        bne  a2, t1, bad            # left(U)  == A
        bne  a3, t2, bad            # right(U) == B
        add  a0, t5, zero
        jal  ra, term
        bne  a1, t6, bad
        bne  a2, t1, bad            # left(V)  == A
        bne  a3, t3, bad            # right(V) == C
        jal  zero, next

# ---- modus ponens : line a is (cb -> concl), line b is cb
chk_mp: bge  s7, s4, bad            # premise a must be an EARLIER line
        bge  s8, s4, bad            # premise b must be an EARLIER line
        slli t0, s7, 4
        add  t0, t0, s2
        lw   t1, 12(t0)             # ca = conclusion of line a
        slli t0, s8, 4
        add  t0, t0, s2
        lw   t2, 12(t0)             # cb = conclusion of line b
        add  a0, t1, zero
        jal  ra, term
        bne  a1, t6, bad            # ca must be an implication
        bne  a2, t2, bad            # its antecedent == cb
        bne  a3, s9, bad            # its consequent == this line's conclusion
        jal  zero, next

bad:    li   s5, 0

next:   addi s4, s4, 1
        jal  zero, loop

done:   bne  s3, zero, haveln       # an EMPTY proof proves nothing -> reject
        li   s5, 0
        jal  zero, fin
haveln: addi t0, s3, -1             # last line's conclusion must be the goal
        slli t0, t0, 4
        add  t0, t0, s2
        lw   t1, 12(t0)
        lw   t2, 8(s0)
        beq  t1, t2, fin
        li   s5, 0
fin:    sw   s5, 12(s0)
        jal  zero, halt

# ---- term(a0) -> a1=tag a2=left a3=right ; bounds-checked, clobbers t0 only
term:   lw   t0, 0(s0)              # n_terms
        bltu a0, t0, tok
        li   s5, 0                  # out-of-range index -> reject, permanently:
        jalr zero, 0(ra)            # s5 is never set back to 1, so the verdict is latched.
                                    # (the a1/a2/a3 zeroing that used to sit here was
                                    #  provably dead -- 96 mutant sites that could not
                                    #  change any verdict. Pruned, not excused.)
tok:    slli t0, a0, 1
        add  t0, t0, a0
        slli t0, t0, 2
        add  t0, t0, s1
        lw   a1, 0(t0)
        lw   a2, 4(t0)
        lw   a3, 8(t0)
        jalr zero, 0(ra)

halt:   jal  zero, halt
""" % {"DATA": DATA_BASE, "TERMS": TERMS_BASE, "LINES": LINES_BASE}


# ------------------------------------------------------------------ term graph (interned)
class Terms:
    """Hash-consed term graph. Interning is what makes structural equality == index
    equality, which is the representation the checker program assumes."""

    def __init__(self):
        self.slots = []            # list of (tag, left, right)
        self._seen = {}

    def _intern(self, rec):
        k = self._seen.get(rec)
        if k is None:
            k = len(self.slots)
            self.slots.append(rec)
            self._seen[rec] = k
        return k

    def atom(self, name):
        return self._intern((TAG_ATOM, name, 0))

    def imp(self, a, b):
        return self._intern((TAG_IMP, a, b))

    def words(self):
        out = []
        for tag, l, r in self.slots:
            out += [tag & 0xFFFFFFFF, l & 0xFFFFFFFF, r & 0xFFFFFFFF]
        return out


# ------------------------------------------------------------------ independent reference
def check_reference(slots, lines, goal):
    """INDEPENDENT implementation of the checker's semantics, written straight from the
    rules above. Deliberately NOT sharing code with the program -- it is the thing the
    program is verified against."""
    n = len(slots)

    def get(t):
        if not (0 <= t < n):
            return None
        return slots[t]

    ok = True
    for i, (rule, a, b, concl) in enumerate(lines):
        s = get(concl)
        if s is None:
            ok = False
            continue

        if rule == RULE_K:
            if s[0] != TAG_IMP:
                ok = False; continue
            x = s[1]
            n1 = get(s[2])
            if n1 is None or n1[0] != TAG_IMP or n1[2] != x:
                ok = False

        elif rule == RULE_S:
            if s[0] != TAG_IMP:
                ok = False; continue
            P, Q = get(s[1]), get(s[2])
            if P is None or Q is None or P[0] != TAG_IMP or Q[0] != TAG_IMP:
                ok = False; continue
            A, R = P[1], get(P[2])
            if R is None or R[0] != TAG_IMP:
                ok = False; continue
            B, C = R[1], R[2]
            U, V = get(Q[1]), get(Q[2])
            if U is None or V is None or U[0] != TAG_IMP or V[0] != TAG_IMP:
                ok = False; continue
            if U[1] != A or U[2] != B or V[1] != A or V[2] != C:
                ok = False

        elif rule == RULE_MP:
            if not (0 <= a < i and 0 <= b < i):
                ok = False; continue
            ca = get(lines[a][3])
            cb = lines[b][3]
            if ca is None or ca[0] != TAG_IMP or ca[1] != cb or ca[2] != concl:
                ok = False

        else:
            ok = False

    if not lines or lines[-1][3] != goal:
        ok = False
    return 1 if ok else 0


# ------------------------------------------------------------------ image assembly
def build_image(slots, lines, goal, code_words, fill=None):
    """Lay the program and its data into one word-addressed image {byte_addr: word}.

    `fill` pre-populates memory BEYOND the declared term table. That matters: an emulator
    zero-fills unmapped words, so an out-of-range term read looks like an ATOM and gets
    rejected by the tag check even with no bounds guard at all. On the substrate those
    bytes are whatever the container holds. Adversarial fill makes the bounds guard the
    only thing standing between a bogus index and a false ACCEPT — which is its real job.
    """
    mem = {}
    if fill:
        mem.update({a & ~3: w & 0xFFFFFFFF for a, w in fill.items()})
    for i, w in enumerate(code_words):
        mem[CODE_BASE + 4 * i] = w & 0xFFFFFFFF
    mem[DATA_BASE + 0] = len(slots)
    mem[DATA_BASE + 4] = len(lines)
    mem[DATA_BASE + 8] = goal & 0xFFFFFFFF
    mem[DATA_BASE + 12] = NO_VERDICT      # sentinel: a hang/crash must NOT read as REJECT
    for i, (tag, l, r) in enumerate(slots):
        base = TERMS_BASE + 12 * i
        mem[base + 0] = tag & 0xFFFFFFFF
        mem[base + 4] = l & 0xFFFFFFFF
        mem[base + 8] = r & 0xFFFFFFFF
    for i, (rule, a, b, concl) in enumerate(lines):
        base = LINES_BASE + 16 * i
        mem[base + 0] = rule & 0xFFFFFFFF
        mem[base + 4] = a & 0xFFFFFFFF
        mem[base + 8] = b & 0xFFFFFFFF
        mem[base + 12] = concl & 0xFFFFFFFF
    return mem


# ------------------------------------------------------------------ proof generation
def proof_deduction_identity(atom_name=0):
    """A REAL theorem with a REAL Hilbert proof: A -> A, the classic five-line derivation.
    Nothing about it is degenerate -- it uses both axioms and two MP steps."""
    T = Terms()
    A = T.atom(atom_name)
    AA = T.imp(A, A)                      # A -> A          (the goal)
    A_AA = T.imp(A, AA)                   # A -> (A -> A)
    # S instance with A:=A, B:=(A->A), C:=A
    S_ante = T.imp(A, T.imp(AA, A))       # A -> ((A->A) -> A)
    S_l = T.imp(A, AA)                    # A -> (A->A)
    S_r = T.imp(A, A)                     # A -> A
    S_cons = T.imp(S_l, S_r)              # (A->(A->A)) -> (A->A)
    S_full = T.imp(S_ante, S_cons)
    K1 = T.imp(A, T.imp(AA, A))           # K: A -> ((A->A) -> A)
    K2 = A_AA                             # K: A -> (A -> A)

    lines = [
        (RULE_S,  0, 0, S_full),          # 0 : S instance
        (RULE_K,  0, 0, K1),              # 1 : K instance  A -> ((A->A) -> A)
        (RULE_MP, 0, 1, S_cons),          # 2 : MP(0,1) -> (A->(A->A)) -> (A->A)
        (RULE_K,  0, 0, K2),              # 3 : K instance  A -> (A -> A)
        (RULE_MP, 2, 3, AA),              # 4 : MP(2,3) -> A -> A
    ]
    return T, lines, AA


def proof_k_only():
    """A one-line proof that IS an axiom K instance, and is its own goal."""
    T = Terms()
    A, B = T.atom(0), T.atom(1)
    BA = T.imp(B, A)
    g = T.imp(A, BA)                       # A -> (B -> A)
    return T, [(RULE_K, 0, 0, g)], g


def proof_s_only():
    """A one-line proof that IS an axiom S instance, and is its own goal."""
    T = Terms()
    A, B, C = T.atom(0), T.atom(1), T.atom(2)
    BC = T.imp(B, C)
    P = T.imp(A, BC)                       # A -> (B -> C)
    U = T.imp(A, B)
    V = T.imp(A, C)
    Q = T.imp(U, V)                        # (A->B) -> (A->C)
    g = T.imp(P, Q)
    return T, [(RULE_K, 0, 0, T.imp(A, T.imp(B, A))), (RULE_S, 0, 0, g)], g


def proof_mp_only():
    """Two axiom lines then one MP, so the MP path is exercised on its own."""
    T = Terms()
    A, B = T.atom(0), T.atom(1)
    BA = T.imp(B, A)
    KAB = T.imp(A, BA)                     # A -> (B -> A)      (axiom K)
    # line0: K gives  KAB ; line1: K gives  KAB -> (B -> KAB) ; MP is not applicable to those,
    # so build a genuine MP: line0 = X, line1 = X -> Y, conclude Y.
    X = KAB
    Y = T.imp(B, X)
    XY = T.imp(X, Y)                       # X -> (B -> X)   which is axiom K with A:=X, B:=B
    return T, [(RULE_K, 0, 0, X), (RULE_K, 0, 0, XY), (RULE_MP, 1, 0, Y)], Y


def _clone(T):
    t2 = Terms()
    t2.slots = list(T.slots)
    t2._seen = dict(T._seen)
    return t2


def case_battery():
    """Every distinct check in the program gets a case that fails ONLY that check, plus the
    valid proofs. This makes the FUNCTIONAL bar strictly harder -- it is never relaxed."""
    cases = []

    # ---- valid proofs (ACCEPT paths) -------------------------------------------------
    for nm, fn in (("valid_identity", proof_deduction_identity),
                   ("valid_k", proof_k_only),
                   ("valid_s", proof_s_only),
                   ("valid_mp", proof_mp_only)):
        T, lines, goal = fn()
        cases.append((nm, T.slots, lines, goal))

    # ---- axiom K, each sub-check broken in isolation ---------------------------------
    T = Terms(); A, B = T.atom(0), T.atom(1)
    BA = T.imp(B, A); g = T.imp(A, BA)
    atom_only = T.atom(9)
    cases.append(("K_concl_not_imp", T.slots, [(RULE_K, 0, 0, atom_only)], atom_only))
    T2 = _clone(T); wrong = T2.imp(A, A)      # right(concl) is an ATOM-headed pair -> n1 not IMP
    bad_n1 = T2.imp(A, T2.atom(5))
    cases.append(("K_n1_not_imp", T2.slots, [(RULE_K, 0, 0, bad_n1)], bad_n1))
    T3 = _clone(T); C = T3.atom(2)
    bad_x = T3.imp(A, T3.imp(B, C))           # right(n1)=C != x=A
    cases.append(("K_x_mismatch", T3.slots, [(RULE_K, 0, 0, bad_x)], bad_x))

    # ---- axiom S, each sub-check broken in isolation ---------------------------------
    def s_terms(mutate=None):
        t = Terms()
        A, B, C = t.atom(0), t.atom(1), t.atom(2)
        D = t.atom(3)
        BC = t.imp(B, C)
        P = t.imp(A, BC)
        U = t.imp(A, B)
        V = t.imp(A, C)
        if mutate == "U_left":   U = t.imp(D, B)
        if mutate == "U_right":  U = t.imp(A, D)
        if mutate == "V_left":   V = t.imp(D, C)
        if mutate == "V_right":  V = t.imp(A, D)
        if mutate == "U_atom":   U = D
        if mutate == "V_atom":   V = D
        if mutate == "P_atom":   P = D
        if mutate == "R_atom":   P = t.imp(A, D)
        Q = t.imp(U, V)
        if mutate == "Q_atom":   Q = D
        g = t.imp(P, Q)
        return t, g

    for m in ("P_atom", "R_atom", "Q_atom", "U_atom", "V_atom",
              "U_left", "U_right", "V_left", "V_right"):
        t, g = s_terms(m)
        cases.append(("S_" + m, t.slots, [(RULE_S, 0, 0, g)], g))
    t, g = s_terms()
    cases.append(("S_concl_not_imp", t.slots, [(RULE_S, 0, 0, t.atom(7))], t.atom(7)))

    # ---- modus ponens, each sub-check broken in isolation ----------------------------
    T, lines, goal = proof_mp_only()
    X, XY, Y = lines[0][3], lines[1][3], lines[2][3]
    cases.append(("MP_a_not_earlier", T.slots,
                  [lines[0], lines[1], (RULE_MP, 2, 0, Y)], Y))
    cases.append(("MP_b_not_earlier", T.slots,
                  [lines[0], lines[1], (RULE_MP, 1, 2, Y)], Y))
    Tb = _clone(T); atom = Tb.atom(31)
    cases.append(("MP_ca_not_imp", Tb.slots,
                  [(RULE_K, 0, 0, X), (RULE_K, 0, 0, atom), (RULE_MP, 1, 0, Y)], Y))
    cases.append(("MP_antecedent_mismatch", T.slots,
                  [lines[0], lines[1], (RULE_MP, 1, 1, Y)], Y))
    cases.append(("MP_consequent_mismatch", T.slots,
                  [lines[0], lines[1], (RULE_MP, 1, 0, X)], X))

    # ---- structural / bounds / goal --------------------------------------------------
    T, lines, goal = proof_deduction_identity()
    n = len(T.slots)
    for pos in range(len(lines)):
        ls = [list(x) for x in lines]
        ls[pos][3] = n + 3                                   # out-of-range conclusion
        cases.append(("oob_line%d" % pos, T.slots, [tuple(x) for x in ls], goal))
    for pos in range(len(lines)):
        ls = [list(x) for x in lines]
        ls[pos][0] = 9                                       # unknown rule code
        cases.append(("badrule_line%d" % pos, T.slots, [tuple(x) for x in ls], goal))
    cases.append(("goal_mismatch", T.slots, lines, (goal + 1) % n))
    cases.append(("empty_proof", T.slots, [], goal))

    # ---- ADVERSARIAL OUT-OF-RANGE: the bounds guard is the ONLY thing that rejects ----
    # slots: 0 = ATOM(0)=A, 1 = IMP(0,0) = A->A.  The out-of-range slot 2 is planted in
    # memory as IMP(0,1), which reads as a PERFECTLY WELL-FORMED axiom-K instance:
    #   tag(2)=IMP, x=left(2)=0, n1=right(2)=1, tag(1)=IMP, right(1)=0 == x.
    # So without the bounds check the program would ACCEPT. The reference rejects, because
    # index 2 is not a declared term. Any mutant that weakens the guard shows up here.
    adv = Terms()
    a0 = adv.atom(0)
    a1 = adv.imp(a0, a0)
    planted = len(adv.slots)                       # index 2, deliberately NOT declared
    base = TERMS_BASE + 12 * planted
    fill = {base + 0: TAG_IMP, base + 4: a0, base + 8: a1}
    cases.append(("oob_adversarial_K", adv.slots, [(RULE_K, 0, 0, planted)], planted, fill))
    # same planting, reached through an MP premise rather than a conclusion
    cases.append(("oob_adversarial_MP", adv.slots,
                  [(RULE_K, 0, 0, a1), (RULE_MP, planted, 0, a1)], a1, fill))
    # and a planted region that would satisfy the S schema shape if read unguarded
    adv2 = Terms()
    A2, B2, C2 = adv2.atom(0), adv2.atom(1), adv2.atom(2)
    P2 = adv2.imp(A2, adv2.imp(B2, C2))
    U2, V2 = adv2.imp(A2, B2), adv2.imp(A2, C2)
    Q2 = adv2.imp(U2, V2)
    planted2 = len(adv2.slots)
    b2 = TERMS_BASE + 12 * planted2
    fill2 = {b2 + 0: TAG_IMP, b2 + 4: P2, b2 + 8: Q2}
    cases.append(("oob_adversarial_S", adv2.slots, [(RULE_S, 0, 0, planted2)], planted2, fill2))

    return [(c[0], c[1], c[2], c[3], c[4] if len(c) > 4 else None) for c in cases]


def mutate_proof(T, lines, goal, kind, rng):
    """Produce a proof that MUST be rejected, one defect at a time."""
    ls = [list(x) for x in lines]
    if kind == "circular":                       # MP citing a later line
        for i, l in enumerate(ls):
            if l[0] == RULE_MP:
                l[1] = len(ls) - 1
                break
    elif kind == "wrong_goal":
        goal = rng.randrange(len(T.slots))
        if goal == lines[-1][3]:
            goal = (goal + 1) % len(T.slots)
    elif kind == "bad_mp":                       # MP whose premise is not the antecedent
        for l in ls:
            if l[0] == RULE_MP:
                l[2] = (l[2] + 1) % max(1, l[0] + 1) if l[2] > 0 else 0
                l[3] = (l[3] + 1) % len(T.slots)
                break
    elif kind == "bad_axiom":                    # an axiom line whose term is not an instance
        for l in ls:
            if l[0] in (RULE_K, RULE_S):
                l[3] = (l[3] + 1) % len(T.slots)
                break
    elif kind == "oob":                          # out-of-range term index
        ls[rng.randrange(len(ls))][3] = len(T.slots) + 7
    elif kind == "bad_rule":
        ls[rng.randrange(len(ls))][0] = 9
    return [tuple(x) for x in ls], goal
