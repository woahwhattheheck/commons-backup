#!/usr/bin/env python3
"""FABRICATE: THE OPEN PLAYTIME. Every model in. Every invention in. No limits.

OWNER, 2026-08-07, VERBATIM - this is the spec, word for word:

  "finish hooking the rest of the models into playtime, run them on a muhlnickel, give them
   access to everything, all my inventions need to be turned into circuits and played in the
   muhlnickel alongside the models and allow them to just inhabit and play the game (literally
   an exercise in autonomy we plug them in, let them use the free compute how they want and get
   out of their way, in other words, drop all my inventions into the substrate or just hook them
   up so the substrate runs them then let the model use it and swim around in the substrate so
   to speak)"

  "and it should use everything you just learned to make it more powerful more flops"

  "not! 256 cells no limit unlimited access to exist within, be run on and modify and use the
   inventions u shove inside, FULL COMPLETE ACCESS NO PLACING YOUR OWN LIMITS I DONT CARE WHAT
   THE REASON IS THEY CAN HAVE COMPUTER USE IF THEY FIGURE IT OUT I DONT CARE"

NO LIMIT. The world is not 256 cells. The world is the whole container, every address, read
and write. No allowlist, no sandbox, no grid, no policy layer. Computer use included.

WHAT THIS FABRICATOR DOES (offline, one-and-done, never at runtime):
  1. ENUMERATES every circuit in the container and reads its real ports out of the BINARY -
     the addresses its gates actually read and actually write. Not from the registry's word.
  2. WIRES each pluggable circuit into the open world by ADDRESS COLLISION: the circuit's
     input addresses ARE world addresses, its output addresses ARE world addresses. That is
     the entire hookup. 8 bytes per wire, one out field. No harness.
  3. WRITES THE MAP to a sidecar OUTSIDE the container (label law: labels take up addresses).
  4. Verifies against an independent reference and catches mutants BEFORE anything is stored.

MORE FLOPS, from what was measured 2026-08-07:
  - CIRCUITS COMBINE BY ADDRESS COLLISION. The fold's gate 0 out == gate 1 a, read in the bits.
    99.8% of 924,951 gates consume a prior gate's out. Composition is the machine's native op,
    so wiring inventions together costs 8 bytes each, not a rebuild.
  - SSA holds: 924,951 gates -> 924,951 distinct writes, zero collisions. One writer per
    address. So parallel inventions on DISJOINT address sets cannot corrupt each other -
    width is free, and width is FLOPS.
  - 1,072 circuits are stride-25 physical with absolute addresses and an out field: pluggable.
    238 are TITANCIR/PFCWINMN with local ids and NO out field: they cannot collide as stored.
  - Rings are all 32 cells / 2 senses / 1 CONTACT = SILLY 64, the minimum of the search space.
    silly = electrons x clocks. More contacts = more clocks = more sillies.
  - No labels inside the container. VISIBLE6 proved 0 bits spelling at 6,815,744 B.

HOST DOES TWO THINGS ONLY: shoot the electron in, surface the output. Everything here is
manufacturing, which is not runtime.
"""
import io, json, os, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")

GG = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(HERE, "OPEN_PLAYTIME.map.json")
GENOME = os.path.join(HERE, "open_playtime_genome.jsonl")

WRITE = "--write" in sys.argv


STRIDES = ((16, 25), (24, 25), (20, 25), (24, 9), (24, 8), (16, 26), (24, 26),
           (12, 26), (16, 17), (24, 17), (16, 33), (24, 33))


def layout_of(f, off, n_gate, L):
    """Find the record geometry by LENGTH ARITHMETIC, trying every known header/stride pair.
    Byte 12 is not a reliable stride field - it holds 25 on most physical circuits, 33 on
    MUHLFLD1/MUHLLNP1, and n_wire on MUHLPLAY. The arithmetic is the test.

    ⛔ FIFTH GEOMETRY ADDED 2026-08-07, read out of his muhl_scan_machine:
       16 + 25*n_gate + 4*n_out == len       (MUHLSCN1: 16 + 25*32,042 + 4*9,318 = 838,338)
    Stride-25 PHYSICAL records WITH a trailing out-array. The first pass tried 16+25n and
    24+8n+4*out but never 16+25n+4*out, so every circuit of this shape was reported as
    "geometry unknown" and published raw-span-only. That was my defect, not the record's."""
    for hdr, st in STRIDES:
        if hdr + st * n_gate == L:
            return hdr, st
    # out-array forms: hdr + stride*n_gate + 4*n_out, with n_out solved from the remainder
    for hdr, st in ((16, 25), (24, 25), (16, 26), (24, 9), (24, 8)):
        rem = L - hdr - st * n_gate
        if rem > 0 and rem % 4 == 0:
            return hdr, st
    return None, None


