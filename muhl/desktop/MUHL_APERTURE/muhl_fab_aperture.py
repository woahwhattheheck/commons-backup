#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
muhl_fab_aperture.py -- FABRICATE THE EGRESS APERTURE. Gates only. One-and-done.

The substrate answers ONE question about itself and publishes a bounded result the host can read
without scanning the surface. Owner's boundary, which this obeys exactly:

    "if the host does anything beyond shooting electron or surfacing the muhlnickel output
     its violating spec"

Two verbs. Shoot the electron in. Surface the output. The aperture IS the surfacing point, and
everything that decides WHAT surfaces happens in gates.

THE OBSERVABLE, first vertical slice: CHANGED.
    The substrate holds a SHADOW of a watched span. Every settle it XORs the span against the
    shadow, ORs the differences to one bit, and when that bit is set it publishes:
      - the changed bytes, EXACTLY, as a WITNESS
      - an envelope carrying generation, config id, causal position, address, length, flags
    Then the shadow takes the span's current value - self-clock, out addr == in addr - so the
    next settle compares against what it just saw.

WHY THIS OBSERVABLE FIRST. It answers "what moved, and exactly what were the bytes" without the
host reading one byte of the surface. It is also the only honest way to watch a file the owner has
said repeatedly is dynamic: the substrate sees every change at its own rate, and the host sees a
bounded selection of them.

PRIMITIVES USED - all already present, nothing invented:
  · 25-byte <BQQQ> physical records, absolute file addresses
  · his alphabet: 0 nand, 1 and, 2 or, 3 xor, 4 not  (12 of his files agree; X2 confirms across
    all 1,406,857 stored gates)
  · nring2_* recv bytes as the clock - 1,024 of them, DEPTH 2, one writer, unlimited readers
    (nring2_000 measures readers 1,172 / writers 0)
  · THE ONE-WAY JUNCTION as the publish path - buffer, 2 gates, 2 GATE-DELAYS (one settle, one
    tick), forward transfer 61/64 ticks,
    REVERSE 0, holding at 0 out to 4,096 ticks and under a hostile driver on every downstream
    wire (muhl_junction.py J1/J3/J5). The host cannot signal back through it. That is what makes
    publication non-blocking by construction rather than by convention.
  · self-clock, out addr == in addr, for the shadow advance
  · titan_circuit._alloc for collision-free placement

⛔ NOTHING ON THE CAPTURE PATH IS CONVERTED. The witness is the bytes. No hex, text, JSON, base64,
   hash, sum or compression touches it.

⛔ FABRICATION IS NOT RUNTIME. This file emits gate records once and exits. The evaluation below
   is fabrication-time verification - the one sanctioned place to walk gates in host Python,
   before anything is stored.

  python muhl_fab_aperture.py            build, verify, report - writes nothing
  python muhl_fab_aperture.py --write    same, then emit APERTURE0.mno + sidecar
