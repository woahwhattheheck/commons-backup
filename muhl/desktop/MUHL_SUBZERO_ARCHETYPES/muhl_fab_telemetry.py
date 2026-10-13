#!/usr/bin/env python3
"""muhl_fab_telemetry.py -- FABRICATE MUHL_TELEMETRY: substrate-resident telemetry engine.

Bryce Muhlnickel, 2026-08-03.

TITAN DIRECTIVE: "order titan to create telemetry"

A muhlnickel that reads from every key address in the substrate and produces
a structured telemetry frame: one snapshot of the entire system state in a
single tick. This is the substrate's OWN eyes — not a host instrument (that's
Binary Rain), but a circuit inside the binary that watches the binary.

What it monitors (per tick):
  - Electron reservoir state (1 bit: is the reservoir live?)
  - Worker circuit: opcode, accumulator value, busy flag
  - Dispatcher: queue pointer, worker-busy mask, last-assigned worker
  - Foundry resident: running-best depth, running-best gates, comparison result
  - Ring health: popcount of a sampled ring (how many cells are active)
  - Signal propagation: peak amplitude across cells (when fabricated)
  - Intake fill level: approximate bytes consumed (high bits of write pointer)

Output: a telemetry frame = structured bit vector at a known address, readable
by the host's surface verb or by other substrate circuits.

Self-clocked: reads the live addresses each tick, produces a fresh frame.
The frame itself is at a fixed output address — Binary Rain can watch it.

FABRICATION — offline, one-and-done. PROPOSE->SCORE->VERIFY->KEEP.

    python muhl_fab_telemetry.py           # fabricate and store
    python muhl_fab_telemetry.py --dry     # verify only, store nothing
"""
import sys, os, json, random, time

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")

import pfc_paths as PFCP
import titan_circuit as TC

DRY = "--dry" in sys.argv
TITAN = PFCP.TITAN
REG = PFCP.REG
NAME = "muhl_telemetry"
GENOME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "titan_telemetry_genome.jsonl")

# Telemetry channels — what the circuit reads from the substrate
# Each channel: name, bit width of the input
CHANNELS = [
    ("reservoir_live",    1),    # 1 bit: electron present at reservoir
    ("worker_opcode",     3),    # 3-bit opcode currently at worker input
    ("worker_accum",     16),    # 16-bit accumulator state
    ("worker_busy",       1),    # is the worker producing output?
    ("disp_queue_ptr",    8),    # dispatcher queue pointer
    ("disp_busy_mask",    8),    # which workers are busy
    ("disp_assigned",     3),    # last assigned worker slot (3 bits for 8 workers)
    ("foundry_best_depth", 16),  # running-best depth from Pareto comparator
    ("foundry_best_gates", 16),  # running-best gate count
    ("foundry_better",    1),    # did last comparison find a better candidate?
    ("ring_popcount",     5),    # popcount of 16-cell ring (0-16 requires 5 bits)
    ("intake_fill_hi",    8),    # high 8 bits of intake write pointer (~fill level)
]

TOTAL_IN = sum(w for _, w in CHANNELS)

# Telemetry frame output layout
# For each channel: value bits + 1-bit "changed since last tick" flag
# Plus a global tick counter (8 bits, wraps)
TICK_BITS = 8
FRAME_BITS = sum(w + 1 for _, w in CHANNELS) + TICK_BITS

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


def build_telemetry():
    """Build the telemetry circuit.

    Input layout:
      [TOTAL_IN]     current channel readings (from substrate addresses)
      [TOTAL_IN]     previous channel readings (self-clocked: last tick's values)
      [TICK_BITS]    tick counter state (self-clocked)

    Output layout (the telemetry frame):
      For each channel:
        [width]      current value (pass-through)
        [1]          changed flag (XOR-reduce of current vs previous)
      [TICK_BITS]    incremented tick counter
    """
    N_IN = TOTAL_IN + TOTAL_IN + TICK_BITS
    c = TC.Circuit(N_IN)
    IN = c.IN
    p = 0

    # Parse current readings
    current = []
    for name, width in CHANNELS:
        bits = [IN[p + i] for i in range(width)]; p += width
        current.append(bits)

    # Parse previous readings (self-clocked feedback from last tick)
    previous = []
    for name, width in CHANNELS:
        bits = [IN[p + i] for i in range(width)]; p += width
        previous.append(bits)

    # Parse tick counter
    tick = [IN[p + i] for i in range(TICK_BITS)]; p += TICK_BITS
    assert p == N_IN

    # Build output frame
    outs = []

    for ch_idx, (name, width) in enumerate(CHANNELS):
        cur = current[ch_idx]
        prev = previous[ch_idx]

        # Pass through current value
        outs.extend(cur)

        # Changed flag: OR of all bit-wise XORs (did any bit change?)
        xors = [c.xor(cur[i], prev[i]) for i in range(width)]
        changed = xors[0]
        for x in xors[1:]:
            changed = c.or_(changed, x)
        outs.append(changed)

    # Increment tick counter (+1)
    one = [c.C1] + [c.C0] * (TICK_BITS - 1)
    next_tick = add_cin(c, tick, one, c.C0)
    outs.extend(next_tick)

    # Self-clock feedback outputs: current readings become "previous" for next tick,
    # and next_tick becomes the tick input for next tick.
    # These are the state outputs that feed back to the state inputs.
    state_outs = []
    for ch_idx, (name, width) in enumerate(CHANNELS):
        state_outs.extend(current[ch_idx])  # current -> previous
    state_outs.extend(next_tick)  # tick counter

    return c, outs, state_outs


