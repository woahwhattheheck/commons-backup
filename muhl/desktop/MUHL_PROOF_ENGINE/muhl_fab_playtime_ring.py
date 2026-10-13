#!/usr/bin/env python3
"""muhl_fab_playtime_ring.py -- PLAYTIME WITH BOTH MECHANISMS: ring drive AND self-clock.

Owner, 2026-08-06: "IS PLAYTIME WORKING AND CAN U READ IT IF NO GO FINISH"

MEASURED FIRST, then built. `muhl_playtime` (offset 103,789,139,776) is structurally complete
and readable -- magic MUHLPLAY, header arithmetic exact, all 115,200 gates op=0, 115,200
distinct written addresses with 0 duplicates, and the self-clock law holding on 2048 of 2048
state wires. What it does NOT have is a RING.

    free/virgin input ports on muhl_playtime : 0
    nring2 entries overlapping its span      : 0
    other circuits touching its state window : 0

Every one of its input addresses is also a gate output, so there is NOWHERE to inject a ring
tap without putting a second writer on an address. That is a short under the one-writer law,
and it is precisely why `muhl_chimera_ardr_eal` was refused rather than run. A ring cannot be
bolted onto the existing circuit. It needs fresh cells.

THE OWNER'S LAW THIS SATISFIES:
  "we should combine the ring and the initial way i got it to work its not black or white
   both would be best"
  "use the rings only to power all muhlnickel anything else is stale mark that for life"
  "the rings wouldnt be added for the sake of adding more because each requires electrons
   which is a resource and as such each needs an exact purpose for existing."

HOW IT AVOIDS THE SHORT
  Gate inputs in the physical <BQQQ> format are ABSOLUTE file addresses, so a gate may READ
  any byte in the container. Reading is free; only WRITING collides. So the enable is derived
  from gates that read `muhl_ring_clacker`'s tap addresses directly, and this circuit writes
  ONLY its own state bytes. Ring: read. State: written by us, one writer, self-clocked.

THE WORLD IS THE OWNER'S DESIGN, NOT ALTERED HERE: 16x16 torus of 8-bit cells, each tick every cell moves to
avg(4 neighbours). The only addition is the enable:

    next_cell = enable ? avg4(neighbours) : hold

with `enable` derived from the ring, so the world advances on the circulating electron's
rhythm instead of on nothing. Under the alternating 512-electron pattern adjacent clacker
cells differ every settle, so XOR of two adjacent taps is a real ring-derived clock.

VAULT LAW: the original `muhl_playtime` is not touched, not moved, not deleted. This is stored
alongside as a distinct circuit.

    python muhl_fab_playtime_ring.py --dry     # build + verify, store nothing
    python muhl_fab_playtime_ring.py           # fabricate
    python muhl_fab_playtime_ring.py --revert  # byte-exact revert
"""
import json, os, random, struct, sys, time

sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
NAME = "muhl_playtime_ring"
MAGIC = b"MUHLPLYR"
GATE_STRIDE = 25
GENOME = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)

DRY = "--dry" in sys.argv
REVERT = "--revert" in sys.argv

GRID_W = GRID_H = 16
CELL_BITS = 8
N_CELLS = GRID_W * GRID_H
STATE_BITS = N_CELLS * CELL_BITS         # 2048
N_TAPS = 2                               # two adjacent clacker taps -> one toggling clock


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


def avg4(c, a, b, d, e):
    a10 = a + [c.C0, c.C0]; b10 = b + [c.C0, c.C0]
    d10 = d + [c.C0, c.C0]; e10 = e + [c.C0, c.C0]
    ab = add_cin(c, a10, b10, c.C0)
    de = add_cin(c, d10, e10, c.C0)
    total = add_cin(c, ab, de, c.C0)
    return total[2:2 + CELL_BITS]


