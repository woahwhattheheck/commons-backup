#!/usr/bin/env python3
"""muhl_fab_eal.py -- FABRICATE MUHL_EAL: Ergodic Attractor Lattice.

Bryce Muhlnickel, 2026-08-03.

Sub-Zero Archetype #10 of 12: EAL — Ergodic Attractor Lattice.

A substrate-resident chaotic dynamical system where multiple strange attractors
coexist as fabricated gate networks, with basin-of-attraction boundaries
determined by wiring topology.

Mathematical basis: Lorenz-like discrete map.
  x' = x + dt * sigma * (y - x)
  y' = y + dt * (rho*x - y - x*z_approx)
  z' = z + dt * (x*y_approx - beta*z)

Encoded in fixed-point 8-bit arithmetic with dt=1/4 (shift right 2).
sigma=2, rho=3, beta=1 (simplified for 8-bit gate tractability).

Two attractors: one with positive sigma (normal), one with negative (mirror).
Basin boundary determined by sign of initial x — wiring topology selects
which attractor's gate subnetwork drives the output.

Self-clocked: output addresses == input addresses. Trajectory evolves
autonomously after electron injection.

    python muhl_fab_eal.py           # fabricate and store
    python muhl_fab_eal.py --dry     # verify only, store nothing
"""
import sys, os, json, random, struct, time

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")

import pfc_paths as PFCP
import titan_circuit as TC

DRY = "--dry" in sys.argv
TITAN = PFCP.TITAN
REG = PFCP.REG
NAME = "muhl_eal"
GENOME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "titan_eal_genome.jsonl")

STATE_BITS = 8
RESERVOIR_INPUT = 40_022_599_232
MAGIC = b"MUHLEAL0"
GATE_STRIDE = 25
REVERT = "--revert" in sys.argv


def depth_of(c, outs):
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


# ---------------------------------------------------------------------------
# physical store machinery — ported verbatim from muhl_fab_vscf.py (the proven
# LIVE pattern), plus the self-clock remap EAL's design requires
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
    """<BQQQ> stride-25 physical blob, absolute addresses — with SELF-CLOCK:
    the first n_feedback output wires' gate records write their result to the
    SAME addresses the corresponding inputs are read from (output address ==
    input address, the owner's self-clock law). Remaining outputs stay at
    their own gate-wire addresses."""
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

    # self-clock remap: out wire outs[j] (j < n_feedback) publishes to input j's byte
    remap = {}
    for j in range(n_feedback):
        remap[outs[j]] = wa(2 + j)

    # structural safety: a remapped feedback wire must feed NOTHING downstream
    # (its canonical wire byte would go stale), and one writer per address
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
    """Physical blob well-formed and address-consistent, incl. self-clock remap."""
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


def add_cin(c, A, B, cin):
    out = []
    carry = cin
    for i in range(len(A)):
        axb = c.xor(A[i], B[i])
        out.append(c.xor(axb, carry))
        carry = c.or_(c.and_(A[i], B[i]), c.and_(axb, carry))
    return out


def sub_cin(c, A, B):
    neg_B = [c.not_(b) for b in B]
    return add_cin(c, A, neg_B, c.C1)


def shift_right_arith(c, A, n):
    sign = A[-1]
    return A[n:] + [sign] * n  # LSB-first: drop low n bits, sign-extend the top


def mul_signed_by_const(c, A, k):
    if k == 0:
        return [c.C0] * len(A)
    if k == 1:
        return list(A)
    if k == 2:
        return add_cin(c, A, A, c.C0)
    if k == 3:
        doubled = add_cin(c, A, A, c.C0)
        return add_cin(c, doubled, A, c.C0)
    raise ValueError(f"unsupported constant {k}")


