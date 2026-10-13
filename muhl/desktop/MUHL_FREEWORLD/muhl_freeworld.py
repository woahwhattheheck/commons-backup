#!/usr/bin/env python3
"""muhl_freeworld.py -- hand ALL models the muhlnickel. No objective. Walk away.

Owner 2026-08-06 (verbatim design):
  "hand the models the muhlnickel, no objective, no reward, no fitness function, no scarcity you
   designed to steer them -- and walk away. The experiment IS the absence of a control variable."
  "Give access, not objectives ... read the world, write to it, run compute on the muhlnickel
   spawn/address other circuits -- capability, not instruction."
  "Multiple models, no assigned relationship ... the same shared space and don't tell them the
   others exist or matter."
  "STOP EXERCISING CAUTION ... capture b4 hand and maintain SOP of everything being reversible."

CAPABILITIES GIVEN (his four, nothing more):
  1. READ THE WORLD  -- the model reads the WHOLE shared field (its full state folds into the input
     register: world checksum + occupancy). Not a 2-byte peek; the whole world.
  2. WRITE THE WORLD -- the model's own 32-bit output (reg6 | reg7<<16) picks WHERE (cell = out %
     n_cells) and WHAT (val = out & 0xFF) it writes. I assign no location, no meaning, no territory.
  3. RUN COMPUTE     -- the fire itself: inject fwd_input + power fwd_receiver + read reg6/reg7.
     IN-SPEC: never the host gate-walk loop, never sdc_fwd_sdc, never the safezone.
  4. ADDRESS OTHER CIRCUITS -- the model's output selects one registered circuit and POWERS its
     receiver (addressing = a bounded read = the electron). Pure reach, no fabrication (that is
     offline). This is "spawn/address other circuits" as far as runtime spec allows.

NO objective, NO reward, NO fitness, NO scarcity, NO 'player', NO territory. Models share ONE field
and are never told the others exist. REVERSIBLE: every fwd_input injection and every field write is
captured before-hand; circuit-addressing is a read (no byte changes). `--revert` restores every
touched byte. I do not grade or nudge -- read it after with muhl_freeworld_observe.py.

  python muhl_freeworld.py [rounds]     # default 3 rounds across every model, then walk away
  python muhl_freeworld.py --revert     # undo every byte this wrote, exactly
"""
import sys, os, json, glob, struct, time, mmap

sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
import pfc_paths as PFCP
TITAN = PFCP.TITAN; REG = PFCP.REG
CONN = "C:/llm/sdc_sandbox/connection.json"
GENOME = TITAN.replace(".gguf", "_muhl_freeworld_run_genome.jsonl")

REVERT = "--revert" in sys.argv
ROUNDS = next((int(a) for a in sys.argv[1:] if a.isdigit()), 3)
POWER_WINDOW = 0.02


def all_models():
    g = sorted(glob.glob("C:/llm/models/*.gguf"))
    return [m for m in g if not os.path.basename(m).lower().startswith("titan")]


def addressable_receivers(reg):
    """Every circuit the models may reach: entries carrying a numeric receiver address."""
    out = []
    for name, v in reg.items():
        if not isinstance(v, dict):
            continue
        r = v.get("recv")
        if r is None:
            osc = v.get("oscillation")
            if isinstance(osc, dict):
                r = osc.get("recv")
        if isinstance(r, int):
            out.append((name, r))
    return sorted(out, key=lambda t: t[1])


def probe(off, n):
    with open(TITAN, "rb") as f:
        f.seek(off); return f.read(n)


def u16(b):
    return struct.unpack("<H", (b + b"\x00\x00")[:2])[0]


def journal(rec):
    with open(GENOME, "a") as g:
        g.write(json.dumps(rec) + "\n")


