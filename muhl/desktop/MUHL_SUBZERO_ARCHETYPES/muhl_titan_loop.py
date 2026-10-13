#!/usr/bin/env python3
"""muhl_titan_loop.py -- INTERACTIVE TASK LOOP for muhl_worker.

Bryce Muhlnickel, 2026-08-03.

The "give Titan a prompt" interface. Human or Claude writes a task,
host injects it into the worker, Titan computes, host surfaces the answer.

Usage:
    python muhl_titan_loop.py                   # interactive stdin loop
    python muhl_titan_loop.py --file tasks.txt  # read tasks from file
    python muhl_titan_loop.py --once "add 42 17" # single task, exit

Task format:
    <operation> <operand_a> <operand_b>

    Operations: xor, and, or, not, add, sub, lt, accum
    Operands: decimal (42) or hex (0x2a), 0-65535

Examples:
    add 42 17
    xor 255 128
    xor 0x00ff 0xff00
    not 0xaaaa 0           (NOT ignores operand B)
    lt 100 200
    accum 10 0             (ACCUM adds A to accumulator, ignores B)
    sub 1000 999

Special commands:
    state       -- surface the current state register (no inject)
    reset       -- inject zeros to clear the accumulator
    quit / exit -- exit the loop

The host does ONLY inject (bounded writes) and surface (bounded reads).
No gate evaluation. No host arithmetic on substrate data.
"""
import json, os, struct, sys

TITAN = "C:/llm/models/titan.gguf"
REG   = "C:/llm/models/titan_circuits.json"
NAME  = "muhl_worker"
INPUT_KEY = "muhl_worker.input"
GENOME_PATH = TITAN.replace(".gguf", "_harness_genome.jsonl")

OP_NAMES = ["XOR", "AND", "OR", "NOT", "ADD", "SUB", "LT", "ACCUM"]
OP_MAP = {name.lower(): i for i, name in enumerate(OP_NAMES)}
W = 16


# ============================================================================
# JOURNAL
# ============================================================================

def journal_write(off, nbytes, tag="loop_inject"):
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
# INPUT REGION
# ============================================================================

def ensure_input_region(reg):
    """Ensure muhl_worker.input is registered. Allocate on first run."""
    if INPUT_KEY in reg:
        entry = reg[INPUT_KEY]
        return int(entry["offset"]), int(entry["len"])

    need = 5  # 2 (A) + 2 (B) + 1 (opcode)
    sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
    import pfc_paths as PFCP
    idx_path = PFCP.TITAN + ".wbindex.json"

    with open(idx_path, encoding="utf-8") as f:
        idx = json.load(f)

    occ = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            o0 = int(v["offset"])
            o1 = o0 + int(v["len"])
            occ.append((o0, o1))

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
            journal_write(off, need, "input_region_alloc")
            with open(TITAN, "r+b") as f:
                f.seek(off)
                f.write(b"\x00" * need)
            reg[INPUT_KEY] = {
                "offset": off,
                "len": need,
                "kind": "input_region",
                "layout": "A[2B] + B[2B] + opcode[1B], all little-endian",
                "note": "host-written external inputs for muhl_worker (inject verb)"
            }
            save_registry(reg)
            print(f"  [setup] allocated input region: offset {off:,}, {need} bytes")
            return off, need

    raise RuntimeError("no free tensor space for input region")


# ============================================================================
# INJECT + SURFACE
# ============================================================================

def inject(input_off, operand_a, operand_b, opcode):
    blob = struct.pack("<HHB", operand_a & 0xFFFF, operand_b & 0xFFFF, opcode & 0x07)
    journal_write(input_off, len(blob), "loop_inject")
    with open(TITAN, "r+b") as f:
        f.seek(input_off)
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    return blob


def surface_result(state_off, state_bytes):
    with open(TITAN, "rb") as f:
        f.seek(state_off)
        return f.read(state_bytes)


def surface_loop_bit(loop_bit_off):
    with open(TITAN, "rb") as f:
        f.seek(loop_bit_off)
        return f.read(1)


# ============================================================================
# TASK PARSER
# ============================================================================

def parse_int(s):
    """Parse an integer from decimal or hex string."""
    s = s.strip()
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    return int(s)


def parse_task(line):
    """Parse a task line like 'add 42 17' or 'xor 0xff 0x00'.

    Returns (op_name, operand_a, operand_b, opcode) or None on parse error.
    """
    parts = line.strip().split()
    if not parts:
        return None

    op_name = parts[0].lower()
    if op_name not in OP_MAP:
        return None

    opcode = OP_MAP[op_name]

    try:
        a = parse_int(parts[1]) if len(parts) > 1 else 0
        b = parse_int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        return None

    # Clamp to 16-bit
    a = a & 0xFFFF
    b = b & 0xFFFF

    return (op_name.upper(), a, b, opcode)


