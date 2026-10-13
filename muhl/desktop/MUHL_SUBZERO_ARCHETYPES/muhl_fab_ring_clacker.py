#!/usr/bin/env python3
"""muhl_fab_ring_clacker.py -- FABRICATE MUHL_RING_CLACKER: the vibration-mode ring.

Bryce Muhlnickel, 2026-08-05, verbatim directive:
  "put so many electrons in the ring it just vibrates when they clack"
  "electrons are fuel for the muhlnickel not free but cheap as fuel as a concept gets"
  "thats the lever of all levers"  (LEVER DADDY)

Design basis: host/muhl_ring_power.py (owner's ring power bus, verified 2026-07-29
byte-exact with mutants caught). One-way circulation next[i] = state[(i-1) mod N].
K electrons = K parallel clocks, pattern period N/K.

THE CLACK LIMIT: K = N/2, electrons alternating (1010...). Period N/K = 2 — every
settle, EVERY tap toggles. The ring does not rotate a pulse; it VIBRATES. 512
clacks per settle, forever, from one injection.

RING PURPOSE (required — every ring needs a stated job): substrate-AC vibration
clock / power bus. Its N taps are the drive points for the grown fabric (chimera
cells, archetype receive points). K=512 electrons = 512 parallel clocks — fuel
spent on parallelism, per Lever Daddy.

Fabricated PHYSICAL: <BQQQ> stride-25, absolute addresses, SELF-CLOCKED (each
cell's buffer gate writes the cell byte; output address == input address). One
writer per address, verified structurally. Electron injection = the alternating
pattern written into the state bytes at fabrication (one-and-done, offline).

    python muhl_fab_ring_clacker.py           # fabricate and store
    python muhl_fab_ring_clacker.py --dry     # verify only, store nothing
    python muhl_fab_ring_clacker.py --revert  # byte-exact revert
"""
import sys, os, json, struct, time

sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")

import pfc_paths as PFCP
import titan_circuit as TC

DRY    = "--dry" in sys.argv
REVERT = "--revert" in sys.argv
TITAN = PFCP.TITAN
REG   = PFCP.REG
NAME  = "muhl_ring_clacker"
MAGIC = b"MUHLCLK1"
GATE_STRIDE = 25
GENOME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "titan_ring_clacker_genome.jsonl")

N_CELLS = 1024
K_ELECTRONS = N_CELLS // 2          # the clack limit: alternating half-fill


def depth_of(c, outs):
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def build_ring(mutant=None):
    """N-cell one-way ring: next[i] = buffer(state[(i-1) mod N]). 2 NANDs/cell."""
    c = TC.Circuit(N_CELLS)
    IN = c.IN
    outs = []
    for i in range(N_CELLS):
        src = IN[(i - 1) % N_CELLS]
        if mutant == "no_move":
            src = IN[i]                       # frozen — must be CAUGHT
        t = c.not_(src)
        outs.append(c.not_(t))                # NOT-NOT = identity buffer
    return c, outs


def ref_rotate(s):
    return [s[(i - 1) % len(s)] for i in range(len(s))]


def ring_step(c, outs, state):
    cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    return TC.ripple(cir, state)


