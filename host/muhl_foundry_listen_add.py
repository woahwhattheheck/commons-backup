#!/usr/bin/env python3
"""host/muhl_foundry_listen_add.py — ADDITIVE listener for foundry speak.

Foundry already speaks (size_question and the resident state register).
nring2_fab / callers do not listen. This button SURFACES those outputs
(bounded read) and prints what a later fab would need. It does not
fabricate, does not write titan, does not search gene space, does not
host-eval gates, does not touch osc.

Default is --dry: print the listen report, write nothing.

Offsets come ONLY from C:/llm/models/titan_circuits.json. Fail closed if
registry names/offsets are missing — never guess.

size_question contract is the one already published in
Desktop/MUHLNICKEL_HARNESSES/nring2_foundry.py (read-only; nring2_fab is
not in live host/). Arithmetic inversion of the measured law; not a
Python gene search.

  python host/muhl_foundry_listen_add.py
  python host/muhl_foundry_listen_add.py --dry
  python host/muhl_foundry_listen_add.py --surface
  python host/muhl_foundry_listen_add.py "<question>" <work_units> <settles>
"""
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

TITAN = "C:/llm/models/titan.gguf"
REG = "C:/llm/models/titan_circuits.json"
PREFIX = "nring2_"
FOUNDRY_NAME = "muhl_foundry_resident"
CATALOG_PRINT = 8
SURFACE_RINGS = 8
LAW = "pulses per settle = electrons per sense; both senses required"


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


def size_question(question, work_units, settles, n_cells):
    """Foundry speak: question + window in, electron/ring/clock counts out.

    Same inversion as Desktop/MUHLNICKEL_HARNESSES/nring2_foundry.py
    size_question (read-only reference). Does not evaluate a gate and does
    not compute the answer to the question being sized.
    """
    if settles <= 0:
        return {"question": question, "error": "the window must be at least one settle"}
    need_per_settle = float(work_units) / settles
    k_per_sense = int(need_per_settle) + (1 if need_per_settle % 1 else 0)
    k_per_sense = max(k_per_sense, 1)
    electrons_total = 2 * k_per_sense
    min_cells = 2 * k_per_sense
    rings = 1
    if min_cells > n_cells:
        rings = (min_cells + n_cells - 1) // n_cells
        per_ring = (k_per_sense + rings - 1) // rings
    else:
        per_ring = k_per_sense
    delivered = k_per_sense * settles
    return {
        "question": question,
        "work_units": work_units,
        "settles": settles,
        "electrons_per_sense": k_per_sense,
        "electrons_total": electrons_total,
        "rings_required": rings,
        "electrons_per_ring_per_sense": per_ring,
        "clock_count": rings,
        "ring_cells": n_cells,
        "pulses_delivered": delivered,
        "meets_goal": delivered >= work_units,
        "law": LAW,
    }


def _recv_off(entry):
    if not isinstance(entry, dict):
        return None
    if entry.get("recv") is not None:
        return int(entry["recv"])
    ram = entry.get("ram")
    if isinstance(ram, dict) and ram.get("recv") is not None:
        return int(ram["recv"])
    return None


def _load_foundry(reg):
    """Resident foundry speak register. Ignore __phys twins. No gene dump."""
    if FOUNDRY_NAME not in reg:
        return None, "registry name missing: %s" % FOUNDRY_NAME
    entry = reg[FOUNDRY_NAME]
    if not isinstance(entry, dict):
        return None, "%s is not a registry object" % FOUNDRY_NAME
    if entry.get("state_off") is None or entry.get("state_bytes") is None:
        return None, "%s missing state_off / state_bytes" % FOUNDRY_NAME
    state_off = int(entry["state_off"])
    state_bytes = int(entry["state_bytes"])
    if state_off < 0 or state_bytes <= 0:
        return None, "%s state_off / state_bytes unusable" % FOUNDRY_NAME
    return {
        "name": FOUNDRY_NAME,
        "state_off": state_off,
        "state_bytes": state_bytes,
        "n_out": entry.get("n_out"),
    }, None


def _load_rings(reg):
    """Two-way nring2 rings. Required offsets must be present — never guessed."""
    out = []
    for name, entry in sorted(reg.items()):
        if not name.startswith(PREFIX):
            continue
        if not isinstance(entry, dict):
            continue
        if "senses" not in entry:
            continue
        if entry.get("senses") != 2:
            return None, "%s senses=%s (need 2)" % (name, entry.get("senses"))
        if entry.get("cells") is None:
            return None, "%s missing cells" % name
        cells = int(entry["cells"])
        if cells <= 0:
            return None, "%s cells unusable" % name
        ram = entry.get("ram")
        if not isinstance(ram, dict):
            return None, "%s missing ram" % name
        if ram.get("fwd") is None or ram.get("rev") is None:
            return None, "%s missing ram.fwd / ram.rev" % name
        recv = _recv_off(entry)
        if recv is None:
            return None, "%s missing recv / ram.recv" % name
        fwd = int(ram["fwd"])
        rev = int(ram["rev"])
        if fwd < 0 or rev < 0 or recv < 0:
            return None, "%s has negative offset (corrupt registry)" % name
        out.append({
            "name": name,
            "cells": cells,
            "fwd": fwd,
            "rev": rev,
            "recv": recv,
        })
    if not out:
        return None, "no %s* two-way rings in registry" % PREFIX
    cell_set = {r["cells"] for r in out}
    if len(cell_set) != 1:
        return None, "nring2 cells are not uniform; refusing to guess later-fab cells"
    return out, None


