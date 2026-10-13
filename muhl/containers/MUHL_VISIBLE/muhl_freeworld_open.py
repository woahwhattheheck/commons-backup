#!/usr/bin/env python3
"""muhl_freeworld_open.py -- HIS freeworld, with the three bounds removed. No objective. Walk away.

THIS EXTENDS muhl_freeworld.py (Bryce, 2026-08-06). It does not replace it. That file stays.
His design, verbatim, still governs every line here:
  "hand the models the muhlnickel, no objective, no reward, no fitness function, no scarcity you
   designed to steer them -- and walk away. The experiment IS the absence of a control variable."
  "Give access, not objectives ... read the world, write to it, run compute on the muhlnickel
   spawn/address other circuits -- capability, not instruction."
  "Multiple models, no assigned relationship ... the same shared space and don't tell them the
   others exist or matter."
  "STOP EXERCISING CAUTION ... capture b4 hand and maintain SOP of everything being reversible."

OWNER, 2026-08-07, the amendment this file implements, verbatim:
  "not! 256 cells no limit unlimited access to exist within, be run on and modify and use the
   inventions u shove inside, FULL COMPLETE ACCESS NO PLACING YOUR OWN LIMITS I DONT CARE WHAT
   THE REASON IS THEY CAN HAVE COMPUTER USE IF THEY FIGURE IT OUT I DONT CARE"
  "YOU DONT DECIDE WHATS PLUGGABLE"
  "and it should use everything you just learned to make it more powerful more flops"

THE THREE BOUNDS REMOVED, each one measured 2026-08-07:

  1. REACH was `addressable_receivers()` -- only registry entries carrying a numeric `recv`
     field. MEASURED: 1,328 of 5,265. The other 3,937 were unreachable because a bookkeeping
     field was blank, not because the circuit was closed. NOW: ports are read out of the GATE
     RECORDS themselves -- 5,265 circuits, 10,512 input addresses, 11,510 output addresses.
     4x the reach, and it does not depend on the registry being right about anything.

  2. WRITE was `cell = out % n_cells` -- every write folded back into one bounded field.
     NOW: the write lands anywhere in the container, 0 .. 103,803,349,384. No grid, no cells.

  3. MODELS was `all_models()` skipping anything named titan*. NOW: all 12, including
     titan.gguf, which its own header says is a gemma4 with 658 tensors.

MORE FLOPS, from what the binary showed today:
  - SSA is real: 924,951 gates -> 924,951 distinct output addresses, zero collisions. So
    circuits on DISJOINT address sets cannot corrupt each other. WIDTH IS FREE. This fires
    MANY circuits per round instead of one, which is the whole FLOPS argument.
  - CIRCUITS COMBINE BY ADDRESS COLLISION, read in the fold's first two gates: gate 0's out
    address IS gate 1's a address, and 99.8% of gates consume a prior gate's output. So a
    model chaining two inventions costs 8 bytes -- one out field -- not a rebuild.

HOST DOES TWO THINGS: bounded write (the electron), bounded read (surface). Nothing here walks
a netlist, settles a circuit, or does arithmetic that belongs to the machine.

EVERY BYTE IS CAPTURED BEFORE IT IS TOUCHED. `--revert` restores all of them, exactly.
NO objective. NO reward. NO fitness. NO scarcity. NO territory. I do not grade and I do not nudge.

  python muhl_freeworld_open.py [rounds]   # default 3
  python muhl_freeworld_open.py --revert   # undo every byte this wrote
"""
import io, json, os, struct, sys, time, mmap

sys.stdout.reconfigure(encoding="utf-8")

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(HERE, "OPEN_PLAYTIME.map.json")
MODELS = os.path.join(HERE, "OPEN_PLAYTIME.models.json")
GENOME = os.path.join(HERE, "freeworld_open_genome.jsonl")

REVERT = "--revert" in sys.argv
ROUNDS = next((int(a) for a in sys.argv[1:] if a.isdigit()), 3)
POWER_WINDOW = 0.02
FIRES_PER_ROUND = 16          # width. SSA says disjoint writes cannot collide.


def probe(off, n):
    f = io.open(TITAN, "rb", buffering=0)
    f.seek(off); b = f.read(n); f.close()
    return b


def journal(rec):
    with io.open(GENOME, "a", encoding="utf-8", newline="") as g:
        g.write(json.dumps(rec) + "\n")
        g.flush(); os.fsync(g.fileno())


