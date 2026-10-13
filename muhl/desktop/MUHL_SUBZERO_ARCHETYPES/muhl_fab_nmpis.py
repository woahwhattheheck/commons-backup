#!/usr/bin/env python3
"""muhl_fab_nmpis.py -- FABRICATE Non-Markovian Path-Integral Synthesizer (NMPIS)

Feynman path integrals as a flat-binary NAND gate network stored in titan.gguf.
Physical format: <BQQQ> stride-25, absolute file offsets.

Structure (4 paths x 3 steps):
  Input:  8 bits (initial amplitude / state)
  Paths:  4 independent paths, each a 3-step chain of XOR transformations
          with path-specific constants encoding the action S along each path.
  Non-Markovian: each step reads ALL prior steps' outputs (DAG, not chain).
          Step k accumulates XOR of input + step_0 + ... + step_{k-1} + const_k.
  Attenuation: depth-proportional signal thinning via right-shift.
          Path p is right-shifted by p bits (div by 2^p -- exponential weighting).
  Fan-in: tree of adders collecting all attenuated path contributions.

Output: 8-bit sum + 4 x 8-bit individual path outputs = 40 output bits.

PROPOSE -> SCORE -> VERIFY -> KEEP.
  Candidate A (ripple): ripple-carry adders for fan-in tree.  Fewer gates.
  Candidate B (prefix): Kogge-Stone prefix adders.  Shallower.

Minimal: 4 paths, 3 steps each, 8-bit data path.

    python muhl_fab_nmpis.py             # fabricate and store (journaled)
    python muhl_fab_nmpis.py --dry       # build + verify, store nothing
    python muhl_fab_nmpis.py --revert    # byte-exact revert

Manufacturing -- offline, one-and-done.  NOT runtime.
"""
import json, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"
REG   = "C:/llm/models/titan_circuits.json"
NAME  = "muhl_nmpis"
MAGIC = b"MUHLNMPI"
GATE_STRIDE = 25
GENOME_PATH = TITAN.replace(".gguf", f"_{NAME}_genome.jsonl")
DRY    = "--dry" in sys.argv
REVERT = "--revert" in sys.argv

N_PATHS = 4
N_STEPS = 3
WIDTH   = 8

# Path constants encoding the action S along each path.
# Each path has N_STEPS constants.  Different constants = different actions.
PATH_CONSTS = [
    [0x11, 0x22, 0x33],   # path 0
    [0x44, 0x55, 0x66],   # path 1
    [0x77, 0x88, 0x99],   # path 2
    [0xAA, 0xBB, 0xCC],   # path 3
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def depth_of(circ, outs):
    n_in = circ.n_in
    d = [0] * circ.n_wire()
    for k in range(len(circ.ga)):
        d[2 + n_in + k] = 1 + max(d[circ.ga[k]], d[circ.gb[k]])
    return max(d[o] for o in outs) if outs else 0


def circ_dict(c, outs):
    return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def xor_vecs(c, a, b):
    return [c.xor(a[i], b[i]) for i in range(len(a))]


def xor_const(c, bits, val, w=WIDTH):
    """XOR wire vector with a constant.  NOT for 1-bits, identity for 0-bits."""
    return [c.not_(bits[i]) if (val >> i) & 1 else bits[i] for i in range(w)]


def alloc_space(nbytes):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    occupied = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            occupied.append((v["offset"], v["offset"] + v["len"]))
    hi = max((e for _, e in occupied), default=0)
    off = ((hi + 63) // 64) * 64
    fsize = os.path.getsize(TITAN)
    if off + nbytes > fsize:
        print(f"  NOTE: {NAME} ({nbytes:,} B) extends past EOF ({fsize:,}).  Will grow.")
    return off


def to_physical(circ, outs, base_off):
    n_in    = circ.n_in
    n_gates = len(circ.ga)
    n_wires = circ.n_wire()
    n_out   = len(outs)
    depth   = depth_of(circ, outs)

    hdr_size   = 28 + n_out * 8
    wire_start = hdr_size
    gate_start = wire_start + n_wires
    total      = gate_start + n_gates * GATE_STRIDE

    def wa(w):
        return base_off + wire_start + w

    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, n_gates, n_wires, n_in, n_out, depth)
    for i, o in enumerate(outs):
        struct.pack_into("<Q", blob, 28 + i * 8, wa(o))
    blob[wire_start]     = 0
    blob[wire_start + 1] = 1

    off = gate_start
    for k in range(n_gates):
        struct.pack_into("<BQQQ", blob, off, 0,
                         wa(circ.ga[k]), wa(circ.gb[k]), wa(2 + n_in + k))
        off += GATE_STRIDE

    input_addrs  = [wa(2 + i) for i in range(n_in)]
    output_addrs = [wa(o) for o in outs]
    return bytes(blob), total, depth, input_addrs, output_addrs


def journal_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off); orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({"action": f"{NAME}_fab", "off": off,
                             "len": len(blob), "orig": orig.hex()}) + "\n")
    fsize = os.path.getsize(TITAN)
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)


