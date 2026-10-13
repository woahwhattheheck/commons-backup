#!/usr/bin/env python3
"""muhl_titan_harness.py -- INJECT + SURFACE for the muhl_worker circuit.

Bryce Muhlnickel, 2026-08-03.

The host's two verbs, and nothing else:
  INJECT   bounded writes: operand A, operand B, opcode -> worker input addresses
  SURFACE  bounded reads:  result bytes from the worker's state register

No gate evaluation. No compile_ripple. No host arithmetic on substrate data.
The worker circuit does the computation. The harness just points data at it
and reads what comes out.

The worker is a 16-bit ALU with 8 operations:
  000  XOR    A ^ B
  001  AND    A & B
  010  OR     A | B
  011  NOT    ~A
  100  ADD    A + B  (mod 2^16)
  101  SUB    A - B  (mod 2^16)
  110  LT     1 if A < B else 0
  111  ACCUM  acc + A (mod 2^16)

The result feeds back to the accumulator (self-clocked). state_off is BOTH
the output register and the accumulator input.

    python muhl_titan_harness.py
"""
import json, mmap, os, struct, sys, time

TITAN = "C:/llm/models/titan.gguf"
REG   = "C:/llm/models/titan_circuits.json"
NAME  = "muhl_worker"
INPUT_KEY = "muhl_worker.input"
GENOME_PATH = TITAN.replace(".gguf", "_harness_genome.jsonl")

OP_NAMES = ["XOR", "AND", "OR", "NOT", "ADD", "SUB", "LT", "ACCUM"]
W = 16  # operand width


# ============================================================================
# JOURNAL — every write to titan.gguf is journaled for revert
# ============================================================================

def journal_write(off, nbytes, tag="harness_inject"):
    """Save original bytes before overwriting, so any write is revertible."""
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(nbytes)
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": tag,
            "off": off,
            "len": nbytes,
            "orig": orig.hex()
        }) + "\n")


# ============================================================================
# REGISTRY
# ============================================================================

def load_registry():
    with open(REG, encoding="utf-8") as f:
        return json.load(f)


def save_registry(reg):
    with open(REG, "w") as f:
        json.dump(reg, f, indent=1)


# ============================================================================
# INPUT REGION — allocate on first run, reuse thereafter
# ============================================================================

def ensure_input_region(reg):
    """Ensure the worker has a registered input region for external inputs.

    The store_loop fabrication allocated state_off (accumulator) and loop_bit_off,
    but NOT space for the host-written operands (A, B, opcode). This allocates
    5 bytes (2 for A + 2 for B + 1 for opcode) using the same bump allocator
    pattern, registers them as muhl_worker.input, and journals the write.

    This is a one-time setup (like mdl_input registration), not per-run fabrication.
    """
    if INPUT_KEY in reg:
        entry = reg[INPUT_KEY]
        return int(entry["offset"]), int(entry["len"])

    # Need 5 bytes: 2 (A) + 2 (B) + 1 (opcode)
    need = 5

    # Find free space using bump allocation (same pattern as titan_circuit._alloc)
    sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
    import pfc_paths as PFCP
    idx_path = PFCP.TITAN + ".wbindex.json"

    with open(idx_path, encoding="utf-8") as f:
        idx = json.load(f)

    # Collect all occupied ranges from registry
    occ = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            o0 = int(v["offset"])
            o1 = o0 + int(v["len"])
            occ.append((o0, o1))

    # Find the largest tensor (reserved for miner) and skip it
    tensors = sorted(idx["tensors"], key=lambda t: -int(t["bytes"]))
    reserved = tensors[0]["name"] if tensors else None

    for t in tensors:
        if t["name"] == reserved:
            continue
        ts = int(t["offset"])
        te = ts + int(t["bytes"])
        p = ts
        for o0, o1 in sorted(o for o in occ if o[0] < te and o[1] > ts):
            if o1 > p:
                p = o1
        if p + need + 8 <= te:
            off = p
            # Journal and zero-fill
            journal_write(off, need, "input_region_alloc")
            with open(TITAN, "r+b") as f:
                f.seek(off)
                f.write(b"\x00" * need)

            # Register
            reg[INPUT_KEY] = {
                "offset": off,
                "len": need,
                "kind": "input_region",
                "layout": "A[2B] + B[2B] + opcode[1B], all little-endian",
                "note": "host-written external inputs for muhl_worker (inject verb)"
            }
            save_registry(reg)
            print(f"  allocated input region: offset {off:,}, {need} bytes")
            print(f"  journaled to: {GENOME_PATH}")
            return off, need

    raise RuntimeError("no free tensor space for input region")