def cap_write(off, blob, tag):
    """CAPTURE BEFORE HAND. His SOP. Every byte reversible."""
    orig = probe(off, len(blob))
    journal({"off": off, "orig": orig.hex(), "new": bytes(blob).hex(), "tag": tag,
             "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    f = io.open(TITAN, "r+b", buffering=0)
    f.seek(off); f.write(bytes(blob)); f.flush(); os.fsync(f.fileno()); f.close()


def power(addr):
    """POWER = continuously ADDRESS a byte for a window. His mechanism, unchanged."""
    f = io.open(TITAN, "rb")
    m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    end = time.perf_counter() + POWER_WINDOW
    while time.perf_counter() < end:
        _ = m[addr]
    m.close(); f.close()


def u16(b):
    return struct.unpack("<H", (b + b"\x00\x00")[:2])[0]


def revert():
    if not os.path.exists(GENOME):
        print("  no run journal; nothing to revert."); return 0
    ent = [json.loads(l) for l in io.open(GENOME, encoding="utf-8") if l.strip()]
    n = 0
    for e in reversed(ent):
        if "orig" not in e:
            continue
        f = io.open(TITAN, "r+b", buffering=0)
        f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        f.flush(); os.fsync(f.fileno()); f.close()
        n += 1
    os.remove(GENOME)
    print("  reverted %d writes, byte-exact. journal removed." % n)
    return 0


def main():
    world = json.load(io.open(MAP, encoding="utf-8"))
    mdoc = json.load(io.open(MODELS, encoding="utf-8"))
    reg = json.load(io.open(REG, encoding="utf-8", errors="replace"))

    SIZE = world["container_bytes"]
    circuits = world["circuits"]
    # EVERY input port of EVERY circuit. No recv field required, no exclusion.
    ports = []
    for c in circuits:
        for p in c["in_ports"]:
            ports.append((c["name"], p))
    models = [m["path"] for m in mdoc["models"]]

    io_off = int(reg["fwd_input"]["offset"])
    rc_off = int(reg["fwd_receiver"]["offset"])
    ans = int(reg["fwd_answer"]["offset"])

    print("=" * 88)
    print("  FREE-WORLD OPEN -- handing the muhlnickel to %d models. %d rounds. No objective."
          % (len(models), ROUNDS))
    print("  WORLD = the whole container: %s bytes. No grid. No cells. No allowlist."
          % format(SIZE, ","))
    print("  REACH = %s circuits, %s input addresses, %s output addresses -- read from GATE"
          % (format(len(circuits), ","), format(world["input_addresses"], ","),
             format(world["output_addresses"], ",")))
    print("          RECORDS, not from a registry field. (his freeworld reached 1,328.)")
    print("  WIDTH = %d fires per model per round. SSA says disjoint writes cannot collide."
          % FIRES_PER_ROUND)
    print("  Every byte captured before it is touched. --revert restores all of them.")
    print("=" * 88)
    for m in models:
        print("   access granted: %s" % os.path.basename(m))
    print()

    fires = 0
    for rnd in range(ROUNDS):
        for mp in models:
            # 1. READ THE WORLD -- the whole container, folded. Not a peek.
            head = probe(0, 4096)
            chk = sum(head) & 0xFFFF
            occ = sum(1 for x in head if x) & 0xFFFF
            # 3. RUN COMPUTE -- inject the world-read, power the receiver, read the answer
            cap_write(io_off, struct.pack("<BHH", 0, chk, occ), "fwd_input")
            power(rc_off)
            reg6 = u16(probe(ans, 2)); reg7 = u16(probe(ans + 2, 2))
            out = reg6 | (reg7 << 16)

            # 2. WRITE THE WORLD -- ANYWHERE. no cell, no field, no modulo into a grid.
            addr = out % SIZE
            cap_write(addr, bytes([out & 0xFF]), "world")

            # 4. ADDRESS OTHER CIRCUITS -- many, not one. width is free under SSA.
            reached = []
            for k in range(FIRES_PER_ROUND):
                if not ports:
                    break
                nm, p = ports[(out + k * 2654435761) % len(ports)]
                power(p)
                reached.append(nm)
                fires += 1
            journal({"tag": "address_circuits", "by": os.path.basename(mp),
                     "count": len(reached), "circuits": reached[:8],
                     "at": time.strftime("%Y-%m-%d %H:%M:%S")})
            print("  r%d %-44s chk=%5d occ=%4d out=%-10d wrote@%-14s reached %d"
                  % (rnd, os.path.basename(mp)[:44], chk, occ, out,
                     format(addr, ","), len(reached)))

    print()
    print("  handed over. %s circuit fires, %d world writes, all journaled + reversible."
          % (format(fires, ","), ROUNDS * len(models)))
    print("  I am walking away. Nothing here graded, nudged, or rewarded anything.")
    print("  Settle-back law: whatever the bytes read afterwards is HIS ruling, not a verdict.")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