def update_registry(base_off, total, depth, n_gates, n_in, n_out,
                    input_addrs, output_addrs, genome):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "name": NAME,
        "offset": base_off,
        "len": total,
        "n_gate": n_gates,
        "n_in": n_in,
        "n_out": n_out,
        "depth": depth,
        "format": "physical",
        "magic": MAGIC.decode(),
        "gate_stride": GATE_STRIDE,
        "input_addrs": input_addrs,
        "output_addrs": output_addrs,
        "foundry_genome": genome,
        "units": "n_gate=GATES, depth=TICKS, len=BYTES",
        "genome": GENOME_PATH,
        "note": ("NMPIS: Non-Markovian Path-Integral Synthesizer -- Feynman "
                 "path integrals as NAND gates.  4 paths x 3 steps, "
                 "depth-proportional attenuation, tree fan-in."),
        "verified_by": "byte-exact vs Python reference, 256/256 inputs"
    }
    json.dump(reg, open(REG, "w"), indent=1)


# ---------------------------------------------------------------------------
# circuit builders
# ---------------------------------------------------------------------------
def _build_paths(c, input_bits):
    """Build 4 path computations with non-Markovian wiring.
    Returns list of 4 path-final wire vectors (8 bits each)."""
    paths = []
    for p in range(N_PATHS):
        step_outputs = []       # outputs of completed steps
        for k in range(N_STEPS):
            # Non-Markovian: accumulate XOR of input + all prior step outputs
            acc = list(input_bits)
            for prior in step_outputs:
                acc = xor_vecs(c, acc, prior)
            # Apply path constant (the action for this step)
            step_out = xor_const(c, acc, PATH_CONSTS[p][k])
            step_outputs.append(step_out)
        paths.append(step_outputs[-1])
    return paths


def _attenuate(c, paths):
    """Depth-proportional attenuation: right-shift path p by p bits.
    Pure rewiring (no gates for the shift itself)."""
    attenuated = []
    for p in range(N_PATHS):
        shifted = []
        for i in range(WIDTH):
            if i + p < WIDTH:
                shifted.append(paths[p][i + p])
            else:
                shifted.append(c.C0)
        attenuated.append(shifted)
    return attenuated


def build_nmpis_ripple():
    """Candidate A: ripple-carry adders for the fan-in tree."""
    c = TC.Circuit(WIDTH)
    input_bits = list(c.IN)

    paths = _build_paths(c, input_bits)
    attenuated = _attenuate(c, paths)

    # Fan-in tree: sum all attenuated paths (ripple carry)
    temp1  = c.add(attenuated[0], attenuated[1])
    temp2  = c.add(attenuated[2], attenuated[3])
    result = c.add(temp1, temp2)

    # Outputs: individual path finals + sum
    outs = []
    for p in range(N_PATHS):
        outs.extend(paths[p])           # 4 x 8 = 32 bits
    outs.extend(result)                  # 8 bits
    return c, outs, "ripple"


def build_nmpis_prefix():
    """Candidate B: Kogge-Stone prefix adders for the fan-in tree.  Shallower."""
    c = TC.Circuit(WIDTH)
    input_bits = list(c.IN)

    paths = _build_paths(c, input_bits)
    attenuated = _attenuate(c, paths)

    # Fan-in tree: sum via prefix adders
    temp1  = c.add_prefix(attenuated[0], attenuated[1])
    temp2  = c.add_prefix(attenuated[2], attenuated[3])
    result = c.add_prefix(temp1, temp2)

    outs = []
    for p in range(N_PATHS):
        outs.extend(paths[p])
    outs.extend(result)
    return c, outs, "prefix"


