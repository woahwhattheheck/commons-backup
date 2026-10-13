#!/usr/bin/env python3
"""muhl_fab_vscf.py -- FABRICATE Viable System Cybernetic Field (VSCF)

Stafford Beer's Viable System Model as a flat-binary NAND gate network stored
in titan.gguf.  Physical format: <BQQQ> stride-25, absolute file offsets.

5-tier recursive control hierarchy:
  S1 (operations):    2 units transforming environment input
  S2 (coordination):  XOR of S1 outputs (detect divergence between units)
  S3 (control):       OR-tree reduce of S2 (any divergence? 1-bit flag)
  S4 (intelligence):  MUX: if divergence, pass raw env; else pass S1_0 output
  S5 (policy):        AND of S4 bits with S3 flag (policy gate)

Each tier reads from below, writes to above.  Recursive: S1 units are the
operational core and could themselves contain viable systems.

PROPOSE -> SCORE -> VERIFY -> KEEP.
  Candidate A (xor):  S1 = NOT + rotated-NOT.  Shallow, fewer gates.
  Candidate B (inc):  S1 = add-1 + NOT.  Deeper, more gates (arithmetic S1).

Minimal: 2 System-1 units, 8-bit data path, 9 output wires.

    python muhl_fab_vscf.py              # fabricate and store (journaled)
    python muhl_fab_vscf.py --dry        # build + verify, store nothing
    python muhl_fab_vscf.py --revert     # byte-exact revert

Manufacturing -- offline, one-and-done.  NOT runtime.
"""
import json, os, random, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"
REG   = "C:/llm/models/titan_circuits.json"
NAME  = "muhl_vscf"
MAGIC = b"MUHLVSCF"
GATE_STRIDE = 25
GENOME_PATH = TITAN.replace(".gguf", f"_{NAME}_genome.jsonl")
DRY    = "--dry" in sys.argv
REVERT = "--revert" in sys.argv


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def depth_of(circ, outs):
    """Structural depth in ticks from gate topology.  Pure structure, no eval."""
    n_in = circ.n_in
    d = [0] * circ.n_wire()
    for k in range(len(circ.ga)):
        d[2 + n_in + k] = 1 + max(d[circ.ga[k]], d[circ.gb[k]])
    return max(d[o] for o in outs) if outs else 0


def circ_dict(c, outs):
    """Wrap Circuit + outputs for TC.ripple."""
    return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def tree_or(c, bits):
    """Balanced OR-tree reduce.  Depth = ceil(log2(N)) * 2."""
    items = list(bits)
    while len(items) > 1:
        nxt = [c.or_(items[i], items[i + 1]) for i in range(0, len(items) - 1, 2)]
        if len(items) % 2:
            nxt.append(items[-1])
        items = nxt
    return items[0] if items else c.C0


def alloc_space(nbytes):
    """Bump-allocate past all existing circuits (64-byte aligned)."""
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
    """Convert TC.Circuit to physical <BQQQ> stride-25 blob with absolute addresses.

    Layout:
      [0:8]     magic
      [8:28]    n_gates(4) n_wires(4) n_in(4) n_out(4) depth(4)
      [28:28+n_out*8]  output wire absolute addresses
      [hdr_end : hdr_end+n_wires]  wire bytes (const0, const1, inputs, gate outputs)
      [wire_end : wire_end+n_gates*25]  gate table (<BQQQ>)
    """
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
    blob[wire_start]     = 0   # const0
    blob[wire_start + 1] = 1   # const1

    off = gate_start
    for k in range(n_gates):
        struct.pack_into("<BQQQ", blob, off, 0,
                         wa(circ.ga[k]), wa(circ.gb[k]), wa(2 + n_in + k))
        off += GATE_STRIDE

    input_addrs  = [wa(2 + i) for i in range(n_in)]
    output_addrs = [wa(o) for o in outs]
    return bytes(blob), total, depth, input_addrs, output_addrs


def journal_write(off, blob):
    """Journaled write -- save original bytes first for revert."""
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
        "note": ("VSCF: Viable System Cybernetic Field -- Beer's 5-tier VSM "
                 "as NAND gates.  2 S1 units, 8-bit, self-clocked."),
        "verified_by": "byte-exact vs Python reference, 256/256 inputs"
    }
    json.dump(reg, open(REG, "w"), indent=1)


# ---------------------------------------------------------------------------
# circuit builders
# ---------------------------------------------------------------------------
def build_vscf_xor():
    """Candidate A: S1 = NOT / rotated-NOT.  Shallow, low gate count."""
    c   = TC.Circuit(8)
    env = list(c.IN)                       # 8 input wires

    # S1_0: NOT all bits (bitwise inversion)
    s1_0 = [c.not_(env[i]) for i in range(8)]

    # S1_1: NOT with 1-bit left rotation of input
    s1_1 = [c.not_(env[(i + 1) % 8]) for i in range(8)]

    # S2 (coordination): XOR(S1_0, S1_1) -- detect divergence
    s2 = [c.xor(s1_0[i], s1_1[i]) for i in range(8)]

    # S3 (control): OR-tree of S2 -- any divergence?
    s3 = tree_or(c, s2)

    # S4 (intelligence): MUX(S3, S1_0, env)  -- s3 ? env : s1_0
    s4 = [c.mux(s3, s1_0[i], env[i]) for i in range(8)]

    # S5 (policy): AND(S4[i], S3) -- output only when divergent
    s5 = [c.and_(s4[i], s3) for i in range(8)]

    outs = s5 + [s3]                       # 9 outputs: 8-bit policy + 1-bit flag
    return c, outs, "xor"