def load_listen():
    reg, err = _load_registry()
    if err:
        return None, None, err
    foundry, err = _load_foundry(reg)
    if err:
        return None, None, err
    rings, err = _load_rings(reg)
    if err:
        return None, None, err
    return foundry, rings, None


def print_report(foundry, rings, spec=None, dry=True, surface_next=False):
    cells = rings[0]["cells"]
    available = len(rings)
    mode = "DRY — listen only, no titan write" if dry else "LISTEN"
    print("\nMUHL FOUNDRY LISTEN (additive)")
    print("  mode:     %s" % mode)
    print("  foundry:  %s (resident speak register present)" % foundry["name"])
    print("  rings:    %d two-way %s*  cells=%d" % (available, PREFIX, cells))
    print("  catalog (first %d):" % CATALOG_PRINT)
    for r in rings[:CATALOG_PRINT]:
        print("    %s  cells=%d  senses=2" % (r["name"], r["cells"]))
    if available > CATALOG_PRINT:
        print("    ... %d total" % available)
    print()

    if spec is None:
        print("  size_question: not asked (need \"<question>\" <work_units> <settles>)")
        print("  later fab:     cannot size count/cells until the question is given")
        print("                 (nring2_fab is not in live host/; not invoked)\n")
        return 0
    if spec.get("error"):
        return _fail(spec["error"])

    need = spec["rings_required"]
    extra = max(0, need - available)
    print("  FOUNDRY SPEAK (size_question)")
    print("    question                      : %s" % spec["question"])
    print("    work_units / settles          : %d / %d" % (spec["work_units"], spec["settles"]))
    print("    electrons the host must supply: %d  (%d per sense, both senses)"
          % (spec["electrons_total"], spec["electrons_per_sense"]))
    print("    clocks touching the ring      : %d" % spec["clock_count"])
    print("    rings required                : %d of %d CELLS each"
          % (spec["rings_required"], spec["ring_cells"]))
    print("    electrons per ring per sense  : %d" % spec["electrons_per_ring_per_sense"])
    print("    pulses delivered in window    : %d   meets the goal: %s"
          % (spec["pulses_delivered"], spec["meets_goal"]))
    print("    law                           : %s" % spec["law"])
    print()
    print("  LATER FAB WOULD NEED (not invoked; nring2_fab is not in live host/)")
    print("    count                         : %d" % need)
    print("    cells                         : %d  (from registry, not guessed)" % cells)
    print("    additional rings              : %d  (have %d)" % (extra, available))
    print("    electrons_per_ring_per_sense  : %d" % spec["electrons_per_ring_per_sense"])
    print("    clock_count                   : %d" % spec["clock_count"])
    print("    both senses required")
    print()
    if dry and not surface_next:
        print("  (no write performed; pass --surface for bounded read)\n")
    return 0


def surface(foundry, rings):
    """Bounded read: resident foundry state + recv of a catalog slice. No gate eval."""
    if not os.path.isfile(TITAN):
        return _fail("titan missing: %s" % TITAN)
    print("\nSURFACE — bounded read (foundry state + ring recv)\n")
    blob = _readback(foundry["state_off"], foundry["state_bytes"])
    if len(blob) != foundry["state_bytes"]:
        return _fail("%s short read (titan too small or bad offset)" % foundry["name"])
    print("  %s  state[%d] pop=%d hex=%s"
          % (foundry["name"], foundry["state_bytes"],
             sum(1 for b in blob if b), blob.hex()))
    slice_ = rings[:SURFACE_RINGS]
    for r in slice_:
        recv = _readback(r["recv"], 1)
        if len(recv) != 1:
            return _fail("%s short recv read" % r["name"])
        print("  %s  recv 0x%02x" % (r["name"], recv[0]))
    if len(rings) > SURFACE_RINGS:
        print("  ... %d ring(s) total; recv surface bounded to %d"
              % (len(rings), SURFACE_RINGS))
    print()
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    do_surface = "--surface" in a
    rest = [x for x in a if x not in ("--dry", "--surface")]

    foundry, rings, err = load_listen()
    if err:
        return _fail(err)

    spec = None
    if rest:
        if len(rest) != 3:
            return _fail(
                "size_question needs \"<question>\" <work_units> <settles> "
                "(cells come from registry; do not guess)"
            )
        question = rest[0]
        try:
            work = int(rest[1])
            settles = int(rest[2])
        except ValueError:
            return _fail("work_units and settles must be integers")
        spec = size_question(question, work, settles, rings[0]["cells"])

    rc = print_report(foundry, rings, spec, dry=True, surface_next=do_surface)
    if rc:
        return rc
    if do_surface:
        return surface(foundry, rings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