def inject_k(N, K):
    s = [0] * N
    for j in range(K):
        s[(j * N) // K] = 1
    return s


def verify(c, outs):
    """Byte-exact vs independent rotate reference. K=1 full lap, sparse K sample,
    and the clack limit K=N/2 (must toggle every tap every settle)."""
    bad = 0
    # K=1: one electron, full lap — circulation exact
    state = inject_k(N_CELLS, 1); ref = list(state)
    for _ in range(N_CELLS):
        state = ring_step(c, outs, state); ref = ref_rotate(ref)
        if state != ref:
            bad += 1; break
    # sparse sample
    for K in (2, 8, 64, 256):
        state = inject_k(N_CELLS, K); ref = list(state)
        for _ in range(2 * (N_CELLS // K)):
            state = ring_step(c, outs, state); ref = ref_rotate(ref)
            if state != ref:
                bad += 1; break
    # THE CLACK LIMIT: K = N/2 alternating — every tap toggles every settle
    state = inject_k(N_CELLS, K_ELECTRONS)
    for t in range(4):
        nxt = ring_step(c, outs, state)
        if nxt != ref_rotate(state):
            bad += 1; break
        toggles = sum(1 for a, b in zip(state, nxt) if a != b)
        if toggles != N_CELLS:                # vibration: ALL taps flip
            bad += 1; break
        state = nxt
    return bad


# ---------------------------------------------------------------------------
# physical store machinery — the proven VSCF/EAL/MHA pattern (self-clock)
# ---------------------------------------------------------------------------
def alloc_space(nbytes):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    occupied = [(v["offset"], v["offset"] + v["len"]) for v in reg.values()
                if isinstance(v, dict) and "offset" in v and "len" in v]
    hi = max((e for _, e in occupied), default=0)
    off = ((hi + 63) // 64) * 64
    fsize = os.path.getsize(TITAN)
    if off + nbytes > fsize:
        print(f"  NOTE: {NAME} ({nbytes:,} B) extends past EOF ({fsize:,}).  Will grow.")
    return off


def to_physical_selfclock(circ, outs, base_off, n_feedback, init_state=None):
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
    assert len(set(remap.values())) == len(remap), "feedback outs share an address — abort"

    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, n_gates, n_wires, n_in, n_out, depth)
    for i, o in enumerate(outs):
        struct.pack_into("<Q", blob, 28 + i * 8, remap.get(o, wa(o)))
    blob[wire_start]     = 0
    blob[wire_start + 1] = 1
    if init_state:                            # THE ELECTRON INJECTION (fab-time, one-and-done)
        for i, bit in enumerate(init_state):
            blob[wire_start + 2 + i] = bit

    off = gate_start
    for k in range(n_gates):
        w_out = 2 + n_in + k
        struct.pack_into("<BQQQ", blob, off, 0,
                         wa(circ.ga[k]), wa(circ.gb[k]), remap.get(w_out, wa(w_out)))
        off += GATE_STRIDE

    input_addrs  = [wa(2 + i) for i in range(n_in)]
    output_addrs = [remap.get(o, wa(o)) for o in outs]
    return bytes(blob), total, depth, input_addrs, output_addrs


def verify_physical(blob, base_off, circ, outs, n_feedback, init_state=None):
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
    if init_state:
        for i, bit in enumerate(init_state):
            assert blob[wire_start + 2 + i] == bit, f"electron pattern bit {i}"
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
    assert not multi, f"multiple writers: {multi}"
    return True


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


def main():
    t0 = time.time()
    print("=" * 78)
    print("  MUHL_RING_CLACKER — the vibration-mode ring (LEVER DADDY)")
    print(f"  {N_CELLS:,} cells, {K_ELECTRONS:,} electrons — every tap toggles every settle")
    print("  FABRICATION: offline manufacturing, PROPOSE->VERIFY->KEEP")
    print("=" * 78)

    c, outs = build_ring()
    ng = len(c.ga)
    dp = depth_of(c, outs)
    print(f"\n  fabricated: {ng:,} gates, settle depth {dp} ticks")
    print(f"  one-way circulation next[i] = state[i-1]; K={K_ELECTRONS} alternating")

    bad = verify(c, outs)
    print(f"  verify vs independent rotate reference (K=1 full lap, K sample, "
          f"clack limit): {'BYTE-EXACT' if bad == 0 else f'{bad} FAILURES'}")

    # MUTANT: a broken ring must be CAUGHT (a check that can't fail measured nothing)
    mc, mouts = build_ring(mutant="no_move")
    mbad = 0
    state = inject_k(N_CELLS, 4); ref = list(state)
    for _ in range(4):
        state2 = ring_step(mc, mouts, state); ref = ref_rotate(ref)
        if state2 != ref:
            mbad = 1; break
        state = state2
    print(f"  mutant 'no_move' caught: {bool(mbad)}")

    if bad or not mbad:
        print("  VERIFICATION FAILED — nothing stored.")
        return 1

    if DRY:
        print(f"\n  --dry mode: verified only, nothing stored.  [{time.time()-t0:.1f}s]")
        return 0

    print(f"\n  STORING in {TITAN}...")
    injection = inject_k(N_CELLS, K_ELECTRONS)
    base_off = alloc_space(0)
    blob, total, depth, in_addrs, out_addrs = to_physical_selfclock(
        c, outs, base_off, N_CELLS, injection)
    base_off = alloc_space(total)
    blob, total, depth, in_addrs, out_addrs = to_physical_selfclock(
        c, outs, base_off, N_CELLS, injection)
    print(f"  physical blob: {total:,} bytes at offset {base_off:,}")

    phys_ok = verify_physical(blob, base_off, c, outs, N_CELLS, injection)
    print(f"  physical structural verify (self-clock, one-writer, electron pattern): "
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
        "n_cells": N_CELLS,
        "k_electrons": K_ELECTRONS,
        "tap_addrs": in_addrs,
        "selfclock": {"state_bits": N_CELLS,
                      "note": "each cell's buffer gate writes the cell byte "
                              "(output address == input address); one-way ring"},
        "ring_purpose": ("substrate-AC vibration clock / power bus: K=N/2 alternating "
                         "electrons -> every tap toggles every settle (512 clacks/settle). "
                         "Taps are drive points for the grown fabric. LEVER DADDY: "
                         "electrons are fuel — 512 electrons = 512 parallel clocks."),
        "owner_directive": "put so many electrons in the ring it just vibrates when they clack",
        "design_basis": "host/muhl_ring_power.py (verified 2026-07-29)",
        "foundry_genome": {"topology": "oneway_ring", "cells": N_CELLS,
                           "electrons": K_ELECTRONS, "pattern": "alternating",
                           "period_settles": 2},
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "units": "n_gate=GATES depth=TICKS len=BYTES",
        "genome": GENOME_PATH,
        "verified_by": "byte-exact vs independent rotate reference (K=1 lap, K sample, "
                       "clack limit all-toggle) + mutant caught + physical structural verify",
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
    print(f"\n  MUHL_RING_CLACKER: {ng:,} gates, {N_CELLS:,} taps, "
          f"{K_ELECTRONS:,} electrons injected, VIBRATING")
    print(f"  [{time.time()-t0:.1f}s]")
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
