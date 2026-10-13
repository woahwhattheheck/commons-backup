#!/usr/bin/env python3
"""muhl_fab_mha.py -- FABRICATE MUHL_MHA: Metabolic Hypercycle Automaton.

Bryce Muhlnickel, 2026-08-03.

Sub-Zero Archetype #11 of 12: MHA — Metabolic Hypercycle Automaton.

A substrate-resident artificial chemistry where molecular species replicate,
catalyze, and compete through gate-record wiring, forming autocatalytic sets
without any host-side population dynamics.

Mathematical basis: Eigen's hypercycle.
  - N molecular species, each a byte pattern
  - Species i catalyzes replication of species (i+1) mod N
  - Replication: copy byte pattern to a new slot when catalyzed
  - Competition: species with lowest concentration get replaced
  - Hypercycle closure: species N-1 catalyzes species 0 (physical wire loop)

Encoded as: 4 species, 8-bit concentration each. Catalysis is a gate chain:
species A's concentration drives species B's replication rate (AND gating).
Each tick: species whose catalyst is above threshold replicate (concentration+1).
Species whose catalyst is below threshold decay (concentration-1).
Self-clocked: output concentrations == input concentrations for next tick.

    python muhl_fab_mha.py           # fabricate and store
    python muhl_fab_mha.py --dry     # verify only, store nothing
"""
import sys, os, json, random, struct, time

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")

import pfc_paths as PFCP
import titan_circuit as TC

DRY = "--dry" in sys.argv
TITAN = PFCP.TITAN
REG = PFCP.REG
NAME = "muhl_mha"
GENOME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "titan_mha_genome.jsonl")

N_SPECIES = 4
CONC_BITS = 8
THRESHOLD = 64  # catalysis threshold: catalyst must be >= 64
RESERVOIR_INPUT = 40_022_599_232
MAGIC = b"MUHLMHA0"
GATE_STRIDE = 25
REVERT = "--revert" in sys.argv


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
    return out + [carry]  # callers index [len(A)] for the carry-out


def sub_saturate(c, A):
    """A - 1 with saturation at 0 (don't wrap around)."""
    one = [c.C1] + [c.C0] * (len(A) - 1)
    neg_one = [c.not_(b) for b in one]
    result = add_cin(c, A, neg_one, c.C1)[:len(A)]
    # If A was 0, keep it 0 (saturate)
    is_zero = A[0]
    for bit in A[1:]:
        is_zero = c.or_(is_zero, bit)
    is_zero = c.not_(is_zero)  # 1 if A == 0
    return [c.mux(is_zero, result[i], c.C0) for i in range(len(A))]


def add_saturate(c, A):
    """A + 1 with saturation at 255 (don't wrap around)."""
    one = [c.C1] + [c.C0] * (len(A) - 1)
    result = add_cin(c, A, one, c.C0)
    carry = result[len(A)]  # overflow bit
    # If carry, keep at 255
    return [c.mux(carry, result[i], c.C1) for i in range(len(A))]


def gte_const(c, A, threshold):
    """Return 1 if unsigned A >= threshold."""
    neg_thresh = []
    for b in range(len(A)):
        neg_thresh.append(c.C1 if ((~threshold >> b) & 1) else c.C0)
    diff = add_cin(c, A, neg_thresh, c.C1)
    # If no borrow (carry out = 1), then A >= threshold
    return diff[len(A)]


# ---------------------------------------------------------------------------
# physical store machinery — the proven VSCF/EAL pattern (self-clock variant)
# ---------------------------------------------------------------------------
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