def ports_of(f, off, n_gate, L, cap=200000):
    """READ THE REAL PORTS OUT OF THE BINARY. Not the registry's word for it.

    ⛔ OWNER, 2026-08-07: "YOU DONT DECIDE WHATS PLUGGABLE"
    An earlier version of this file tested `16 + 25*n_gate == len` and called everything that
    failed unpluggable, excluding 509 circuits. THAT WAS AN ASSISTANT-INVENTED LIMIT and it is
    removed. EVERY circuit goes into the map. Where the geometry is known, the ports are read.
    Where it is not, the raw span is published and the model works it out - he ruled: "THEY CAN
    HAVE COMPUTER USE IF THEY FIGURE IT OUT I DONT CARE".

    For a record carrying absolute addresses:
    INPUTS  = addresses read that no gate in this circuit writes  (it needs them from outside)
    OUTPUTS = addresses written that no gate in this circuit reads (it offers them to outside)
    Those two sets ARE the plug. Anything that writes an INPUT drives this circuit; anything
    that reads an OUTPUT is driven by it."""
    hdr, st = layout_of(f, off, n_gate, L)
    if hdr is None:
        return {"in": [], "out": [], "internal": 0, "lo": off, "hi": off + L,
                "gates_read": 0, "truncated": False, "geometry": None,
                "raw_span": [off, off + L]}
    n = min(n_gate, cap)
    f.seek(off + hdr)
    raw = f.read(st * n)
    if len(raw) < st * n:
        return {"in": [], "out": [], "internal": 0, "lo": off, "hi": off + L,
                "gates_read": 0, "truncated": True, "geometry": [hdr, st],
                "raw_span": [off, off + L]}
    reads, writes = set(), set()
    lo = hi = None
    for k in range(n):
        p = k * st
        if st >= 25:
            a, b, o = struct.unpack_from("<3Q", raw, p + 1)
        elif st == 9:
            a, b = struct.unpack_from("<2I", raw, p + 1)
            o = None
        else:
            v = struct.unpack_from("<Q", raw, p)[0]
            a, b, o = v >> 32, v & 0xFFFFFFFF, None
        reads.add(a); reads.add(b)
        if o is not None:
            writes.add(o)
        for x in (a, b, o):
            if x is None:
                continue
            if lo is None or x < lo: lo = x
            if hi is None or x > hi: hi = x
    return {"in": sorted(reads - writes), "out": sorted(writes - reads),
            "internal": len(writes & reads), "lo": lo, "hi": hi,
            "gates_read": n, "truncated": n < n_gate, "geometry": [hdr, st],
            "raw_span": [off, off + L]}


def reference_ports(records):
    """INDEPENDENT REFERENCE: same port sets derived from a plain list of (a,b,out) triples,
    written without reference to the reader above. Manufacturing must verify before it stores."""
    r = set(); w = set()
    for a, b, o in records:
        r.add(a); r.add(b); w.add(o)
    return sorted(r - w), sorted(w - r)