# ---------------------------------------------------------------------------
# reference implementation
# ---------------------------------------------------------------------------
def nmpis_ref(env_byte):
    """Python reference: 4 paths x 3 steps, non-Markovian, attenuated, summed."""
    path_finals = []
    for p in range(N_PATHS):
        steps = []
        for k in range(N_STEPS):
            acc = env_byte
            for s in steps:
                acc ^= s
            acc ^= PATH_CONSTS[p][k]
            steps.append(acc & 0xFF)
        path_finals.append(steps[-1])

    # Attenuation: right-shift by path index
    attenuated = [(path_finals[p] >> p) & 0xFF for p in range(N_PATHS)]

    # Sum (mod 256)
    total = sum(attenuated) & 0xFF

    return path_finals, total


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------
def verify_candidate(circ, outs, label):
    """Byte-exact verification against Python reference over all 256 inputs."""
    cd = circ_dict(circ, outs)
    mismatches = 0
    first_mm = None
    for val in range(256):
        inbits = [(val >> b) & 1 for b in range(WIDTH)]
        raw = TC.ripple(cd, inbits)

        # Parse circuit output: 4 path outputs (8 bits each) + sum (8 bits)
        got_paths = []
        for p in range(N_PATHS):
            got_paths.append(TC.frombits(raw[p * 8:(p + 1) * 8]))
        got_sum = TC.frombits(raw[N_PATHS * 8:(N_PATHS + 1) * 8])

        exp_paths, exp_sum = nmpis_ref(val)

        if got_paths != exp_paths or got_sum != exp_sum:
            mismatches += 1
            if first_mm is None:
                first_mm = (val, got_paths, got_sum, exp_paths, exp_sum)

    ok = (mismatches == 0)
    status = "PASS" if ok else f"FAIL ({mismatches}/256 mismatches)"
    print(f"  [{label}] verify: {status} (256/256 inputs)")
    if first_mm:
        v, gp, gs, ep, es = first_mm
        print(f"    first mismatch: input={v:#04x}")
        print(f"      got paths={[hex(x) for x in gp]} sum={gs:#04x}")
        print(f"      exp paths={[hex(x) for x in ep]} sum={es:#04x}")
    return ok


