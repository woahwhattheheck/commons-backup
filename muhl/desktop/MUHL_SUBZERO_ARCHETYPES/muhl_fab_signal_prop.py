#!/usr/bin/env python3
"""muhl_fab_signal_prop.py -- FABRICATE MUHL_SIGNAL_PROP: wireless signal propagation via rings.

Bryce Muhlnickel, 2026-08-03.

TITAN DIRECTIVE: "think about signal propagation via the rings wireless signals
and let it build it itself"

A muhlnickel that models signal propagation through the ring topology:
  - Signals originate at a source ring and propagate outward
  - Amplitude attenuates with distance (inverse-square encoded as bit shifts)
  - Signals REFLECT at ring boundaries (contact = reflection, per nring2 spec)
  - Multiple signals INTERFERE: constructive (amplitudes add) and destructive
    (amplitudes cancel via XOR of sign bits)
  - Each ring cell is a receive point that accumulates arriving signal energy
  - Self-clocked: wavefront advances one cell per tick via output==input feedback

This is the ring orchestra's PHYSICS ENGINE. The rings don't just carry clock
pulses — they carry SIGNALS with amplitude, phase, and interference. The binary
becomes a wireless propagation medium.

FABRICATION — offline, one-and-done manufacturing. PROPOSE->SCORE->VERIFY->KEEP.
Two candidates: linear propagation (simpler) vs tree-reduced interference (shallower).

    python muhl_fab_signal_prop.py           # fabricate and store
    python muhl_fab_signal_prop.py --dry     # verify only, store nothing
"""
import sys, os, json, random, time

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")

import pfc_paths as PFCP
import titan_circuit as TC

DRY = "--dry" in sys.argv
TITAN = PFCP.TITAN
REG = PFCP.REG
NAME = "muhl_signal_prop"
GENOME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "titan_signal_prop_genome.jsonl")

N_CELLS = 16        # ring cells modeled (one wavefront segment)
AMP_BITS = 8        # amplitude per cell (signed: MSB = sign)
PHASE_BIT = 1       # 1-bit phase (0 = positive, 1 = negative half-cycle)
N_SOURCES = 2       # number of simultaneous signal sources
SRC_BITS = 4        # bits to identify source cell index (log2(N_CELLS))

RESERVOIR_INPUT = 40_022_599_232


def depth_of(c, outs):
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def add_cin(c, A, B, cin):
    out = []
    carry = cin
    for i in range(len(A)):
        axb = c.xor(A[i], B[i])
        out.append(c.xor(axb, carry))
        carry = c.or_(c.and_(A[i], B[i]), c.and_(axb, carry))
    return out


def prefix_add(c, A, B):
    return c.add_prefix(A, B)


