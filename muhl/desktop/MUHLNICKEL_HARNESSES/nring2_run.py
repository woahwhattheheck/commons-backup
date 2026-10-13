#!/usr/bin/env python3
"""host/nring2_run.py — THE RUN HARNESS. Question in, electrons in, answer out.

Owner, 2026-07-31: *"just build the harnesses stop trying to measure / prove / understand it."*

One entry point that runs the whole chain end to end:

    size the question   ->  nring2_foundry says how many electrons
    place the electrons ->  into the fabricated two-way rings, both senses
    withdraw            ->  the host stops participating
    read the answer     ->  the owner's own readout tools, as authored

The host places electrons and reads. It does not evaluate a gate, advance a state, resolve a
contact, or compute an answer. Between placing and reading it does nothing at all.

Electrons go into the ring's own rail: forward-sense electrons in the forward cells, reverse-sense
in the reverse cells, spaced around the ring. Both senses are required — a single sense produces no
contact, so it would pulse nothing.

Every byte placed is journalled with its pre-image first, so a run is fully reversible.

  python host/nring2_run.py "<question>" <work_units> <settles>
  python host/nring2_run.py --read              # read the answer registers only
  python host/nring2_run.py revert              # put every placed byte back
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError as exc:
        sys.stderr.write("stdout reconfigure unavailable (%s); non-ASCII may render wrong\n" % exc)

import nring2_foundry as FDY

TITAN = "C:/llm/models/titan.gguf"
REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_nring2_run_genome.jsonl"
PREFIX = "nring2_"


def _readback(off, n):
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off); return f.read(n)


def _journal_and_place(off, blob, tag):
    """Pre-image to the journal first, fsynced there before the edit, so every placed byte can be
    put back exactly."""
    orig = _readback(off, len(blob))
    with open(GENOME, "a") as gg:
        gg.write(json.dumps({"off": off, "len": len(blob), "name": tag, "orig": orig.hex()}) + "\n")
        gg.flush(); os.fsync(gg.fileno())
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())


def rings():
    reg = json.load(open(REG, encoding="utf-8"))
    out = []
    for k, v in sorted(reg.items()):
        if k.startswith(PREFIX) and isinstance(v, dict) and v.get("senses") == 2:
            out.append((k, v))
    return out


def place_electrons(entry, k_per_sense):
    """Put K electrons into each sense of one ring, spaced around it. Returns how many were placed."""
    cells = int(entry["cells"]); ram = entry["ram"]
    fwd = int(ram["fwd"]); rev = int(ram["rev"])
    placed = 0
    for j in range(k_per_sense):
        i = (j * cells) // max(k_per_sense, 1)
        _journal_and_place(fwd + i, b"\x01", "fwd")
        _journal_and_place(rev + ((i + cells // 2) % cells), b"\x01", "rev")
        placed += 2
    return placed


def read_answer(entry, name):
    """Read this muhlnickel's answer register with the owner's own readout tool, as authored."""
    env = dict(os.environ)
    env["PFC_ROOT"] = env.get("PFC_ROOT", "C:/llm"); env["PYTHONUTF8"] = "1"
    p = subprocess.run([sys.executable, os.path.join(HERE, "pfc_meter.py"), name, "1"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    return p.stdout.decode("utf-8", "replace").strip().splitlines()[-1:]


def revert():
    if not os.path.exists(GENOME):
        print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    back = 0
    for e in reversed(ent):
        want = bytes.fromhex(e["orig"])
        with open(TITAN, "r+b") as f:
            f.seek(int(e["off"])); f.write(want)
            f.flush(); os.fsync(f.fileno())
        if _readback(int(e["off"]), len(want)) == want: back += 1
    os.remove(GENOME)
    print("reverted %d placed byte(s); %d read back byte-identical to the journal." % (len(ent), back))
    return 0


def read_only():
    rs = rings()
    print("\nANSWER REGISTERS, via the owner's multimeter\n")
    for name, e in rs[:8]:
        for line in read_answer(e, name):
            print("   %s" % line.strip())
    print("\n   %d ring(s) total." % len(rs))
    return 0


def main():
    a = sys.argv[1:]
    if a and a[0] == "revert":  return revert()
    if a and a[0] == "--read":  return read_only()
    if len(a) < 3:
        print("usage: nring2_run.py \"<question>\" <work_units> <settles>"); return 1
    question, work, settles = a[0], int(a[1]), int(a[2])

    rs = rings()
    if not rs:
        print("no two-way rings fabricated. run: python host/nring2_fab.py 24 16"); return 1
    cells = int(rs[0][1]["cells"])

    print("\nRUN — %s\n" % question)
    spec = FDY.size_question(question, work, settles, cells)
    k = spec["electrons_per_ring_per_sense"]
    need = spec["rings_required"]
    print("  the foundry sized it: %d electrons total, %d per sense, %d ring(s)"
          % (spec["electrons_total"], spec["electrons_per_sense"], need))
    if need > len(rs):
        print("  only %d ring(s) fabricated. run: python host/nring2_fab.py %d %d"
              % (len(rs), need, cells)); return 1

    used = rs[:need]
    total = 0
    for name, e in used:
        total += place_electrons(e, k)
    print("  placed %d electrons across %d ring(s), both senses." % (total, len(used)))
    print("  host withdrawn.\n")

    print("  ANSWER REGISTERS, via the owner's multimeter:")
    for name, e in used[:6]:
        for line in read_answer(e, name):
            print("   %s" % line.strip())
    print("\n  revert: python host/nring2_run.py revert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