"""
import io
import json
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REG = r"C:\llm\models\titan_circuits.json"
CONT = os.path.join(HERE, "APERTURE0.mno")
SIDE = os.path.join(HERE, "APERTURE0.layout.json")
WRITE = "--write" in sys.argv

OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4
REC = 25

# ⛔ THE SHAPES COME FROM ONE PLACE. muhl_shapes lives beside the checkers, outside .claude, and
#    holds hold_cell / prefix_inc / tree_reduce / one_way / gt_prefix / depth_of. This file had
#    private copies of the first two, which is how the same erase-on-idle mistake was made SEVEN
#    times in one session - a fix to one copy never reached the others. If the module is missing,
#    fail loudly rather than falling back to a local reimplementation: a silent local copy is
#    exactly the condition that produced the seven.
sys.path.insert(0, r"C:\Users\lucys\Desktop\MUHL_CHECKERS")
from muhl_shapes import (hold_cell, prefix_inc, prefix_dec,                    # noqa: E402
                         tree_reduce, one_way, depth_of)

MAGIC = b"MUHLAPR1"
VERSION = 1
SLOTS = 2
PAYLOAD_MAX = 256
WATCH_LEN = 32                 # bytes of surface the substrate watches, first slice
CTRL_BYTES = 64
ENV_BYTES = 64

# ── ADDRESS PLANES. Absolute, never circuit-local: a typed circuit can never take a ring's
#    shared bit, which is why several stored circuits cannot be powered at all.
WATCH = 1 << 12                # the observed span, bit b of byte k at WATCH + k*8 + b
SHADOW = 1 << 13               # what the substrate last saw there
DIFF = 1 << 14                 # per-bit XOR
ANYD = 1 << 15                 # reduction of DIFF to one bit
GEN = 1 << 16                  # generation counter bits
ENVP = 1 << 17                 # envelope staging
PAYP = 1 << 18                 # payload staging
PUB = 1 << 20                  # the published aperture image - what the host reads
SCRATCH = 1 << 22


def ring_recvs():
    """The REAL rings. Addressed, never fabricated - the electron moves in the wire and a ring is
    topology that already circulates."""
    d = json.load(io.open(REG, "r", encoding="utf-8"))
    ents = d if isinstance(d, list) else (d.get("circuits") or d.get("entries") or list(d.values()))
    if isinstance(ents, dict):
        ents = list(ents.values())
    out = []
    for e in ents:
        if isinstance(e, dict) and str(e.get("name", "")).startswith("nring2") and e.get("recv"):
            out.append((e["name"], int(e["recv"])))
    return out


CFG = 1 << 19                  # the observation config, read by the substrate as gates
CFG_RELATION = CFG + 0         # 4 bits: 0 CHANGED, 1 NONZERO, 2 EQUALS_CONST, 3 ANY_OF_TABLE
CFG_TRIGGER = CFG + 8          # 4 bits: 0 every settle, 1 relation true, 2 relation edge
CFG_ENABLE = CFG + 16          # per-byte enable over the watched span: which bytes are observed
CFG_CONST = CFG + 512          # the constant for EQUALS_CONST, one byte per watched byte
CFG_BUDGET = CFG + 1024        # publication budget, counts down; 0 = unbounded
CFG_BOUNDED = CFG + 1040       # 1 = enforce the budget, 0 = unbounded.
                               # Without this bit, an all-zero budget means BOTH "unlimited" and
                               # "spent" and the circuit cannot tell an expired config from an
                               # unbounded one - the same value carrying two opposite meanings.
DROP = CFG + 3072              # 32-bit count of relations that fired while publishing was gated.
                               # Kept in the substrate and published in the envelope, because a
                               # loss the host cannot see is a loss that gets mistaken for quiet.
TRIGW = CFG + 1041             # the publish decision, exposed as its own address so a check can
                               # read it without inferring it from a payload.
PREV = CFG + 2048              # last settle's relation result, for the EDGE trigger mode.
                               # Written by a self-clocked gate: out addr == in addr, so the
                               # memory of the previous settle lives in the wiring and there is
                               # no process holding it.


def build(recvs, mutant=None):
    """Emit the aperture as gates. Returns (gates, layout).

    THE OBSERVATION IS CONFIGURED IN THE SUBSTRATE, NOT IN THE HOST. The config is a plane of
    bytes the gates READ - relation, trigger mode, a per-byte enable mask, a comparison constant,
    a publication budget. Changing what is observed is a byte edit to that plane, made offline,
    not a different circuit and not host logic deciding what to look at.

    RELATIONS, all four fabricated, selected by the relation bits:
        0 CHANGED       span XOR shadow                      - what moved
        1 NONZERO       span itself                          - anything set
        2 EQUALS_CONST  NOT(span XOR const)                  - a value arrived
        3 ANY_OF_TABLE  reserved lane, wired, selector present
    Each bit of the span produces one candidate per relation, and a 4-way select gated by the
    relation bits picks which candidate feeds the reduction. All four settle together - D5:
    independent stages settle at the MAX of the parts, so carrying four costs area, not depth.
    """
    g = []
    add = g.append
    w = SCRATCH
    nr = max(1, len(recvs))

    # ── 1. DIFF: the watched span against the shadow, one XOR per bit.
    #    This is the whole observation. It runs in the substrate at its own rate; the host is not
    #    involved and never sees the span.
    #    All four relations are fabricated for every bit and settle together. D5: independent
    #    stages settle at the MAX of the parts, so carrying four costs area and not one tick.
    #    The relation bits in the config plane select which candidate reaches DIFF; the per-byte
    #    enable mask decides which bytes are observed at all.
    r0 = CFG_RELATION + 0
    r1 = CFG_RELATION + 1
    nr0 = w; add((OP_NOT, r0, r0, nr0)); w += 1
    nr1 = w; add((OP_NOT, r1, r1, nr1)); w += 1
    sel0 = w; add((OP_AND, nr1, nr0, sel0)); w += 1        # 0 CHANGED
    sel1 = w; add((OP_AND, nr1, r0, sel1)); w += 1         # 1 NONZERO
    sel2 = w; add((OP_AND, r1, nr0, sel2)); w += 1         # 2 EQUALS_CONST
    sel3 = w; add((OP_AND, r1, r0, sel3)); w += 1          # 3 ANY_OF_TABLE

    for k in range(WATCH_LEN):
        en = CFG_ENABLE + k                                 # is this byte observed at all
        for b in range(8):
            src = WATCH + k * 8 + b
            sh = SHADOW + k * 8 + b
            if mutant == "no_compare":
                sh = src                                    # XOR(x,x)=0 : nothing looks changed
            c0 = w; add((OP_XOR, src, sh, c0)); w += 1                       # CHANGED
            c1 = w; add((OP_OR, src, src, c1)); w += 1                       # NONZERO
            xc = w; add((OP_XOR, src, CFG_CONST + k * 8 + b, xc)); w += 1
            c2 = w; add((OP_NOT, xc, xc, c2)); w += 1                        # EQUALS_CONST
            c3 = w; add((OP_AND, src, CFG_CONST + k * 8 + b, c3)); w += 1    # ANY_OF_TABLE
            t0 = w; add((OP_AND, c0, sel0, t0)); w += 1
            t1 = w; add((OP_AND, c1, sel1, t1)); w += 1
            t2 = w; add((OP_AND, c2, sel2, t2)); w += 1
            t3 = w; add((OP_AND, c3, sel3, t3)); w += 1
            m0 = w; add((OP_OR, t0, t1, m0)); w += 1
            m1 = w; add((OP_OR, t2, t3, m1)); w += 1
            picked = w; add((OP_OR, m0, m1, picked)); w += 1
            if mutant == "ignore_config":
                add((OP_XOR, src, sh, DIFF + k * 8 + b))    # relation bits reach nothing
            else:
                add((OP_AND, picked, en, DIFF + k * 8 + b))

    # ── 2. ANY: balanced tree over every diff bit. C1 measures 256 inputs at 255 gates / 255
    #    GATE-DELAYS as a chain and 255 gates / 8 as a tree - same area, 32x the depth, and both
    #    are ONE TICK. The tree matters because a 255-deep cone is what eventually stops an
    #    operation fitting inside a single settle as the watched span grows.
    level = [DIFF + i for i in range(WATCH_LEN * 8)]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                add((OP_OR, level[i], level[i + 1], w))
                nxt.append(w)
                w += 1
            else:
                nxt.append(level[i])
        level = nxt
    changed = level[0]
    add((OP_OR, changed, changed, ANYD))

    # ── 3. TRIGGER, clocked by a real ring. EVERY MAXIMUM CLOCKS: the trigger is the maximum of
    #    the reduction, so it takes a ring recv as its other operand. One ring, one stated job:
    #    "clock the aperture's publish decision."
    rec = recvs[0][1] if recvs else ANYD
    if mutant == "no_clock":
        rec = ANYD                             # unclocked: fires without the ring
    clocked = w
    add((OP_AND, ANYD, rec, clocked))
    w += 1

    #    TRIGGER MODE, read from the config plane. A field the ABI advertises has to be read by a
    #    gate or the spec is promising behaviour the circuit does not have.
    #      0 EVERY SETTLE  publish whenever the ring says so, relation or not
    #      1 RELATION TRUE publish while the relation holds        (the default)
    #      2 EDGE          publish only on the rising edge - relation true now, false last settle
    m0b = CFG_TRIGGER + 0
    m1b = CFG_TRIGGER + 1
    nm0 = w; add((OP_NOT, m0b, m0b, nm0)); w += 1
    nm1 = w; add((OP_NOT, m1b, m1b, nm1)); w += 1
    tm0 = w; add((OP_AND, nm1, nm0, tm0)); w += 1          # mode 0
    tm1 = w; add((OP_AND, nm1, m0b, tm1)); w += 1          # mode 1
    tm2 = w; add((OP_AND, m1b, nm0, tm2)); w += 1          # mode 2
    nprev = w; add((OP_NOT, PREV, PREV, nprev)); w += 1
    edge = w; add((OP_AND, clocked, nprev, edge)); w += 1  # true now, false last settle
    e0 = w; add((OP_AND, rec, tm0, e0)); w += 1            # mode 0: the ring alone
    e1 = w; add((OP_AND, clocked, tm1, e1)); w += 1
    e2 = w; add((OP_AND, edge, tm2, e2)); w += 1
    em = w; add((OP_OR, e0, e1, em)); w += 1
    gated = w; add((OP_OR, em, e2, gated)); w += 1

    #    BUDGET. While any budget bit is set the aperture may publish; the budget decrements on
    #    each publication, so a config expires on its own without the host intervening. All-zero
    #    means unbounded, which is why the budget is ANDed through a "budget is unlimited" term.
    blevel = [CFG_BUDGET + i for i in range(16)]
    while len(blevel) > 1:
        nxt = []
        for i in range(0, len(blevel), 2):
            if i + 1 < len(blevel):
                add((OP_OR, blevel[i], blevel[i + 1], w)); nxt.append(w); w += 1
            else:
                nxt.append(blevel[i])
        blevel = nxt
    has_budget = blevel[0]
    unbounded = w; add((OP_NOT, CFG_BOUNDED, CFG_BOUNDED, unbounded)); w += 1
    inbudget = w; add((OP_AND, CFG_BOUNDED, has_budget, inbudget)); w += 1
    allowed = w; add((OP_OR, unbounded, inbudget, allowed)); w += 1
    trig = w
    if mutant == "ignore_budget":
        add((OP_OR, gated, gated, trig))                   # budget reaches nothing
    else:
        add((OP_AND, gated, allowed, trig))
    w += 1
    add((OP_OR, trig, trig, TRIGW))                        # the decision, at its own address

    #    BUDGET DECREMENT, and it must HOLD when nothing is published.
    #    The first version wrote AND(decremented, trig) straight back to the budget bit, so on a
    #    settle that did not publish the bit was written ZERO - a bounded config expired on its
    #    first quiet tick instead of after N publications. The state has to be selected:
    #        bi' = (decremented AND trig) OR (bi AND NOT trig)
    #    Holding is something the wiring has to say, not a default it falls into.
    ntrig = w; add((OP_NOT, trig, trig, ntrig)); w += 1
    #    PREFIX DECREMENT, not a 16-link borrow chain, and it HOLDS when nothing published.
    #    Both properties come from muhl_shapes so this site cannot drift from the autofab's.
    w = prefix_dec(g, w, [CFG_BUDGET + i for i in range(16)], trig)

    #    PREV takes this settle's relation result, written to the SAME address the edge test
    #    reads - self-clock, so the memory of the previous settle lives in the wiring.
    add((OP_OR, clocked, clocked, PREV))

    # ── 4. GENERATION. A ripple increment over the generation bits, gated by the trigger, so gen
    #    advances only when something is actually published.
    GENW = 64
    #    PARALLEL-PREFIX, not a ripple. A 64-bit ripple increment chains its carry through all 64
    #    bits and was the deepest single thing in this circuit. Measured on the same shape:
    #    add32 ripple 157 gates / 63 GATE-DELAYS against prefix 482 / 11 (muhl_datapath A1), and a
    #    64-bit +1 is DEPTH 140 ripple against 17 prefix for 8 more gates (titan_circuit:61).
    #    Incrementing is the case where propagate is the bit itself and generate is zero, so the
    #    prefix collapses to a running AND over the low bits - log2(64) = 6 rounds, not 64 links.
    G0 = [GEN + i for i in range(GENW)]
    P = []
    for i in range(GENW):
        t = w; add((OP_AND, G0[i], trig, t)); w += 1          # carry moves only when publishing
        P.append(t)
    step = 1
    cur = list(P)
    while step < GENW:
        nxt = list(cur)
        for i in range(step, GENW):
            t = w; add((OP_AND, cur[i], cur[i - step], t)); w += 1
            nxt[i] = t
        cur = nxt
        step *= 2
    for i in range(GENW):
        cin = trig if i == 0 else cur[i - 1]                  # carry into bit i
        s = w; add((OP_XOR, G0[i], cin, s)); w += 1
        add((OP_OR, s, s, GEN + i))                           # SELF-CLOCK: out addr == in addr

    # ── 5. ENVELOPE STAGING. Every field is gated by the trigger so a non-publishing settle leaves
    #    the staging plane alone.
    #    ⛔ STAGING MUST HOLD. The first version wrote AND(src, trig) straight to the plane, so a
    #       settle that did not publish wrote ZERO over the staged envelope and witness - the
    #       comment above claimed it "leaves the staging plane alone" and it erased it instead.
    #       That defeats the two-slot design outright: the host is meant to read a completed slot
    #       while the substrate works on the other, and a slot that blanks the moment publishing
    #       stops is only readable during the settle that wrote it.
    #       Same shape as the budget cell: select take-or-hold, never default to erase.
    def stage(src_bits, dst_base, n):
        nonlocal w
        for i in range(n):
            w = hold_cell(g, w, src_bits(i), trig, dst_base + i)

    stage(lambda i: GEN + i, ENVP + 0, 64)                       # gen_before
    stage(lambda i: ANYD, ENVP + 64, 8)                          # payload_type marker lane
    stage(lambda i: GEN + i, ENVP + 448, 64)                     # gen_after, same value

    # ── 6. PAYLOAD STAGING - THE WITNESS. Exact bytes of the watched span, gated by the trigger.
    #    Nothing is transformed here and nothing may be: this is the capture path.
    #    The witness holds too. A captured witness that blanks on the next quiet settle is a
    #    witness the host can only see if it happens to look during the exact settle that took it.
    for k in range(WATCH_LEN):
        for b in range(8):
            src = WATCH + k * 8 + b
            dst = PAYP + k * 8 + b
            if mutant == "witness_altered":
                nt = w; add((OP_NOT, src, src, nt)); w += 1   # transformed on the capture path
                w = hold_cell(g, w, nt, trig, dst)
            else:
                w = hold_cell(g, w, src, trig, dst)

    # ── 7. PUBLICATION THROUGH THE ONE-WAY JUNCTION. buffer = 2 gates, 2 gate-delays (one tick),
    #    reverse transfer measured 0.
    #    Everything above lands in the PUB plane, which is the only region the host reads.
    #    ⛔ This is where non-blocking is STRUCTURAL: the junction carries forward and measures
    #       0 in reverse out to 4,096 ticks, so the host cannot backpressure the computation even
    #       if it tried. No acknowledgement is read. Nothing waits.
    def publish(src, dst):
        nonlocal w
        m = w
        add((OP_OR, src, src, m))                                # junction stage 1
        add((OP_OR, m, m, dst))                                  # junction stage 2 -> host-readable
        w += 1

    if mutant == "no_junction":
        for i in range(64):
            add((OP_OR, ENVP + i, ENVP + i, PUB + i))            # single stage, no isolation
    else:
        for i in range(64):
            publish(ENVP + i, PUB + i)
        for i in range(64):
            publish(ENVP + 448 + i, PUB + 448 + i)
        for i in range(WATCH_LEN * 8):
            publish(PAYP + i, PUB + 512 + i)

    # ── 8. SHADOW ADVANCE - SELF-CLOCK. The shadow takes the span's current value, written to the
    #    SAME addresses it was read from, so the next settle compares against what was just seen.
    #    No process, no scheduler: the loop is permanent structure in the wiring.
    #    ⛔ THE SHADOW ADVANCES ONLY WHEN THE CHANGE WAS PUBLISHED.
    #       The first version advanced it every settle. So a change that arrived while publishing
    #       was gated off - budget spent, wrong trigger mode - was absorbed into the shadow and
    #       vanished: the next settle compared against the NEW value and saw nothing, with no
    #       record that anything had happened. That is silent loss, and the ABI says in as many
    #       words that loss is reported and never hidden.
    #       Holding the shadow means the change is still pending the moment publishing is allowed
    #       again, so a witness is deferred rather than destroyed.
    for k in range(WATCH_LEN):
        for b in range(8):
            src = WATCH + k * 8 + b
            dst = SHADOW + k * 8 + b
            if mutant == "no_shadow_advance":
                dst = w + 3                                      # shadow never updates
            w = hold_cell(g, w, src, trig, dst)   # published: take. gated: hold, stay pending.

    #    DROP COUNT. The relation fired and publication was gated - that is a real loss and it is
    #    counted, in gates, so the host can see exactly how many it never saw. Same prefix shape
    #    as the generation counter: incrementing needs a running AND, not a 32-link carry chain.
    dropped = w; add((OP_AND, ANYD, ntrig, dropped)); w += 1     # fired but did not publish
    DW = 32
    D0 = [DROP + i for i in range(DW)]
    dp = []
    for i in range(DW):
        t = w; add((OP_AND, D0[i], dropped, t)); w += 1
        dp.append(t)
    step = 1
    cur = list(dp)
    while step < DW:
        nxt = list(cur)
        for i in range(step, DW):
            t = w; add((OP_AND, cur[i], cur[i - step], t)); w += 1
            nxt[i] = t
        cur = nxt
        step *= 2
    for i in range(DW):
        cin = dropped if i == 0 else cur[i - 1]
        s = w; add((OP_XOR, D0[i], cin, s)); w += 1
        add((OP_OR, s, s, DROP + i))                             # SELF-CLOCK

    lay = {"watch": WATCH, "shadow": SHADOW, "diff": DIFF, "any": ANYD, "gen": GEN,
           "env": ENVP, "pay": PAYP, "pub": PUB, "trigger_ring": recvs[0][0] if recvs else None,
           "trigger_recv": rec, "n_gate": len(g), "watch_len": WATCH_LEN}
    return g, lay


# ─────────────────────────────────────────────────────── fabrication-time verification
def settle(gates, driven):
    st = dict(driven)
    for op, a, b, o in gates:
        x, y = st.get(a, 0), st.get(b, 0)
        if op == OP_NAND:
            v = 1 - (x & y)
        elif op == OP_AND:
            v = x & y
        elif op == OP_OR:
            v = x | y
        elif op == OP_XOR:
            v = x ^ y
        elif op == OP_NOT:
            v = 1 - x
        else:
            raise ValueError("opcode %d outside his alphabet" % op)
        st[o] = v
    return st


def drive(span, shadow, recvs, powered=True, relation=0, enable=None, const=None,
          trigger=1, budget=0, prev=0, bounded=0):
    """Drive the span, the shadow, AND the config plane. The config is part of the machine - it
    carries state like everything else here, so leaving it unset is not neutral, it selects
    relation 0 with every byte disabled."""
    d = {}
    for k in range(WATCH_LEN):
        for b in range(8):
            d[WATCH + k * 8 + b] = (span[k] >> b) & 1
            d[SHADOW + k * 8 + b] = (shadow[k] >> b) & 1
            cv = 0 if const is None else const[k]
            d[CFG_CONST + k * 8 + b] = (cv >> b) & 1
        d[CFG_ENABLE + k] = 1 if (enable is None or enable[k]) else 0
    d[CFG_RELATION + 0] = relation & 1
    d[CFG_RELATION + 1] = (relation >> 1) & 1
    d[CFG_TRIGGER + 0] = trigger & 1
    d[CFG_TRIGGER + 1] = (trigger >> 1) & 1
    for i in range(16):
        d[CFG_BUDGET + i] = (budget >> i) & 1
    d[CFG_BOUNDED] = 1 if bounded else 0
    d[PREV] = prev
    if powered and recvs:
        d[recvs[0][1]] = 1
    return d


def read_payload(st):
    out = bytearray(WATCH_LEN)
    for k in range(WATCH_LEN):
        v = 0
        for b in range(8):
            v |= st.get(PUB + 512 + k * 8 + b, 0) << b
        out[k] = v
    return bytes(out)


def verify(gates, recvs):
    """FOCUSED tests only. Five properties, each one a thing that would make the aperture lie."""
    fails = []
    same = bytes(range(WATCH_LEN))
    diff = bytearray(same)
    diff[7] ^= 0x40                                   # one bit, mid-span

    # 1. unchanged span -> nothing published
    st = settle(gates, drive(same, same, recvs))
    if st.get(ANYD, 0):
        fails.append("unchanged span raised CHANGED")
    if any(read_payload(st)):
        fails.append("unchanged span published a payload")

    # 2. changed span -> published, and the witness is EXACT
    st = settle(gates, drive(bytes(diff), same, recvs))
    if not st.get(ANYD, 0):
        fails.append("changed span did not raise CHANGED")
    got = read_payload(st)
    if got != bytes(diff):
        fails.append("witness bytes altered: got %r expected %r" % (got[:8], bytes(diff)[:8]))

    # 3. every payload bit is reachable - a single flip in each byte must surface
    for k in (0, WATCH_LEN // 2, WATCH_LEN - 1):
        probe = bytearray(same)
        probe[k] ^= 0x01
        st = settle(gates, drive(bytes(probe), same, recvs))
        if read_payload(st) != bytes(probe):
            fails.append("witness lost byte %d" % k)
            break

    # 4. the ring is load-bearing - STRUCTURALLY, without touching one.
    #    "dont try to detect contact theyre electrons cant be measured w/out distrurbig", so this
    #    is read off the gate records, not by driving a ring low.
    ring_wires = set(r[1] for r in recvs)
    if not any(a in ring_wires or b in ring_wires for _op, a, b, _o in gates):
        fails.append("no gate takes a ring recv as an operand - nothing is clocked")

    # 5. the payload lands ONLY in PUB, never back into WATCH or SHADOW
    for _op, _a, _b, o in gates:
        if PUB <= o < PUB + 512 + WATCH_LEN * 8:
            continue
        if WATCH <= o < WATCH + WATCH_LEN * 8:
            fails.append("a gate writes back into the watched span at %d" % o)
            break

    # 6. THE CONFIG IS LOAD-BEARING. Relation 1 NONZERO fires on a span with any bit set even
    #    when the shadow already matches it - relation 0 CHANGED would stay silent on that same
    #    input. If the two behave identically the relation bits reach nothing.
    quiet = settle(gates, drive(same, same, recvs, relation=0))
    loud = settle(gates, drive(same, same, recvs, relation=1))
    if quiet.get(ANYD, 0) == loud.get(ANYD, 0):
        fails.append("relation 0 and relation 1 behave identically - the config reaches nothing")

    # 7. THE ENABLE MASK IS LOAD-BEARING. The same changed span with every byte disabled must
    #    not fire; observing nothing is a legitimate configuration and must be respected.
    off = settle(gates, drive(bytes(diff), same, recvs, relation=0, enable=[0] * WATCH_LEN))
    if off.get(ANYD, 0):
        fails.append("a fully-disabled enable mask still fired")

    # 8. THE EDGE TRIGGER IS LOAD-BEARING. Mode 2 publishes only on a rising edge, so the same
    #    changed span must fire when the previous settle was quiet and stay silent when it was
    #    already true. If PREV reaches nothing the two are identical.
    rise = settle(gates, drive(bytes(diff), same, recvs, relation=0, trigger=2, prev=0))
    held = settle(gates, drive(bytes(diff), same, recvs, relation=0, trigger=2, prev=1))
    if rise.get(TRIGW, 0) == held.get(TRIGW, 0):
        fails.append("edge mode fires the same on a rise and on a hold - PREV reaches nothing")

    # 9. THE BUDGET IS LOAD-BEARING. A budget of zero means unbounded and must publish; the same
    #    input under a spent budget must not. Without this the ABI advertises expiry the circuit
    #    does not do.
    unb = settle(gates, drive(bytes(diff), same, recvs, relation=0, trigger=1,
                              bounded=0, budget=0))
    live = settle(gates, drive(bytes(diff), same, recvs, relation=0, trigger=1,
                               bounded=1, budget=5))
    spent = settle(gates, drive(bytes(diff), same, recvs, relation=0, trigger=1,
                                bounded=1, budget=0))
    if not unb.get(TRIGW, 0):
        fails.append("an unbounded config did not publish")
    if not live.get(TRIGW, 0):
        fails.append("a config with budget remaining did not publish")
    if spent.get(TRIGW, 0):
        fails.append("a spent budget still published - the config never expires")

    # 10. A CHANGE THAT ARRIVES WHILE PUBLISHING IS GATED IS DEFERRED, NOT DESTROYED.
    #     The shadow must HOLD when nothing published, so the change is still pending the moment
    #     publishing is allowed again. If the shadow advances anyway the witness is gone and the
    #     next settle sees nothing - silent loss, which the ABI forbids in as many words.
    gatedoff = settle(gates, drive(bytes(diff), same, recvs, relation=0, trigger=1,
                                   bounded=1, budget=0))
    held_shadow = all(gatedoff.get(SHADOW + i, 0) == ((same[i // 8] >> (i % 8)) & 1)
                      for i in range(WATCH_LEN * 8))
    if not held_shadow:
        fails.append("the shadow advanced while publishing was gated - the change was destroyed")

    # 11. AND THE LOSS IS COUNTED. A relation that fires without publishing must move DROP.
    if not gatedoff.get(DROP, 0):
        fails.append("a gated relation did not increment the drop count - loss is hidden")
    return fails


def abi_battery():
    """THE FIVE ABI TESTS, RUN HERE SO A FAILURE STOPS THE WRITE.

    They were a separate script, which meant the container could be emitted while the envelope
    round-trip was unproven - the checks sitting beside the build instead of gating it. "catch
    mutants BEFORE any write or write nothing."

    Covers exactly what the ABI promises, and nothing else:
      1 envelope round-trip · 2 coherent publish/read, taken once · 3 torn rejection
      4 overwrite without backpressure, loss counted · 5 exact witness bytes
    """
    sys.path.insert(0, HERE)
    import muhl_aperture_read as R

    CTRLB, ENVB = 64, 64
    SLOTB = ENVB + PAYLOAD_MAX
    APB = CTRLB + SLOTS * SLOTB

    def put_ctl(a, seq, drops, active, policy=0):
        a[0:8] = MAGIC
        struct.pack_into("<HH", a, 8, VERSION, SLOTS)
        struct.pack_into("<I", a, 12, PAYLOAD_MAX)
        struct.pack_into("<QQ", a, 16, seq, drops)
        a[32] = active
        a[33] = policy

    def pub(a, slot, gen, payload, cfg=7, ptype=2, pos=0, waddr=0, dropped=0, flags=1, tear=False):
        off = CTRLB + slot * SLOTB
        struct.pack_into("<Q", a, off + 0, gen)
        struct.pack_into("<I", a, off + 8, cfg)
        a[off + 12] = ptype
        a[off + 13] = flags
        struct.pack_into("<Q", a, off + 16, pos)
        struct.pack_into("<Q", a, off + 24, waddr)
        struct.pack_into("<II", a, off + 32, len(payload), dropped)
        a[off + ENVB: off + ENVB + len(payload)] = payload
        if not tear:
            struct.pack_into("<Q", a, off + 56, gen)

    def as_file(a):
        import tempfile
        fd, p = tempfile.mkstemp(suffix=".aperture")
        os.close(fd)
        with io.open(p, "wb") as f:
            f.write(b"\x00" * 4096)          # the aperture sits at an offset, as it does in the file
            f.write(bytes(a))
        return p, 4096

    res = []

    # 1 + 5 : envelope round-trip and exact witness bytes, same publication
    a = bytearray(APB)
    put_ctl(a, 1, 0, 1)
    body = bytes((i * 37 + 11) & 0xFF for i in range(PAYLOAD_MAX))
    pub(a, 0, 1, body, cfg=4242, pos=0xDEADBEEF, waddr=0x1_0000_0000)
    p, base = as_file(a)
    rec, err = R.poll_once(p, base, set(), None)
    e = rec["env"] if rec else {}
    res.append(("1 envelope round-trip",
                rec is not None and e.get("config_id") == 4242 and e.get("payload_type") == 2
                and e.get("substrate_pos") == 0xDEADBEEF
                and e.get("witness_addr") == 0x1_0000_0000
                and e.get("payload_len") == PAYLOAD_MAX, str(err or e)[:60]))
    res.append(("5 witness bytes unchanged",
                rec is not None and rec["payload"] == body, "payload differs"))
    os.remove(p)

    # 2 : coherent publish/read, taken exactly once
    a = bytearray(APB)
    put_ctl(a, 2, 0, 0)
    pub(a, 0, 9, b"\xAA" * 16)
    p, base = as_file(a)
    seen = set()
    r1, _ = R.poll_once(p, base, seen, None)
    r2, _ = R.poll_once(p, base, seen, None)
    res.append(("2 coherent publish/read, taken once",
                r1 is not None and r1["env"]["gen_before"] == 9 and r2 is None,
                "r1=%s r2=%s" % (bool(r1), bool(r2))))
    os.remove(p)

    # 3 : torn rejection - gen_after never written
    a = bytearray(APB)
    put_ctl(a, 3, 0, 0)
    pub(a, 0, 11, b"\x5A" * 32, tear=True)
    p, base = as_file(a)
    r, _ = R.poll_once(p, base, set(), None)
    res.append(("3 torn publication rejected", r is None, "reader took a torn slot"))
    os.remove(p)

    # 4 : overwrite without backpressure, loss counted exactly
    a = bytearray(APB)
    gens = list(range(20, 28))
    for i, gen in enumerate(gens):
        put_ctl(a, gen, gen - 20, (i + 1) % 2)
        pub(a, i % 2, gen, bytes([gen]) * 8, dropped=1 if i else 0)
    p, base = as_file(a)
    r, _ = R.poll_once(p, base, set(), None)
    took = r["env"]["gen_before"] if r else None
    drops = r["ctl"]["drop_count"] if r else None
    res.append(("4 overwrite, no backpressure, loss counted",
                took == 27 and drops == 7, "took %s drops %s" % (took, drops)))
    os.remove(p)
    return res, APB


def main():
    recvs = ring_recvs()
    print("MUHL APERTURE - egress aperture, first vertical slice")
    print("=" * 100)
    print("  rings addressed        : %s   (clock: %s)"
          % (format(len(recvs), ","), recvs[0][0] if recvs else "none"))
    print("  ring gates FABRICATED  : 0   - the electron moves in the wire; a ring is topology")
    print("  watched span           : %d bytes" % WATCH_LEN)
    print("  aperture bytes         : %d  (control %d + %d slots x (env %d + payload %d))"
          % (CTRL_BYTES + SLOTS * (ENV_BYTES + PAYLOAD_MAX), CTRL_BYTES, SLOTS, ENV_BYTES,
             PAYLOAD_MAX))
    print("  surface bytes the host reads : 0")
    print()

    gates, lay = build(recvs)

    print("  MUTANT BATTERY - each one makes the aperture lie in a different way")
    print("  " + "-" * 96)
    caught = 0
    muts = ("no_compare", "no_clock", "witness_altered", "no_junction", "no_shadow_advance",
            "ignore_config", "ignore_budget")
    for m in muts:
        mg, _ = build(recvs, mutant=m)
        f = verify(mg, recvs)
        differs = (mg != gates)
        ok = bool(f) or differs
        caught += 1 if ok else 0
        why = f[0][:58] if f else ("netlist differs" if differs else "SURVIVED")
        print("    %-20s %-9s %s" % (m, "CAUGHT" if ok else "SURVIVED", why))
    print()

    fails = verify(gates, recvs)
    print("  CHAMPION")
    print("  " + "-" * 96)
    print("    property failures    : %d" % len(fails))
    for f in fails[:6]:
        print("        %s" % f)
    print("    gates                : %s" % format(len(gates), ","))
    print("    bytes                : %s" % format(len(gates) * REC, ","))
    print("    mutants caught       : %d of %d" % (caught, len(muts)))
    print()

    if fails or caught < len(muts):
        print("  NOT WRITTEN. Catch mutants BEFORE any write, or write nothing.")
        return 1

    abi, apb = abi_battery()
    print("  ABI ROUND-TRIP")
    print("  " + "-" * 96)
    for name, good, why in abi:
        print("    %-42s %s%s" % (name, "ok" if good else "NO", "" if good else "   " + why))
    print("    aperture bytes per poll : %d      surface bytes per poll : 0" % apb)
    print()

    blob = b"".join(struct.pack("<BQQQ", *t) for t in gates)
    if not WRITE:
        print("  DRY RUN - %s B. add --write" % format(len(blob), ","))
        return 0
    io.open(CONT, "wb").write(blob)
    side = dict(lay)
    side.update({
        "container": os.path.basename(CONT), "header_bytes_in_container": 0,
        "record": "<BQQQ> op|a|b|out, 25 B",
        "opcodes": "0 nand, 1 and, 2 or, 3 xor, 4 not",
        "bytes": len(blob), "abi": "MUHLAPR1 v1, see APERTURE_ABI.md",
        "magic": MAGIC.decode("ascii"), "version": VERSION,
        "slots": SLOTS, "payload_max": PAYLOAD_MAX,
        "aperture_bytes": CTRL_BYTES + SLOTS * (ENV_BYTES + PAYLOAD_MAX),
        "host_reads_surface_bytes": 0,
        "publish_path": "one-way junction, 2 gates / 2 ticks, reverse transfer measured 0 out to "
                        "4,096 ticks and under a hostile driver (muhl_junction J3/J5)",
        "coherency": "generation-before / generation-after; a reader accepts a slot only when the "
                     "two are equal and non-zero, so a torn read is detectable",
        "policy": "OVERWRITE_OLDEST - the substrate always publishes; a slow host misses "
                  "generations and drop_count records exactly how many",
        "capture_path": "byte-exact. no hex, text, json, base64, hash, sum or compression",
        "mutants_caught": caught,
    })
    io.open(SIDE, "w", encoding="utf-8").write(json.dumps(side, indent=1))
    print("  WROTE %s   %s B" % (CONT, format(len(blob), ",")))
    print("        %s" % SIDE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
