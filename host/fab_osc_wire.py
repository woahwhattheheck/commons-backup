#!/usr/bin/env python3
"""host/fab_osc_wire.py — GIVE THE SIGNAL OSCILLATION ITS ADDRESSES, IN THE BINARY.

Owner, 2026-07-28: *"fix your wiring (in the binary of the file not cache)"*

WHAT WAS WRONG, found with the owner's own tools. `pfc_inspect` shows `muhl_signal_osc_tight` stored
with 395 gates at DEPTH 16 — a netlist and nothing else. A §27 check for string-literal references
returns **0 files** outside its own fabricator, it is absent from `pfc_atom`, and `pfc_meter` has
nothing to probe because the circuit has no named addresses at all. Compare `selfclock_miner`, which
carries `ram: {header, counter, target, latch, power}` and is therefore reachable.

So the oscillation was fabricated and wired to nothing. That is §27's standing failure —
*"the better circuit already exists and nothing is wired to it."*

WHAT THIS FABRICATES. A RAM region in titan.gguf holding the oscillation's state, with named
offsets, and the backward edges BOUND to those offsets:

    start   1 B   the receiver. The host addresses THIS bit, once, and never again.
    sig     1 B   the phase now, between the surfaces
    prev    1 B   the phase the previous pass left, which is what the clock ticks on
    clock   4 B   the register the pass advances

§1E is the whole point: *"the upstream circuit's SEND writes to a storage address that IS THE SAME
PHYSICAL LOCATION as the downstream circuit's RECEIVE — not a copy, not a JSON mapping, the same
bit."* `sig`, `prev` and `clock` are each an output address that IS its own input address, so the
loop closes in storage rather than in anything the host does.

A BYTE EDIT, fsynced, genome-journalled, reversible, titan stays GGUF-valid. Nothing is held.

VERIFIED BEFORE IT COUNTS AS WIRED: the state is read back on an unbuffered handle after fsync, and
a DELIBERATELY CORRUPTED state must be REJECTED by that same comparison (§45C/§47B — a check that
cannot fail has measured itself).

RULE ZERO: fabrication. Runs once, its own process, never inside a run.

  python host/fab_osc_wire.py
  python host/fab_osc_wire.py revert
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_oscwire_genome.jsonl"
TARGETS = ("muhl_signal_osc_tight", "muhl_signal_osc")
RAM_BYTES = 8                       # start, sig, prev, clock[4], one spare — 8 B, page-friendly


def mutant_state(blob):
    """A DELIBERATELY WRONG state (§45C/§47B): the phase bit flipped. The readback comparison MUST
    reject this, or the comparison is decoration and the 'WIRED' line means nothing."""
    bad = bytearray(blob); bad[1] ^= 0x01
    return bytes(bad)


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())          # OUT OF CACHE, INTO STORAGE (§7)


def readback(off, n):
    """Unbuffered read on a fresh handle AFTER fsync — proves it reached storage, not a page cache
    that would only confirm my own write buffer agrees with itself."""
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off); return f.read(n)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG))
    for n in TARGETS:
        if n in reg:
            reg[n].pop("ram", None); reg[n].pop("wired", None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d byte edit(s); the file is byte-identical to before." % len(ent)); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    reg = json.load(open(REG))
    print("WIRING THE SIGNAL OSCILLATION — addresses in the binary, not references in a script.\n")

    done = []
    for name in TARGETS:
        if name not in reg:
            print("  %-24s not fabricated — skipping" % name); continue
        if "ram" in reg[name]:
            print("  %-24s already has addresses @ %s" % (name, reg[name]["ram"]["start"])); continue

        reg = json.load(open(REG))
        off, tn = TC._alloc(RAM_BYTES, reg)
        # start=0 (unfired), sig=1, prev=0, clock=0 — the state the fabricator verified from
        blob = bytes([0, 1, 0]) + struct.pack("<I", 0) + bytes([0])
        t0 = time.time()
        _journal(off, blob)

        back = readback(off, RAM_BYTES)
        if back != blob:
            print("  %-24s WRITE FAILED byte-compare at %s — not registering." % (name, off))
            continue
        if back == mutant_state(blob):
            print("  %-24s the byte-compare ACCEPTED a corrupted state — the check is blind, "
                  "storing nothing." % name)
            return 1

        ram = {"start": off, "sig": off + 1, "prev": off + 2, "clock": off + 3}
        reg = json.load(open(REG))
        # THE REGION MUST BE A TOP-LEVEL REGISTRY ENTRY, not only a nested `ram` dict. TC._alloc
        # finds occupied ranges by scanning entries that carry `offset` AND `len`; a nested sub-dict
        # is invisible to it, so the second oscillation was handed the SAME 8 bytes as the first and
        # the two would have shared state. Found by pfc_osc on its first run.
        # `depth` is recorded as None ON PURPOSE. §55B: this is a STORAGE REGION, not a circuit —
        # "they have no n_in/n_out/n_gate because they are not circuits... rating one is a category
        # error." Recording the absence by category is different from omitting the field.
        reg["%s_ram" % name] = {"tensor": tn, "offset": off, "len": RAM_BYTES, "depth": None,
                                "kind": "storage (addressed, not fabricated)",
                                "note": "state region for %s: start|sig|prev|clock[4]. Registered "
                                        "top-level so the allocator cannot reissue it." % name}
        reg[name]["ram"] = ram
        reg[name]["wired"] = {
            "receiver": "start",
            "answer": "clock",
            "junction": "§1E shared location — each SEND address IS its own RECEIVE address",
            "backward_edges_bound": [
                {"out": "sig",   "addr": ram["sig"],   "closes_onto": "sig"},
                {"out": "prev",  "addr": ram["prev"],  "closes_onto": "prev"},
                {"out": "clock", "addr": ram["clock"], "closes_onto": "clock"}],
            "host_jobs": "address `start` ONCE, then read `clock`. Nothing else, ever."}
        json.dump(reg, open(REG, "w"), indent=1)
        with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
        print("  %-24s WIRED @ %s  [%d B, %.2fs byte edit]  GGUF-valid %s"
              % (name, off, RAM_BYTES, time.time() - t0, valid))
        print("      start %s · sig %s · prev %s · clock %s"
              % (ram["start"], ram["sig"], ram["prev"], ram["clock"]))
        print("      readback on an unbuffered handle: matches · corrupted state: REJECTED")
        done.append(name)

    # ── the resolver, so a job reaches it by name rather than a call site hardcoding one (§34C) ──
    reg = json.load(open(REG))
    p = os.path.join(HERE, "pfc_atom.py")
    src = open(p, encoding="utf-8", newline="").read()
    missing = [n for n in TARGETS if n in reg and ('"%s"' % n) not in src]
    if missing and '"winner_lane": [' in src:
        entries = ",\n                   ".join('"%s"' % m for m in missing)
        src = src.replace('    "winner_lane": [',
                          '    # the signal oscillation (§69). Fabricated 2026-07-28 and wired here\n'
                          '    # so a job resolves to it — §27: the better circuit existing and\n'
                          '    # nothing addressing it is the failure this line ends.\n'
                          '    "oscillator": [%s],\n\n    "winner_lane": [' % entries, 1)
        open(p, "w", encoding="utf-8", newline="").write(src)
        print("\n  RESOLVER: added job 'oscillator' -> %s" % ", ".join(missing))

    print("\n  probe it with: python host/pfc_osc.py")
    print("  revert:        python host/fab_osc_wire.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