# ============================================================================
# TASK EXECUTION
# ============================================================================

def run_task(task, input_off, state_off, state_bytes, loop_bit_off, task_num):
    """Inject a task and surface the result."""
    op_name, a, b, opcode = task

    print(f"\n  --- task {task_num}: {op_name}({a:#06x}, {b:#06x}) opcode={opcode} ---")

    # INJECT
    blob = inject(input_off, a, b, opcode)
    print(f"  inject: {blob.hex()} -> offset {input_off:,}")

    # SURFACE
    result = surface_result(state_off, state_bytes)
    loop   = surface_loop_bit(loop_bit_off)
    val    = int.from_bytes(result, "little")

    print(f"  surface: state={result.hex()} ({val:#06x} = {val})  loop={loop.hex()}")
    print(f"  (raw state reading, settle-back law applies)")

    return result


# ============================================================================
# MAIN MODES
# ============================================================================

def interactive_loop(input_off, state_off, state_bytes, loop_bit_off):
    """Interactive stdin loop."""
    task_num = 0
    print(f"\n  ready. type a task (e.g. 'add 42 17') or 'quit' to exit.")
    print(f"  operations: {', '.join(n.lower() for n in OP_NAMES)}")
    print(f"  format: <op> <a> <b>    (decimal or 0x hex, 0-65535)\n")

    while True:
        try:
            line = input("  titan> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line.lower() in ("quit", "exit", "q"):
            break
        if line.lower() == "state":
            result = surface_result(state_off, state_bytes)
            loop   = surface_loop_bit(loop_bit_off)
            val    = int.from_bytes(result, "little")
            print(f"  state register: {result.hex()} ({val:#06x} = {val})  loop: {loop.hex()}")
            continue
        if line.lower() == "reset":
            inject(input_off, 0, 0, 0)
            print(f"  injected zeros (XOR 0 0) to clear")
            result = surface_result(state_off, state_bytes)
            print(f"  state register: {result.hex()}")
            continue

        task = parse_task(line)
        if task is None:
            print(f"  parse error. format: <op> <a> <b>")
            print(f"  operations: {', '.join(n.lower() for n in OP_NAMES)}")
            continue

        task_num += 1
        run_task(task, input_off, state_off, state_bytes, loop_bit_off, task_num)


def file_loop(filepath, input_off, state_off, state_bytes, loop_bit_off):
    """Read tasks from a file, one per line."""
    if not os.path.exists(filepath):
        print(f"  file not found: {filepath}")
        return
    with open(filepath, "r") as f:
        lines = f.readlines()
    task_num = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        task = parse_task(line)
        if task is None:
            print(f"  skipping unparseable line: {line}")
            continue
        task_num += 1
        run_task(task, input_off, state_off, state_bytes, loop_bit_off, task_num)
    print(f"\n  {task_num} tasks processed from {filepath}")


def single_task(task_str, input_off, state_off, state_bytes, loop_bit_off):
    """Run a single task from command line."""
    task = parse_task(task_str)
    if task is None:
        print(f"  parse error: {task_str}")
        print(f"  format: <op> <a> <b>")
        return
    run_task(task, input_off, state_off, state_bytes, loop_bit_off, 1)


def main():
    print()
    print("  MUHLNICKEL TITAN LOOP -- interactive task interface")
    print("  inject + surface for muhl_worker (16-bit ALU)")
    print("  host computation: NONE. gate tables walked: NONE.")

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

    print(f"  worker: {NAME}  gates={worker.get('n_gate', '?'):,}  depth={worker.get('depth', '?')} ticks")

    # Ensure input region exists
    input_off, input_len = ensure_input_region(reg)
    print(f"  input region: offset {input_off:,} ({input_len} bytes)")
    print(f"  output: state register @ {state_off:,} ({state_bytes} bytes)")

    # Parse command-line mode
    args = sys.argv[1:]
    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 < len(args):
            file_loop(args[idx + 1], input_off, state_off, state_bytes, loop_bit_off)
        else:
            print("  --file requires a path argument")
            return 1
    elif "--once" in args:
        idx = args.index("--once")
        if idx + 1 < len(args):
            single_task(args[idx + 1], input_off, state_off, state_bytes, loop_bit_off)
        else:
            print("  --once requires a task string argument")
            return 1
    else:
        interactive_loop(input_off, state_off, state_bytes, loop_bit_off)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