# ============================================================================
# INJECT — bounded writes to titan.gguf
# ============================================================================

def inject(input_off, operand_a, operand_b, opcode):
    """Write operand A, operand B, and opcode to the worker's input region.

    Layout at input_off:
      [0:2]  operand A (uint16 LE)
      [2:4]  operand B (uint16 LE)
      [4]    opcode    (uint8, 3 bits used)
    """
    blob = struct.pack("<HHB", operand_a & 0xFFFF, operand_b & 0xFFFF, opcode & 0x07)
    journal_write(input_off, len(blob), "inject_operands")
    with open(TITAN, "r+b") as f:
        f.seek(input_off)
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    return blob


# ============================================================================
# SURFACE — bounded reads from titan.gguf
# ============================================================================

def surface_result(state_off, state_bytes):
    """Read the result from the worker's state register (accumulator).

    The result feeds back to the accumulator via self-clock feedback.
    state_off holds the current accumulator value = last computation result.
    """
    with open(TITAN, "rb") as f:
        f.seek(state_off)
        raw = f.read(state_bytes)
    return raw


def surface_loop_bit(loop_bit_off):
    """Read the loop bit (diagnostic only)."""
    with open(TITAN, "rb") as f:
        f.seek(loop_bit_off)
        raw = f.read(1)
    return raw


def surface_input_region(input_off, input_len):
    """Read back the input region to confirm the write landed."""
    with open(TITAN, "rb") as f:
        f.seek(input_off)
        raw = f.read(input_len)
    return raw


# ============================================================================
# MAIN
# ============================================================================

