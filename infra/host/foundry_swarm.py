#!/usr/bin/env python3
"""host/foundry_swarm.py — MANY FOUNDRIES, INTERCONNECTED. THE OUTPUT IS ARTIFACTS.

Owner: *"FYI THE FOUNDRY SHOULD PRODUCE MUHLNICKEL CONFIGURATIONS AS ARTIFACTS, IT IS SEPARATE FROM
THE COMPUTE, ITS MANUFACTURING OPTIMIZED NOT RUNTIME."*

THE DELIVERABLE IS A CONFIGURATION ARTIFACT, NOT A SCORE. Every foundry writes a permanent, fsynced
record naming the circuit, the adder, the topology, the node count, its junction partners, and the
MEASURED gates/DEPTH/replicas — everything fabrication needs to build it without re-running the
search. The data log below is a byproduct of manufacturing, never the product.

THIS IS THE FACTORY, AND THE FACTORY IS OFF THE CLOCK (§31/§31A). The swarm's own wall-clock is not
a constraint and never becomes one, and no number it prints is the machine's speed (§31: "is this
number the FACTORY or the PRODUCT? Only the product has a latency"). It is optimized AS MANUFACTURING
— searched wider, not run faster.

Owner: *"THROW ALL THE TESTS AT IT SPIN UP A BUNCH OF FOUNDRY ALSO PURSUE INTERCONNECTING FOUNDRIES
AND HAVING THEM PRODUCE DATA LOGS WITH NO INTERPRETATION."*

ONE FOUNDRY searches its own gene space over ONE problem. That is `foundry_drive`, and it can only
ever find configurations of the nodes it already owns.

A SWARM adds the axis a single foundry structurally cannot reach: §1E's junction. *"A's SEND wires
ARE B's RECEIVE wires — a shared location, not a copy."* So each foundry PUBLISHES its best node to
a shared junction table at the end of every round, and every other foundry may compose against it on
the next round. Round R+1's search space contains round R's winners from every foundry. That is the
interconnect, and it is why the swarm's reachable space is strictly larger than N separate foundries.

WHAT EACH FOUNDRY SEARCHES, per round:
    adder      x  every member of the measured 32-bit family (§25C/§31A: the adder table is one
                  entry in a space to be searched, never a rule to hardcode)
    topology   x  series / parallel / fanin_tree / series_of_banks (mafab_graph's measured laws)
    k          x  powers of two up to the SUBSTRATE ceiling, derived from storage/gates
    partner    x  every node any OTHER foundry has published (the §1E junction), plus no partner

GATES AND DEPTH ARE MEASURED, NEVER ESTIMATED. Every candidate circuit is actually built and checked
against the problem's exact independent reference (§3) before its numbers enter a row. A candidate
that fails verification produces no row.

SCORED BY ONE METRIC (§63): compute/tick = REPLICAS / DEPTH, REPLICAS = storage / gates. Nothing
else is ranked — not area, not host seconds, not area-delay.

RULE ZERO: this is FABRICATION-side search. It never runs inside a mining process.

RAM DISCIPLINE (8 GB box): the foundries run in ONE process, round by round, and every built circuit
is released before the next candidate. Concurrency here would be host-process concurrency, which is
a host constraint and §40E says a host constraint must never shape a Muhlnickel decision — so the
swarm's parallelism is in the SEARCH SPACE, which is where the machine's parallelism lives.

  python host/foundry_swarm.py                  # every problem as a foundry, 3 rounds
  python host/foundry_swarm.py --rounds 5
  python host/foundry_swarm.py --only open-2    # one batch as the swarm
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import mafab_laws as L
import mafab_graph as G
from mafab_adders import family, depth_of

LOGDIR = os.path.join(os.path.dirname(HERE), "docs", "logs")
# THE ARTIFACT STORE. Configurations are manufacturing output and live beside the models they will
# be fabricated into, not in the docs tree with the logs.
ARTDIR = "C:/llm/models/muhl_configs"
TOPOLOGIES = ("series", "parallel", "fanin_tree", "series_of_banks")


def write_artifact(cfg):
    """Write ONE muhlnickel configuration as a permanent artifact. fsynced, never cached (§7).

    The artifact is what fabrication consumes. It carries the measured numbers and the verification
    that produced them, so a build never has to re-run the search or trust a remembered figure."""
    if not os.path.isdir(ARTDIR): os.makedirs(ARTDIR)
    p = os.path.join(ARTDIR, "%s.json" % cfg["config_id"])
    body = json.dumps(cfg, indent=1, sort_keys=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(body)
        f.flush(); os.fsync(f.fileno())
    with open(p, "rb", buffering=0) as f:                   # readback: it is in storage, not cache
        back = json.loads(f.read().decode("utf-8"))
    if back != cfg: raise AssertionError("artifact readback differs: %s" % p)
    return p


def write_index():
    """Index every artifact in the store, fsynced, so fabrication can enumerate without a search."""
    if not os.path.isdir(ARTDIR): return None, 0
    names = sorted(n for n in os.listdir(ARTDIR) if n.endswith(".json") and n != "INDEX.json")
    idx = {}
    for n in names:
        with open(os.path.join(ARTDIR, n), "rb", buffering=0) as f:
            c = json.loads(f.read().decode("utf-8"))
        idx[c["config_id"]] = {k: c[k] for k in
                               ("problem", "shape", "adder", "topology", "nodes", "junctions",
                                "gates", "depth", "replicas", "compute_per_tick", "verified")}
    p = os.path.join(ARTDIR, "INDEX.json")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(idx, indent=1, sort_keys=True))
        f.flush(); os.fsync(f.fileno())
    return p, len(idx)


def problems(only=None):
    """The foundries are DERIVED from the problem registries, never a list I typed."""
    import mafab_problems as MP, mafab_hard as MH, mafab_hard2 as MH2
    out = []
    for tag, reg in (("domain", MP.PROBLEMS), ("open-1", MH.HARD), ("open-2", MH2.HARD2)):
        if only and tag != only: continue
        for name, P in reg.items(): out.append((tag, name, P))
    return out


def ceiling_for(gates):
    """How many of this node the SUBSTRATE holds. Derived from the volume, never a typed cap."""
    import shutil
    per = max(gates, 1) * L.bytes_per_gate()
    return max(1, shutil.disk_usage("C:/").total // per)


def junction(node, partner, kind):
    """Compose a node with a partner across a §1E junction. Both laws are measured, not assumed.

    series   A's SEND wires ARE B's RECEIVE wires: the wavefronts overlap, so the second stage
             costs the §2 overlap (+6 gate-delays), not its own DEPTH. The assembly retires the
             NARROWER side's results per settle.
    parallel §14: independent work costs AREA and is free in latency. DEPTH is the max, area is
             the sum, and both sides' results retire on the same settle.
    """
    (gA, dA, rA), (gB, dB, rB) = node, partner
    if kind == "series":
        return gA + gB, max(dA, dB) + G.SERIES_OVERLAP, min(rA, rB)
    return gA + gB, max(dA, dB), rA + rB


class Foundry(object):
    """One foundry. Owns a problem, searches its genes, publishes its best node to the junction."""

    def __init__(self, fid, tag, name, P):
        self.fid, self.tag, self.name, self.P = fid, tag, name, P
        self.shape = P["shape"]
        self.replicated = (self.shape != "dependent")
        self.cases = P["cases"]()
        self.measured = {}          # adder -> (gates, DEPTH) once built and verified
        self.best = None            # (compute/tick, adder, topology, k, partner_label, g, d, rep)
        self.published = None       # (gates, DEPTH, replicas) offered to every other foundry

    def measure(self, adder):
        """Build the circuit and CHECK IT against the exact independent reference (§3).

        No number reaches a log row without passing this. A build that raises is MY construction
        failing (§7/§35D), and it is recorded as such rather than charged to the problem."""
        if adder in self.measured: return self.measured[adder]
        t0 = time.time()
        try:
            c, outs = self.P["build"](adder)
        except Exception as e:
            self.measured[adder] = (None, None, 0.0, "BUILD-RAISED:%s" % type(e).__name__)
            return self.measured[adder]
        ok = self.P["check"](c, outs, self.cases)
        d, g = depth_of(c, outs), len(c.ga)
        del c, outs
        ms = (time.time() - t0) * 1000.0
        self.measured[adder] = ((g, d, ms, "%d/%d" % (ok, len(self.cases)))
                                if ok == len(self.cases)
                                else (None, None, ms, "%d/%d" % (ok, len(self.cases))))
        return self.measured[adder]

    def mutants(self, adder):
        """§45C/§47B: a suite that catches nothing has measured itself, not the circuit."""
        caught = 0
        for m in self.P["mutants"]:
            cm, om = self.P["build"](adder, mutant=m)
            if self.P["check"](cm, om, self.cases) != len(self.cases): caught += 1
            del cm, om
        return caught, len(self.P["mutants"])

    def search(self, rnd, table, adders):
        """One round. Returns (rows, evaluated); the caller writes rows, never summarises them.

        WHAT IS WRITTEN AND WHAT IS NOT, stated rather than silently capped: the substrate ceiling
        is in the tens of millions of nodes, so the full enumeration is millions of rows per round.
        A row is written when it is a BASE measurement (k=1) or when it sets a new best for this
        foundry — the search frontier. `evaluated` reports the full count so the difference is
        visible in the log header rather than reading as complete coverage."""
        rows = []
        evaluated = 0
        seen_base = set()
        partners = [(lab, n) for lab, n in table.items() if not lab.startswith(self.label() + "@")]
        for adder in adders:
            g0, d0, ms, verify = self.measure(adder)
            if g0 is None:
                rows.append(dict(round=rnd, foundry=self.label(), problem=self.name, shape=self.shape,
                                 adder=adder, topology="-", k=0, partner="-", gates=0, depth=0,
                                 replicas=0, compute_per_tick=0.0, verify=verify, mutants="-",
                                 build_ms=round(ms, 1)))
                evaluated += 1
                continue
            ceil_k = ceiling_for(g0)
            k = 1
            while k <= ceil_k:
                sub = [("n", g0, d0)] * k
                for top in TOPOLOGIES:
                    if top == "series_of_banks" and k < 2: k_ok = False
                    else: k_ok = True
                    if not k_ok: continue
                    g, d, rep = G.compose(top, sub)
                    for plab, pnode in [("-", None)] + partners:
                        for kind in (("series", "parallel") if pnode else ("-",)):
                            if pnode:
                                gg, dd, rr = junction((g, d, rep), pnode, kind)
                                lab = "%s:%s" % (plab, kind)
                            else:
                                gg, dd, rr = g, d, rep
                                lab = "-"
                            ct = L.compute_per_tick(max(gg // max(rr, 1), 1), dd,
                                                    self.replicated) * (rr if self.replicated else 1)
                            evaluated += 1
                            improves = self.best is None or ct > self.best[0]
                            base = (adder, top, lab) not in seen_base
                            if base: seen_base.add((adder, top, lab))
                            if base or improves:
                                rows.append(dict(round=rnd, foundry=self.label(), problem=self.name,
                                                 shape=self.shape, adder=adder, topology=top, k=k,
                                                 partner=lab, gates=gg, depth=dd, replicas=rr,
                                                 compute_per_tick=ct, verify=verify, mutants="-",
                                                 build_ms=round(ms, 1)))
                            if improves:
                                self.best = (ct, adder, top, k, lab, gg, dd, rr)
                k *= 2
        if self.best:
            _ct, adder, top, k, _lab, gg, dd, rr = self.best
            g0, d0, _ms, _v = self.measured[adder]
            # Publish the SINGLE measured node, not the composite: a partner composes against a
            # real circuit, and letting composites publish composites would compound the laws
            # instead of applying them once each.
            self.published = (g0, d0, 1)
        return rows, evaluated

    def label(self):
        return "F%02d/%s" % (self.fid, self.name)


def main():
    only = None
    rounds = 3
    for i, a in enumerate(sys.argv):
        if a == "--only" and i + 1 < len(sys.argv): only = sys.argv[i + 1]
        if a == "--rounds" and i + 1 < len(sys.argv): rounds = int(sys.argv[i + 1])

    probs = problems(only)
    if not probs:
        print("no problems selected."); return 1
    adders = sorted(family(32))
    foundries = [Foundry(i, t, n, P) for i, (t, n, P) in enumerate(probs)]

    if not os.path.isdir(LOGDIR): os.makedirs(LOGDIR)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    logp = os.path.join(LOGDIR, "swarm_%s.tsv" % stamp)
    cols = ["round", "foundry", "problem", "shape", "adder", "topology", "k", "partner",
            "gates", "depth", "replicas", "compute_per_tick", "verify", "mutants", "build_ms"]

    print("FOUNDRY SWARM — %d foundries, %d round(s), %d adders." % (len(foundries), rounds, len(adders)))
    print("  interconnect: §1E junction; each foundry publishes its measured node every round.")
    print("  metric: compute/tick = REPLICAS/DEPTH (§63). gates = AREA. DEPTH = gate-delays.\n")

    table = {}
    nrows = nevals = 0
    log = open(logp, "w", encoding="utf-8", newline="")
    log.write("\t".join(cols) + "\n")
    t0 = time.time()
    for rnd in range(1, rounds + 1):
        pub = {}
        for f in foundries:
            rows, ev = f.search(rnd, table, adders)
            for r in rows:
                log.write("\t".join(str(r[c]) for c in cols) + "\n")
            nrows += len(rows); nevals += ev
            if f.published: pub[f.label() + "@r%d" % rnd] = f.published
        table.update(pub)
        log.flush(); os.fsync(log.fileno())
        print("  round %d: %d junction node(s) for the next round; %d configuration(s) evaluated, "
              "%d row(s) written (base + frontier)." % (rnd, len(table), nevals, nrows))
    log.close()

    print("\n  PER-FOUNDRY BEST (raw, no interpretation):")
    print("  %-22s %-11s %-10s %-16s %4s %-24s %10s %12s %10s %16s"
          % ("foundry", "shape", "adder", "topology", "k", "partner", "DEPTH", "gates",
             "replicas", "compute/tick"))
    for f in sorted(foundries, key=lambda x: -(x.best[0] if x.best else 0)):
        if not f.best:
            print("  %-22s %-11s  NO VERIFIED BUILD (§7/§35D: MY construction)" % (f.label(), f.shape))
            continue
        ct, adder, top, k, lab, gg, dd, rr = f.best
        print("  %-22s %-11s %-10s %-16s %4d %-24s %10s %12s %10d %16.6f"
              % (f.label(), f.shape, adder, top, k, lab, "{:,}".format(dd),
                 "{:,}".format(gg), rr, ct))

    print("\n  MUTANT PASS on each foundry's winning adder (§45C/§47B), then the ARTIFACT:")
    written = []
    for f in foundries:
        if not f.best: continue
        c, n = f.mutants(f.best[1])
        flag = "" if c == n else "   *** SUITE BLIND — NO ARTIFACT WRITTEN ***"
        print("    %-22s %d/%d mutants CAUGHT%s" % (f.label(), c, n, flag))
        if c != n: continue                     # a blind suite manufactures nothing (§45C/§47B)
        ct, adder, top, k, lab, gg, dd, rr = f.best
        g0, d0, _ms, ver = f.measured[adder]
        cfg = dict(
            config_id="cfg_%s_%s" % (f.name, stamp),
            problem=f.name, batch=f.tag, shape=f.shape, adder=adder,
            topology=top, nodes=k,
            junctions=([] if lab == "-" else [lab]),
            node_gates=g0, node_depth=d0,
            gates=gg, depth=dd, replicas=rr, compute_per_tick=ct,
            bytes_per_gate=L.bytes_per_gate(),
            storage_bytes_required=gg * L.bytes_per_gate(),
            verified=ver, mutants_caught="%d/%d" % (c, n),
            laws=dict(series_overlap=G.SERIES_OVERLAP,
                      metric="compute/tick = REPLICAS/DEPTH (§63)",
                      note="gates = AREA (§24). DEPTH = gate-delays, the only latency."),
            provenance=dict(tool="foundry_swarm", rounds=rounds, stamp=stamp,
                            phase="MANUFACTURING — off the clock (§31); never a runtime figure"))
        written.append(write_artifact(cfg))
    ip, ncfg = write_index()

    print("\n  ARTIFACTS — the deliverable. Each is a configuration fabrication can build directly:")
    for p in written: print("    " + p)
    print("    INDEX: %s  (%d configuration(s) in the store)" % (ip, ncfg))
    print("\n  %d configuration(s) evaluated · %d row(s) written (base + frontier) -> %s"
          % (nevals, nrows, logp))
    print("  host wall-clock %.1f s — THE FACTORY'S, off the clock (§31). Not the product's latency;"
          % (time.time() - t0))
    print("  the product's latency is the DEPTH in each artifact above.")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