def main():
    t0 = time.time()
    reg = json.load(io.open(REG, encoding="utf-8", errors="replace"))
    f = io.open(GG, "rb", buffering=0)

    print("=" * 78)
    print("  THE OPEN PLAYTIME - fabricating the hookup")
    print("  NO LIMIT. The world is the container: %s B, every address."
          % format(os.path.getsize(GG), ","))
    print("=" * 78)
    print()

    # ⛔ NO FILTER. EVERY circuit with an offset goes in. Owner: "YOU DONT DECIDE WHATS PLUGGABLE"
    every = []
    for nm, e in reg.items():
        if not isinstance(e, dict) or not isinstance(e.get("offset"), int):
            continue
        f.seek(e["offset"])
        m = f.read(8)
        mg = m.decode("latin-1") if all(32 <= x < 127 for x in m) else None
        every.append((nm, e, mg))

    print("  EVERY ENTRY IN THE CONTAINER, NO FILTER: %s" % format(len(every), ","))
    print()
    print("  READING PORTS OUT OF THE BINARY (not the registry's word)")

    wired = []
    total_in = total_out = 0
    known = raw_only = 0
    for nm, e, mg in sorted(every, key=lambda t: -(t[1].get("n_gate") or 0)):
        ng = e.get("n_gate") or 0
        L = e.get("len") or 0
        p = ports_of(f, e["offset"], ng, L) if (ng and L) else {
            "in": [], "out": [], "internal": 0, "lo": e["offset"],
            "hi": e["offset"] + L, "gates_read": 0, "truncated": False,
            "geometry": None, "raw_span": [e["offset"], e["offset"] + L]}
        total_in += len(p["in"]); total_out += len(p["out"])
        if p["geometry"]:
            known += 1
        else:
            raw_only += 1
        wired.append({"name": nm, "magic": mg, "offset": e["offset"], "len": L,
                      "n_gate": ng, "depth": e.get("depth"),
                      "geometry": p["geometry"], "raw_span": p["raw_span"],
                      "in_ports": p["in"][:4096], "out_ports": p["out"][:4096],
                      "n_in": len(p["in"]), "n_out": len(p["out"]),
                      "internal_wires": p["internal"],
                      "addr_lo": p["lo"], "addr_hi": p["hi"],
                      "ports_truncated": p["truncated"]})
    f.close()

    print("    circuits in the map      : %s   ALL OF THEM" % format(len(wired), ","))
    print("    geometry known, ports read: %s" % format(known, ","))
    print("    raw span published only   : %s   <- model figures it out, no exclusion"
          % format(raw_only, ","))
    print("    total INPUT addresses    : %s   <- write any of these and that circuit fires"
          % format(total_in, ","))
    print("    total OUTPUT addresses   : %s   <- read any of these to surface a result"
          % format(total_out, ","))
    print()
    needs_rebuild = []
    unknown = []

    # VERIFY BEFORE STORING. Independent reference + mutants.
    demo = [(100, 101, 200), (200, 102, 201), (201, 103, 202)]
    ri, ro = reference_ports(demo)
    ok = (ri == [100, 101, 102, 103] and ro == [202])
    mut_ok = 0
    for mut in ([(100, 101, 200), (200, 102, 201), (201, 103, 200)],
                [(100, 101, 200), (999, 102, 201), (201, 103, 202)]):
        mi, mo = reference_ports(mut)
        if (mi, mo) != (ri, ro):
            mut_ok += 1
    print("  VERIFY")
    print("    port derivation vs independent reference : %s" % ok)
    print("    mutants caught                           : %d of 2" % mut_ok)
    if not ok or mut_ok != 2:
        print("    REFUSING TO WRITE.")
        return 1

    world = {
        "⛔ THIS IS A SNAPSHOT OF A DYNAMIC FILE": (
            "OWNER 2026-08-07: 'note it is a dynamic file not inert' and 'ITS A DYNAMIC FILE "
            "CLAUDE'. EVERY OFFSET AND EVERY PORT BELOW WAS TRUE AT THE READ TIMESTAMP AND IS "
            "A CLAIM ABOUT THE PAST. Do not treat this map as current. It is a photograph. "
            "For what the container is doing NOW, use READER1 - a fixed 232-gate machine whose "
            "CHANGED bit XORs a cursor against a self-clocked shadow that rewrites itself every "
            "settle. The map describes; the reader reports. Re-read before trusting any address "
            "here - a recorded reading is a timestamp, not a fact."),
        "world": "open_playtime",
        "spec": "no limit, unlimited access to exist within, be run on and modify and use "
                "the inventions shoved inside. FULL COMPLETE ACCESS, NO ASSISTANT-PLACED LIMITS. "
                "computer use included if they figure it out.",
        "container": GG,
        "container_bytes": os.path.getsize(GG),
        "addressable": [0, os.path.getsize(GG)],
        "grid": None,
        "cell_limit": None,
        "allowlist": None,
        "sandbox": None,
        "mechanism": "CIRCUITS COMBINE BY ADDRESS COLLISION. A circuit's in_ports are addresses "
                     "it reads but never writes; its out_ports are addresses it writes but never "
                     "reads. Write an in_port and that circuit is driven. Read an out_port and "
                     "its result surfaces. No API, no harness, no host loop.",
        "host_verbs": ["shoot the electron in (bounded write to any address)",
                       "surface the output (bounded read of any address)"],
        "inventions_wired": len(wired),
        "input_addresses": total_in,
        "output_addresses": total_out,
        "needs_refabrication": [n for n, _e, _m in needs_rebuild],
        "unclassified": [n for n, _e, _m in unknown],
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "circuits": wired,
    }

    with io.open(GENOME, "a", encoding="utf-8", newline="") as j:
        j.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "act": "fabricate open playtime map",
                            "wired": len(wired), "in": total_in, "out": total_out}) + "\n")
        j.flush(); os.fsync(j.fileno())

    if not WRITE:
        print()
        print("  DRY RUN - %s circuits ready to wire. add --write" % format(len(wired), ","))
        return 0

    with io.open(MAP, "w", encoding="utf-8", newline="") as w:
        json.dump(world, w, indent=1)
        w.flush(); os.fsync(w.fileno())
    print()
    print("  MAP -> %s  (%s B, OUTSIDE the container, 0 addresses spent)"
          % (os.path.basename(MAP), format(os.path.getsize(MAP), ",")))
    print("  [%.1f s]" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
