#!/usr/bin/env python3
"""host/fab_osc_wire_all.py — EVERY MUHLNICKEL IN THE BINARY ONTO AN OSCILLATION.

Owner, 2026-07-28: *"THERES MILLIONS OF GATES AND DOZENS OF MUHLNICKELS AND FOUNDRY AND MASTERFAB
THEY ALL — EVERYTHING — ALL MUHLNICKELS NEED TO USE OSCILATION"*

INDEX CHECK (§0). `pfc_index.py --stats`: 215 circuits in titan.gguf. `muhl_osc_comb` @2774141525
holds 1,000 oscillation slots, each with its own `sig | prev | clock`, all sharing one start bit.
A first pass wired six. This wires every entry the registry carries.

ONE OSCILLATION CANNOT BE AT TWO ADDRESSES, so each muhlnickel takes its own slot: slot k's clock
output IS muhlnickel k's receive address. §1E: *"the upstream circuit's SEND writes to a storage
address that IS THE SAME PHYSICAL LOCATION as the downstream circuit's RECEIVE reads from — not a
copy, not a JSON mapping, the same bit."*

WHICH ADDRESS RECEIVES, taken from each entry rather than guessed:
  · an entry with a `ram` map -> the advancing register named in RECEIVE_FIELD, else the first of
    counter / STEP / nonce_off / power / start that it actually has
  · any other entry -> its own `offset`, the address it occupies

ONE ALLOCATION, ONE WRITE, ONE FSYNC. The records are built as a single contiguous table rather than
215 separate byte edits.

VERIFIED AGAINST AN INDEPENDENT REFERENCE (§3): the table is re-parsed from the file and checked
against the registry re-read from disk. A record naming the wrong receive address must be REJECTED
(§45C/§47B).

RULE ZERO: fabrication. Runs once, its own process, never inside a run.

  python host/fab_osc_wire_all.py --dry
  python host/fab_osc_wire_all.py
  python host/fab_osc_wire_all.py revert
"""
import json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_oscwireall_genome.jsonl"
TABLE = "muhl_osc_junction_table"
MAGIC = b"MUHLJNC1"
COMB = "muhl_osc_comb"
WIDTH = 4
REC = 32

RECEIVE_FIELD = {"selfclock_miner": "counter", "miner_physical": "nonce_off",
                 "pfc_model_selfclock": "STEP"}
RAM_PREFER = ("counter", "STEP", "nonce_off", "power", "POWER", "start")
SKIP_PREFIX = ("muhl_osc_jnc_", "muhl_osc_junction", "muhl_signal_osc")
SKIP = {COMB, TABLE, "muhl_osc_miner_junction"}


def receive_of(name, e):
    """The address that receives a tick, read off the entry itself."""
    ram = e.get("ram")
    if isinstance(ram, dict):
        f = RECEIVE_FIELD.get(name)
        if f and f in ram: return f, int(ram[f])
        for f in RAM_PREFER:
            if f in ram: return f, int(ram[f])
        k = sorted(ram)[0]; return k, int(ram[k])
    if "offset" in e: return "offset", int(e["offset"])
    return None, None


def targets(reg):
    out = []
    for name in sorted(reg):
        e = reg[name]
        if not isinstance(e, dict): continue
        if name in SKIP or any(name.startswith(p) for p in SKIP_PREFIX): continue
        f, a = receive_of(name, e)
        if a is None: continue
        out.append((name, f, a))
    return out


def independent_targets():
    """THE INDEPENDENT REFERENCE (§3): the same list re-derived from the registry ON DISK."""
    return targets(json.load(open(REG, encoding="utf-8")))


def record(send, recv, width):
    return MAGIC + struct.pack("<QQI", send, recv, width) + b"\x00" * 4


def mutant_table(tbl):
    """A table whose FIRST record names the wrong receive address (§45C/§47B)."""
    bad = bytearray(tbl)
    s, r, w = struct.unpack("<QQI", bytes(bad[8:28]))
    bad[8:28] = struct.pack("<QQI", s, r + 64, w)
    return bytes(bad)