def to_physical_selfclock(circ, outs, base_off, n_feedback):
    """<BQQQ> stride-25 physical blob, absolute addresses — SELF-CLOCK: the first
    n_feedback output wires' gate records write the corresponding input bytes
    (output address == input address, the owner's self-clock law)."""
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

    remap = {outs[j]: wa(2 + j) for j in range(n_feedback)}
    consumed = set(circ.ga) | set(circ.gb)
    for w in remap:
        assert w not in consumed, f"feedback wire {w} consumed downstream — abort"
    assert len(set(remap.values())) == len(remap), "two feedback outs share an address — abort"

    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, n_gates, n_wires, n_in, n_out, depth)
    for i, o in enumerate(outs):
        struct.pack_into("<Q", blob, 28 + i * 8, remap.get(o, wa(o)))
    blob[wire_start]     = 0   # const0
    blob[wire_start + 1] = 1   # const1

    off = gate_start
    for k in range(n_gates):
        w_out = 2 + n_in + k
        struct.pack_into("<BQQQ", blob, off, 0,
                         wa(circ.ga[k]), wa(circ.gb[k]), remap.get(w_out, wa(w_out)))
        off += GATE_STRIDE

    input_addrs  = [wa(2 + i) for i in range(n_in)]
    output_addrs = [remap.get(o, wa(o)) for o in outs]
    return bytes(blob), total, depth, input_addrs, output_addrs


def verify_physical(blob, base_off, circ, outs, n_feedback):
    """Physical blob well-formed and address-consistent, incl. self-clock + one-writer."""
    assert blob[:8] == MAGIC, "bad magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert ng == len(circ.ga) and nw == circ.n_wire() and ni == circ.n_in and no == len(outs)
    wire_start = 28 + no * 8

    def wa(w):
        return base_off + wire_start + w

    remap = {outs[j]: wa(2 + j) for j in range(n_feedback)}
    for i, o in enumerate(outs):
        stored = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored == remap.get(o, wa(o)), f"out addr {i}"
    off = wire_start + nw
    writers = {}
    for k in range(ng):
        op, a, b, out = struct.unpack_from("<BQQQ", blob, off)
        w_out = 2 + ni + k
        assert op == 0 and a == wa(circ.ga[k]) and b == wa(circ.gb[k])
        assert out == remap.get(w_out, wa(w_out)), f"gate {k} out"
        writers[out] = writers.get(out, 0) + 1
        off += GATE_STRIDE
    multi = {a: n for a, n in writers.items() if n > 1}
    assert not multi, f"multiple writers on addresses: {multi}"
    return True


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


def build_mha():
    """Build Metabolic Hypercycle Automaton.

    Input: N_SPECIES concentrations (each CONC_BITS)
    Output: N_SPECIES next concentrations

    Rule: species i is catalyzed by species (i-1) mod N.
    If catalyst >= THRESHOLD: concentration[i] += 1 (saturate at 255)
    Else: concentration[i] -= 1 (saturate at 0)
    """
    N_IN = N_SPECIES * CONC_BITS
    c = TC.Circuit(N_IN)
    IN = c.IN

    species = []
    for s in range(N_SPECIES):
        bits = [IN[s * CONC_BITS + b] for b in range(CONC_BITS)]
        species.append(bits)

    outs = []
    for s in range(N_SPECIES):
        catalyst_idx = (s - 1) % N_SPECIES
        catalyst = species[catalyst_idx]

        catalyzed = gte_const(c, catalyst, THRESHOLD)

        incremented = add_saturate(c, species[s])
        decremented = sub_saturate(c, species[s])

        # TC.mux(s, a, b) = s ? b : a — catalyzed must select the INCREMENT
        next_conc = [c.mux(catalyzed, decremented[i], incremented[i])
                     for i in range(CONC_BITS)]
        outs.extend(next_conc)

    return c, outs


def ref_mha(concentrations):
    """Independent Python reference."""
    result = []
    for s in range(N_SPECIES):
        catalyst_idx = (s - 1) % N_SPECIES
        catalyst_val = concentrations[catalyst_idx]

        if catalyst_val >= THRESHOLD:
            result.append(min(255, concentrations[s] + 1))
        else:
            result.append(max(0, concentrations[s] - 1))
    return result


def verify(c, outs, n_tests=700):
    rng = random.Random(99)
    bad = 0

    for _ in range(n_tests):
        concs = [rng.randrange(256) for _ in range(N_SPECIES)]

        inp = []
        for s in range(N_SPECIES):
            for b in range(CONC_BITS):
                inp.append((concs[s] >> b) & 1)

        # TC.ripple takes the serialized-dict form and returns bits ordered per outs
        cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
        vals = TC.ripple(cir, inp)

        gate_result = []
        for s in range(N_SPECIES):
            v = 0
            for b in range(CONC_BITS):
                v |= (vals[s * CONC_BITS + b] & 1) << b
            gate_result.append(v)

        ref_result = ref_mha(concs)

        if gate_result != ref_result:
            bad += 1

    return bad