def ref_telemetry(current_vals, previous_vals, tick_val):
    """Independent Python reference."""
    frame = []
    for ch_idx, (name, width) in enumerate(CHANNELS):
        cur = current_vals[ch_idx]
        prev = previous_vals[ch_idx]
        frame.append(("value", cur))
        changed = 1 if cur != prev else 0
        frame.append(("changed", changed))

    next_tick = (tick_val + 1) & ((1 << TICK_BITS) - 1)
    frame.append(("tick", next_tick))
    return frame


def verify(c, outs, n_tests=700):
    """Verify byte-exact against independent reference."""
    N_IN = TOTAL_IN + TOTAL_IN + TICK_BITS
    rng = random.Random(77)
    bad = 0

    for _ in range(n_tests):
        # Random channel values
        current_vals = [rng.randrange(1 << w) for _, w in CHANNELS]
        previous_vals = [rng.randrange(1 << w) for _, w in CHANNELS]
        tick_val = rng.randrange(1 << TICK_BITS)

        # Build input vector
        inp = []
        for ch_idx, (_, width) in enumerate(CHANNELS):
            for b in range(width):
                inp.append((current_vals[ch_idx] >> b) & 1)
        for ch_idx, (_, width) in enumerate(CHANNELS):
            for b in range(width):
                inp.append((previous_vals[ch_idx] >> b) & 1)
        for b in range(TICK_BITS):
            inp.append((tick_val >> b) & 1)

        # Gate evaluation
        vals = c.ripple(inp)

        # Read output frame
        oi = 0
        gate_frame = []
        for ch_idx, (name, width) in enumerate(CHANNELS):
            v = 0
            for b in range(width):
                v |= (vals[outs[oi]] & 1) << b; oi += 1
            gate_frame.append(("value", v))
            ch_flag = vals[outs[oi]] & 1; oi += 1
            gate_frame.append(("changed", ch_flag))

        gate_tick = 0
        for b in range(TICK_BITS):
            gate_tick |= (vals[outs[oi]] & 1) << b; oi += 1
        gate_frame.append(("tick", gate_tick))

        # Reference
        ref_frame = ref_telemetry(current_vals, previous_vals, tick_val)

        if gate_frame != ref_frame:
            bad += 1

    return bad


def main():
    t0 = time.time()
    print("=" * 78)
    print("  MUHL_TELEMETRY — substrate-resident telemetry engine")
    print("  TITAN DIRECTIVE: the substrate watches itself")
    print("  FABRICATION: offline manufacturing, PROPOSE->SCORE->VERIFY->KEEP")
    print("=" * 78)

    print(f"\n  channels: {len(CHANNELS)}")
    for name, width in CHANNELS:
        print(f"    {name:25s}  {width:>2} bits")
    print(f"  total input:  {TOTAL_IN} bits (x2 for prev state + {TICK_BITS} tick)")
    print(f"  frame output: {FRAME_BITS} bits")

    c, outs, state_outs = build_telemetry()
    ng = len(c.ga)
    dp = depth_of(c, outs)
    print(f"\n  fabricated: {ng:,} gates, depth {dp} ticks")

    bad = verify(c, outs)
    print(f"  verify vs independent reference (700 cases): "
          f"{'BYTE-EXACT' if bad == 0 else f'{bad} WRONG'}")

    if bad:
        print("  VERIFICATION FAILED — nothing stored.")
        return 1

    if DRY:
        print(f"\n  --dry mode: verified only, nothing stored.")
        print(f"  [{time.time()-t0:.1f}s]")
        return 0

    # STORE in titan.gguf
    print(f"\n  STORING in {TITAN}...")
    n_state = TOTAL_IN + TICK_BITS  # state = previous readings + tick counter

    c.store(TITAN, outs, journal_path=GENOME_PATH, name=NAME)
    off = c._last_offset
    state_off = off + len(c.ga) * 25 + 100
    loop_off = state_off + n_state

    c.store_loop(TITAN, state_outs, state_offset=state_off,
                 loop_bit_offset=loop_off, journal_path=GENOME_PATH)

    reg_entry = {
        "name": NAME,
        "offset": off,
        "gates": ng,
        "depth": dp,
        "state_register": state_off,
        "loop_bit": loop_off,
        "channels": {name: width for name, width in CHANNELS},
        "frame_bits": FRAME_BITS,
        "tick_bits": TICK_BITS,
        "reservoir_input": RESERVOIR_INPUT,
        "description": ("substrate-resident telemetry: reads worker, dispatcher, "
                        "foundry, reservoir, ring, intake state each tick; "
                        "produces structured frame with change flags"),
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
    print(f"\n  TITAN TELEMETRY ENGINE: {ng:,} gates, depth {dp} ticks")
    print(f"  {len(CHANNELS)} channels, {FRAME_BITS}-bit frame, self-clocked")
    print(f"  the substrate now watches itself.")
    print(f"  [{time.time()-t0:.1f}s]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