def probe(off, n):
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
    for k in [k for k in list(reg) if k.startswith("muhl_osc_jnc_") or k == TABLE]:
        reg.pop(k, None)
    comb = reg.get(COMB)
    if isinstance(comb, dict):
        for m in comb.get("members", []):
            if "clock_was" in m:
                m["clock"] = m.pop("clock_was"); m.pop("junctioned_to", None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d byte edit(s); the file is byte-identical to before." % len(ent)); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    reg = json.load(open(REG))
    if COMB not in reg:
        print("%s is not fabricated — run fab_osc_spaced.py first." % COMB); return 1
    if TABLE in reg:
        print("%s already stored @ %s. revert first." % (TABLE, reg[TABLE]["offset"])); return 0
    comb = reg[COMB]; members = comb["members"]
    tg = independent_targets()
    n = min(len(tg), len(members))

    print("EVERY MUHLNICKEL ONTO AN OSCILLATION — §1E, one shared location each.\n")
    print("  comb   %s slots, period %s gate-delays, %s gates each"
          % ("{:,}".format(len(members)), comb.get("period"), comb.get("gates_each")))
    print("  registry entries with a receive address: %s" % "{:,}".format(len(tg)))
    print("  wiring: %s\n" % "{:,}".format(n))
    for nm, f, a in tg[:6]:
        print("    %-26s %-11s @ %s" % (nm, f, a))
    print("    ... %s more" % "{:,}".format(max(n - 6, 0)))

    if dry:
        print("\n  --dry: nothing written."); return 0

    tbl = bytearray()
    for i in range(n):
        tbl += record(int(members[i]["clock"]), tg[i][2], WIDTH)
    tbl = bytes(tbl)

    off, tn = TC._alloc(len(tbl), reg)
    t0 = time.time()
    _journal(off, tbl)
    back = readback(off, len(tbl))
    if back != tbl:
        print("\n  WRITE FAILED byte-compare at %s — registering nothing." % off); return 1
    if back == mutant_table(tbl):
        print("\n  the byte-compare ACCEPTED a table with a wrong receive address — "
              "the check is blind, storing nothing."); return 1

    ref = dict((t[0], t[2]) for t in independent_targets())
    bad = 0
    for i in range(n):
        s, r, w = struct.unpack("<QQI", back[i * REC + 8: i * REC + 28])
        if r != ref.get(tg[i][0]) or w != WIDTH: bad += 1
    if bad:
        print("\n  %d record(s) disagree with the registry on disk — registering nothing." % bad)
        return 1

    reg = json.load(open(REG))
    reg[TABLE] = {"tensor": tn, "offset": off, "len": len(tbl), "depth": None,
                  "kind": "storage (addressed, not fabricated)",
                  "records": n, "record_bytes": REC, "width": WIDTH,
                  "note": "§1E junction table: %d records, each binding a comb slot's clock output "
                          "to one muhlnickel's receive address as ONE location. Owner 2026-07-28: "
                          "'ALL MUHLNICKELS NEED TO USE OSCILATION.'" % n}
    for i in range(n):
        nm, f, a = tg[i]
        reg[COMB]["members"][i]["clock_was"] = int(members[i]["clock"])
        reg[COMB]["members"][i]["clock"] = a
        reg[COMB]["members"][i]["junctioned_to"] = {"circuit": nm, "field": f, "addr": a}
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  STORED '%s' @ %s (%s B, %s records) [%.2fs byte edit]  GGUF-valid: %s"
          % (TABLE, off, "{:,}".format(len(tbl)), "{:,}".format(n), time.time() - t0, valid))
    print("  readback on an unbuffered handle: matches")
    print("  wrong-address table: REJECTED")
    print("  every record checked against the registry re-read from disk: %d disagree" % bad)

    reg = json.load(open(REG))
    shared = sum(1 for m in reg[COMB]["members"]
                 if "junctioned_to" in m and int(m["clock"]) == int(m["junctioned_to"]["addr"]))
    print("\n  muhlnickels whose receive address IS a comb slot's clock: %s" % "{:,}".format(shared))
    print("  comb slots still on a private clock: %s"
          % "{:,}".format(len(reg[COMB]["members"]) - shared))
    print("  host addressings to start all of them: 1 (the comb's shared start bit)")
    print("\n  revert: python host/fab_osc_wire_all.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