def build_vscf_inc():
    """Candidate B: S1 = increment / NOT.  Deeper S1 (arithmetic), more gates."""
    c   = TC.Circuit(8)
    env = list(c.IN)

    # S1_0: env + 1 (ripple carry)
    s1_0 = c.add(env, c.cvec(1, 8))

    # S1_1: NOT(env)
    s1_1 = [c.not_(env[i]) for i in range(8)]

    # S2
    s2 = [c.xor(s1_0[i], s1_1[i]) for i in range(8)]

    # S3
    s3 = tree_or(c, s2)

    # S4
    s4 = [c.mux(s3, s1_0[i], env[i]) for i in range(8)]

    # S5
    s5 = [c.and_(s4[i], s3) for i in range(8)]

    outs = s5 + [s3]
    return c, outs, "inc"


# ---------------------------------------------------------------------------
# reference implementations (Python)
# ---------------------------------------------------------------------------
def vscf_xor_ref(env_byte):
    bits = [(env_byte >> i) & 1 for i in range(8)]
    s1_0 = [1 - bits[i] for i in range(8)]
    s1_1 = [1 - bits[(i + 1) % 8] for i in range(8)]
    s2   = [s1_0[i] ^ s1_1[i] for i in range(8)]
    s3   = 1 if any(s2) else 0
    s4   = [bits[i] if s3 else s1_0[i] for i in range(8)]
    s5   = [s4[i] & s3 for i in range(8)]
    s5v  = sum(b << i for i, b in enumerate(s5))
    return s5v, s3


def vscf_inc_ref(env_byte):
    s1_0v = (env_byte + 1) & 0xFF
    s1_1v = (~env_byte) & 0xFF
    bits  = [(env_byte >> i) & 1 for i in range(8)]
    s1_0  = [(s1_0v >> i) & 1 for i in range(8)]
    s1_1  = [(s1_1v >> i) & 1 for i in range(8)]
    s2    = [s1_0[i] ^ s1_1[i] for i in range(8)]
    s3    = 1 if any(s2) else 0
    s4    = [bits[i] if s3 else s1_0[i] for i in range(8)]
    s5    = [s4[i] & s3 for i in range(8)]
    s5v   = sum(b << i for i, b in enumerate(s5))
    return s5v, s3


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------
def verify_candidate(circ, outs, ref_fn, label):
    """Byte-exact verification against Python reference over all 256 inputs."""
    cd = circ_dict(circ, outs)
    mismatches = 0
    first_mm   = None
    for val in range(256):
        inbits = [(val >> b) & 1 for b in range(8)]
        raw    = TC.ripple(cd, inbits)
        got_s5 = TC.frombits(raw[:8])
        got_s3 = raw[8]
        exp_s5, exp_s3 = ref_fn(val)
        if got_s5 != exp_s5 or got_s3 != exp_s3:
            mismatches += 1
            if first_mm is None:
                first_mm = (val, got_s5, got_s3, exp_s5, exp_s3)
    ok = (mismatches == 0)
    status = "PASS" if ok else f"FAIL ({mismatches} mismatches)"
    print(f"  [{label}] verify: {status} (256/256 inputs)")
    if first_mm:
        v, gs5, gs3, es5, es3 = first_mm
        print(f"    first mismatch: input={v:#04x} got_s5={gs5:#04x} got_s3={gs3} "
              f"exp_s5={es5:#04x} exp_s3={es3}")
    return ok