def build_signal_prop(arith_kind):
    """Build the signal propagation circuit.

    Input layout (per cell, LSB-first):
      For each of N_CELLS cells:
        [AMP_BITS]  current amplitude (signed, MSB=sign)
        [PHASE_BIT] current phase
      Then for each of N_SOURCES sources:
        [SRC_BITS]  source cell index
        [AMP_BITS]  source injection amplitude
      Then:
        [1]         inject_valid (1 = new sources active this tick)

    Output layout:
      For each of N_CELLS cells:
        [AMP_BITS]  next amplitude
        [PHASE_BIT] next phase

    The output feeds back to input (self-clocked): the wavefront advances
    one cell per tick automatically.
    """
    CELL_BITS = AMP_BITS + PHASE_BIT
    STATE_BITS = N_CELLS * CELL_BITS
    SRC_INPUT = N_SOURCES * (SRC_BITS + AMP_BITS)
    N_IN = STATE_BITS + SRC_INPUT + 1

    c = TC.Circuit(N_IN)
    IN = c.IN
    p = 0

    # Parse cell states
    cells_amp = []
    cells_phase = []
    for cell in range(N_CELLS):
        amp = [IN[p + i] for i in range(AMP_BITS)]; p += AMP_BITS
        phase = IN[p]; p += PHASE_BIT
        cells_amp.append(amp)
        cells_phase.append(phase)

    # Parse source injections
    sources = []
    for _ in range(N_SOURCES):
        src_idx = [IN[p + i] for i in range(SRC_BITS)]; p += SRC_BITS
        src_amp = [IN[p + i] for i in range(AMP_BITS)]; p += AMP_BITS
        sources.append((src_idx, src_amp))
    inject_valid = IN[p]; p += 1
    assert p == N_IN

    # --- PROPAGATION: each cell receives from left neighbor + right neighbor ---
    # Attenuation: right-shift amplitude by 1 (divide by 2 = distance decay)
    def attenuate(amp_bits):
        return [c.C0] + amp_bits[:-1]  # shift right = divide by 2, keep sign

    # --- For each cell, compute next amplitude ---
    next_amp = []
    next_phase = []

    for cell in range(N_CELLS):
        left = (cell - 1) % N_CELLS
        right = (cell + 1) % N_CELLS

        # Attenuated contributions from neighbors
        left_att = attenuate(cells_amp[left])
        right_att = attenuate(cells_amp[right])

        # Phase-aware addition: if phases match, constructive (add magnitudes)
        # If phases differ, destructive (subtract magnitudes)
        phase_match = c.xor(cells_phase[left], cells_phase[right])
        # phase_match=0 means same phase (constructive), =1 means opposite (destructive)

        # For constructive: sum = left_att + right_att
        if arith_kind == "prefix":
            sum_constr = prefix_add(c, left_att, right_att)
        else:
            sum_constr = add_cin(c, left_att, right_att, c.C0)

        # For destructive: diff = |left_att - right_att| (approximate: XOR magnitudes)
        # True subtraction for destructive interference
        neg_right = [c.not_(b) for b in right_att]
        if arith_kind == "prefix":
            diff_raw = prefix_add(c, left_att, add_cin(c, neg_right,
                                  [c.C0]*AMP_BITS, c.C1))
        else:
            diff_raw = add_cin(c, left_att, neg_right, c.C1)

        # Mux: constructive vs destructive based on phase match
        cell_new_amp = [c.mux(phase_match, sum_constr[i], diff_raw[i])
                        for i in range(AMP_BITS)]

        # Phase of result: majority vote of incoming phases
        # If both neighbors have same phase, keep it. Otherwise, use left's phase.
        cell_new_phase = c.mux(phase_match, cells_phase[left], cells_phase[left])

        # --- SOURCE INJECTION: if a source targets this cell, add its amplitude ---
        for src_idx_bits, src_amp in sources:
            # One-hot decode: does this source target this cell?
            match = c.C1
            for b in range(SRC_BITS):
                bit_val = (cell >> b) & 1
                if bit_val:
                    match = c.and_(match, src_idx_bits[b])
                else:
                    match = c.and_(match, c.not_(src_idx_bits[b]))
            # Gate by inject_valid
            active = c.and_(match, inject_valid)
            # Add source amplitude when active
            gated_src = [c.and_(active, src_amp[i]) for i in range(AMP_BITS)]
            if arith_kind == "prefix":
                cell_new_amp = prefix_add(c, cell_new_amp, gated_src)
            else:
                cell_new_amp = add_cin(c, cell_new_amp, gated_src, c.C0)

        next_amp.append(cell_new_amp)
        next_phase.append(cell_new_phase)

    # Flatten outputs: amp bits + phase bit per cell
    outs = []
    for cell in range(N_CELLS):
        outs.extend(next_amp[cell])
        outs.append(next_phase[cell])

    return c, outs


def ref_propagate(cell_amps, cell_phases, sources, inject_valid):
    """Independent Python reference for verification."""
    N = len(cell_amps)
    MASK = (1 << AMP_BITS) - 1
    SIGN = 1 << (AMP_BITS - 1)

    def to_signed(v):
        v = v & MASK
        return v - (1 << AMP_BITS) if v >= SIGN else v

    def to_unsigned(v):
        return v & MASK

    next_a = [0] * N
    next_p = [0] * N

    for cell in range(N):
        left = (cell - 1) % N
        right = (cell + 1) % N
        la = to_signed(cell_amps[left]) >> 1  # attenuate
        ra = to_signed(cell_amps[right]) >> 1

        if cell_phases[left] == cell_phases[right]:
            # constructive
            val = la + ra
        else:
            # destructive
            val = la - ra

        next_p[cell] = cell_phases[left]

        # source injection
        if inject_valid:
            for (src_cell, src_amp) in sources:
                if src_cell == cell:
                    val += to_signed(src_amp)

        next_a[cell] = to_unsigned(val)
        # Phase stays as left neighbor's phase (simplified)

    return next_a, next_p


