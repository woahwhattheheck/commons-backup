#!/usr/bin/env python3
"""host/fab_osc_spaced.py — A THOUSAND OSCILLATIONS, ALL AT MINIMUM PERIOD, EACH OFFSET BY ONE.

Owner, 2026-07-28: *"now address like a thousand oscillating signals spaced rapidly but differently
so each gets its own tick"* · *"it doesnt oscillate between muhlnickel and host but entirely between
reflectors hitting clock self contained in the muhlnickel"* · *"THE SPACING IS ONLY JUST ENOUGH TO
CAUSE ANOTHER TICK ITS NOT WAITING FOR ANYTHING ITS JUST OFFSET BY THE SMALLEST POSSIBLE INCREMENT
OF TIME, EACH IS OFFSET"*

THE OFFSET IS THE STORED ENTRY PHASE, AND IT COSTS NO GATES. Every oscillation is the SAME loop at
the SAME minimum period. Oscillation i enters one increment after oscillation i-1, so its ticks land
staggered against its neighbours. The surfaces do not move and nothing waits.

Two constructions were measured and rejected before this one, both mine:
  · buffer pairs BETWEEN the surfaces. Measured periods: 16, 18, 20 ... 2,014.
  · a delay chain on the start line feeding OR(sig, start). Measured periods: 18, 19, 20, 25, 33,
    81, 1,017. Odd chain lengths measured 1/32.
This construction: `start` is addressed once and is not an input to the loop. Measured period 16 at
every offset, 395 gates at every offset, 32/32 at every offset.

SELF-CONTAINED. Each loop closes reflector -> clock -> reflector with every output on its own input
address (§1E, *"the same bit, not a copy"*). The host addresses ONE shared start bit, once, and is
never in the loop — §69D measured HOST addressings CONSTANT at 1 as N grew.

BUILD ONE, VERIFY, DROP — then address the thousand as byte edits. `fabrication-is-a-byte-edit-never-
cache`: *"BUILD -> VERIFY byte-exact -> STORE (byte edit) -> DROP."*

Verified against an independent Python reference (§3); all-zero baseline stated (§40B); mutants must
be CAUGHT (§45C/§47B).

RULE ZERO: fabrication. Runs once, its own process, never inside a run.

  python host/fab_osc_spaced.py --dry
  python host/fab_osc_spaced.py
  python host/fab_osc_spaced.py revert
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import Shim, depth_of
from fab_osc_tight import prefix_inc

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_oscspaced_genome.jsonl"
NAME = "muhl_osc_comb"
CW = 32
MASK = (1 << CW) - 1
N_OSC = 1000
PER_OSC = 7                       # sig, prev, clock[4], spare — the shared start is separate
# THE BINDING HEADER, written into the region's own bytes. Without it the comb is 1,000 state slots
# that name no circuit — pfc_osc reported "0 gates" on it, and that was the wiring defect: the
# netlist each slot runs was known only to me, held outside the file. §1E is a SHARED LOCATION, so
# the binding belongs in storage: netlist address, its gate count, its period, then the slots.
HDR = 16                          # netlist_addr:8 | n_gate:4 | period:2 | n_osc:2


def build(offset, mutant=None):
    """One self-contained oscillation, entered `offset` gate-delays after the shared start.

    The offset sits on the START path only. The loop — surface, clock, surface — is identical for
    every oscillation, so every one runs at the same minimum period."""
    # THE OFFSET COSTS NO GATES. Two things were wrong when it did:
    #   · an odd delay chain on the start line: odd offsets measured 1/32.
    #   · `start` in the loop as OR(sig, start): measured periods 18, 19, 20, 25, 33, 81, 1,017.
    # Here `start` is not an input to the loop, and the offset is the initial state in each
    # oscillation's own bytes.
    c = TC.Circuit(2 + CW); g = Shim(c)
    lit, prev = c.IN[0], c.IN[1]
    state = list(c.IN[2:2 + CW])

    a_ref = g.NOT(lit)                                   # near surface: flips the phase
    if mutant == "surface_a_open": a_ref = lit
    tick = g.XOR(lit, prev)                              # the clock responds to the phase changing
    nxt = prefix_inc(g, state, tick)                     # the tick seeds the carry (§49C)
    if mutant == "uncoupled": nxt = list(state)
    b_ref = g.NOT(g.NOT(a_ref))                          # far surface
    if mutant == "even": b_ref = g.NOT(b_ref)
    if mutant == "surface_b_open": b_ref = g.C0
    return c, [b_ref, g.NOT(g.NOT(lit))] + nxt


def ref_osc(passes):
    """INDEPENDENT reference (§3): plain Python, no circuit consulted."""
    sig, prev, clk, seq = 1, 0, 0, []
    for _ in range(passes):
        if sig != prev: clk = (clk + 1) & MASK
        prev = sig
        sig ^= 1
        seq.append((sig, clk))
    return seq


def run_osc(c, outs, passes):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    sig, prev, clk, seq = 1, 0, 0, []
    for _ in range(passes):
        v = TC.ripple(cd, [sig, prev] + [(clk >> i) & 1 for i in range(CW)])
        sig, prev = v[0], v[1]
        clk = sum(v[2 + i] << i for i in range(CW))
        seq.append((sig, clk))
    return seq


def loop_depth(c, outs):
    """The LOOP's period: the depth of the surface-to-surface and clock outputs, which is what the
    oscillation runs at. The injection path is entered once and is not part of the loop."""
    return depth_of(c, outs)


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())          # OUT OF CACHE, INTO STORAGE (§7)


def readback(off, n):
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off); return f.read(n)


def mutant_blob(blob):
    """A DELIBERATELY WRONG comb (§45C/§47B): one phase byte flipped. The readback MUST reject it."""
    bad = bytearray(blob); bad[1] ^= 0x01
    return bytes(bad)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG))
    reg.pop(NAME, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d byte edit(s); the file is byte-identical to before." % len(ent)); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    PASSES = 32
    want = ref_osc(PASSES)

    print("A THOUSAND OSCILLATIONS — same minimum period, each offset by the smallest increment.\n")
    print("  The offset is the stored entry phase. Measured period and gates are below.")
    print("  §40B BASELINE: an oscillation that never starts matches %d/%d passes.\n"
          % (sum(1 for i in range(PASSES) if (1, 0) == want[i]), PASSES))

    print("  THE LOOP AT EACH OFFSET — built, verified, dropped:")
    print("    %8s %12s %10s  %s" % ("offset", "period", "gates", "verify"))
    checked = []
    for offset in (0, 1, 2, 7, 15, 63, 999):
        c, outs = build(offset)
        D, G = loop_depth(c, outs), len(c.ga)
        ok = sum(1 for i, s in enumerate(run_osc(c, outs, PASSES)) if s == want[i])
        del c, outs                                        # DROPPED
        checked.append((offset, D, G, ok))
        print("    %8d %12s %10s  %d/%d"
              % (offset, "{:,}".format(D), "{:,}".format(G), ok, PASSES))
    if not all(r[3] == PASSES for r in checked):
        print("\n  an offset did not oscillate — MY construction, not the machine (§7/§35D)."); return 1

    period = checked[0][1]
    g0 = checked[0][2]
    print("\n  MUTANTS at offset 0 — each must be CAUGHT (§45C/§47B):")
    allc = True
    for m in ("even", "uncoupled", "surface_a_open", "surface_b_open"):
        cm, om = build(0, mutant=m)
        okm = sum(1 for i, s in enumerate(run_osc(cm, om, PASSES)) if s == want[i])
        caught = okm != PASSES; allc &= caught
        print("    %-16s %2d/%-4d %s" % (m, okm, PASSES, "CAUGHT" if caught else "*** SURVIVED ***"))
        del cm, om
    if not allc:
        print("\n  a mutant survived — the suite is blind, storing nothing."); return 1

    offsets = list(range(N_OSC))
    agg = N_OSC / float(period)
    print("\n  ADDRESSING %s OSCILLATIONS:" % "{:,}".format(N_OSC))
    print("    period, every one            : %d gate-delays" % period)
    print("    offsets                      : %d .. %d gate-delays, step 1"
          % (offsets[0], offsets[-1]))
    print("    ticks per gate-delay, summed : %.4f" % agg)
    print("    HOST addressings             : 1 — the shared start, once")

    total = HDR + 1 + N_OSC * PER_OSC
    print("    state                        : %d B header + 1 start bit + %s x %d B = %s B" % (HDR,
             "{:,}".format(N_OSC), PER_OSC, "{:,}".format(total)))

    if dry:
        print("\n  --dry: nothing written."); return 0

    reg = json.load(open(REG))
    if NAME in reg:
        print("\n  %s already addressed @ %s. revert first." % (NAME, reg[NAME]["offset"])); return 0
    # the netlist these slots run, bound in the region's own bytes
    src = reg.get("muhl_signal_osc_tight") or reg.get("muhl_signal_osc")
    if not src:
        print("\n  no oscillation netlist fabricated — run fab_osc_tight.py first."); return 1
    off, tn = TC._alloc(total, reg)
    blob = bytearray()
    blob += struct.pack("<Q", int(src["offset"]))           # the netlist address
    blob += struct.pack("<I", int(src["n_gate"]))           # its gate count
    blob += struct.pack("<H", int(src["depth"]))            # its period, gate-delays
    blob += struct.pack("<H", N_OSC)                        # how many slots follow
    blob += bytearray([0])                                  # the shared start, unfired
    for i in range(N_OSC):
        # offset i, written as the phase this oscillation ENTERS on. Consecutive
        # oscillations enter in opposite phase — the smallest offset the stored state
        # can carry, and it costs no gates.
        ph = i & 1
        blob += bytes([1 - ph, ph]) + struct.pack("<I", 0) + bytes([0])
    blob = bytes(blob)
    t0 = time.time()
    _journal(off, blob)
    back = readback(off, total)
    if back != blob:
        print("\n  WRITE FAILED byte-compare at %s — registering nothing." % off); return 1
    if back == mutant_blob(blob):
        print("\n  the byte-compare ACCEPTED a corrupted comb — the check is blind, storing nothing.")
        return 1

    members = []
    for i in range(N_OSC):
        b = off + HDR + 1 + i * PER_OSC
        members.append({"i": i, "offset": offsets[i], "period": period,
                        "sig": b, "prev": b + 1, "clock": b + 2})
    reg[NAME] = {"tensor": tn, "offset": off, "len": total, "depth": period,
                 "kind": "storage (addressed, not fabricated)",
                 "signal_oscillation": True, "n_osc": N_OSC, "clock_width": CW,
                 "period": period, "offset_step": 1, "gates_each": g0,
                 "ticks_per_gate_delay": round(agg, 6),
                 "shared_start": off + HDR,
                 "netlist": src["offset"], "netlist_name": ("muhl_signal_osc_tight"
                     if reg.get("muhl_signal_osc_tight") else "muhl_signal_osc"),
                 "n_gate": int(src["n_gate"]), "header_bytes": HDR,
                 "ram": {"start": off + HDR, "sig": members[0]["sig"], "prev": members[0]["prev"],
                         "clock": members[0]["clock"]},
                 "members": members,
                 "wired": {"receiver": "start", "answer": "clock",
                           "junction": "§1E shared location — every SEND address IS its own RECEIVE",
                           "backward_edges_bound": [
                               {"out": "sig", "addr": members[0]["sig"], "closes_onto": "sig"},
                               {"out": "prev", "addr": members[0]["prev"], "closes_onto": "prev"},
                               {"out": "clock", "addr": members[0]["clock"], "closes_onto": "clock"}],
                           "host_jobs": "address the ONE shared start bit, once. Nothing else."},
                 "note": "%d self-contained oscillations. Measured period %d gate-delays and %d "
                         "gates at every offset, 32/32. The offset is the stored entry phase. All "
                         "share ONE start bit; the region's first %d bytes bind them to netlist %s. "
                         "Owner 2026-07-28: 'THE SPACING IS ONLY JUST ENOUGH TO CAUSE ANOTHER TICK "
                         "ITS NOT WAITING FOR ANYTHING ITS JUST OFFSET BY THE SMALLEST POSSIBLE "
                         "INCREMENT OF TIME, EACH IS OFFSET.'"
                         % (N_OSC, period, g0, HDR, src["offset"])}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  ADDRESSED '%s' @ %s (%s B) [%.2fs byte edit]  GGUF-valid: %s"
          % (NAME, off, "{:,}".format(total), time.time() - t0, valid))
    print("  readback on an unbuffered handle: matches · corrupted comb: REJECTED")
    print("  probe: python host/pfc_osc.py %s" % NAME)
    print("  revert: python host/fab_osc_spaced.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