def build():
    """inputs: STATE_BITS state bits (self-clocked) then N_TAPS ring taps (read-only)."""
    c = TC.Circuit(STATE_BITS + N_TAPS)
    IN = c.IN
    grid = [[IN[i * CELL_BITS + b] for b in range(CELL_BITS)] for i in range(N_CELLS)]
    taps = [IN[STATE_BITS + j] for j in range(N_TAPS)]

    # RING-DERIVED CLOCK: adjacent cells of the alternating clacker differ every settle,
    # so their XOR toggles with the circulating electrons. This is the drive.
    enable = c.xor(taps[0], taps[1])

    def cell(r, col):
        return grid[(r % GRID_H) * GRID_W + (col % GRID_W)]

    outs = []
    for r in range(GRID_H):
        for col in range(GRID_W):
            nxt = avg4(c, cell(r - 1, col), cell(r + 1, col),
                       cell(r, col - 1), cell(r, col + 1))
            held = cell(r, col)
            # mux(s, a, b) = s ? b : a  -> enable ? nxt : hold
            outs.extend(c.mux(enable, held[b], nxt[b]) for b in range(CELL_BITS))
    return c, outs


def ref(flat, enable):
    """Independent reference: the owner's diffusion law, gated by the ring enable."""
    def cell(r, col):
        return flat[(r % GRID_H) * GRID_W + (col % GRID_W)]
    out = []
    for r in range(GRID_H):
        for col in range(GRID_W):
            nxt = (cell(r - 1, col) + cell(r + 1, col) +
                   cell(r, col - 1) + cell(r, col + 1)) >> 2
            out.append(nxt if enable else cell(r, col))
    return out


def verify(c, outs, n_tests=120):
    rng = random.Random(6806)
    cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    bad = 0
    both = [0, 0]
    for t in range(n_tests):
        flat = [rng.randrange(256) for _ in range(N_CELLS)]
        t0, t1 = rng.randrange(2), rng.randrange(2)
        en = t0 ^ t1
        both[en] += 1
        inp = []
        for v in flat:
            for b in range(CELL_BITS):
                inp.append((v >> b) & 1)
        inp += [t0, t1]
        vals = TC.ripple(cir, inp)
        got = [sum((vals[i * CELL_BITS + b] & 1) << b for b in range(CELL_BITS))
               for i in range(N_CELLS)]
        if got != ref(flat, en):
            bad += 1
    return bad, both


def mutant_check(c, outs):
    """A deliberately corrupted copy must FAIL. Placed on an OUTPUT-DRIVING gate, because a
    mutant low in a 120k-gate netlist is masked before it reaches any output -- the lesson
    already paid for on the PFCWINMN rebuilds."""
    import copy
    ga = list(c.ga); gb = list(c.gb)
    victim = outs[0] - (2 + c.n_in)
    gb[victim] = ga[victim]
    cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": ga, "gb": gb, "outs": outs}
    rng = random.Random(11)
    for _ in range(60):
        flat = [rng.randrange(256) for _ in range(N_CELLS)]
        t0, t1 = rng.randrange(2), rng.randrange(2)
        inp = []
        for v in flat:
            for b in range(CELL_BITS):
                inp.append((v >> b) & 1)
        inp += [t0, t1]
        vals = TC.ripple(cir, inp)
        got = [sum((vals[i * CELL_BITS + b] & 1) << b for b in range(CELL_BITS))
               for i in range(N_CELLS)]
        if got != ref(flat, t0 ^ t1):
            return True
    return False