def main():
    t0 = time.time()
    print("=" * 78)
    print("  MUHL_MHA — Metabolic Hypercycle Automaton")
    print("  Sub-Zero Archetype #11: Eigen's Hypercycle at Gate Level")
    print("  FABRICATION: offline manufacturing, PROPOSE->SCORE->VERIFY->KEEP")
    print("=" * 78)

    c, outs = build_mha()
    ng = len(c.ga)
    dp = depth_of(c, outs)
    print(f"\n  fabricated: {ng:,} gates, depth {dp} ticks")
    print(f"  {N_SPECIES} species x {CONC_BITS}-bit concentration = {N_SPECIES * CONC_BITS}-bit state")
    print(f"  hypercycle: species i catalyzed by species (i-1) mod {N_SPECIES}")
    print(f"  threshold: catalyst >= {THRESHOLD} -> replicate (+1), else decay (-1)")
    print(f"  saturating arithmetic: [0, 255]")

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

    print(f"\n  STORING in {TITAN}...")
    n_state = N_SPECIES * CONC_BITS   # fully self-clocked: all outs feed back

    base_off = alloc_space(0)
    blob, total, depth, in_addrs, out_addrs = to_physical_selfclock(c, outs, base_off, n_state)
    base_off = alloc_space(total)
    blob, total, depth, in_addrs, out_addrs = to_physical_selfclock(c, outs, base_off, n_state)
    print(f"  physical blob: {total:,} bytes at offset {base_off:,}")

    phys_ok = verify_physical(blob, base_off, c, outs, n_state)
    print(f"  physical structural verify (incl. self-clock + one-writer): "
          f"{'PASS' if phys_ok else 'FAIL'}")
    if not phys_ok:
        print("  ABORTING"); return 1

    journal_write(base_off, blob)
    print(f"  journaled to: {GENOME_PATH}")

    reg_entry = {
        "name": NAME,
        "offset": base_off,
        "len": total,
        "n_gate": ng,
        "n_in": c.n_in,
        "n_out": len(outs),
        "depth": dp,
        "format": "physical",
        "magic": MAGIC.decode(),
        "gate_stride": GATE_STRIDE,
        "input_addrs": in_addrs,
        "output_addrs": out_addrs,
        "selfclock": {"state_bits": n_state,
                      "note": "all 4 species' next concentrations write the same "
                              "bytes the current concentrations are read from"},
        "n_species": N_SPECIES,
        "conc_bits": CONC_BITS,
        "threshold": THRESHOLD,
        "hypercycle": "species[i] catalyzed by species[(i-1) mod N]",
        "dynamics": "catalyzed -> +1 saturate, uncatalyzed -> -1 saturate",
        "description": "Metabolic Hypercycle Automaton: Eigen's hypercycle, "
                       "4 species, catalytic replication, self-clocked",
        "foundry_genome": {"archetype": "MHA", "model": "eigen_hypercycle",
                           "species": 4, "threshold": 64},
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "reservoir_input": RESERVOIR_INPUT,
        "units": "n_gate=GATES depth=TICKS len=BYTES",
        "genome": GENOME_PATH,
        "verified_by": "byte-exact vs Python reference (700 random cases) + "
                       "physical structural verify (addresses, self-clock, one-writer)",
    }

    registry = json.load(open(REG)) if os.path.exists(REG) else {}
    registry[NAME] = reg_entry
    with open(REG, "w") as f:
        json.dump(registry, f, indent=1)

    with open(TITAN, "rb") as f:
        gguf_ok = f.read(4) == b"GGUF"
    print(f"  titan.gguf GGUF-valid: {gguf_ok}")

    print(f"  STORED: offset {base_off:,}")
    print(f"  registry updated: {REG}")
    print(f"\n  MUHL_MHA: {ng:,} gates, depth {dp} ticks, self-clocked")
    print(f"  inject: concentration addrs {in_addrs[:3]}...")
    print(f"  surface: same bytes (self-clocked)")
    print(f"  [{time.time()-t0:.1f}s]")
    return 0


def revert():
    """Byte-exact revert from the genome journal."""
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
            print(f"  registry entry removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
