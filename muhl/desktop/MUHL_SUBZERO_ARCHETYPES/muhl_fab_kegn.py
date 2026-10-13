#!/usr/bin/env python3
"""muhl_fab_kegn.py -- FABRICATE Kinetic Enthalpy Gas Network (KEGN)

Lattice Boltzmann thermodynamic gas as a flat-binary NAND gate network stored
in titan.gguf.  Physical format: <BQQQ> stride-25, absolute file offsets.

Structure (3x3 torus lattice, 9 cells):
  Input:      9 x 8 bits = 72 bits (one byte per lattice cell)
  Collision:  NOT each bit (relaxation toward complement -- simplest BGK)
  Streaming:  each cell receives XOR of its neighbors (particle redistribution)
  Temperature: OR-tree over all 72 post-streaming bits (any activity? 1-bit)
  Free energy: byte-wise XOR of all 9 cells (per-bit parity = disorder, 8-bit)

Output: 72 bits (streamed lattice) + 1 bit (temperature) + 8 bits (free energy)
      = 81 output wires.

PROPOSE -> SCORE -> VERIFY -> KEEP.
  Candidate A (4n):  4-neighbor streaming (N/S/E/W on torus).  Full LB.
  Candidate B (2n):  2-neighbor streaming (E/W only).  1D-like, fewer gates.

Minimal: 3x3 torus, 8-bit cells, self-clocked.

    python muhl_fab_kegn.py              # fabricate and store (journaled)
    python muhl_fab_kegn.py --dry        # build + verify, store nothing
    python muhl_fab_kegn.py --revert     # byte-exact revert

Manufacturing -- offline, one-and-done.  NOT runtime.
"""
import json, os, random, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"
REG   = "C:/llm/models/titan_circuits.json"
NAME  = "muhl_kegn"
MAGIC = b"MUHLKEGN"
GATE_STRIDE = 25
GENOME_PATH = TITAN.replace(".gguf", f"_{NAME}_genome.jsonl")
DRY    = "--dry" in sys.argv
REVERT = "--revert" in sys.argv

ROWS = 3
COLS = 3
CELLS = ROWS * COLS
BITS_PER_CELL = 8
TOTAL_IN = CELLS * BITS_PER_CELL  # 72


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


def tree_or(c, bits):
    items = list(bits)
    while len(items) > 1:
        nxt = [c.or_(items[i], items[i + 1]) for i in range(0, len(items) - 1, 2)]
        if len(items) % 2:
            nxt.append(items[-1])
        items = nxt
    return items[0] if items else c.C0


def xor_vecs(c, a, b):
    """XOR two equal-length wire vectors."""
    return [c.xor(a[i], b[i]) for i in range(len(a))]


def cidx(i, j):
    """Torus-wrapped cell index for (row, col)."""
    return (i % ROWS) * COLS + (j % COLS)


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
        "note": ("KEGN: Kinetic Enthalpy Gas Network -- Lattice Boltzmann "
                 "3x3 torus, NOT collision, XOR streaming, self-clocked."),
        "verified_by": "byte-exact vs Python reference, 1012 test vectors"
    }
    json.dump(reg, open(REG, "w"), indent=1)


# ---------------------------------------------------------------------------
# circuit builders
# ---------------------------------------------------------------------------
def build_kegn_4n():
    """Candidate A: 4-neighbor (N/S/E/W) streaming on 3x3 torus."""
    c = TC.Circuit(TOTAL_IN)
    cells = [list(c.IN[i * 8:(i + 1) * 8]) for i in range(CELLS)]

    # Collision: NOT each bit
    post = [[c.not_(cells[ci][b]) for b in range(8)] for ci in range(CELLS)]

    # Streaming: each cell = XOR of 4 torus neighbors
    streamed = []
    for i in range(ROWS):
        for j in range(COLS):
            n = post[cidx(i - 1, j)]
            s = post[cidx(i + 1, j)]
            e = post[cidx(i, j + 1)]
            w = post[cidx(i, j - 1)]
            t1 = xor_vecs(c, n, s)
            t2 = xor_vecs(c, t1, e)
            cell_out = xor_vecs(c, t2, w)
            streamed.append(cell_out)

    # Flatten all streamed bits
    all_bits = [b for cell in streamed for b in cell]  # 72 bits

    # Temperature: OR-tree over all bits
    temp = tree_or(c, all_bits)

    # Free energy: byte-wise XOR of all 9 cells
    acc = streamed[0]
    for k in range(1, CELLS):
        acc = xor_vecs(c, acc, streamed[k])
    free_energy = acc  # 8 bits

    outs = all_bits + [temp] + free_energy  # 72 + 1 + 8 = 81
    return c, outs, "4n"


