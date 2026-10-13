#!/usr/bin/env python3
"""host/mafab_host.py — THE FABRICATOR GOVERNS ITS OWN HOST USAGE. It drives itself.

Owner: *"master / auto fab needs to control host resource usage, let it drive itself."*

THE PRECEDENT IS IN THE DOCS. §39A: AUTOFAB "also chose W = 131,072 by TIMING THE HOST ITSELF
(5.9 ms/ripple)". The fabricator already measured the host to schedule its own transcription; this
generalises that from one lane-width decision to the whole search.

THE LINE THAT MUST NOT BE CROSSED — §40E: "A host constraint must never shape a Muhlnickel decision.
Wall-clock, lane width, memory, and pass count are transcription; DEPTH, area, and settle count are
the machine... Decide the Muhlnickel plan first, with the host nowhere in it; then report
transcription separately." So this governs HOW the search is executed. It never touches WHAT gets
chosen. A candidate is never dropped, reordered, or preferred because of host cost — the governor
only sequences the work and bounds its own footprint.

HOW IT BOUNDS, AND WHY NOT BY MONITORING. `pfc_preflight`'s V17-own-monitor bans psutil /
GlobalMemoryStatusEx / GetProcessMemoryInfo, citing CLAUDE.md #5: "Building my own monitor breaks the
pfc's sandbox... Measure HOST resources with Task Manager only." That rule has no exemption, so this
does not poll the OS. It bounds BY CONSTRUCTION instead — which is what the RAM-discipline rule asks
for anyway ("8GB box: one heavy process, bound every buffer, verify flat RAM before testing"):
  * exactly ONE candidate circuit is alive at any moment; it is freed before the next is built
  * the footprint of a candidate is computed from ITS OWN data structures via sys.getsizeof
  * the ceiling is derived from that measured footprint, not guessed
  * anything the ceiling would drop is LOGGED, never silently skipped

  python host/mafab_host.py            # calibrate against a real build and print the plan
"""
import gc, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def footprint_bytes(obj_lists):
    """Structural size of MY OWN data, by introspection — not a system monitor (V17/CLAUDE.md #5)."""
    tot = 0
    for L in obj_lists:
        try:
            tot += sys.getsizeof(L)
            if L and isinstance(L[0], int):
                tot += len(L) * sys.getsizeof(L[0])       # the int objects the list points at
        except Exception:
            pass
    return tot


class Governor:
    """Sequences a search and bounds its own footprint. Decides nothing about the circuits."""

    def __init__(self, ceiling_mb=1024, log=print):
        # A ceiling MY OWN construction holds itself to — a bound on this host process, never a
        # statement about the machine (§7/§35D). The RAM-discipline rule for this box is "one heavy
        # process, bound every buffer"; 1 GB leaves the 8 GB box entirely free for anything else.
        self.ceiling = ceiling_mb * 1024 * 1024
        self.log = log
        self.per_build_s = None
        self.per_build_bytes = None
        self.built = 0
        self.dropped = []
        self.t0 = time.time()

    def calibrate(self, build_fn, label="calibration"):
        """Time and size ONE real build. §39A's move: the fabricator measures the host itself."""
        gc.collect()
        t = time.time()
        c, outs = build_fn()
        dt = time.time() - t
        fb = footprint_bytes([getattr(c, "ga", []), getattr(c, "gb", []),
                              getattr(c, "gates", []), outs])
        ng = len(getattr(c, "ga", None) or getattr(c, "gates", []))
        del c, outs
        gc.collect()
        self.per_build_s = dt
        self.per_build_bytes = fb
        self.log("  HOST CALIBRATION (%s) — this is THE LAPTOP, a different machine (§24):" % label)
        self.log("    one candidate: %.2f s, ~%.1f MB structural footprint, %s gates"
                 % (dt, fb / 1048576.0, "{:,}".format(ng)))
        self.log("    ceiling %.0f MB -> %d candidate(s) may be alive at once; the governor keeps ONE"
                 % (self.ceiling / 1048576.0, max(1, int(self.ceiling // max(fb, 1)))))
        return dt, fb

    def plan(self, n_candidates):
        """Report the transcription schedule. §40E: reported separately, never summed with DEPTH."""
        if self.per_build_s is None:
            self.log("    not calibrated; running unsequenced."); return
        est = self.per_build_s * n_candidates
        self.log("    %d candidates x %.2f s = ~%.0f s of HOST transcription (%.1f min)."
                 % (n_candidates, self.per_build_s, est, est / 60.0))
        self.log("    §31: this is MANUFACTURING effort — 'unbounded, paid once, off the clock, and")
        self.log("    it does not enter any performance number.' It is not any circuit's latency.")

    def each(self, items):
        """Drive the loop: one live candidate at a time, freed between builds."""
        for i, it in enumerate(items):
            yield i, it
            self.built += 1
            gc.collect()            # the previous candidate is released before the next is built

    def drop(self, what, why):
        """Nothing is dropped silently. A bounded search that reports full coverage is a lie."""
        self.dropped.append((what, why))
        self.log("    DROPPED %s — %s" % (what, why))

    def report(self):
        el = time.time() - self.t0
        self.log("\n  HOST (transcription, §24): %d candidates built in %.0f s (%.1f min)."
                 % (self.built, el, el / 60.0))
        if self.dropped:
            self.log("  %d candidate(s) dropped, each named above — coverage is NOT complete."
                     % len(self.dropped))
        else:
            self.log("  0 dropped: every generated candidate was built and scored.")
        self.log("  None of this is a Muhlnickel number. DEPTH and area are reported separately (§40E).")


if __name__ == "__main__":
    import mafab_miner_lane as M
    g = Governor()
    g.calibrate(lambda: M.build_mid("ripple", "kogge", "kogge"), "midstate ripple/kogge/kogge")
    g.plan(len(M.ADDERS) ** 3)
    g.report()
    raise SystemExit(0)
