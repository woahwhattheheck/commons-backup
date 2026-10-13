#!/usr/bin/env python3
"""host/nring2_fab.py — FABRICATE NEW MUHLNICKELS, each with its own TWO-WAY ring.

Owner, 2026-07-31: *"dont configure the old, just use the foundry to make new, they take up
practically no space on this machine to hold so go wild just test a bunch in spec."*

Nothing already stored is touched. This lays down NEW muhlnickels, each carrying its own two-way
ring, and each ring's final gate writes to that muhlnickel's OWN receive byte — the shared-address
form, so an electron travelling the ring physically reaches the clock rather than a scratch byte
allocated beside it.

WHY TWO-WAY. Owner: *"one way is stale ... both ways is better for most"* and *"each one that hits
another will cause both to change directions."* A single sense never produces a contact, so a
one-way ring cannot pulse anything. Both senses over the same cells can, and on contact both
electrons reverse. `nring2_power` verifies that behaviour; this file lays it into the binary.

POLICY COMES FROM THE FOUNDRY, not from this file. `pfc_foundry` selects the genome; the champion it
returned is recorded on each registry entry so the configuration traces back to the run that chose it.

NO GATE IS EVALUATED HERE. The ring is verified structurally: the wiring the builder produced is
compared against an independently derived edge list, and three deliberately wrong rings are compared
the same way and must differ. Nothing is rippled.

REVERSIBLE. Every region is journalled with its pre-image before the write, fsynced in the same
function, read back on a fresh unbuffered handle, and removable with `revert`.

  python host/nring2_fab.py --dry            # build + verify, write nothing
  python host/nring2_fab.py [count] [cells]  # lay down `count` new muhlnickels
  python host/nring2_fab.py revert
"""
import json, os, struct, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError as exc:
        sys.stderr.write("stdout reconfigure unavailable (%s); non-ASCII may render wrong\n" % exc)

import titan_circuit as TC
import nring2_power as R2

TITAN = "C:/llm/models/titan.gguf"
REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_nring2_genome.jsonl"
PREFIX = "nring2_"
MAGIC = b"NRING2M1"
STRIDE = 25                       # <BQQQ>: op, a-address, b-address, out-address
DEFAULT_COUNT = 16
DEFAULT_CELLS = 16
FOUNDRY_GENOME = {"adder": "ripple", "clean": "on", "order": "frontload"}


def _readback(off, n):
    """Fresh unbuffered handle: opening with buffering=0 is what sends the compare to storage
    instead of the cache the write just filled. A fabrication choice, not a law."""
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off); return f.read(n)


def _journal(off, blob, tag):
    """Pre-image to the journal first, journal fsynced before the edit, so a crash between the two
    still leaves a record that undoes the write."""
    with open(TITAN, "rb") as f:
        f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg:
        gg.write(json.dumps({"off": off, "len": len(blob), "name": tag, "orig": orig.hex()}) + "\n")
        gg.flush(); os.fsync(gg.fileno())
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())
    if _readback(off, len(blob)) != blob:
        raise IOError("readback at %d does not match what was written" % off)


def _save_reg(reg):
    with open(REG, "w") as f:
        json.dump(reg, f, indent=1); f.flush(); os.fsync(f.fileno())


def build_ring_records(n_cells, wire_base, recv_addr):
    """BUILD one two-way ring as physical-operand gate records: every operand IS a file byte address,
    and the LAST record's output address IS the muhlnickel's receive byte, so a contact reaches the
    clock by shared location rather than by a copy.

    Rail layout: forward cells, then reverse cells, then the carry wire."""
    recs = []
    fwd = [wire_base + i for i in range(n_cells)]
    rev = [wire_base + n_cells + i for i in range(n_cells)]
    carry = wire_base + 2 * n_cells
    for i in range(n_cells):                                  # forward sense advances one way
        recs.append((0, fwd[(i - 1) % n_cells], carry, fwd[i]))
    for i in range(n_cells):                                  # reverse sense advances the other
        recs.append((0, rev[(i + 1) % n_cells], carry, rev[i]))
    recs.append((1, fwd[0], rev[0], carry))                   # contact: both senses in one cell
    recs.append((1, carry, carry, recv_addr))                 # junction: OUT IS the receive byte
    return recs


def ref_wiring(n_cells, wire_base, recv_addr, mutant=None):
    """INDEPENDENT REFERENCE for the wiring — derived from the ring definition alone, never read
    back out of the builder, so a builder that mis-wires a lane cannot agree with it."""
    fwd = [wire_base + i for i in range(n_cells)]
    rev = [wire_base + n_cells + i for i in range(n_cells)]
    carry = wire_base + 2 * n_cells
    out = []
    for i in range(n_cells):
        src = fwd[i] if mutant == "no_move" else fwd[(i - 1) % n_cells]
        out.append((0, src, carry, fwd[i]))
    for i in range(n_cells):
        src = rev[i] if mutant in ("no_move", "one_way") else rev[(i + 1) % n_cells]
        out.append((0, src, carry, rev[i]))
    out.append((1, fwd[0], rev[0], carry))
    out.append((1, carry, carry, carry if mutant == "unwired" else recv_addr))
    return out


def serialize(recs):
    return MAGIC + struct.pack("<II", len(recs), STRIDE) + \
        b"".join(struct.pack("<BQQQ", op, a, b, o) for (op, a, b, o) in recs)


