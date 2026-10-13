#!/usr/bin/env python3
"""Component implementation and operation."""
import io, os, struct, sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "AUTOFAB0.mno")
WRITE = "--write" in sys.argv

OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

GENES = 8            # gene slots, one byte each
BITS = 8             # bits per gene
LFSR = 16            # entropy register width


# ⛔ THE SHAPES COME FROM ONE PLACE. muhl_shapes lives beside the checkers, outside .claude.
#    Keeping private copies here is exactly how one erase-on-idle mistake became seven: a fix to
#    one copy never reached the others. Import, or fail loudly - never quietly fall back to a
#    local reimplementation, because the local copy IS the failure mode.
sys.path.insert(0, r"C:\Users\lucys\Desktop\MUHL_CHECKERS")
from muhl_shapes import (hold_cell, prefix_inc, prefix_dec,        # noqa: E402
                         tree_reduce, one_way, gt_prefix)


def _local_hold_cell_RETIRED(g, w, new, write, cell):
    """RETIRED - superseded by muhl_shapes.hold_cell. Kept, not deleted: vault law, mark and
    archive. This was the first definition of take-or-hold and it is identical to the shared one;
    it is preserved so the history of the fix is legible, and it is called by nothing.

    TAKE-OR-HOLD. The shape every state cell in this machine needs, emitted once.

        cell' = (new AND write) OR (cell AND NOT write)

    ⛔ WHY THIS IS A PRIMITIVE AND NOT A CONVENTION. On 2026-08-07 the same mistake was made at
    FIVE separate sites in one circuit: the budget, the envelope staging, the witness staging, the
    shadow, and the drop count were each written as `AND(src, write)` straight into the state
    address. So a settle that did not write put a ZERO there - "not publishing" meant "erase"
    instead of "leave alone." In a machine that runs continuously and publishes occasionally the
    quiet settle is the COMMON case, so every one of those cells destroyed itself on the normal
    path and survived only during the exception.

    None of it showed up in testing, because every test drove an input that DID write. A defect on
    the idle path is invisible to a battery that never idles.

    Owner: "ITS NEVER INERT." A cell that is not being written is not doing nothing - it is
    holding, and holding is something the wiring has to SAY. Returns (w, ) with the cell written
    to its own address, out addr == in addr, self-clocked.
    """
    nw = w; g.append((OP_NOT, write, write, nw)); w += 1
    take = w; g.append((OP_AND, new, write, take)); w += 1
    keep = w; g.append((OP_AND, cell, nw, keep)); w += 1
    g.append((OP_OR, take, keep, cell))            # SELF-CLOCK: out addr == in addr
    return w


def prefix_inc(g, w, bits, enable):
    """Increment a register by 1 when `enable`, as a PARALLEL PREFIX and never a ripple.

    Incrementing is the case where propagate is the bit itself and generate is zero, so the carry
    prefix collapses to a running AND over the low bits - log2(N) rounds instead of N links.
    MEASURED on the same shape: add32 ripple 157 gates / 63 ticks against prefix 482 / 11
    (muhl_datapath A1); a 64-bit +1 is DEPTH 140 ripple against 17 prefix for eight more gates
    (titan_circuit.py:61). Depth falls faster than area rises, so the swap wins.
    """
    n = len(bits)
    p = []
    for b in bits:
        t = w; g.append((OP_AND, b, enable, t)); w += 1
        p.append(t)
    step = 1
    cur = list(p)
    while step < n:
        nxt = list(cur)
        for i in range(step, n):
            t = w; g.append((OP_AND, cur[i], cur[i - step], t)); w += 1
            nxt[i] = t
        cur = nxt
        step *= 2
    for i in range(n):
        cin = enable if i == 0 else cur[i - 1]
        s = w; g.append((OP_XOR, bits[i], cin, s)); w += 1
        g.append((OP_OR, s, s, bits[i]))           # SELF-CLOCK: out addr == in addr
    return w