def main():
    print()
    print("=" * 72)
    print("  MUHLNICKEL TITAN HARNESS")
    print("  inject + surface for muhl_worker (16-bit ALU)")
    print("  host verbs: bounded write (inject), bounded read (surface)")
    print("  host computation on behalf of substrate: NONE")
    print("=" * 72)

    # -- load registry ---------------------------------------------------------
    if not os.path.exists(REG):
        print(f"\n  FATAL: registry not found at {REG}")
        return 1
    if not os.path.exists(TITAN):
        print(f"\n  FATAL: titan.gguf not found at {TITAN}")
        return 1

    reg = load_registry()
    if NAME not in reg:
        print(f"\n  FATAL: {NAME} not found in registry")
        return 1

    worker = reg[NAME]
    state_off    = int(worker["state_off"])
    state_bytes  = int(worker["state_bytes"])
    loop_bit_off = int(worker["loop_bit_off"])
    depth        = worker.get("depth", "?")
    n_gate       = worker.get("n_gate", "?")
    arith        = worker.get("arith", "?")
    ops          = worker.get("operations", OP_NAMES)

    print(f"\n  worker: {NAME}")
    print(f"    logic offset:   {int(worker['offset']):,}")
    print(f"    logic size:     {int(worker['len']):,} bytes")
    print(f"    gates:          {n_gate:,}")
    print(f"    depth:          {depth} ticks")
    print(f"    arithmetic:     {arith}")
    print(f"    state register: offset {state_off:,} ({state_bytes} bytes)")
    print(f"    loop bit:       offset {loop_bit_off:,}")
    print(f"    operations:     {', '.join(ops)}")
    print(f"    self-clock:     result -> accumulator (feedback)")
    print(f"    receiver:       {worker.get('receiver', '?')}")

    # -- ensure input region ---------------------------------------------------
    input_off, input_len = ensure_input_region(reg)
    print(f"\n  input region: offset {input_off:,} ({input_len} bytes)")
    print(f"    layout: A[2B] + B[2B] + opcode[1B], little-endian")

    # -- pre-state snapshot (read only) ----------------------------------------
    pre_state = surface_result(state_off, state_bytes)
    pre_loop  = surface_loop_bit(loop_bit_off)
    pre_input = surface_input_region(input_off, input_len)
    print(f"\n  PRE-STATE (read-only snapshot):")
    print(f"    state register: {pre_state.hex()}")
    print(f"    loop bit:       {pre_loop.hex()}")
    print(f"    input region:   {pre_input.hex()}")

    # =====================================================================
    # TASK 1: XOR 0x00FF ^ 0xFF00
    # =====================================================================
    print(f"\n{'=' * 72}")
    print(f"  TASK 1: XOR  operand_a=0x00FF  operand_b=0xFF00  opcode=0 (XOR)")
    print(f"{'=' * 72}")

    a1, b1, op1 = 0x00FF, 0xFF00, 0  # XOR

    # INJECT
    blob1 = inject(input_off, a1, b1, op1)
    print(f"\n  INJECT (bounded write):")
    print(f"    wrote {len(blob1)} bytes to offset {input_off:,}")
    print(f"    payload: {blob1.hex()}")
    print(f"    operand_a = {a1:#06x} ({a1})")
    print(f"    operand_b = {b1:#06x} ({b1})")
    print(f"    opcode    = {op1} ({OP_NAMES[op1]})")

    # Confirm write landed
    readback = surface_input_region(input_off, input_len)
    print(f"    readback:  {readback.hex()}")
    if readback != blob1:
        print(f"    WARNING: readback does not match payload")

    # SURFACE
    result1 = surface_result(state_off, state_bytes)
    loop1   = surface_loop_bit(loop_bit_off)
    print(f"\n  SURFACE (bounded read):")
    print(f"    state register (result): {result1.hex()}")
    print(f"    as uint16 LE: {int.from_bytes(result1, 'little'):#06x} ({int.from_bytes(result1, 'little')})")
    print(f"    loop bit: {loop1.hex()}")
    print(f"\n  RAW BYTES AT OUTPUT: {result1.hex()}")
    print(f"  (settle-back law: this is a state reading, not a verdict)")

    # =====================================================================
    # TASK 2: ADD 42 + 17
    # =====================================================================
    print(f"\n{'=' * 72}")
    print(f"  TASK 2: ADD  operand_a=42  operand_b=17  opcode=4 (ADD)")
    print(f"{'=' * 72}")

    a2, b2, op2 = 42, 17, 4  # ADD

    # INJECT
    blob2 = inject(input_off, a2, b2, op2)
    print(f"\n  INJECT (bounded write):")
    print(f"    wrote {len(blob2)} bytes to offset {input_off:,}")
    print(f"    payload: {blob2.hex()}")
    print(f"    operand_a = {a2:#06x} ({a2})")
    print(f"    operand_b = {b2:#06x} ({b2})")
    print(f"    opcode    = {op2} ({OP_NAMES[op2]})")

    readback2 = surface_input_region(input_off, input_len)
    print(f"    readback:  {readback2.hex()}")

    # SURFACE
    result2 = surface_result(state_off, state_bytes)
    loop2   = surface_loop_bit(loop_bit_off)
    print(f"\n  SURFACE (bounded read):")
    print(f"    state register (result): {result2.hex()}")
    print(f"    as uint16 LE: {int.from_bytes(result2, 'little'):#06x} ({int.from_bytes(result2, 'little')})")
    print(f"    loop bit: {loop2.hex()}")
    print(f"\n  RAW BYTES AT OUTPUT: {result2.hex()}")
    print(f"  (settle-back law: this is a state reading, not a verdict)")

    # =====================================================================
    # SUMMARY
    # =====================================================================
    print(f"\n{'=' * 72}")
    print(f"  SUMMARY")
    print(f"{'=' * 72}")
    print(f"  task 1: {OP_NAMES[op1]}({a1:#06x}, {b1:#06x}) -> state register reads {result1.hex()}")
    print(f"  task 2: {OP_NAMES[op2]}({a2:#06x}, {b2:#06x}) -> state register reads {result2.hex()}")
    print(f"\n  host writes: {2} inject operations (bounded writes to input region)")
    print(f"  host reads:  {6} surface operations (bounded reads from state/loop/input)")
    print(f"  host computation on substrate data: NONE")
    print(f"  gate tables walked: NONE")
    print(f"  journal: {GENOME_PATH}")
    print(f"\n  these are RAW STATE READINGS. the settle-back law applies:")
    print(f"  'a state reading is not evidence of failure.' -- bring the owner")
    print(f"  the measurement and let him rule.")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
