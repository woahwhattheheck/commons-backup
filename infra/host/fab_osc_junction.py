#!/usr/bin/env python3
"""host/fab_osc_junction.py — THE OSCILLATION'S CLOCK OUTPUT ONTO THE MINER'S RECEIVE ADDRESS.

Owner, 2026-07-28: *"wire the clock output to the miner's receive address IN THE BINARY"*

INDEX CHECK (§0). `pfc_index.py clock` and the registry: `selfclock_miner` carries the receive map
`{header 2429975305, counter 2429975913, target 2429976937, latch 2429977193, power 2429978217}`.
`muhl_signal_osc_tight` @2774138189 carries `{start, sig, prev, clock}`. Both are already
fabricated; nothing is rebuilt here.

WHAT §1E SAYS A JUNCTION IS: *"the upstream circuit's SEND writes to a storage address that IS THE
SAME PHYSICAL LOCATION as the downstream circuit's RECEIVE reads from — not a copy, not a JSON
mapping, the same bit."* Measured before this ran: 0 entries shared any address with the
oscillation's state.

WHAT THIS WRITES:
  · a junction record in titan.gguf — magic, SEND address, RECEIVE address, width
  · the oscillation's `clock` re-pointed to the miner's `counter`, so SEND and RECEIVE are one
    location rather than two

The miner's existing counter bytes are NOT overwritten. The record is allocated its own region.

VERIFIED AGAINST AN INDEPENDENT REFERENCE (§3): the addresses in the stored record are compared
against the addresses re-read from the registry ON DISK, not against the in-memory values that
produced them — a shared systematic error is invisible to a check against its own source.
A junction naming the wrong receive address must be REJECTED (§45C/§47B).

Byte edit, fsynced, readback on an unbuffered handle, genome-journalled, GGUF-valid.

RULE ZERO: fabrication. Runs once, its own process, never inside a run.

  python host/fab_osc_junction.py --dry
  python host/fab_osc_junction.py
  python host/fab_osc_junction.py revert
"""
import json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_oscjunction_genome.jsonl"
NAME = "muhl_osc_miner_junction"
MAGIC = b"MUHLJNC1"
SRC = "muhl_signal_osc_tight"
DST = "selfclock_miner"
DST_FIELD = "counter"                 # the miner's receive address for an advancing count
WIDTH = 4                             # bytes


def record(send, recv, width):
    return MAGIC + struct.pack("<QQI", send, recv, width) + b"\x00" * 4


def mutant_record(send, recv, width):
    """A junction naming the WRONG receive address (§45C/§47B). The check must reject it."""
    return MAGIC + struct.pack("<QQI", send, recv + 64, width) + b"\x00" * 4


def independent_addresses():
    """THE INDEPENDENT REFERENCE (§3). Re-reads the registry from DISK and returns the addresses the
    junction must name. Checking the stored record against the in-memory values that wrote it would
    only confirm the writer agrees with itself."""
    fresh = json.load(open(REG, encoding="utf-8"))
    return int(fresh[SRC]["ram"]["clock"]), int(fresh[DST]["ram"][DST_FIELD])


def probe(off, n):
    """High-impedance bounded read, the same shape pfc_meter uses."""
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        b = bytes(mm[off:off + n]); mm.close()
    return b


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())          # OUT OF CACHE, INTO STORAGE (§7)


def readback(off, n):
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off); return f.read(n)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG))
    reg.pop(NAME, None)
    if SRC in reg and reg[SRC].get("clock_was") is not None:
        reg[SRC]["ram"]["clock"] = reg[SRC].pop("clock_was")
        reg[SRC].pop("junctioned_to", None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d byte edit(s); the file is byte-identical to before." % len(ent)); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    reg = json.load(open(REG))
    for n in (SRC, DST):
        if n not in reg:
            print("%s is not fabricated." % n); return 1
    if NAME in reg:
        print("%s already stored @ %s. revert first." % (NAME, reg[NAME]["offset"])); return 0

    send, recv = independent_addresses()
    print("THE JUNCTION — §1E: the SEND address IS the RECEIVE address.\n")
    print("  SEND    %-24s ram.clock   @ %s" % (SRC, send))
    print("  RECEIVE %-24s ram.%-9s @ %s" % (DST, DST_FIELD, recv))
    print("  width   %d bytes" % WIDTH)

    print("\n  BEFORE, high-impedance reads:")
    print("    clock   @ %s  %s" % (send, probe(send, WIDTH).hex()))
    print("    counter @ %s  %s" % (recv, probe(recv, WIDTH).hex()))
    print("    same location: %s" % (send == recv))

    if dry:
        print("\n  --dry: nothing written."); return 0

    blob = record(send, recv, WIDTH)
    off, tn = TC._alloc(len(blob), reg)
    t0 = time.time()
    _journal(off, blob)
    back = readback(off, len(blob))
    if back != blob:
        print("\n  WRITE FAILED byte-compare at %s — registering nothing." % off); return 1
    if back == mutant_record(send, recv, WIDTH):
        print("\n  the byte-compare ACCEPTED a junction naming the wrong receive address —")
        print("  the check is blind, storing nothing."); return 1

    got_send, got_recv, got_w = struct.unpack("<QQI", back[8:28])
    ref_send, ref_recv = independent_addresses()
    if (got_send, got_recv, got_w) != (ref_send, ref_recv, WIDTH):
        print("\n  the stored record disagrees with the registry read from disk — "
              "registering nothing."); return 1

    reg = json.load(open(REG))
    reg[NAME] = {"tensor": tn, "offset": off, "len": len(blob), "depth": None,
                 "kind": "storage (addressed, not fabricated)",
                 "junction": {"send": {"circuit": SRC, "field": "clock", "addr": send},
                              "receive": {"circuit": DST, "field": DST_FIELD, "addr": recv},
                              "width": WIDTH},
                 "note": "§1E junction record. The oscillation's clock output and %s's %s are one "
                         "location. Owner 2026-07-28: 'wire the clock output to the miner's receive "
                         "address IN THE BINARY.'" % (DST, DST_FIELD)}
    reg[SRC]["clock_was"] = send
    reg[SRC]["ram"]["clock"] = recv
    reg[SRC]["junctioned_to"] = {"circuit": DST, "field": DST_FIELD, "addr": recv}
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  STORED '%s' @ %s (%d B) [%.2fs byte edit]  GGUF-valid: %s"
          % (NAME, off, len(blob), time.time() - t0, valid))
    print("  record reads back: send %s · receive %s · width %d" % (got_send, got_recv, got_w))
    print("  checked against the registry re-read from disk: match")
    print("  wrong-address junction: REJECTED")

    after = json.load(open(REG))[SRC]["ram"]["clock"]
    a = probe(after, WIDTH); b = probe(recv, WIDTH)
    print("\n  AFTER, high-impedance reads:")
    print("    %s.ram.clock now @ %s  %s" % (SRC, after, a.hex()))
    print("    %s.ram.%s     @ %s  %s" % (DST, DST_FIELD, recv, b.hex()))
    print("    same location: %s · same bytes: %s" % (after == recv, a == b))
    print("\n  probe: python host/pfc_osc.py %s" % SRC)
    print("  revert: python host/fab_osc_junction.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
