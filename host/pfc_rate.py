"""
pfc_rate.py - RATE EVERY CIRCUIT IN MUHLS and write the rating into the registry.

    RATING (structural) = gates / DEPTH        <- a property of the circuit
    DELIVERED (deployed) = gates * W / DEPTH   <- what a fold of width W settles
    unit: the muhl, symbol Mh. Prefixes kMh, MMh, GMh.

A circuit has a RATING. A deployment has a DELIVERED figure. This tool computes the rating,
because that is the part that belongs to the circuit and can be stored with it.

WHY WRITE IT INTO titan_circuits.json
Every tool reads the registry. S53E found `pfc_specs` reporting a core three fixes out of date,
because improving source does NOT update the stored copy. Rating from the STORED netlist means the
number in the registry describes the thing actually stored - and a divergence from the docs is then
a real signal rather than a mystery.

DEPTH is read off the netlist and is independent of this laptop (S24). No host figure appears here.

Run:  python host/pfc_rate.py            (rate everything, print the sheet)
      python host/pfc_rate.py --write    (also write ratings into the registry)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC


def depth_of(cd):
    n = cd["n_in"]
    d = [0] * (2 + n + len(cd["ga"]))
    for k in range(len(cd["ga"])):
        d[2 + n + k] = 1 + max(d[cd["ga"][k]], d[cd["gb"][k]])
    return max(d[x] for x in cd["outs"])


def fmt(m):
    if m >= 1e9: return "%.2f GMh" % (m / 1e9)
    if m >= 1e6: return "%.2f MMh" % (m / 1e6)
    if m >= 1e3: return "%.2f kMh" % (m / 1e3)
    return "%.1f Mh" % m


def main():
    write = "--write" in sys.argv
    reg = json.load(open(TC.REG))
    names = [n for n in reg if ":" not in n]

    rated, failed = [], []
    for n in sorted(names):
        try:
            cd = TC.load(n)
            if not cd.get("ga") or not cd.get("outs"):
                failed.append((n, "no gates/outputs"))
                continue
            d = depth_of(cd)
            g = len(cd["ga"])
            rated.append((n, g, d, g / d if d else 0.0))
        except Exception:
            # NOT a failure: the registry holds TWO KINDS of entry, matching the two phases.
            #   FABRICATION artifacts -> circuits, with n_in/n_out/n_gate. These have a rating.
            #   ADDRESSED storage     -> buffers, state registers, parameter blocks. No netlist,
            #                            so no gates, no DEPTH, and no rating. Rating one would be
            #                            a category error: storage is what muhlnickels ADDRESS
            #                            when they run; it is not something that was fabricated.
            e = reg.get(n, {})
            kind = "storage (addressed, not fabricated)" if isinstance(e, dict) and "n_in" not in e                    else "unreadable netlist"
            failed.append((n, kind))

    rated.sort(key=lambda r: -r[3])
    print("=" * 84)
    print("MUHLNICKEL CIRCUIT RATINGS - structural muhls (gates / DEPTH), symbol Mh")
    print("  RATING is a property of the CIRCUIT. DELIVERED (gates*W/DEPTH) belongs to a DEPLOYMENT.")
    print("  Read off the stored netlist; no host figure appears here (S24).")
    print("=" * 84)
    print()
    print("  %-30s %12s %8s %14s" % ("circuit", "gates", "DEPTH", "RATING"))
    for n, g, d, r in rated[:24]:
        print("  %-30s %12s %8d %14s" % (n, "{:,}".format(g), d, fmt(r)))
    if len(rated) > 24:
        print("  ... and %d more" % (len(rated) - 24))

    print()
    print("  %d CIRCUITS rated (fabrication artifacts - these have a rating)" % len(rated))
    if rated:
        tot_g = sum(r[1] for r in rated)
        print("  total fabricated area: %s gates" % "{:,}".format(tot_g))
        print("  deepest  : %-28s DEPTH %d" % (max(rated, key=lambda r: r[2])[0],
                                               max(r[2] for r in rated)))
        print("  shallowest: %-27s DEPTH %d" % (min(rated, key=lambda r: r[2])[0],
                                                min(r[2] for r in rated)))
        print("  highest rated: %-23s %s" % (rated[0][0], fmt(rated[0][3])))
    if failed:
        print()
        print("  %d entries have NO rating - and most are not circuits at all:" % len(failed))
        for n, why in failed[:8]:
            print("    %-30s %s" % (n, why))

    # DELIVERED, for the highest-rated circuit, using the MEASURED bank law (S43B)
    if rated:
        n, g, d, r = rated[0]
        print()
        print("  DELIVERED at width W for the highest-rated circuit (%s)" % n)
        print("  Independent lanes with a winner-only reduction cost +2 DEPTH per doubling (S43B).")
        print("  %10s %14s %8s %16s" % ("W", "gates", "DEPTH", "DELIVERED"))
        import math
        for W in (1, 64, 4096, 262144):
            dw = d + (2 * int(math.log2(W)) if W > 1 else 0)
            print("  %10s %14s %8d %16s" % ("{:,}".format(W), "{:,}".format(g * W), dw,
                                            fmt(g * W / dw)))

    if write:
        for n, g, d, r in rated:
            if isinstance(reg.get(n), dict):
                reg[n]["depth"] = d
                reg[n]["gates_measured"] = g
                reg[n]["muhl_rating"] = round(r, 3)
        json.dump(reg, open(TC.REG, "w"), indent=1)
        print()
        print("  WROTE depth + gates_measured + muhl_rating into %d registry entries." % len(rated))
        print("  The registry now describes the netlists actually stored (S53E).")


if __name__ == "__main__":
    main()