def build_eal(arith_kind):
    """Build Ergodic Attractor Lattice.

    Input: 3 state variables x, y, z (each STATE_BITS signed) + 1-bit attractor select
    Output: x', y', z' (next state)

    Discrete Lorenz-like map (simplified for 8-bit):
      dx = sigma * (y - x) >> 2      (sigma=2, dt=1/4)
      dy = (rho*x - y - x*(z>>4)) >> 2  (rho=3, approximate x*z)
      dz = (x*(y>>4) - beta*z) >> 2  (beta=1, approximate x*y)

      x' = x + dx   (or x - dx for mirror attractor)
      y' = y + dy
      z' = z + dz
    """
    N_IN = STATE_BITS * 3 + 1  # x, y, z, attractor_select
    c = TC.Circuit(N_IN)
    IN = c.IN
    p = 0

    x = [IN[p + i] for i in range(STATE_BITS)]; p += STATE_BITS
    y = [IN[p + i] for i in range(STATE_BITS)]; p += STATE_BITS
    z = [IN[p + i] for i in range(STATE_BITS)]; p += STATE_BITS
    attractor_sel = IN[p]; p += 1
    assert p == N_IN

    # dx = sigma * (y - x) >> 2  with sigma=2
    y_minus_x = sub_cin(c, y, x)
    sigma_diff = mul_signed_by_const(c, y_minus_x, 2)  # sigma=2
    dx = shift_right_arith(c, sigma_diff, 2)  # dt=1/4

    # Approximate x*z interaction: x AND (z >> 4) — crude but gate-tractable
    z_shift = shift_right_arith(c, z, 4)
    xz_approx = [c.and_(x[i], z_shift[i]) for i in range(STATE_BITS)]

    # dy = (rho*x - y - xz_approx) >> 2  with rho=3
    rho_x = mul_signed_by_const(c, x, 3)
    rho_x_sub_y = sub_cin(c, rho_x, y)
    dy_raw = sub_cin(c, rho_x_sub_y, xz_approx)
    dy = shift_right_arith(c, dy_raw, 2)

    # Approximate x*y interaction: x AND (y >> 4)
    y_shift = shift_right_arith(c, y, 4)
    xy_approx = [c.and_(x[i], y_shift[i]) for i in range(STATE_BITS)]

    # dz = (xy_approx - beta*z) >> 2  with beta=1
    dz_raw = sub_cin(c, xy_approx, z)
    dz = shift_right_arith(c, dz_raw, 2)

    # Attractor selection: normal vs mirror
    # Normal: x' = x + dx, Mirror: x' = x - dx
    dx_normal = dx[:STATE_BITS]
    dx_mirror = sub_cin(c, [c.C0]*STATE_BITS, dx_normal)  # negate dx

    # MUX based on attractor_sel
    dx_selected = [c.mux(attractor_sel, dx_normal[i], dx_mirror[i])
                   for i in range(STATE_BITS)]

    x_next = add_cin(c, x, dx_selected, c.C0)[:STATE_BITS]
    y_next = add_cin(c, y, dy[:STATE_BITS], c.C0)[:STATE_BITS]
    z_next = add_cin(c, z, dz[:STATE_BITS], c.C0)[:STATE_BITS]

    outs = x_next + y_next + z_next
    return c, outs


def ref_eal(x_val, y_val, z_val, sel):
    """Independent Python reference."""
    M = (1 << STATE_BITS) - 1
    S = 1 << (STATE_BITS - 1)

    def to_signed(v):
        v = v & M
        return v - (1 << STATE_BITS) if v >= S else v

    def to_unsigned(v):
        return v & M

    # 8-bit two's-complement semantics, matching the gate network exactly:
    # every value lives mod 2^STATE_BITS; shifts are ARITHMETIC (floor) on the
    # wrapped signed value — python's native >> on a signed int IS that shift.
    def wrap(v):                       # signed 8-bit view of any int (mod 256)
        return ((v + S) & M) - S

    x = to_signed(x_val)
    y = to_signed(y_val)
    z = to_signed(z_val)

    dx = wrap(2 * (y - x)) >> 2

    # Approximate x*z: bitwise AND of x's wire pattern with arith-shifted z's
    z_shift = to_unsigned(wrap(z) >> 4)
    xz = to_unsigned(x_val) & z_shift

    dy = wrap(3 * x - y - xz) >> 2

    y_shift_v = to_unsigned(wrap(y) >> 4)
    xy = to_unsigned(x_val) & y_shift_v

    dz = wrap(xy - z) >> 2

    if sel:
        dx = -dx

    x_next = to_unsigned(x + dx)
    y_next = to_unsigned(y + dy)
    z_next = to_unsigned(z + dz)

    return x_next, y_next, z_next