# ---------------------------------------------------------------------------
# structural verification of physical blob
# ---------------------------------------------------------------------------
def verify_physical(blob, base_off, circ, outs):
    """Check the physical blob is well-formed and address-consistent."""
    assert blob[:8] == MAGIC, "bad magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert ng == len(circ.ga), f"gate count {ng} vs {len(circ.ga)}"
    assert nw == circ.n_wire(), f"wire count {nw} vs {circ.n_wire()}"
    assert ni == circ.n_in
    assert no == len(outs)

    hdr  = 28 + no * 8
    wst  = hdr
    gst  = wst + nw

    def wa(w):
        return base_off + wst + w

    # check output addresses
    for i, o in enumerate(outs):
        stored = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored == wa(o), f"out addr {i}: {stored} vs {wa(o)}"

    # check gate records
    off = gst
    for k in range(ng):
        op, a, b, out = struct.unpack_from("<BQQQ", blob, off)
        assert op == 0, f"gate {k} opcode {op}"
        assert a == wa(circ.ga[k]), f"gate {k} a"
        assert b == wa(circ.gb[k]), f"gate {k} b"
        assert out == wa(2 + ni + k), f"gate {k} out"
        off += GATE_STRIDE

    return True


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("\n  MUHLNICKEL VSCF -- Viable System Cybernetic Field")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    if not os.path.exists(TITAN):
        print(f"  ERROR: {TITAN} not found."); return 1

    # Check if already fabricated
    if os.path.exists(REG):
        reg = json.load(open(REG))
        if NAME in reg and not DRY:
            print(f"  {NAME} already in registry.  Run --revert first."); return 1

    # ---- PROPOSE: build both candidates ----
    candidates = []
    for builder, ref_fn, label in [
        (build_vscf_xor, vscf_xor_ref, "xor"),
        (build_vscf_inc, vscf_inc_ref, "inc"),
    ]:
        circ, outs, tag = builder()
        d = depth_of(circ, outs)
        g = len(circ.ga)
        candidates.append((circ, outs, ref_fn, tag, d, g))

    # ---- SCORE ----
    print("  PROPOSE / SCORE:")
    for circ, outs, ref_fn, tag, d, g in candidates:
        print(f"    {tag:6s}  gates={g:>6,}  depth={d:>3} ticks  "
              f"wires={circ.n_wire():>6,}  n_out={len(outs)}")

    # ---- VERIFY: byte-exact against Python reference ----
    print("\n  VERIFY (byte-exact, 256/256 inputs per candidate):")
    all_ok = True
    for circ, outs, ref_fn, tag, d, g in candidates:
        ok = verify_candidate(circ, outs, ref_fn, tag)
        all_ok = all_ok and ok

    if not all_ok:
        print("\n  FABRICATION ABORTED: verification failed."); return 1

    # ---- PARETO SET ----
    # A dominates B iff A.depth <= B.depth AND A.gates <= B.gates (one strict)
    pareto = list(candidates)
    dominated = set()
    for i, (_, _, _, ti, di, gi) in enumerate(candidates):
        for j, (_, _, _, tj, dj, gj) in enumerate(candidates):
            if i != j and dj <= di and gj <= gi and (dj < di or gj < gi):
                dominated.add(i)
    pareto = [c for i, c in enumerate(candidates) if i not in dominated]

    print(f"\n  PARETO SET ({len(pareto)} candidate{'s' if len(pareto) != 1 else ''}):")
    for circ, outs, ref_fn, tag, d, g in pareto:
        print(f"    {tag:6s}  gates={g:>6,}  depth={d:>3} ticks")

    # ---- KEEP: pick the shallowest Pareto member ----
    winner = min(pareto, key=lambda x: (x[4], x[5]))  # min depth, then min gates
    circ, outs, ref_fn, tag, d, g = winner
    print(f"\n  WINNER: {tag}  (depth {d}, {g:,} gates)")

    # ---- BUILD PHYSICAL BLOB ----
    base_off = alloc_space(0)  # preliminary
    blob, total, depth, in_addrs, out_addrs = to_physical(circ, outs, base_off)

    # re-alloc with actual size
    base_off = alloc_space(total)
    blob, total, depth, in_addrs, out_addrs = to_physical(circ, outs, base_off)

    print(f"  physical blob: {total:,} bytes at offset {base_off:,}")

    # ---- STRUCTURAL VERIFY of physical blob ----
    phys_ok = verify_physical(blob, base_off, circ, outs)
    print(f"  physical structural verify: {'PASS' if phys_ok else 'FAIL'}")
    if not phys_ok:
        print("  ABORTING"); return 1

    genome = {
        "archetype": "VSCF",
        "candidate": tag,
        "topology": "5-tier-vsm",
        "s1_variant": tag,
        "depth": d,
        "gates": g,
        "pareto_set": [{"tag": t, "depth": dd, "gates": gg}
                       for _, _, _, t, dd, gg in pareto]
    }

    if DRY:
        print(f"\n  --dry: nothing stored.  Run without --dry to fabricate.")
        return 0

    # ---- STORE (journaled) ----
    print(f"\n  FABRICATING: writing {total:,} bytes at offset {base_off:,}")
    journal_write(base_off, blob)
    print(f"  journaled to: {GENOME_PATH}")

    # ---- REGISTRY ----
    update_registry(base_off, total, depth, g, circ.n_in, len(outs),
                    in_addrs, out_addrs, genome)
    print(f"  registry updated: {NAME}")

    # ---- GGUF header sanity ----
    with open(TITAN, "rb") as f:
        gguf_ok = f.read(4) == b"GGUF"
    print(f"  titan.gguf GGUF-valid: {gguf_ok}")

    print(f"\n  VSCF FABRICATED.")
    print(f"  inject: write 8 input bits to addresses {in_addrs[:3]}...")
    print(f"  surface: read 9 output bits from {out_addrs[:3]}...")
    print(f"  depth: {depth} ticks end-to-end.")
    return 0


def revert():
    """Byte-exact revert."""
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
        print("  no genome journal found -- nothing to revert")

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