def alloc(nbytes):
    reg = json.load(open(REG))
    hi = 0
    for v in reg.values():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            hi = max(hi, int(v["offset"]) + int(v["len"]))
    hi = max(hi, os.path.getsize(TITAN))
    return ((hi + 63) // 64) * 64


def to_physical(c, outs, base, tap_addrs):
    """State inputs live in OUR wire region and are written back by our own gates (self-clock).
    The N_TAPS ring inputs are REMAPPED to the clacker's absolute tap addresses, so those wires
    are READ from the ring and never written by us."""
    ni, no, ng = c.n_in, len(outs), len(c.ga)
    nw = c.n_wire()
    depth = depth_of(c, outs)
    wire_start = 28 + no * 8
    gate_start = wire_start + nw
    total = gate_start + ng * GATE_STRIDE

    def wa(w):
        if 2 + STATE_BITS <= w < 2 + STATE_BITS + N_TAPS:
            return tap_addrs[w - (2 + STATE_BITS)]        # READ the ring, absolute
        return base + wire_start + w

    # SELF-CLOCK, IMPLEMENTED IN THE GATE RECORDS — not merely declared in the outs table.
    # The first version published the state addresses in the outs table but let every gate
    # write its own wire, so nothing actually routed the computed value back onto the state
    # byte. Rippling the STORED bytes caught it: all 19 hold cases passed and all 11 diffuse
    # cases failed, because reading the "output address" returned the untouched input.
    # This is the owner's own construction from muhl_fab_playtime_v2.py:135.
    remap = {outs[j]: wa(2 + j) for j in range(no)}
    consumed = set(c.ga) | set(c.gb)
    for w in remap:
        assert w not in consumed, "feedback wire %d consumed downstream" % w
    assert len(set(remap.values())) == len(remap), "feedback outs alias"

    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, ng, nw, ni, no, depth)
    for i, o in enumerate(outs):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[o])
    blob[wire_start] = 0
    blob[wire_start + 1] = 1
    off = gate_start
    for k in range(ng):
        w_out = 2 + ni + k
        struct.pack_into("<BQQQ", blob, off, 0, wa(c.ga[k]), wa(c.gb[k]),
                         remap.get(w_out, base + wire_start + w_out))
        off += GATE_STRIDE
    return bytes(blob), total, depth, wire_start


def journal_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"action": NAME + "_fab", "off": off,
                            "len": len(blob), "orig": orig.hex()}) + "\n")
    fs = os.path.getsize(TITAN)
    if off + len(blob) > fs:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fs))
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def revert():
    print("  reverting %s ..." % NAME)
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f:
                f.seek(int(e["off"]))
                f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
        print("  journal replayed — byte-exact")
    reg = json.load(open(REG))
    if NAME in reg:
        reg.pop(NAME)
        json.dump(reg, open(REG, "w"), indent=1)
        print("  registry entry removed")
    return 0