def build_kegn_2n():
    """Candidate B: 2-neighbor (E/W only) streaming.  Fewer gates, shallower."""
    c = TC.Circuit(TOTAL_IN)
    cells = [list(c.IN[i * 8:(i + 1) * 8]) for i in range(CELLS)]

    post = [[c.not_(cells[ci][b]) for b in range(8)] for ci in range(CELLS)]

    streamed = []
    for i in range(ROWS):
        for j in range(COLS):
            e = post[cidx(i, j + 1)]
            w = post[cidx(i, j - 1)]
            cell_out = xor_vecs(c, e, w)
            streamed.append(cell_out)

    all_bits = [b for cell in streamed for b in cell]
    temp = tree_or(c, all_bits)
    acc = streamed[0]
    for k in range(1, CELLS):
        acc = xor_vecs(c, acc, streamed[k])
    free_energy = acc

    outs = all_bits + [temp] + free_energy
    return c, outs, "2n"


# ---------------------------------------------------------------------------
# reference implementations
# ---------------------------------------------------------------------------
def kegn_4n_ref(cell_bytes):
    """Python reference: 4-neighbor streaming on 3x3 torus."""
    post = [(~cb) & 0xFF for cb in cell_bytes]
    def at(i, j):
        return post[(i % ROWS) * COLS + (j % COLS)]
    streamed = []
    for i in range(ROWS):
        for j in range(COLS):
            v = at(i - 1, j) ^ at(i + 1, j) ^ at(i, j - 1) ^ at(i, j + 1)
            streamed.append(v & 0xFF)
    all_or = 0
    for s in streamed:
        all_or |= s
    temp = 1 if all_or else 0
    parity = 0
    for s in streamed:
        parity ^= s
    return streamed, temp, parity & 0xFF


def kegn_2n_ref(cell_bytes):
    """Python reference: 2-neighbor (E/W) streaming on 3x3 torus."""
    post = [(~cb) & 0xFF for cb in cell_bytes]
    def at(i, j):
        return post[(i % ROWS) * COLS + (j % COLS)]
    streamed = []
    for i in range(ROWS):
        for j in range(COLS):
            v = at(i, j - 1) ^ at(i, j + 1)
            streamed.append(v & 0xFF)
    all_or = 0
    for s in streamed:
        all_or |= s
    temp = 1 if all_or else 0
    parity = 0
    for s in streamed:
        parity ^= s
    return streamed, temp, parity & 0xFF


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------
def bytes_to_inbits(cell_bytes):
    """Convert list of 9 bytes to 72-bit input vector for TC.ripple."""
    bits = []
    for bv in cell_bytes:
        bits.extend([(bv >> b) & 1 for b in range(8)])
    return bits


