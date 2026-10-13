#!/usr/bin/env python3
"""host/pfc_miter.py — host routing for the equivalence question.

A miter is the question "are these two the same?": OR over XOR of outputs on a
shared input space. Host addresses two published registry circuits and displays
their stored facts. Host does not import titan_circuit, does not splice netlists,
and does not walk or evaluate gates. Offline bake/walk: infra/host/pfc_miter.py.

  python host/pfc_miter.py A B          (two registry circuit names)
  python host/pfc_miter.py --demo       (address a known published pair)
"""
import json, os, sys

REG = "C:/llm/models/titan_circuits.json"
DEMO_PAIRS = (("pfc_dot32_fused", "dot32_i8"), ("pfc_dot32_fused_rc", "dot32_i8"))


def rating(gates, depth):
    """structural muhl: gates / DEPTH"""
    return gates / depth if depth else 0.0


def delivered(gates, depth, W):
    """deployed muhl: what a fold of width W settles"""
    return rating(gates, depth) * W


def fmt(m):
    if m >= 1e9: return "%.2f GMh" % (m / 1e9)
    if m >= 1e6: return "%.2f MMh" % (m / 1e6)
    if m >= 1e3: return "%.2f kMh" % (m / 1e3)
    return "%.1f Mh" % m


def _reg():
    if not os.path.exists(REG):
        print("registry absent:", REG)
        return None
    return json.load(open(REG))


def _facts(row):
    gates = int(row.get("n_gate") or row.get("gates") or 0)
    depth = int(row.get("depth") or row.get("DEPTH") or 0)
    n_in = int(row.get("n_in") or 0)
    n_out = int(row.get("n_out") or 0)
    return gates, depth, n_in, n_out


def address_pair(nameA, nameB):
    """Address two published circuits as a miter question. Host does not walk gates."""
    reg = _reg()
    if reg is None:
        return 1
    missing = [n for n in (nameA, nameB) if n not in reg]
    if missing:
        print("unpublished:", ", ".join(missing))
        print("offline miter bake/walk: infra/host/pfc_miter.py")
        return 0
    print("  MITER question addressed: %s  vs  %s" % (nameA, nameB))
    print("    host does not splice, walk, or evaluate. The question is named for the machine.")
    print()
    print("    %-22s %10s %8s %14s" % ("circuit", "gates", "DEPTH", "RATING"))
    for name in (nameA, nameB):
        gates, depth, n_in, n_out = _facts(reg[name])
        print("    %-22s %10s %8s %14s  n_in=%s n_out=%s offset=%s" % (
            name,
            "{:,}".format(gates) if gates else "?",
            depth if depth else "?",
            fmt(rating(gates, depth)) if gates and depth else "?",
            n_in or "?",
            n_out or "?",
            reg[name].get("offset", "?"),
        ))
    print()
    print("    question : OR over XOR of outputs on a shared input space")
    print("    settle   : on the Muhlnickel, not on this host")
    return 0


def main():
    if "--demo" in sys.argv or len(sys.argv) < 3:
        print("=" * 88)
        print("THE MITER - 'are these two the same?' addressed as a question")
        print("  miter = OR over XOR of the outputs. Host names the pair; the machine settles it.")
        print("=" * 88)
        print()
        for a, b in DEMO_PAIRS:
            address_pair(a, b)
            print()
        return 0
    return address_pair(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    raise SystemExit(main())