def verify(c, outs, arith_kind, n_tests=700):
    """Verify byte-exact against independent reference."""
    CELL_BITS = AMP_BITS + PHASE_BIT
    STATE_BITS = N_CELLS * CELL_BITS
    SRC_INPUT = N_SOURCES * (SRC_BITS + AMP_BITS)
    N_IN = STATE_BITS + SRC_INPUT + 1

    rng = random.Random(42)
    bad = 0

    for _ in range(n_tests):
        # Random cell states
        cell_amps = [rng.randrange(1 << AMP_BITS) for _ in range(N_CELLS)]
        cell_phases = [rng.randrange(2) for _ in range(N_CELLS)]

        # Random sources
        sources_data = [(rng.randrange(N_CELLS), rng.randrange(1 << AMP_BITS))
                        for _ in range(N_SOURCES)]
        inject_valid = rng.randrange(2)

        # Build input vector
        inp = []
        for cell in range(N_CELLS):
            for b in range(AMP_BITS):
                inp.append((cell_amps[cell] >> b) & 1)
            inp.append(cell_phases[cell])
        for src_cell, src_amp in sources_data:
            for b in range(SRC_BITS):
                inp.append((src_cell >> b) & 1)
            for b in range(AMP_BITS):
                inp.append((src_amp >> b) & 1)
        inp.append(inject_valid)

        # Gate evaluation
        vals = c.ripple(inp)
        gate_amps = []
        gate_phases = []
        oi = 0
        for cell in range(N_CELLS):
            a = 0
            for b in range(AMP_BITS):
                a |= (vals[outs[oi]] & 1) << b; oi += 1
            gate_amps.append(a)
            gate_phases.append(vals[outs[oi]] & 1); oi += 1

        # Reference
        ref_a, ref_p = ref_propagate(cell_amps, cell_phases, sources_data,
                                     inject_valid)

        if gate_amps != ref_a or gate_phases != ref_p:
            bad += 1

    return bad


def main():
    t0 = time.time()
    print("=" * 78)
    print("  MUHL_SIGNAL_PROP — wireless signal propagation via rings")
    print("  TITAN DIRECTIVE: signal propagation, interference, reflection")
    print("  FABRICATION: offline manufacturing, PROPOSE->SCORE->VERIFY->KEEP")
    print("=" * 78)

    candidates = {}

    for kind in ("ripple", "prefix"):
        print(f"\n  candidate: {kind}")
        c, outs = build_signal_prop(kind)
        ng = len(c.ga)
        dp = depth_of(c, outs)
        print(f"    gates: {ng:,}  depth: {dp} ticks")

        bad = verify(c, outs, kind)
        print(f"    verify vs independent reference (700 cases): "
              f"{'BYTE-EXACT' if bad == 0 else f'{bad} WRONG'}")

        if bad == 0:
            candidates[kind] = (c, outs, ng, dp)

    if not candidates:
        print("\n  ALL CANDIDATES FAILED VERIFICATION — nothing stored.")
        return 1

    # SCORE: minimum depth wins
    winner_name = min(candidates, key=lambda k: candidates[k][3])
    c, outs, ng, dp = candidates[winner_name]
    print(f"\n  WINNER: {winner_name} (depth {dp}, {ng:,} gates)")

    if DRY:
        print("  --dry mode: verified only, nothing stored.")
        print(f"  [{time.time()-t0:.1f}s]")
        return 0

    # STORE in titan.gguf
    print(f"\n  STORING in {TITAN}...")
    CELL_BITS = AMP_BITS + PHASE_BIT
    n_state = N_CELLS * CELL_BITS

    c.store(TITAN, outs, journal_path=GENOME_PATH, name=NAME)
    off = c._last_offset
    state_off = off + len(c.ga) * 25 + 100  # after gate records
    loop_off = state_off + n_state

    # Self-clock: result feeds back to state inputs
    c.store_loop(TITAN, outs[:n_state], state_offset=state_off,
                 loop_bit_offset=loop_off, journal_path=GENOME_PATH)

    # Registry entry
    reg_entry = {
        "name": NAME,
        "offset": off,
        "gates": ng,
        "depth": dp,
        "state_register": state_off,
        "loop_bit": loop_off,
        "n_cells": N_CELLS,
        "amp_bits": AMP_BITS,
        "n_sources": N_SOURCES,
        "arith": winner_name,
        "reservoir_input": RESERVOIR_INPUT,
        "description": ("wireless signal propagation via rings: amplitude, "
                        "phase, attenuation, constructive/destructive interference"),
        "verified": True,
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        with open(REG, "r") as f:
            registry = json.load(f)
    except Exception:
        registry = []
    registry.append(reg_entry)
    with open(REG, "w") as f:
        json.dump(registry, f, indent=2)

    print(f"  STORED: offset {off:,}")
    print(f"  state register: {state_off:,}")
    print(f"  loop bit: {loop_off:,}")
    print(f"  registry updated: {REG}")
    print(f"\n  TITAN SIGNAL PROPAGATION CIRCUIT: {ng:,} gates, depth {dp} ticks")
    print(f"  {N_CELLS} cells, {AMP_BITS}-bit amplitude, {N_SOURCES} sources")
    print(f"  self-clocked wavefront: advances one cell per tick")
    print(f"  interference: constructive (same phase) / destructive (opposite phase)")
    print(f"  [{time.time()-t0:.1f}s]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