def verify_candidate(circ, outs, ref_fn, label):
    """Byte-exact verification against Python reference over test vectors."""
    cd = circ_dict(circ, outs)
    mismatches = 0
    first_mm = None
    total_tests = 0

    test_cases = []
    # Edge cases
    test_cases.append([0x00] * 9)
    test_cases.append([0xFF] * 9)
    test_cases.append(list(range(1, 10)))
    test_cases.append(list(range(0xF0, 0xF9)))
    # Single-cell active
    for ci in range(9):
        vec = [0x00] * 9
        vec[ci] = 0x01
        test_cases.append(vec)
        vec2 = [0x00] * 9
        vec2[ci] = 0x80
        test_cases.append(vec2)
    # Random
    rng = random.Random(42)
    for _ in range(990):
        test_cases.append([rng.randint(0, 255) for _ in range(9)])

    for cell_bytes in test_cases:
        total_tests += 1
        inbits = bytes_to_inbits(cell_bytes)
        raw = TC.ripple(cd, inbits)

        # Parse circuit output
        got_cells = []
        for ci in range(CELLS):
            got_cells.append(TC.frombits(raw[ci * 8:(ci + 1) * 8]))
        got_temp = raw[72]
        got_fe = TC.frombits(raw[73:81])

        # Reference
        exp_cells, exp_temp, exp_fe = ref_fn(cell_bytes)

        ok = (got_cells == exp_cells and got_temp == exp_temp and got_fe == exp_fe)
        if not ok:
            mismatches += 1
            if first_mm is None:
                first_mm = (cell_bytes, got_cells, got_temp, got_fe,
                            exp_cells, exp_temp, exp_fe)

    ok = (mismatches == 0)
    status = "PASS" if ok else f"FAIL ({mismatches}/{total_tests} mismatches)"
    print(f"  [{label}] verify: {status} ({total_tests} test vectors)")
    if first_mm:
        cb, gc, gt, gf, ec, et, ef = first_mm
        print(f"    first mismatch: input={cb[:3]}... got_temp={gt} exp_temp={et}")
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
        assert stored == wa(o), f"out addr {i}"

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
    print("\n  MUHLNICKEL KEGN -- Kinetic Enthalpy Gas Network")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    if not os.path.exists(TITAN):
        print(f"  ERROR: {TITAN} not found."); return 1

    if os.path.exists(REG):
        reg = json.load(open(REG))
        if NAME in reg and not DRY:
            print(f"  {NAME} already in registry.  Run --revert first."); return 1

    # ---- PROPOSE ----
    candidates = []
    for builder, ref_fn, label in [
        (build_kegn_4n, kegn_4n_ref, "4n"),
        (build_kegn_2n, kegn_2n_ref, "2n"),
    ]:
        print(f"  building candidate {label} ...", end=" ", flush=True)
        circ, outs, tag = builder()
        d = depth_of(circ, outs)
        g = len(circ.ga)
        print(f"done ({g:,} gates, depth {d})")
        candidates.append((circ, outs, ref_fn, tag, d, g))

    # ---- SCORE ----
    print("\n  PROPOSE / SCORE:")
    for circ, outs, ref_fn, tag, d, g in candidates:
        print(f"    {tag:6s}  gates={g:>6,}  depth={d:>3} ticks  "
              f"wires={circ.n_wire():>6,}  n_out={len(outs)}")

    # ---- VERIFY ----
    print("\n  VERIFY (byte-exact, ~1012 test vectors per candidate):")
    all_ok = True
    for circ, outs, ref_fn, tag, d, g in candidates:
        ok = verify_candidate(circ, outs, ref_fn, tag)
        all_ok = all_ok and ok

    if not all_ok:
        print("\n  FABRICATION ABORTED: verification failed."); return 1

    # ---- PARETO SET ----
    dominated = set()
    for i, (_, _, _, ti, di, gi) in enumerate(candidates):
        for j, (_, _, _, tj, dj, gj) in enumerate(candidates):
            if i != j and dj <= di and gj <= gi and (dj < di or gj < gi):
                dominated.add(i)
    pareto = [c for i, c in enumerate(candidates) if i not in dominated]

    print(f"\n  PARETO SET ({len(pareto)} candidate{'s' if len(pareto) != 1 else ''}):")
    for circ, outs, ref_fn, tag, d, g in pareto:
        print(f"    {tag:6s}  gates={g:>6,}  depth={d:>3} ticks")

    # ---- KEEP: shallowest ----
    winner = min(pareto, key=lambda x: (x[4], x[5]))
    circ, outs, ref_fn, tag, d, g = winner
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
        "archetype": "KEGN",
        "candidate": tag,
        "topology": f"lattice_boltzmann_{ROWS}x{COLS}_torus",
        "streaming": tag,
        "collision": "NOT",
        "depth": d,
        "gates": g,
        "pareto_set": [{"tag": t, "depth": dd, "gates": gg}
                       for _, _, _, t, dd, gg in pareto]
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

    print(f"\n  KEGN FABRICATED.")
    print(f"  lattice: {ROWS}x{COLS} torus, {CELLS} cells, {BITS_PER_CELL}-bit each")
    print(f"  inject: write 72 input bits (9 bytes) to {in_addrs[0]:,}...")
    print(f"  surface: read 81 output bits from {out_addrs[0]:,}...")
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