def verify_physical(blob, base_off, circ, outs):
    assert blob[:8] == MAGIC, "bad magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert ng == len(circ.ga)
    assert nw == circ.n_wire()
    assert ni == circ.n_in
    assert no == len(outs)

    hdr = 28 + no * 8
    wst = hdr

    def wa(w):
        return base_off + wst + w

    for i, o in enumerate(outs):
        stored = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored == wa(o)

    gst = wst + nw
    off = gst
    for k in range(ng):
        op, a, b, out = struct.unpack_from("<BQQQ", blob, off)
        assert op == 0
        assert a == wa(circ.ga[k])
        assert b == wa(circ.gb[k])
        assert out == wa(2 + ni + k)
        off += GATE_STRIDE
    return True


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("\n  MUHLNICKEL NMPIS -- Non-Markovian Path-Integral Synthesizer")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    if not os.path.exists(TITAN):
        print(f"  ERROR: {TITAN} not found."); return 1

    if os.path.exists(REG):
        reg = json.load(open(REG))
        if NAME in reg and not DRY:
            print(f"  {NAME} already in registry.  Run --revert first."); return 1

    # ---- PROPOSE ----
    candidates = []
    for builder, label in [
        (build_nmpis_ripple, "ripple"),
        (build_nmpis_prefix, "prefix"),
    ]:
        print(f"  building candidate {label} ...", end=" ", flush=True)
        circ, outs, tag = builder()
        d = depth_of(circ, outs)
        g = len(circ.ga)
        print(f"done ({g:,} gates, depth {d})")
        candidates.append((circ, outs, tag, d, g))

    # ---- SCORE ----
    print("\n  PROPOSE / SCORE:")
    for circ, outs, tag, d, g in candidates:
        print(f"    {tag:8s}  gates={g:>6,}  depth={d:>3} ticks  "
              f"wires={circ.n_wire():>6,}  n_out={len(outs)}")

    # ---- VERIFY ----
    print("\n  VERIFY (byte-exact, 256/256 inputs per candidate):")
    all_ok = True
    for circ, outs, tag, d, g in candidates:
        ok = verify_candidate(circ, outs, tag)
        all_ok = all_ok and ok

    if not all_ok:
        print("\n  FABRICATION ABORTED: verification failed."); return 1

    # ---- PARETO SET ----
    dominated = set()
    for i, (_, _, ti, di, gi) in enumerate(candidates):
        for j, (_, _, tj, dj, gj) in enumerate(candidates):
            if i != j and dj <= di and gj <= gi and (dj < di or gj < gi):
                dominated.add(i)
    pareto = [c for i, c in enumerate(candidates) if i not in dominated]

    print(f"\n  PARETO SET ({len(pareto)} candidate{'s' if len(pareto) != 1 else ''}):")
    for circ, outs, tag, d, g in pareto:
        print(f"    {tag:8s}  gates={g:>6,}  depth={d:>3} ticks")

    # ---- KEEP: shallowest ----
    winner = min(pareto, key=lambda x: (x[3], x[4]))
    circ, outs, tag, d, g = winner
    print(f"\n  WINNER: {tag}  (depth {d}, {g:,} gates)")

    # ---- BUILD PHYSICAL ----
    base_off = alloc_space(0)
    blob, total, depth, in_addrs, out_addrs = to_physical(circ, outs, base_off)
    base_off = alloc_space(total)
    blob, total, depth, in_addrs, out_addrs = to_physical(circ, outs, base_off)

    print(f"  physical blob: {total:,} bytes at offset {base_off:,}")

    phys_ok = verify_physical(blob, base_off, circ, outs)
    print(f"  physical structural verify: {'PASS' if phys_ok else 'FAIL'}")
    if not phys_ok:
        print("  ABORTING"); return 1

    genome = {
        "archetype": "NMPIS",
        "candidate": tag,
        "topology": f"path_integral_{N_PATHS}paths_{N_STEPS}steps",
        "fan_in": tag,
        "non_markovian": True,
        "attenuation": "right_shift_by_path_index",
        "path_consts": PATH_CONSTS,
        "depth": d,
        "gates": g,
        "pareto_set": [{"tag": t, "depth": dd, "gates": gg}
                       for _, _, t, dd, gg in pareto]
    }

    if DRY:
        print(f"\n  --dry: nothing stored."); return 0

    # ---- STORE ----
    print(f"\n  FABRICATING: writing {total:,} bytes at offset {base_off:,}")
    journal_write(base_off, blob)
    print(f"  journaled to: {GENOME_PATH}")

    update_registry(base_off, total, depth, g, circ.n_in, len(outs),
                    in_addrs, out_addrs, genome)
    print(f"  registry updated: {NAME}")

    with open(TITAN, "rb") as f:
        gguf_ok = f.read(4) == b"GGUF"
    print(f"  titan.gguf GGUF-valid: {gguf_ok}")

    print(f"\n  NMPIS FABRICATED.")
    print(f"  paths: {N_PATHS}, steps: {N_STEPS}, non-Markovian (full DAG)")
    print(f"  inject: write 8 input bits to {in_addrs[0]:,}...")
    print(f"  surface: read 40 output bits from {out_addrs[0]:,}...")
    print(f"    bits  0-31: individual path outputs (4 x 8-bit)")
    print(f"    bits 32-39: attenuated sum (the path integral)")
    print(f"  depth: {depth} ticks end-to-end.")
    return 0


def revert():
    print(f"\n  reverting {NAME} ...")
    if os.path.exists(GENOME_PATH):
        entries = [json.loads(l) for l in open(GENOME_PATH) if l.strip()]
        for entry in reversed(entries):
            with open(TITAN, "r+b") as f:
                f.seek(int(entry["off"]))
                f.write(bytes.fromhex(entry["orig"]))
        os.remove(GENOME_PATH)
        print(f"  restored {len(entries)} journal entries")
    else:
        print("  no genome journal found")
    if os.path.exists(REG):
        reg = json.load(open(REG))
        if NAME in reg:
            reg.pop(NAME)
            json.dump(reg, open(REG, "w"), indent=1)
            print(f"  removed {NAME} from registry")
    with open(TITAN, "rb") as f:
        gguf_ok = f.read(4) == b"GGUF"
    print(f"  titan.gguf GGUF-valid: {gguf_ok}")
    return 0


if __name__ == "__main__":
    if REVERT:
        raise SystemExit(revert())
    else:
        raise SystemExit(main())