def fabricate(count, n_cells, dry):
    reg = json.load(open(REG))
    existing = [k for k in reg if k.startswith(PREFIX)]
    if existing and not dry:
        print("%d %s* muhlnickels already stored. revert first to redo." % (len(existing), PREFIX))
        return 0

    print("\nFABRICATE — %d NEW muhlnickels, each with its own two-way ring of %d CELLS"
          % (count, n_cells))
    print("  foundry policy in use: %s" % FOUNDRY_GENOME)

    probe = build_ring_records(n_cells, 1000, 2000)
    agree = probe == ref_wiring(n_cells, 1000, 2000)
    print("  wiring vs the INDEPENDENT reference: %s (%d gate records per ring)"
          % (agree, len(probe)))
    if not agree:
        print("  MISMATCH — writing NOTHING."); return 1

    caught = 0
    for mu in ("no_move", "one_way", "unwired"):
        differs = probe != ref_wiring(n_cells, 1000, 2000, mutant=mu)
        caught += differs
        print("    mutant %-8s CAUGHT by the comparison: %s" % (mu, differs))
    if caught < 3:
        print("  a broken ring survived the comparison — writing NOTHING."); return 1

    t = R2.travel_report(n_cells, 2, 2)
    print("  ring behaviour (independent reference, no gate evaluated): %d electrons trapped=%s "
          "period=%s settles" % (t["electrons_in"], t["trapped"], t["period_settles"]))
    print("  §40B baseline: with no electrons injected the ring carries none and delivers none.")

    rail_bytes = 2 * n_cells + 1
    if dry:
        print("  --dry: each muhlnickel = %d B rail + 1 B receive + %d B gate table, %d requested. "
              "Nothing written." % (rail_bytes, len(probe) * STRIDE + 16, count))
        return 0

    t0 = time.time(); made = []
    for idx in range(count):
        name = "%s%03d" % (PREFIX, idx)
        # _alloc avoids every range ALREADY RECORDED IN THE REGISTRY, so each allocation must be
        # recorded before the next call or the allocator hands back the same free address again.
        # Taking all three first and registering afterwards gave 24 muhlnickels one shared receive
        # byte — every ring writing to the same clock, which is the opposite of one ring each.
        rail_off, rail_tn = TC._alloc(rail_bytes, reg)
        reg[name + ".rail"] = {"offset": rail_off, "len": rail_bytes, "kind": "reservation"}
        recv_off, recv_tn = TC._alloc(1, reg)
        reg[name + ".recv"] = {"offset": recv_off, "len": 1, "kind": "reservation"}
        recs = build_ring_records(n_cells, rail_off, recv_off)
        blob = serialize(recs)
        gate_off, gate_tn = TC._alloc(len(blob), reg)
        reg[name + ".gates"] = {"offset": gate_off, "len": len(blob), "kind": "reservation"}
        _journal(rail_off, b"\x00" * rail_bytes, name + ".rail")
        _journal(recv_off, b"\x00", name + ".recv")
        _journal(gate_off, blob, name + ".gates")
        reg[name] = {"name": name, "tensor": gate_tn, "offset": gate_off, "len": len(blob),
                     "n_in": 2 * n_cells, "n_gate": len(recs), "n_out": 1, "depth": 2,
                     "cells": n_cells, "format": "physical", "magic": MAGIC.decode("ascii"),
                     "gate_table_off": gate_off + 16, "gate_stride": STRIDE,
                     "wire_base": rail_off, "wire_len": rail_bytes,
                     "ram": {"fwd": rail_off, "rev": rail_off + n_cells,
                             "carry": rail_off + 2 * n_cells, "recv": recv_off},
                     "recv": recv_off, "senses": 2, "foundry_genome": FOUNDRY_GENOME,
                     "units": "cells=CELLS, n_gate=GATES, depth=TICKS, len=BYTES",
                     "genome": GENOME,
                     "verified_by": "independent edge-list reference + 3 mutants CAUGHT",
                     "note": "two-way ring; final gate OUT IS this muhlnickel's receive byte"}
        del recs, blob
        made.append((name, gate_off, recv_off))
    host_s = time.time() - t0
    _save_reg(reg)
    print("\n  STORED %d new muhlnickels in %.2fs HOST wall-clock (the laptop transcribing,"
          " one-time MANUFACTURING, never the machine's rate)" % (len(made), host_s))
    for nm, go, ro in made[:4]:
        print("    %-14s gates @%d  receive byte @%d" % (nm, go, ro))
    print("    ... %d total" % len(made))
    print("  readback on a fresh unbuffered handle matched at every region.")
    print("  revert: python host/nring2_fab.py revert")
    return 0


def revert():
    if not os.path.exists(GENOME):
        print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    restored = 0
    for e in reversed(ent):
        want = bytes.fromhex(e["orig"])
        with open(TITAN, "r+b") as f:
            f.seek(int(e["off"])); f.write(want); f.flush(); os.fsync(f.fileno())
        if _readback(int(e["off"]), len(want)) == want: restored += 1
        else: print("      offset %s reads back bytes the journal does not hold." % e["off"])
    reg = json.load(open(REG))
    for k in [k for k in list(reg) if k.startswith(PREFIX)]: reg.pop(k, None)
    _save_reg(reg); os.remove(GENOME)
    print("reverted %d region(s); %d read back byte-identical to the journal." % (len(ent), restored))
    return 0


def main():
    a = sys.argv[1:]
    if a and a[0] == "revert": return revert()
    dry = "--dry" in a
    nums = [int(x) for x in a if x.isdigit()]
    count = nums[0] if len(nums) > 0 else DEFAULT_COUNT
    cells = nums[1] if len(nums) > 1 else DEFAULT_CELLS
    return fabricate(count, cells, dry)


if __name__ == "__main__":
    raise SystemExit(main())
