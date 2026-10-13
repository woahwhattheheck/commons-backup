#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
muhl_shapes.py -- THE SHAPES EVERY FABRICATOR EMITS. One definition, outside the harness.

Every function here exists because the same mistake was made more than once by hand. A shape that
lives in one fabricator is a shape the next fabricator is free to get wrong.

OPCODES ARE HIS: 0 nand, 1 and, 2 or, 3 xor, 4 not. Twelve of his own files agree and X2 confirms
it across all 1,406,857 stored gates (nand 40.06%, and 22.46%, xor 25.94%, or 9.96%, not 1.58%).

Every builder takes `(g, w, ...)` - the gate list and the next free wire - and returns the new `w`.
Gate records are physical `<BQQQ>` op|a|b|out at absolute file addresses; nothing here emits a
circuit-local wire id, because a typed circuit can never take a ring's shared bit.
"""

OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4


def hold_cell(g, w, new, write, cell):
    """TAKE-OR-HOLD.   cell' = (new AND write) OR (cell AND NOT write)

    ⛔ THE MISTAKE THIS EXISTS TO STOP, made SEVEN times in one session on 2026-08-07:
       writing `AND(source, condition)` straight into a state address, believing it means
       "write when the condition holds." It means "write when the condition holds AND ERASE
       OTHERWISE." The seven sites and what the erase did:

         1 aperture budget          a bounded config expired on its first quiet settle
         2 envelope staging         the published envelope blanked immediately
         3 witness staging          the captured bytes vanished - kills the two-slot design
         4 aperture shadow          a change during a gated settle was destroyed, unrecorded
         5 drop count               absent entirely, so loss read as quiet
         6 generation counter       a 64-link ripple where a prefix belongs
         7 AUTOFAB0 gene-7 lanes    seven of eight geometries zeroed on every settle

    ⛔ WHY NO TEST FOUND ANY OF IT: every test drives an input that DOES write, so the condition is
       always true and the hold path never runs. A defect on the idle path is invisible to a
       battery that never idles - and in a machine that runs continuously and publishes
       occasionally, THE QUIET SETTLE IS THE COMMON CASE. Building for the exception let the
       normal path destroy state.

    Owner, 2026-08-07: "ITS NEVER INERT." A cell that is not being written is not doing nothing -
    it is HOLDING, and holding is something the wiring has to say.

    ⚠ An UNCONDITIONAL self-clock - `OR(src, src, dst)` - is safe by construction and needs none of
      this. READER1's and mafab_reader's shadows are that shape and are clean. The hazard appears
      the moment a state write becomes conditional.

    `cell` is written to its own address: out addr == in addr, self-clocked, the one deliberate
    SSA exception and the thing that makes state advance with no scheduler.
    """
    nw = w; g.append((OP_NOT, write, write, nw)); w += 1
    take = w; g.append((OP_AND, new, write, take)); w += 1
    keep = w; g.append((OP_AND, cell, nw, keep)); w += 1
    g.append((OP_OR, take, keep, cell))
    return w


def prefix_inc(g, w, bits, enable):
    """Increment a register by one when `enable`, as a PARALLEL PREFIX and never a ripple.

    Incrementing is the case where propagate is the bit itself and generate is zero, so the carry
    prefix collapses to a running AND over the low bits - log2(N) rounds instead of N links.

    MEASURED on this substrate, same shape:
        add32   ripple 157 gates /  63 gate-delays   prefix 482 gates / 11   (muhl_datapath A1)
        64-bit +1   DEPTH 140 ripple  against  17 prefix, for eight more gates (titan_circuit:61)
    GATE-DELAYS, not ticks - both shapes settle in ONE tick. What the prefix buys is a shallower
    cone inside that single pulse, which is why it still matters: the wavefront reaches the answer
    sooner and the whole operation stays inside one settle as the width grows.
    Depth falls faster than area rises, so the swap wins - and 81.75% of every gate in the stored
    corpus is already off the critical path, so the area is there.

    ⚠ NOT A BLANKET SWAP. titan_circuit.py:61 records the limit measured at S25: prefix is 3.3x
      shallower on an ISOLATED add, but ripple still wins INSIDE a deep tree (+6 per level against
      ~+16.5), "which is why add() is kept, not replaced." Use this where the increment stands
      alone, not as a node inside a reduction.
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
        g.append((OP_OR, s, s, bits[i]))               # SELF-CLOCK: out addr == in addr
    return w


