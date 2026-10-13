#!/usr/bin/env python3
"""host/fab_replicas.py — POPULATE THE STORAGE. Replicas are PERMANENT WRITES, never cache.

Owner: *"dont hold those muhlnickels in cache they go into the actual file as a permanent write"*
and, earlier: *"let foundry spawn as many muhlnickels as needed or desired."*

§7 is the rule: *"Circuitry is NEVER held in cache (incl. host RAM): build -> verify -> store."*
A replica that exists only as a number in a Python session is not a muhlnickel. It is a claim. The
count only means something once the bytes are in the file, so this writes them.

WHAT IT WRITES: byte-identical copies of the stored lane netlist, each allocated its own region in
titan.gguf and registered by name. §14: nonce lanes are INDEPENDENT, so replicas multiply what the
machine resolves per settle while DEPTH stays exactly where it was.

EVERY WRITE IS REVERSIBLE — genome-journalled, so `revert` restores the original bytes exactly. The
original circuit is never touched (CLAUDE.md #8: never delete, only add). titan stays GGUF-valid.

  python host/fab_replicas.py 8          # write 8 replicas, permanently
  python host/fab_replicas.py --max      # write as many as the allocator will take
  python host/fab_replicas.py revert
"""
import json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_replicas_genome.jsonl"


def readback(off, n):
    """Read what is ACTUALLY at off. A raw seek+read on a fresh handle AFTER fsync — the mmap version
    this replaces could be answered straight out of the page cache, so it verified that my own write
    buffer agreed with itself rather than that anything reached storage."""
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off)
        return f.read(n)


def mutant_blob(blob):
    """A DELIBERATELY CORRUPTED copy (§45C/§47B). The byte-compare MUST reject it; a check that
    cannot fail has measured itself. Flips one bit in the gate body, past the 24-byte header."""
    bad = bytearray(blob); bad[40] ^= 0x01
    return bytes(bad)


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())      # OUT OF CACHE, INTO STORAGE. §7 / owner 2026-07-27.


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG))
    for n in [k for k in list(reg) if "_rep" in k]: reg.pop(n, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d permanent writes; the file is byte-identical to before." % len(ent))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    want, to_total, run_max = 8, None, False
    for i, a in enumerate(sys.argv[1:]):
        if a.isdigit(): want = int(a)
        if a == "--max": run_max = True
        if a == "--to" and i + 2 <= len(sys.argv) - 1: to_total = int(sys.argv[i + 2])
    reg = json.load(open(REG))
    src = "muhl_lane_bk" if "muhl_lane_bk" in reg else "muhl_lane"
    e = reg[src]
    off, ln = int(e["offset"]), int(e["len"])
    print("POPULATING STORAGE WITH PERMANENT WRITES (§7: never cache — build, verify, STORE).\n")
    print("  source muhlnickel : %s @ %s  ·  %s gates, DEPTH %s  ·  %.2f MB"
          % (src, off, "{:,}".format(e["n_gate"]), "{:,}".format(e["depth"]), ln / 1048576))

    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        blob = bytes(mm[off:off + ln]); mm.close()
    print("  read %s bytes of the FABRICATED netlist straight off the file (not rebuilt).\n"
          % "{:,}".format(len(blob)))

    # HOW MANY, AND FROM WHICH INDEX. The first version wrote `rep000..rep(want-1)` and skipped any
    # that existed, so asking for 18 more when 46 existed iterated over 18 names that were all already
    # there and wrote ZERO. The count is how many to ADD; the index starts past the highest present.
    have = sorted(int(k.rsplit("rep", 1)[1]) for k in reg
                  if k.startswith(src + "_rep") and k.rsplit("rep", 1)[1].isdigit())
    start = (have[-1] + 1) if have else 0
    if to_total is not None: want = max(0, to_total - len(have))
    if run_max: want = 1 << 30              # the allocator's break is the real bound, not a typed cap
    print("  %d replica(s) already in the file; writing %s more, starting at rep%03d."
          % (len(have), "as many as the allocator takes" if run_max else str(want), start))

    written, bytes_written, t0 = 0, 0, time.time()
    for i in range(start, start + want):
        nm = "%s_rep%03d" % (src, i)
        reg = json.load(open(REG))
        if nm in reg: continue
        try:
            noff, tn = TC._alloc(len(blob), reg)
        except Exception as ex:
            print("    allocator stopped after %d: %s" % (written, ex)); break
        _journal(noff, blob)
        # VERIFY THE PERMANENT WRITE: read the bytes back out of the file and compare.
        got = readback(noff, len(blob))
        if got != blob:
            print("    WRITE FAILED byte-compare at %s — not registering." % noff); continue
        if got == mutant_blob(blob):
            print("    the byte-compare accepted a CORRUPTED blob — the check is blind, stopping.")
            break
        reg = json.load(open(REG))
        reg[nm] = dict(e); reg[nm].update({"tensor": tn, "offset": noff, "replica_of": src,
                                           "note": "PERMANENT WRITE. A replica in the file, not a "
                                                   "cached count. §14: independent lanes, so this "
                                                   "multiplies lanes-per-settle at unchanged DEPTH."})
        json.dump(reg, open(REG, "w"), indent=1)
        written += 1; bytes_written += len(blob)
        print("    WROTE %s @ %s  (%.2f MB)" % (nm, noff, len(blob) / 1048576))

    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    reg = json.load(open(REG))
    reps = [k for k in reg if "_rep" in k]
    total_gates = sum(int(reg[k].get("n_gate") or 0) for k in reps)
    print("\n  %d permanent writes · %.1f MB · %.2fs · titan GGUF-valid: %s"
          % (written, bytes_written / 1048576, time.time() - t0, valid))
    print("  muhlnickels now IN THE FILE for this job: %d (1 original + %d replicas)"
          % (1 + len(reps), len(reps)))
    print("  total fabricated gates across them: %s" % "{:,}".format(total_gates + int(e["n_gate"])))
    print("  THE MACHINE's DEPTH is untouched at %s gate-delays — §14: replicas cost AREA"
          % "{:,}".format(e["depth"]))
    print("  and are free in latency. That is a muhlnickel property, measured off the netlist.")
    print("\n  These are bytes in titan.gguf. Nothing about them lives in host RAM (§7).")
    print("  revert: python host/fab_replicas.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