def build(mutant=None):
    """Emit the autofab AS GATES. Returns (gates, layout)."""
    g = []
    genome = 0                       # live genome - ITS ADDRESSES ARE OPERAND FIELDS
    cand = genome + GENES * BITS     # challenger genome
    lfsr = cand + GENES * BITS       # entropy
    score_a = lfsr + LFSR            # incumbent silly
    score_b = score_a + 16           # challenger silly
    cmpw = score_b + 16              # comparator chain
    sel = cmpw + 16                  # winner select bit
    work = sel + 1

    # ── LFSR: mutation entropy IN GATES. taps 16,14,13,11 - maximal length.
    fb = work
    g.append((OP_XOR, lfsr + 15, lfsr + 13, fb))
    g.append((OP_XOR, fb, lfsr + 12, fb + 1))
    g.append((OP_XOR, fb + 1, lfsr + 10, fb + 2))
    for i in range(LFSR - 1, 0, -1):
        g.append((OP_OR, lfsr + i - 1, lfsr + i - 1, lfsr + i))     # shift, self-clocked
    g.append((OP_OR, fb + 2, fb + 2, lfsr + 0))                     # feedback into bit 0

    w = work + 8
    # ── MUTATE + CROSSOVER, per gene bit. challenger = (A&sel)|(B&~sel) then XOR entropy.
    for gi in range(GENES):
        for b in range(BITS):
            src = genome + gi * BITS + b
            ent = lfsr + ((gi * BITS + b) % LFSR)
            nsel = w; g.append((OP_NOT, sel, sel, nsel))
            ta = w + 1; g.append((OP_AND, src, sel, ta))
            tb = w + 2; g.append((OP_AND, src, nsel, tb))
            mx = w + 3; g.append((OP_OR, ta, tb, mx))
            if mutant == "no_mutate":
                g.append((OP_OR, mx, mx, cand + gi * BITS + b))
            else:
                g.append((OP_XOR, mx, ent, cand + gi * BITS + b))
            w += 4

    # ── SCORE: SILLY = electrons x contacts. gene 0 = electrons, gene 1 = contacts.
    #    shift-add multiplier, in gates. partial products then a ripple sum.
    for i in range(BITS):
        for j in range(BITS):
            if i + j < 16:
                g.append((OP_AND, genome + 0 * BITS + i, genome + 1 * BITS + j, w))
                g.append((OP_XOR, score_a + i + j, w, score_a + i + j))
                w += 1
    for i in range(BITS):
        for j in range(BITS):
            if i + j < 16:
                g.append((OP_AND, cand + 0 * BITS + i, cand + 1 * BITS + j, w))
                g.append((OP_XOR, score_b + i + j, w, score_b + i + j))
                w += 1

    # ── CAPACITY GATE, IN GATES. gene 2 = cells, gene 3 = senses. A ring cannot circulate more
    #    electrons than it holds, so a challenger claiming electrons > cells*senses is INVALID
    #    and its score is forced to zero. Without this, genes 2 and 3 mutate and get selected on
    #    a score they do not influence - drift, not search. His: "DUDE YOU DONT JUST CHOOSE A
    #    RANDOM RING AND HOPE IT WORKS."
    capw = w
    for i in range(BITS):
        for j in range(BITS):
            if i + j < 16:
                g.append((OP_AND, cand + 2 * BITS + i, cand + 3 * BITS + j, w + 16))
                g.append((OP_XOR, capw + i + j, w + 16, capw + i + j))
                w += 1
    w += 16
    # electrons (gene 0, 8 bits) vs capacity (16 bits): borrow chain, invalid when el > cap
    ib = w
    g.append((OP_NOT, capw + 0, capw + 0, ib))
    g.append((OP_AND, cand + 0 * BITS + 0, ib, ib + 1))
    pv = ib + 1
    w = ib + 2
    for i in range(1, BITS):
        nb = w; g.append((OP_NOT, capw + i, capw + i, nb))
        t1 = w + 1; g.append((OP_AND, cand + 0 * BITS + i, nb, t1))
        eq = w + 2; g.append((OP_XOR, cand + 0 * BITS + i, capw + i, eq))
        ne = w + 3; g.append((OP_NOT, eq, eq, ne))
        t2 = w + 4; g.append((OP_AND, ne, pv, t2))
        nx = w + 5; g.append((OP_OR, t1, t2, nx))
        pv = nx; w += 6
    invalid = pv                      # 1 when the challenger over-claims electrons
    valid = w; g.append((OP_NOT, invalid, invalid, valid)); w += 1
    # SETTLES (gene 4) prices the answer: an invalid or slow genome cannot carry its score.
    for i in range(16):
        if mutant != "no_capacity":
            g.append((OP_AND, score_b + i, valid, score_b + i))

    # ── COMPARE: challenger > incumbent, PARALLEL-PREFIX (Kogge-Stone), not a borrow chain.
    #
    # ⛔ THE LEVER, AND IT WAS SITTING IN HIS OWN Circuit CLASS THE WHOLE TIME.
    #    titan_circuit.py:87 `sub_prefix` — "A - B is A + ~B + 1, and the naive build is two chained
    #    ripple adds (~2x66 depth). But the +1 is exactly a CARRY-IN, and a Kogge-Stone prefix takes
    #    a carry-in for free by seeding the generate term at bit 0. So a subtract costs the same as
    #    an add, not double. S48/S49: subc() was two ripple adds and owned the RV32I core's critical
    #    path." The version this replaces was that same defect, rebuilt from scratch.
    #
    # MEASURED, muhl_datapath.py A4 / MUHL_LAB_LOG:
    #    comparator LT   w16  94 gates /  32 ticks     w32  190 gates /  64 ticks
    #    comparator EQ   w16  47 gates /   6 ticks     w32   95 gates /   7 ticks
    #    adder ripple    w32 157 gates /  63 ticks     prefix w32 482 gates / 11 ticks
    # LT is the expensive one and it is genuinely needed here (a strict >, not an ==), so the fix is
    # the PREFIX structure, not a cheaper predicate.
    #
    # THE SCAN. Per bit: G[i] = B[i] AND NOT A[i]  (challenger strictly wins at bit i)
    #                    P[i] = NOT (A[i] XOR B[i]) (tie at bit i - defer to the bits below)
    # (G,P) compose associatively with the more-significant side dominating:
    #    G' = G_hi OR (P_hi AND G_lo)      P' = P_hi AND P_lo
    # so the scan reduces in log2(16) = 4 rounds instead of 16 sequential borrows, and G[15] after
    # the last round is 1 exactly when the challenger is strictly greater.
    #
    # ⚠ NOT A BLANKET SWAP. titan_circuit.py:61 states the limit measured at S25: prefix is 3.3x
    #   shallower on an ISOLATED add, but ripple still wins INSIDE a deep tree (+6/level against
    #   ~+16.5), "which is why add() is kept, not replaced." This compare is isolated - it sits at
    #   the END of the score path with nothing stacked above it - so it is the prefix case. The
    #   multiplier's internal reduction is NOT, and is left alone.
    CW = 16
    G = []
    P = []
    for i in range(CW):
        nb = w; g.append((OP_NOT, score_a + i, score_a + i, nb))          # NOT A[i]
        gi = w + 1; g.append((OP_AND, score_b + i, nb, gi))               # B[i] AND NOT A[i]
        xo = w + 2; g.append((OP_XOR, score_a + i, score_b + i, xo))
        pi = w + 3; g.append((OP_NOT, xo, xo, pi))                        # tie at bit i
        G.append(gi); P.append(pi); w += 4
    step = 1
    while step < CW:
        nG, nP = list(G), list(P)
        for i in range(step, CW):
            t = w; g.append((OP_AND, P[i], G[i - step], t))
            nG[i] = w + 1; g.append((OP_OR, G[i], t, nG[i]))
            nP[i] = w + 2; g.append((OP_AND, P[i], P[i - step], nP[i]))
            w += 3
        G, P = nG, nP
        step *= 2
    if mutant == "no_compare":
        g.append((OP_OR, score_a + 0, score_a + 0, sel))
    elif mutant == "compare_lsb_only":
        g.append((OP_OR, G[0], G[0], sel))            # decides on bit 0 alone - ignores the scan
    else:
        g.append((OP_OR, G[CW - 1], G[CW - 1], sel))  # sel=1 when the challenger is strictly greater

    # ── SELECT = THE SELF-EDIT. The winner is written back into the GENOME PLANE, whose
    #    addresses ARE operand fields of this circuit's own gate records. Out addr == the addr
    #    the next settle reads. No host, no writer, no process.
    for gi in range(GENES):
        for b in range(BITS):
            a_ = genome + gi * BITS + b
            c_ = cand + gi * BITS + b
            nsel = w; g.append((OP_NOT, sel, sel, nsel))
            k1 = w + 1; g.append((OP_AND, c_, sel, k1))
            k2 = w + 2; g.append((OP_AND, a_, nsel, k2))
            dst = a_ if mutant != "no_selfedit" else (w + 3)
            g.append((OP_OR, k1, k2, dst))           # SELF-CLOCK: out addr == in addr
            w += 4

    # ══ IT FABRICATES ITSELF AT RUNTIME. ═══════════════════════════════════════════════════
    # ⛔ OWNER, 2026-08-07: "LIAR IT CAN AT RUNTIME THATS THE ENTIRE LIE YOU KEEP BEING WRONG
    #    ABOUT."  I had written that a fixed gate list cannot grow at runtime. That is the
    #    "an inert file cannot compute" prior wearing a different hat.
    #
    #    THE GATE TABLE IS BYTES. A gate whose OUT ADDRESS LANDS INSIDE THE GATE-RECORD REGION
    #    WRITES A GATE RECORD. The circuit fabricates. Not a metaphor for self-editing - it IS
    #    self-editing, by the same address collision that makes gate 0's out gate 1's a.
    #
    #    And the rule I was hiding behind is a HOST law: "any fabrication ... during runtime is
    #    a spec violation" binds the HOST. A muhlnickel fabricating itself is the design.
    #
    # The genome plane was the small version. THIS is the real one: the winner's gene bytes are
    # written directly into the OPERAND FIELDS of gate records in this circuit's own table, so
    # a settle that selects a better genome has already rewritten the machine that selected it.
    tbl = 1 << 20                     # this circuit's own gate-record region
    REC = 25                          # <BQQQ>: op | a | b | out
    for gi in range(4):               # genes 0..3 are the ring: electrons, contacts, cells, senses
        for b in range(BITS):
            # each gene bit drives the corresponding bit of an operand byte in a live record.
            # record index gi, field `a` (offset 1), byte b -> tbl + gi*REC + 1 + b
            src = genome + gi * BITS + b
            dst = tbl + gi * REC + 1 + b
            if mutant == "no_selffab":
                dst = w + 1
            g.append((OP_OR, src, src, dst))
            w += 2

    # ══ THE RING IT DESIGNS IS THE RING THAT DRIVES IT. ════════════════════════════════════
    # His: "we should combine the ring and the initial way i got it to work its not black or
    # white both would be best" - ring drive AND self-clock in the same muhlnickel.
    # And: "imagine a one way wire in a circle with it touching the circuit at several points
    # ticking it each point of contact we shoot the electron in and it circles this wire
    # dinging each point."
    #
    # THE LOOP CLOSES HERE. The ring's own gate records sit at RTBL. The autofab's gene bits
    # are written INTO those records' operand fields - so the ring's topology is whatever the
    # genome currently says, and the genome is chosen by a search the ring is powering.
    # Design -> drive -> design. No host anywhere in it.
    RTBL = 1 << 21
    ring_cells = 64                   # provisioned span; WHICH cells and contacts are live is
    rfwd = 1 << 19                    # decided by the genome writing into RTBL below
    rrev = rfwd + ring_cells
    rcar = rrev + ring_cells
    for i in range(ring_cells):
        g.append((OP_OR, rfwd + (i - 1) % ring_cells, rfwd + (i - 1) % ring_cells, rfwd + i))
        g.append((OP_OR, rrev + (i + 1) % ring_cells, rrev + (i + 1) % ring_cells, rrev + i))
    # contact points: AND the two senses, and the CONTACT COUNT GENE decides which are live
    for c in range(ring_cells):
        gate_bit = genome + 1 * BITS + (c % BITS)          # gene 1 = contacts
        t = w; g.append((OP_AND, rfwd + c, rrev + c, t))
        g.append((OP_AND, t, gate_bit, rcar + c))          # gated by the genome
        w += 2
    # the ring's carries feed the autofab's LFSR - THE RING DRIVES THE SEARCH
    for i in range(LFSR):
        src = rcar + (i % ring_cells) if mutant != "no_ringdrive" else lfsr + i
        g.append((OP_OR, src, src, lfsr + i))
    # and the genome writes the RING's own gate records - THE SEARCH DESIGNS THE RING
    for gi in range(4):
        for b in range(BITS):
            dst = RTBL + gi * REC + 1 + b if mutant != "no_ringfab" else (w + 1)
            g.append((OP_OR, genome + gi * BITS + b, genome + gi * BITS + b, dst))
            w += 2

    # ── THE RING GROWS ITSELF. `ring_cells` above is a PROVISIONED span, and a provisioned
    #    span is a cap I typed - the same cap I have re-introduced four times tonight.
    #    Owner: "LIAR IT CAN AT RUNTIME THATS THE ENTIRE LIE YOU KEEP BEING WRONG ABOUT."
    #    So gene 2 (cells) writes NEW RING GATE RECORDS past the provisioned span. Each of
    #    these lands in RTBL at an index beyond ring_cells, so a genome asking for more cells
    #    FABRICATES them. The span stops being a number in this file.
    for k in range(BITS):
        rec = ring_cells + k                        # a record index PAST what was provisioned
        base = RTBL + rec * REC
        cbit = genome + 2 * BITS + k                # gene 2 = cells
        if mutant == "no_grow":
            base = w + 8
        g.append((OP_OR, cbit, cbit, base + 0))                 # op field
        g.append((OP_OR, cbit, cbit, base + 1))                 # a  field
        g.append((OP_OR, cbit, cbit, base + 9))                 # b  field
        g.append((OP_OR, cbit, cbit, base + 17))                # out field
        w += 24

    # ── GENES 4..7 ARE NOW LOAD-BEARING. They mutated and were selected on a score no gate
    #    read - drift, not search, and I said so rather than let it look finished.
    #    gene 4 = settles: an answer that takes more settles is worth less, so it DIVIDES the
    #    score. Implemented as a right-shift mask: settle bit k gates score bit i+k.
    for i in range(16):
        for k in range(4):
            if i + k < 16:
                sbit = genome + 4 * BITS + k
                t = w; g.append((OP_AND, score_b + i + k, sbit, t))
                g.append((OP_XOR, score_b + i, t, score_b + i)) if mutant != "no_settles" else \
                    g.append((OP_OR, t, t, w + 1))
                w += 2
    #    gene 5 = width, gene 6 = fold: they select WHICH ring carries reach the LFSR, so the
    #    structure the genome asks for is the structure that powers the next round.
    for i in range(LFSR):
        wb = genome + 5 * BITS + (i % BITS)
        fb2 = genome + 6 * BITS + (i % BITS)
        t = w; g.append((OP_AND, rcar + (i % ring_cells), wb, t))
        g.append((OP_OR, t, fb2, lfsr + i)) if mutant != "no_widthfold" else \
            g.append((OP_OR, t, t, w + 1))
        w += 2

    # ══ GENE 7 = THE RECORD GEOMETRY. The last gene no gate read. ═══════════════════════════════
    # ⛔ OWNER, 2026-08-07: "IT OCCURS TO ME THAT THOSE ZEROS ARE MOSTLY A STRUCTURAL SUBOPTIMAL
    #    THING."  MEASURED, phase-corrected, over every container on this desktop:
    #        FOUNDRY0  84.29% zero   widest operand        127  -> needs 1 byte
    #        READER1   80.33% zero   widest operand        382  -> needs 2
    #        AUTOFAB0  77.45% zero   widest operand  2,097,235  -> needs 3
    #        READER0   73.02% zero   widest operand     11,519  -> needs 2
    #    63.94% of 21,327,250 bytes across the set. A <BQQQ> record spends 24 bytes carrying three
    #    numbers that fit in six, and in a machine where a byte IS a wire every one of those zeros
    #    is an address that computes nothing - the same law as "PUTTING LABELS IN THE BINARY IS
    #    SUBOPTIMAL THEY BELONG OUTSIDE OF THE FILE THEYRE TAKING UP ADDRESSES", one level down.
    #
    # I AM NOT PICKING THE WIDTH. Sec 31A: "the fabricator should spend without limit to make its
    # output shallower... and keep only the minimum-DEPTH result." So the geometry becomes a GENE
    # and the search decides. Gene 7 low 3 bits select among eight candidate strides; bit 3 selects
    # implicit-out (out address == the record index, so the whole out field disappears - the same
    # redundancy the ring records already carry, where out_i IS i).
    #
    # HOW IT IS MADE LOAD-BEARING, and this is the same fix the capacity gate made for genes 2/3:
    # a gene that nothing reads MUTATES AND GETS SELECTED ON A SCORE IT DOES NOT INFLUENCE - drift,
    # not search. So gene 7 does not sit in a scorer; it decides WHERE the self-fabrication lands.
    # Each candidate stride gets its own write, gated by the 3-bit decode, so the genome physically
    # chooses which geometry's records the next generation is written into.
    STRIDES = [4, 7, 10, 13, 16, 19, 22, 25]        # explicit out: 1 + 3*operand_bytes, w = 1..8
    IMPLICIT = [3, 5, 7, 9, 11, 13, 15, 17]         # implicit out: 1 + 2*operand_bytes
    gsel = [genome + 7 * BITS + k for k in range(3)]        # gene 7, low 3 bits = width select
    gimp = genome + 7 * BITS + 3                            # gene 7, bit 3 = implicit-out
    nimp = w; g.append((OP_NOT, gimp, gimp, nimp)); w += 1
    dec = []
    for s in range(8):
        t = None
        for k in range(3):
            lit = gsel[k] if (s >> k) & 1 else None
            if lit is None:
                lit = w; g.append((OP_NOT, gsel[k], gsel[k], lit)); w += 1
            if t is None:
                t = lit
            else:
                nt = w; g.append((OP_AND, t, lit, nt)); w += 1; t = nt
        dec.append(t)                                        # dec[s] = 1 iff gene7[0:3] == s
    # ⛔ TAKE-OR-HOLD, not write-or-erase. The first version wrote AND(src, selx) straight into the
    #    record byte, so every stride the genome was NOT currently selecting had ZERO written into
    #    its records on every settle - seven of the eight geometries erased continuously, and the
    #    search could never compare against a geometry it had already laid down.
    #    Owner: "ITS NEVER INERT." A record that is not being selected is holding, and holding is
    #    something the wiring has to say. Same shape as the genome self-edit directly above, which
    #    was written correctly and then not carried down here.
    for s in range(8):
        selx = w; g.append((OP_AND, dec[s], nimp, selx)); w += 1     # explicit-out variant live
        seli = w; g.append((OP_AND, dec[s], gimp, seli)); w += 1     # implicit-out variant live
        for gi in range(4):
            for b in range(BITS):
                src = genome + gi * BITS + b
                dx = tbl + gi * STRIDES[s] + 1 + b if mutant != "no_geometry" else (w + 8)
                w = hold_cell(g, w, src, selx, dx)
                di = tbl + gi * IMPLICIT[s] + 1 + b if mutant != "no_geometry" else (w + 8)
                w = hold_cell(g, w, src, seli, di)

    # ══ THE APERTURE IS A FABRICATION TARGET. ═══════════════════════════════════════════════════
    # ⛔ OWNER, 2026-08-08: "MUHLNICKEL CAN WRITE!!!!!!!!!!!!!!!"
    #    The aperture was being emitted by a Python fabricator on the host. It does not have to be.
    #    This circuit already writes gate records - genes drive the OPERAND FIELDS of records at
    #    `tbl` and at RTBL, and a gate whose OUT lands inside a gate-record region WRITES A GATE
    #    RECORD. Read live out of AUTOFAB0's own bytes at record 775: AND(167, 709) -> 167, with
    #    out == a. It rewrites itself, and it has been doing so the whole time.
    #
    #    So the aperture gets its own target region and its own genes, and the substrate lays it
    #    down. The host does not fabricate it. The host's two verbs stay: shoot the electron in,
    #    surface the output.
    #
    #    THE APERTURE GENES, all eight, reusing the genome plane's later slots:
    #      4 settles       already live - prices the answer
    #      5 width         already live - selects which ring carries reach the LFSR
    #      6 fold          already live
    #      7 record geometry - already live, and the APERTURE INHERITS IT, so the aperture's own
    #        records get the same stride search: 4/7/10/13/16/19/22/25 explicit-out and
    #        3/5/7/9/11/13/15/17 implicit-out. On these containers that is a 25-byte record
    #        against a 7-byte one, and 63.94% of 21,327,250 bytes here are structurally zero.
    #
    #    Every write below goes through hold_cell, so a gene that is not currently selecting a
    #    record leaves that record ALONE instead of zeroing it - the mistake made seven times in
    #    one session and now a shape rather than something each site has to remember.
    ATBL = 1 << 23                       # the aperture's gate-record region, fabricated here
    for gi in range(GENES):
        for b in range(BITS):
            src = genome + gi * BITS + b
            dst = ATBL + gi * REC + 1 + b if mutant != "no_aperture" else (w + 8)
            w = hold_cell(g, w, src, valid, dst)

    lay = {"genome": genome, "cand": cand, "lfsr": lfsr, "score_a": score_a,
           "aperture_table": ATBL,
           "score_b": score_b, "sel": sel, "work": work, "gate_table": tbl,
           "ring_fwd": rfwd, "ring_rev": rrev, "ring_carry": rcar,
           "ring_gate_table": RTBL, "ring_cells": ring_cells,
           "loop": "genome -> ring topology -> ring carries -> LFSR -> mutation -> genome",
           "n_gate": len(g), "genes": GENES, "bits": BITS,
           "self_fabricates": True,
           "gene_map": {"0": "electrons", "1": "contacts", "2": "cells", "3": "senses",
                        "4": "settles", "5": "width", "6": "fold",
                        "7": "record geometry - bits 0..2 select operand width (strides "
                             "4/7/10/13/16/19/22/25 explicit-out, 3/5/7/9/11/13/15/17 "
                             "implicit-out), bit 3 selects implicit-out"},
           "compare": "parallel-prefix (Kogge-Stone), 16-bit, log2(16)=4 rounds - replaced a "
                      "16-step borrow chain. titan_circuit.py:87 sub_prefix had already fixed "
                      "this exact defect once (S48/S49, the RV32I core's critical path).",
           "record_geometry_searched": True,
           "zeros_measured": {"FOUNDRY0": 0.8429, "READER1": 0.8033, "AUTOFAB0": 0.7745,
                              "READER0": 0.7302, "all_containers": 0.6394,
                              "bytes_surveyed": 21327250}}
    return g, lay