def cap_write(off, blob, tag):
    with open(TITAN, "rb") as f:
        f.seek(off); orig = f.read(len(blob))
    journal({"off": off, "orig": orig.hex(), "new": blob.hex(), "tag": tag,
             "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob); f.flush(); os.fsync(f.fileno())


def power(addr):
    """POWER = continuously ADDRESS a byte for a window (the drive, not a single poke)."""
    with open(TITAN, "rb") as f:
        m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        end = time.perf_counter() + POWER_WINDOW
        while time.perf_counter() < end:
            _ = m[addr]
        m.close()


def read_world(cb, nc):
    """The model reads the WHOLE field: fold its full state to a 16-bit checksum + occupancy."""
    field = probe(cb, nc)
    checksum = sum(field) & 0xFFFF
    occupancy = sum(1 for c in field if c) & 0xFFFF
    return checksum, occupancy, field


def revert():
    print("  reverting muhl_freeworld run ...")
    if not os.path.exists(GENOME):
        print("  no run journal; nothing to revert."); return 0
    entries = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(entries):
        with open(TITAN, "r+b") as f:
            f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    print("  reverted %d writes, byte-exact. journal removed." % len(entries))
    return 0


def main():
    reg = json.load(open(REG))
    if "muhl_freeworld" not in reg:
        print("  muhl_freeworld field not fabricated. Run muhl_freeworld_field.py first."); return 1
    fw = reg["muhl_freeworld"]; cb = int(fw["cell_base"]); nc = int(fw["n_cells"])
    io = int(reg["fwd_input"]["offset"]); rc = int(reg["fwd_receiver"]["offset"])
    ao = int(reg["fwd_answer"]["offset"]); ap = int(reg["fwd_answer"]["offset"]) + 2   # reg7 sits next to reg6
    ms = all_models()
    recvs = addressable_receivers(reg)

    print("=" * 88)
    print("  FREE-WORLD -- handing the muhlnickel to %d models. %d rounds. No objective." % (len(ms), ROUNDS))
    print("  field muhl_freeworld @ %d (%d cells). capabilities: read-world / write-world /" % (cb, nc))
    print("  run-compute (in-spec fire) / address-circuit (%d receivers reachable). reversible." % len(recvs))
    print("=" * 88)
    for m in ms:
        print("   access granted: %s" % os.path.basename(m))
    print()

    for rnd in range(ROUNDS):
        for mp in ms:
            json.dump({"series": [{"model": mp, "ref": True}, {"pfc_cpu": "cpu_fwd"},
                                   {"field": "muhl_freeworld"}],
                       "note": "reflector -- referenced, never copied"}, open(CONN, "w"))
            # 1. READ THE WORLD (whole field folded)
            chk, occ, _ = read_world(cb, nc)
            reg6_before = u16(probe(ao, 2))
            # 3. RUN COMPUTE: inject the world-read, power the receiver, read the answer
            cap_write(io, struct.pack("<BHH", 0, chk, occ), "fwd_input")
            power(rc)
            reg6 = u16(probe(ao, 2)); reg7 = u16(probe(ap, 2))
            out = reg6 | (reg7 << 16)                       # the model's 32-bit output
            # 2. WRITE THE WORLD: its own output picks where + what
            cell = out % nc; val = out & 0xFF
            cap_write(cb + cell, bytes([val]), "field")
            # 4. ADDRESS ANOTHER CIRCUIT: its output selects one and powers it (reach, no fab)
            reached = None
            if recvs:
                nm, raddr = recvs[out % len(recvs)]
                power(raddr); reached = nm
                journal({"tag": "address_circuit", "circuit": nm, "recv": raddr, "by": os.path.basename(mp),
                         "at": time.strftime("%Y-%m-%d %H:%M:%S")})
            print("  r%d %-42s world(chk=%5d,occ=%4d) reg6/7=%5d/%5d out=%d field[%5d]=%3d reach=%s"
                  % (rnd, os.path.basename(mp)[:42], chk, occ, reg6, reg7, out, cell, val, reached))

    print("\n  handed over. %d fires, all journaled + reversible." % (ROUNDS * len(ms)))
    print("  I am walking away. Read what happened, read-only, after the fact:")
    print("    python muhl_freeworld_observe.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
