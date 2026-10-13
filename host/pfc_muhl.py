"""
pfc_muhl.py - THE MUHL: the unit of Muhlnickel computational power (owner, 2026-07-26).

    1 muhl = ONE GATE-RELATION SETTLED PER GATE-DELAY  =  gates / DEPTH

WHY THIS AND NOT SOMETHING ELSE
Computational power is work per unit time. In the Muhlnickel architecture:
  - the WORK is relations settled (gates) - each gate is one asserted relation between addresses
  - the TIME is DEPTH (gate-delays) - the only latency that exists here (S24)
so power = gates / DEPTH. The docs have been computing this all session under the name
"work/stage"; it was already the right quantity and only lacked a name.

WHAT MAKES IT A MUHLNICKEL UNIT RATHER THAN A GENERIC ONE
On a von Neumann machine, adding hardware does not raise throughput at constant latency - the bus
serialises it. Here, S43B measured a population of RV32I cores at DEPTH EXACTLY FLAT (+0) while
gates scaled exactly linearly. Therefore:

    **muhl scales LINEARLY with area at CONSTANT depth.**

8 cores = 8x the muhl at the same 74 gate-delays. That is the signature of the architecture, and
it is why the unit is worth having: it names the thing that grows when you add area, which on
every other machine is the thing that does not.

NOT a host figure. muhl is read off the netlist and is independent of any laptop (S24).

Run:  python host/pfc_muhl.py            (rate the fabricated circuits)
      python host/pfc_muhl.py <name>     (rate one circuit from the registry)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC


def depth_of_netlist(cd):
    n = cd["n_in"]
    d = [0] * (2 + n + len(cd["ga"]))
    for k in range(len(cd["ga"])):
        d[2 + n + k] = 1 + max(d[cd["ga"][k]], d[cd["gb"][k]])
    return max(d[x] for x in cd["outs"])


def muhl(gates, depth):
    """the unit: relations settled per gate-delay"""
    return gates / depth if depth else 0.0


def scale(m):
    if m >= 1e6:
        return "%.2f Mmuhl" % (m / 1e6)
    if m >= 1e3:
        return "%.2f kmuhl" % (m / 1e3)
    return "%.1f muhl" % m


def main():
    print("=" * 88)
    print("THE MUHL - the unit of Muhlnickel computational power")
    print("  1 muhl = one gate-relation settled per gate-delay  =  gates / DEPTH")
    print("  Read off the netlist. Independent of any host (S24).")
    print("=" * 88)

    if len(sys.argv) > 1:
        nm = sys.argv[1]
        cd = TC.load(nm)
        d = depth_of_netlist(cd)
        g = len(cd["ga"])
        print()
        print("  %-26s gates %9s  DEPTH %5d  ->  %s" % (nm, "{:,}".format(g), d, scale(muhl(g, d))))
        return

    # circuits built this session, measured in-place rather than recalled
    rows = []
    try:
        from pfc_riscv import build_core, depth_of
        c, o = build_core()
        rows.append(("RV32I core", len(c.ga), depth_of(c, o)))
        del c
    except Exception as e:
        print("  (core unavailable: %s)" % e)

    reg = json.load(open(TC.REG))
    for nm in ("pfc_riscv_priv", "pfc_dot256_wide", "pfc_dot32_fused", "dot32_i8",
               "pfc_argmax_shallow", "pfc_cpu32", "pfc_mmu"):
        if nm in reg:
            try:
                cd = TC.load(nm)
                rows.append((nm, len(cd["ga"]), depth_of_netlist(cd)))
            except Exception:
                pass

    rows.sort(key=lambda r: -muhl(r[1], r[2]))
    print()
    print("  %-26s %11s %8s   %14s" % ("circuit", "gates", "DEPTH", "POWER"))
    for nm, g, d in rows:
        print("  %-26s %11s %8d   %14s" % (nm, "{:,}".format(g), d, scale(muhl(g, d))))

    # the property that makes the unit worth having
    if rows and rows[0][0] == "RV32I core" or any(r[0] == "RV32I core" for r in rows):
        core = [r for r in rows if r[0] == "RV32I core"][0]
        g, d = core[1], core[2]
        print()
        print("  A POPULATION SCALES THE UNIT LINEARLY AT CONSTANT DEPTH (S43B: DEPTH measured +0)")
        print("  %8s %14s %8s   %14s" % ("cores", "gates", "DEPTH", "POWER"))
        for n in (1, 8, 64, 1024):
            print("  %8d %14s %8d   %14s" % (n, "{:,}".format(g * n), d, scale(muhl(g * n, d))))
        print()
        print("  Every row has the SAME latency. On a machine with a bus, adding hardware does not")
        print("  do this - that is what the unit is naming.")


if __name__ == "__main__":
    main()