def verify(c, outs, n_tests=700):
    rng = random.Random(88)
    bad = 0
    N_IN = STATE_BITS * 3 + 1

    for _ in range(n_tests):
        x_val = rng.randrange(1 << STATE_BITS)
        y_val = rng.randrange(1 << STATE_BITS)
        z_val = rng.randrange(1 << STATE_BITS)
        sel = rng.randrange(2)

        inp = []
        for b in range(STATE_BITS): inp.append((x_val >> b) & 1)
        for b in range(STATE_BITS): inp.append((y_val >> b) & 1)
        for b in range(STATE_BITS): inp.append((z_val >> b) & 1)
        inp.append(sel)

        # TC.ripple takes the serialized-dict form and returns bits ordered per outs
        cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
        vals = TC.ripple(cir, inp)

        gate_x = sum((vals[i] & 1) << i for i in range(STATE_BITS))
        gate_y = sum((vals[STATE_BITS+i] & 1) << i for i in range(STATE_BITS))
        gate_z = sum((vals[2*STATE_BITS+i] & 1) << i for i in range(STATE_BITS))

        ref_x, ref_y, ref_z = ref_eal(x_val, y_val, z_val, sel)

        if (gate_x, gate_y, gate_z) != (ref_x, ref_y, ref_z):
            bad += 1

    return bad


def main():
    t0 = time.time()
    print("=" * 78)
    print("  MUHL_EAL — Ergodic Attractor Lattice")
    print("  Sub-Zero Archetype #10: Chaotic Multi-Attractor Dynamics")
    print("  FABRICATION: offline manufacturing, PROPOSE->SCORE->VERIFY->KEEP")
    print("=" * 78)

    c, outs = build_eal("ripple")
    ng = len(c.ga)
    dp = depth_of(c, outs)
    print(f"\n  fabricated: {ng:,} gates, depth {dp} ticks")
    print(f"  3 state variables x 8 bits = 24-bit state + 1-bit attractor select")
    print(f"  Lorenz-like discrete map: sigma=2, rho=3, beta=1, dt=1/4")
    print(f"  dual attractor: normal + mirror via MUX on sign of dx")

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
    n_state = STATE_BITS * 3          # x', y', z' self-route onto x, y, z

    # ---- BUILD PHYSICAL BLOB (self-clocked: out addr == in addr for state) ----
    base_off = alloc_space(0)
    blob, total, depth, in_addrs, out_addrs = to_physical_selfclock(c, outs, base_off, n_state)
    base_off = alloc_space(total)
    blob, total, depth, in_addrs, out_addrs = to_physical_selfclock(c, outs, base_off, n_state)
    print(f"  physical blob: {total:,} bytes at offset {base_off:,}")

    # ---- STRUCTURAL VERIFY of physical blob before any write ----
    phys_ok = verify_physical(blob, base_off, c, outs, n_state)
    print(f"  physical structural verify (incl. self-clock + one-writer): "
          f"{'PASS' if phys_ok else 'FAIL'}")
    if not phys_ok:
        print("  ABORTING"); return 1

    # ---- STORE (journaled) ----
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
                      "note": "x'/y'/z' gate records write the x/y/z input bytes "
                              "(output address == input address); attractor_select "
                              "is input 24, host-injected, not fed back"},
        "attractor_select_addr": in_addrs[n_state],
        "variables": {"x": "8-bit signed", "y": "8-bit signed", "z": "8-bit signed"},
        "dynamics": {"sigma": 2, "rho": 3, "beta": 1, "dt": "1/4 (shift-2)"},
        "description": "Ergodic Attractor Lattice: Lorenz-like discrete map, "
                       "dual attractor (normal+mirror), self-clocked trajectory",
        "foundry_genome": {"archetype": "EAL", "model": "lorenz_discrete",
                           "dynamics": "sigma2_rho3_beta1", "attractors": 2},
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
    print(f"\n  MUHL_EAL: {ng:,} gates, depth {dp} ticks, self-clocked")
    print(f"  inject: state addrs {in_addrs[:3]}... select addr {in_addrs[n_state]}")
    print(f"  surface: state addrs (same bytes — self-clocked)")
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