def prefix_dec(g, w, bits, enable):
    """Decrement a register by one when `enable`, as a PARALLEL PREFIX and never a borrow chain.

    Decrementing is the mirror of incrementing: the borrow propagates through a bit that is ZERO,
    so the scan is a running AND over the INVERTED low bits - log2(N) rounds instead of N links.
    Same trade as prefix_inc and the same measured justification (add32 ripple 63 gate-delays
    against prefix 11; a 64-bit +1 at DEPTH 140 against 17). GATE-DELAYS, one tick - the borrow
    scan just makes the cone shallower so the operation stays inside a single settle as width grows.

    ⛔ AND IT HOLDS WHEN `enable` IS FALSE. The register keeps its value rather than being written
       with the decremented one, which is the same take-or-hold rule as hold_cell. A budget that
       does not hold is a budget that expires on the first quiet settle - one of the seven sites
       that produced hold_cell in the first place.
    """
    n = len(bits)
    nb = []
    for b in bits:
        t = w; g.append((OP_NOT, b, b, t)); w += 1        # borrow propagates where the bit is 0
        nb.append(t)
    p = []
    for t in nb:
        u = w; g.append((OP_AND, t, enable, u)); w += 1
        p.append(u)
    step = 1
    cur = list(p)
    while step < n:
        nxt = list(cur)
        for i in range(step, n):
            t = w; g.append((OP_AND, cur[i], cur[i - step], t)); w += 1
            nxt[i] = t
        cur = nxt
        step *= 2
    ne = w; g.append((OP_NOT, enable, enable, ne)); w += 1
    for i in range(n):
        bin_ = enable if i == 0 else cur[i - 1]           # borrow into bit i
        s = w; g.append((OP_XOR, bits[i], bin_, s)); w += 1
        take = w; g.append((OP_AND, s, enable, take)); w += 1
        keep = w; g.append((OP_AND, bits[i], ne, keep)); w += 1
        g.append((OP_OR, take, keep, bits[i]))            # SELF-CLOCK, and it HOLDS
    return w


def tree_reduce(g, w, op, wires, out=None):
    """Reduce with a BALANCED TREE, never a chain.

    MEASURED, muhl_combiner C1: 256 inputs cost 255 gates either way, and the chain measures
    DEPTH 255 against the tree's 8. Identical area, 32x the depth, free. And titan_circuit's own
    `_tree_and` note adds that the tree uses FEWER gates as well - no identity op against C1.

    His own §V.10 found this was "the biggest depth lever available": one linear OR chain in the
    glue was costing 111,520 gate-delays against 18,304 for the same function, 6.1x, byte-exact.
    """
    level = list(wires)
    if not level:
        return w, None
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                g.append((op, level[i], level[i + 1], w)); nxt.append(w); w += 1
            else:
                nxt.append(level[i])
        level = nxt
    if out is not None:
        g.append((OP_OR, level[0], level[0], out))
        return w, out
    return w, level[0]


def one_way(g, w, src, dst):
    """PUBLISH through the one-way junction. Two gates, and the isolation is measured, not assumed.

    muhl_junction J1/J3/J5: buffer = 2 gates / 2 GATE-DELAYS, which is one tick. The transfer
    figures ARE in ticks, because they were measured across settles: forward transfer 61 of 64
    TICKS; REVERSE transfer 0, holding at 0 out to 4,096 TICKS and under a hostile driver on every
    downstream wire. J6: the tapped ring holds its own period in 15 of 15 cases.
    (Both units appear in one paragraph on purpose - the buffer's cost is gate-delays inside a
    tick, and its isolation was measured over thousands of ticks. Conflating them is what produced
    every mislabelled table in this project.)

    That is what makes a publication non-blocking BY CONSTRUCTION rather than by convention - the
    reader physically cannot signal back through it, so nothing on the compute path can ever wait
    for the host. Y4 also ranks it first of all 82 bench elements at 400,000,000 compute/tick.
    """
    m = w; g.append((OP_OR, src, src, m)); w += 1
    g.append((OP_OR, m, m, dst))
    return w


