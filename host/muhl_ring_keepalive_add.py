#!/usr/bin/env python3
"""host/muhl_ring_keepalive_add.py — ADDITIVE keepalive for nring2 rings 000-003.

Electrons in the ring do not deplete; they traverse. This button INJECTS both senses
(bounded write to ring state wires) and SURFACES (bounded read). It does not evaluate
gates, does not fabricate, does not touch osc, and does not edit nring2_run.py / titan
structure — only sanctioned state-byte inject when explicitly asked.

Default is --dry: print the inject plan, write nothing.

Offsets come ONLY from C:/llm/models/titan_circuits.json (live junctions). Fail closed
if recv / state wires are missing — never guess.

  python host/muhl_ring_keepalive_add.py              # dry plan (default)
  python host/muhl_ring_keepalive_add.py --dry
  python host/muhl_ring_keepalive_add.py --surface    # bounded read only
  python host/muhl_ring_keepalive_add.py --inject     # journal + write state wires
  python host/muhl_ring_keepalive_add.py revert       # restore from this genome only
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

TITAN = "C:/llm/models/titan.gguf"
REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_keepalive_add_genome.jsonl"

# Prefer live junctions on the first four rings (registry READ, never guessed).
RING_NAMES = ("nring2_000", "nring2_001", "nring2_002", "nring2_003")

# Keepalive dose: one electron per sense, spaced like nring2_run (both senses required).
K_PER_SENSE = 1
ELECTRON = b"\x01"


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def _readback(off, n):
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off)
        return f.read(n)


def _load_registry():
    if not os.path.isfile(REG):
        return None, "registry missing: %s" % REG
    with open(REG, encoding="utf-8") as f:
        return json.load(f), None


def _recv_off(entry):
    """Live receive offset from registry fields only. No hardcodes."""
    if not isinstance(entry, dict):
        return None
    if "recv" in entry and entry["recv"] is not None:
        return int(entry["recv"])
    ram = entry.get("ram")
    if isinstance(ram, dict) and ram.get("recv") is not None:
        return int(ram["recv"])
    j = entry.get("junction")
    if isinstance(j, dict) and j.get("address") is not None:
        return int(j["address"])
    jt = entry.get("junctioned_to")
    if isinstance(jt, int):
        return int(jt)
    if isinstance(jt, dict) and jt.get("addr") is not None:
        return int(jt["addr"])
    return None


def _state_wires(entry):
    """Forward / reverse state-wire bases + cell count from registry ram only."""
    if not isinstance(entry, dict):
        return None
    ram = entry.get("ram")
    if not isinstance(ram, dict):
        return None
    if ram.get("fwd") is None or ram.get("rev") is None:
        return None
    if entry.get("cells") is None:
        return None
    cells = int(entry["cells"])
    if cells <= 0:
        return None
    return {
        "fwd": int(ram["fwd"]),
        "rev": int(ram["rev"]),
        "cells": cells,
        "senses": int(entry.get("senses") or 0),
    }


def load_rings():
    """Read rings 000-003 from registry. Fail closed on any missing offset."""
    reg, err = _load_registry()
    if err:
        return None, err
    out = []
    for name in RING_NAMES:
        if name not in reg:
            return None, "ring %s not in registry" % name
        entry = reg[name]
        sw = _state_wires(entry)
        if sw is None:
            return None, "%s missing ram.fwd / ram.rev / cells (state wires)" % name
        if sw["senses"] != 2:
            return None, "%s senses=%s (need 2 for both-sense keepalive)" % (name, sw["senses"])
        recv = _recv_off(entry)
        if recv is None:
            return None, "%s missing recv / junction address" % name
        # Sanity: state bases must fit titan; recv must be a concrete int from registry.
        if sw["fwd"] < 0 or sw["rev"] < 0 or recv < 0:
            return None, "%s has negative offset (corrupt registry)" % name
        out.append({
            "name": name,
            "fwd": sw["fwd"],
            "rev": sw["rev"],
            "cells": sw["cells"],
            "recv": recv,
            "junctioned_to": entry.get("junctioned_to"),
            "wire_base": entry.get("wire_base"),
            "wire_len": entry.get("wire_len"),
        })
    return out, None


def inject_plan(rings, k_per_sense=K_PER_SENSE):
    """Bounded electron sites for both senses — same spacing idea as nring2_run.place_electrons."""
    plan = []
    for r in rings:
        cells = r["cells"]
        sites = []
        for j in range(k_per_sense):
            i = (j * cells) // max(k_per_sense, 1)
            sites.append({
                "sense": "fwd",
                "cell": i,
                "off": r["fwd"] + i,
                "byte": ELECTRON,
            })
            sites.append({
                "sense": "rev",
                "cell": (i + cells // 2) % cells,
                "off": r["rev"] + ((i + cells // 2) % cells),
                "byte": ELECTRON,
            })
        plan.append({"ring": r, "sites": sites})
    return plan


def print_plan(plan, dry=True):
    mode = "DRY — plan only, no titan write" if dry else "INJECT — journal then write"
    print("\nMUHL RING KEEPALIVE (additive)")
    print("  mode:    %s" % mode)
    print("  titan:   %s" % TITAN)
    print("  reg:     %s" % REG)
    print("  genome:  %s" % GENOME)
    print("  rings:   %s" % ", ".join(p["ring"]["name"] for p in plan))
    print("  dose:    %d electron(s)/sense (both senses; traverse, do not deplete)\n" % K_PER_SENSE)
    total = 0
    for p in plan:
        r = p["ring"]
        print("  %s" % r["name"])
        print("    state fwd @ %d  (%d cells)" % (r["fwd"], r["cells"]))
        print("    state rev @ %d  (%d cells)" % (r["rev"], r["cells"]))
        print("    recv      @ %d  (live junction)" % r["recv"])
        for s in p["sites"]:
            print("    inject %s cell[%d] -> off %d byte 0x%02x"
                  % (s["sense"], s["cell"], s["off"], s["byte"][0]))
            total += 1
        print()
    print("  total bounded writes planned: %d" % total)
    if dry:
        print("  (no write performed; pass --inject to journal+place)\n")
    return 0


def surface(rings):
    """Bounded read: state rails (both senses) + 1-byte recv. No gate evaluation."""
    if not os.path.isfile(TITAN):
        return _fail("titan missing: %s" % TITAN)
    print("\nSURFACE — bounded read (state wires + recv)\n")
    for r in rings:
        fwd = _readback(r["fwd"], r["cells"])
        rev = _readback(r["rev"], r["cells"])
        recv = _readback(r["recv"], 1)
        if len(fwd) != r["cells"] or len(rev) != r["cells"] or len(recv) != 1:
            return _fail("%s short read (titan too small or bad offset)" % r["name"])
        print("  %s" % r["name"])
        print("    fwd[%d] pop=%d hex=%s" % (r["cells"], sum(1 for b in fwd if b), fwd.hex()))
        print("    rev[%d] pop=%d hex=%s" % (r["cells"], sum(1 for b in rev if b), rev.hex()))
        print("    recv   0x%02x @ %d" % (recv[0], r["recv"]))
    print()
    return 0


def _journal_and_place(off, blob, tag):
    """Pre-image to NEW keepalive genome first (fsync), then sanctioned state inject."""
    orig = _readback(off, len(blob))
    os.makedirs(os.path.dirname(GENOME), exist_ok=True)
    with open(GENOME, "a", encoding="utf-8") as gg:
        gg.write(json.dumps({
            "off": off,
            "len": len(blob),
            "name": tag,
            "orig": orig.hex(),
            "tool": "muhl_ring_keepalive_add",
        }) + "\n")
        gg.flush()
        os.fsync(gg.fileno())
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())


def inject(plan):
    if not os.path.isfile(TITAN):
        return _fail("titan missing: %s" % TITAN)
    print_plan(plan, dry=False)
    placed = 0
    for p in plan:
        name = p["ring"]["name"]
        for s in p["sites"]:
            tag = "%s.%s[%d]" % (name, s["sense"], s["cell"])
            _journal_and_place(s["off"], s["byte"], tag)
            placed += 1
    print("  placed %d electron byte(s); host withdrawn." % placed)
    print("  genome: %s" % GENOME)
    print("  revert: python host/muhl_ring_keepalive_add.py revert\n")
    return surface([p["ring"] for p in plan])


def revert():
    if not os.path.exists(GENOME):
        print("nothing to revert (no %s)." % GENOME)
        return 0
    ent = [json.loads(l) for l in open(GENOME, encoding="utf-8") if l.strip()]
    back = 0
    for e in reversed(ent):
        want = bytes.fromhex(e["orig"])
        with open(TITAN, "r+b") as f:
            f.seek(int(e["off"]))
            f.write(want)
            f.flush()
            os.fsync(f.fileno())
        if _readback(int(e["off"]), len(want)) == want:
            back += 1
    os.remove(GENOME)
    print("reverted %d placed byte(s); %d read back byte-identical to keepalive genome."
          % (len(ent), back))
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if a and a[0] == "revert":
        return revert()

    rings, err = load_rings()
    if err:
        return _fail(err)

    # Default dry. Explicit flags only; --inject is the only write path.
    do_inject = "--inject" in a
    do_surface = "--surface" in a
    plan = inject_plan(rings)

    if do_inject:
        return inject(plan)
    if do_surface:
        return surface(rings)
    return print_plan(plan, dry=True)


if __name__ == "__main__":
    raise SystemExit(main())