def main():
    t0 = time.time()
    print("=" * 84)
    print("  %s — ring drive AND self-clock, both, in one muhlnickel" % NAME)
    print("=" * 84)

    reg = json.load(open(REG))
    if "muhl_ring_clacker" not in reg:
        print("  muhl_ring_clacker absent — no ring to take drive from.")
        return 1
    taps = reg["muhl_ring_clacker"]["tap_addrs"][:N_TAPS]
    print("  ring: muhl_ring_clacker (%d cells, %d electrons)"
          % (reg["muhl_ring_clacker"]["n_cells"], reg["muhl_ring_clacker"]["k_electrons"]))
    print("  taps READ (never written by us): %s" % taps)

    c, outs = build()
    print("  built: %d gates, %d wires, %d in (%d state + %d taps), %d out"
          % (len(c.ga), c.n_wire(), c.n_in, STATE_BITS, N_TAPS, len(outs)))

    bad, both = verify(c, outs)
    print("  [1] byte-exact vs independent reference over 120 grids: %s"
          % ("PASS" if bad == 0 else "%d WRONG" % bad))
    print("      enable=0 cases %d (must HOLD), enable=1 cases %d (must DIFFUSE)"
          % (both[0], both[1]))
    if bad:
        print("      storing nothing."); return 1
    if both[0] == 0 or both[1] == 0:
        print("      one enable branch untested — storing nothing."); return 1

    caught = mutant_check(c, outs)
    print("  [2] mutant on an output-driving gate caught: %s" % caught)
    if not caught:
        print("      a check that cannot fail has measured nothing — storing nothing."); return 1

    base = alloc(0)
    blob, total, depth, ws = to_physical(c, outs, base, taps)
    base = alloc(total)
    blob, total, depth, ws = to_physical(c, outs, base, taps)
    print("  [3] physical blob %d bytes at %d, DEPTH %d ticks" % (total, base, depth))

    # structural: one writer per address, and we must NOT write any ring address
    writers = {}
    p = ws + c.n_wire()
    for k in range(len(c.ga)):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, p + k * GATE_STRIDE)
        assert op == 0
        writers[o] = writers.get(o, 0) + 1
    multi = {a: n for a, n in writers.items() if n > 1}
    hits_ring = [a for a in writers if a in set(taps)]
    print("  [4] one writer per address: %s   writes into ring taps: %d"
          % ("PASS" if not multi else "FAIL %s" % list(multi)[:3], len(hits_ring)))
    if multi or hits_ring:
        print("      storing nothing."); return 1

    if DRY:
        print("\n  --dry: verified, nothing stored.  [%.1fs]" % (time.time() - t0))
        return 0

    journal_write(base, blob)
    with open(TITAN, "rb") as f:
        f.seek(base)
        back = f.read(total)
    if back != blob:
        print("  READ-BACK MISMATCH — reverting."); revert(); return 1
    print("  [5] journaled + read-back byte-exact")

    reg = json.load(open(REG))
    reg[NAME] = {
        "name": NAME, "offset": base, "len": total, "format": "physical",
        "magic": MAGIC.decode(), "gate_stride": GATE_STRIDE,
        "n_gate": len(c.ga), "n_in": c.n_in, "n_out": len(outs), "depth": depth,
        "grid_w": GRID_W, "grid_h": GRID_H, "cell_bits": CELL_BITS,
        "state_is_bitwise": True,
        "cell_bits_base": base + ws + 2,
        "cell_stride_bits": CELL_BITS,
        "diffusion_rule": "avg4_neighbors_torus, GATED BY THE RING",
        "driven_by": "muhl_ring_clacker",
        "tap_addrs_read": taps,
        "enable_rule": "XOR of two adjacent clacker taps — alternating 512-electron pattern "
                       "makes adjacent cells differ every settle, so this toggles with the "
                       "circulating electrons",
        "selfclock": {"state_bits": STATE_BITS,
                      "note": "each cell's 8 next-state bits write the 8 cell-input bytes it "
                              "read (output addr == input addr)"},
        "ring_purpose": "gives muhl_playtime_ring its clock: the world advances one diffusion "
                        "tick per ring toggle. Owner law — each ring needs an exact purpose; "
                        "this is that purpose, and it is the only drive this circuit takes.",
        "both_mechanisms": "ring drive + self-clock in ONE muhlnickel, per the owner's law "
                           "that it is not either/or",
        "relation_to_original": "muhl_playtime (103,789,139,776) is UNTOUCHED. It has the "
                                "self-clock on 2048/2048 wires but 0 free input ports, so a "
                                "ring could not be attached to it without a second writer. "
                                "This is fresh cells, not a patch.",
        "verified_by": "byte-exact vs independent gated-diffusion reference over 120 grids "
                       "with BOTH enable branches exercised + mutant on an output-driving "
                       "gate caught + one-writer-per-address + writes zero ring addresses",
        "new_matter": "post-2026-08-04; follow-on provisional",
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "units": "n_gate=GATES depth=TICKS len=BYTES", "genome": GENOME,
    }
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f:
        print("  [6] titan.gguf GGUF-valid: %s" % (f.read(4) == b"GGUF"))
    print("      registry updated: %s" % NAME)
    print("\n  FABRICATED. Ring drive and self-clock, both, in one muhlnickel.")
    print("  [%.1fs]" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