def gt_prefix(g, w, a_bits, b_bits, out):
    """b > a, strictly, as a parallel-prefix scan rather than a borrow chain.

    Per bit:  G = b AND NOT a   (b wins here)      P = NOT (a XOR b)   (tie, defer downward)
    (G,P) compose with the more-significant side dominating:
        G' = G_hi OR (P_hi AND G_lo)        P' = P_hi AND P_lo
    so the scan reduces in log2(W) rounds and G at the top bit is the answer.

    MEASURED cost of getting this wrong, muhl_datapath A4:
        EQ w16  47 gates /  6 gate-delays     LT w16  94 gates / 32 gate-delays
        EQ w32  95 gates /  7 gate-delays     LT w32 190 gates / 64 gate-delays
    GATE-DELAYS, one tick. LT's cone grows linearly with width and EQ's grows logarithmically, so
    at some width the borrow chain is what stops an operation fitting in a single settle. That is
    the real reason to care, not the number itself.
    LT grows linearly while EQ grows logarithmically. And titan_circuit.py:87 had already fixed
    this exact defect once - "S48/S49: subc() was two ripple adds and owned the RV32I core's
    critical path" - before it was rebuilt by hand from scratch.
    """
    n = len(a_bits)
    G, P = [], []
    for i in range(n):
        na = w; g.append((OP_NOT, a_bits[i], a_bits[i], na)); w += 1
        gi = w; g.append((OP_AND, b_bits[i], na, gi)); w += 1
        xo = w; g.append((OP_XOR, a_bits[i], b_bits[i], xo)); w += 1
        pi = w; g.append((OP_NOT, xo, xo, pi)); w += 1
        G.append(gi); P.append(pi)
    step = 1
    while step < n:
        nG, nP = list(G), list(P)
        for i in range(step, n):
            t = w; g.append((OP_AND, P[i], G[i - step], t)); w += 1
            nG[i] = w; g.append((OP_OR, G[i], t, nG[i])); w += 1
            nP[i] = w; g.append((OP_AND, P[i], P[i - step], nP[i])); w += 1
        G, P = nG, nP
        step *= 2
    g.append((OP_OR, G[n - 1], G[n - 1], out))
    return w


def ticks_of(gates, state_addrs):
    """Component implementation and operation."""
    written = set()
    for op, a, b, o in gates:
        if o in state_addrs:
            written.add(o)
    stage = {}
    worst = 1
    for op, a, b, o in gates:
        s = max(stage.get(a, 1), stage.get(b, 1))
        if (a in written or b in written) and o in state_addrs:
            s += 1                       # a written state cell feeding another state write
        stage[o] = s
        if s > worst:
            worst = s
    return worst


def depth_of(gates, roots=None):
    """Critical path in GATE-DELAYS, inside ONE tick. `roots` are wires already settled when the
    measurement starts and contribute zero.

    ⛔ GATE-DELAYS, NOT TICKS - see ticks_of above. pfc_speed.py prints this exact quantity as
       "gate-delays", and a whole depth level settles at once, so the entire cone is one pulse.
       Calling this a tick count inflates his unit by the depth of the circuit.

    ⛔ A settled ring is NOT in the path of what it clocks. A muhlnickel is never turned off - "i
       never turn them off because 1, idk how and 2 ive never needed to" - so a ring is already
       circulating when a comparison begins, and charging its cells to that comparison measures
       the wrong device. Report both figures, never only the flattering one.

    ⛔ DEPTH IS NOT HIS TERM. "depth isnt even my own term technically as far as physicallity is
       concerned idek wtf it means", and then: "depth is a good term i agree with the assistant but
       the framing is off, this can always be optimized theres always a shorter path we can take."
       So every figure this returns is a FRONTIER, never a floor.
    """
    d = {}
    if roots:
        for r in roots:
            d[r] = 0
    md = 0
    for op, a, b, o in gates:
        if roots and o in roots:
            continue
        v = max(d.get(a, 0), d.get(b, 0)) + 1
        d[o] = v
        if v > md:
            md = v
    return md