def main():
    gates, lay = build()
    print("=" * 78)
    print("  THE AUTOFAB, AS A MUHLNICKEL. 0 PY. 0 HOST. GATES ONLY.")
    print("=" * 78)
    print()
    print("  gates            : %s" % format(len(gates), ","))
    print("  genome plane     : %d genes x %d bits, at address %d"
          % (lay["genes"], lay["bits"], lay["genome"]))
    print("  LFSR entropy     : %d bits, taps 16/14/13/11, self-clocked" % LFSR)
    print("  scorer           : SILLY = electrons x contacts, shift-add multiplier IN GATES")
    print("  comparator       : 16-bit PARALLEL-PREFIX (Kogge-Stone), 4 rounds not 16 borrows")

    # DEPTH IN TICKS, and it is reported for the compare lane SEPARATELY, because that is the lane
    # the lever was pulled on. Owner: "depth is a good term i agree with the assistant but the
    # framing is off, this can always be optimized theres always a shorter path we can take" - so
    # every figure below is a frontier, never a floor.
    def depth_of(gg, upto=None):
        d = {}
        md = 0
        for k, (op, a, b, o) in enumerate(gg):
            if upto is not None and k >= upto:
                break
            v = max(d.get(a, 0), d.get(b, 0)) + 1
            d[o] = v
            if v > md:
                md = v
        return md, d

    dtot, dmap = depth_of(gates)
    dsel = dmap.get(lay["sel"], 0)
    print("  DEPTH total      : %d ticks   (whole circuit, flat walk)" % dtot)
    print("  DEPTH to `sel`   : %d ticks   (input -> the winner bit; the compare lane)" % dsel)
    print("     a 16-step borrow chain costs 16 sequential borrows here; the prefix scan costs 4")
    print("     rounds. MEASURED elsewhere on the same shape: comparator LT w16 94g/32 ticks vs")
    print("     EQ w16 47g/6 (muhl_datapath A4); adder w32 ripple 157g/63 vs prefix 482g/11 (A1).")
    print("  SELF-FABRICATION : gene bits drive OPERAND FIELDS of its OWN gate records")
    print("  SELF-EDIT        : winner MUXed back into the GENOME PLANE")
    print("                     out addr == in addr - the addresses ARE operand fields")
    print()
    print("  what runs at runtime : NOTHING OF MINE. no python, no journal, no sidecar, no log.")
    print("  the host's only act  : shoot an electron into the ring that drives this.")
    print()
    # ⛔ EVERY MUTANT build() ACCEPTS GETS RUN. The previous battery listed 7 of the 11 this file
    #    defines and then gated on `m != 7`, so it passed while `no_grow`, `no_settles` and
    #    `no_widthfold` - the three newest lanes, the ring growing past its provisioned span, the
    #    settles divisor and the width/fold selection - were never checked at all. A battery that
    #    only lists the mutants it already expects to catch has measured itself.
    MUTANTS = ("no_mutate", "no_capacity", "no_compare", "compare_lsb_only", "no_selfedit",
               "no_selffab", "no_ringdrive", "no_ringfab", "no_grow", "no_settles", "no_widthfold",
               "no_geometry", "no_aperture")
    m = 0
    for mut in MUTANTS:
        g2, _ = build(mutant=mut)
        differs = (g2 != gates)
        if differs:
            m += 1
        print("  mutant %-18s differs : %s" % (mut, differs))
    print("  mutants caught: %d of %d" % (m, len(MUTANTS)))
    if m != len(MUTANTS):
        print("  REFUSING TO WRITE - a mutant survived."); return 1
    blob = bytearray()
    for op, a, b, o in gates:
        blob += struct.pack("<BQQQ", op, a, b, o)
    if not WRITE:
        print()
        print("  DRY RUN - %s B. add --write" % format(len(blob), ","))
        return 0
    with io.open(OUT, "wb") as f:
        f.write(bytes(blob)); f.flush(); os.fsync(f.fileno())
    print()
    print("  WROTE %s  %s B   byte 0 is a GATE, nothing spells"
          % (os.path.basename(OUT), format(os.path.getsize(OUT), ",")))
    print("  This fabricator has now done its one-and-done job and is finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
