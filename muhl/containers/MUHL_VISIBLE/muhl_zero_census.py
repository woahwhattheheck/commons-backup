#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
muhl_zero_census.py -- MEASURE THE DEAD SILICON.

Owner, 2026-08-07:
    "IT OCCURS TO ME THAT THOSE ZEROS ARE MOSTLY A STRUCTURAL SUBOPTIMAL THING"
and earlier, the same crime named at smaller scale:
    "PUTTING LABELS IN THE BINARY IS SUBOPTIMAL THEY BELONG OUTSIDE OF THE FILE
     THEYRE TAKING UP ADDRESSES"

A zero byte in a gate record is not padding. In a muhlnickel a byte IS a wire, so a
structurally-always-zero byte is an ADDRESS THAT COMPUTES NOTHING. This tool measures
exactly how many there are and which byte lanes they sit in.

PHASE MATTERS. Containers built before the HDR=0 law carry a 128-byte header and
128 mod 25 == 3, so a naive stride-25 read at offset 0 is three bytes out of phase and
reports nonsense (op lane reads 100% zero). This tool RECOVERS the phase by scanning all
candidate header offsets and keeping the one where every record carries a legal op code.

NO VERDICTS. It reports bytes. Whether a geometry is adopted is a FABRICATION decision and
belongs to the autofab, not to this tool and not to the assistant.
"""
import io
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REC = 25
LANES = ["op",
         "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7",
         "b0", "b1", "b2", "b3", "b4", "b5", "b6", "b7",
         "o0", "o1", "o2", "o3", "o4", "o5", "o6", "o7"]

# op codes that appear in this corpus's physical records
LEGAL_OPS = set(range(0, 16))


def needbytes(v):
    n = 1
    while v >= (1 << (8 * n)):
        n += 1
    return n


def find_phase(b):
    """Return (hdr, n_gate, tail) for the alignment where every record has a legal op.

    Tries every plausible header size. A container is in phase when EVERY gate record's
    first byte is a legal op code. Prefers the alignment covering the most bytes.
    """
    n = len(b)
    best = None
    for hdr in range(0, min(256, n) + 1):
        avail = n - hdr
        if avail < REC:
            continue
        ng = avail // REC
        tail = avail - ng * REC
        if tail % 4:
            continue                      # out-array is u32; a ragged tail means wrong phase
        ok = True
        step = max(1, ng // 4096)         # sample wide, then confirm fully if it passes
        for i in range(0, ng, step):
            if b[hdr + i * REC] not in LEGAL_OPS:
                ok = False
                break
        if not ok:
            continue
        for i in range(ng):               # full confirm
            if b[hdr + i * REC] not in LEGAL_OPS:
                ok = False
                break
        if not ok:
            continue
        cand = (ng, hdr, tail)
        if best is None or cand[0] > best[0]:
            best = cand
    if best is None:
        return None, 0, 0
    ng, hdr, tail = best
    return hdr, ng, tail


def census(path):
    b = io.open(path, "rb").read()
    n = len(b)
    hdr, ng, tail = find_phase(b)
    if ng == 0:
        return None
    zero = [0] * REC
    mA = mB = mO = 0
    body_zero = 0
    for i in range(ng):
        base = hdr + i * REC
        for j in range(REC):
            if b[base + j] == 0:
                zero[j] += 1
                body_zero += 1
        op, a, bb, o = struct.unpack_from("<BQQQ", b, base)
        if a > mA:
            mA = a
        if bb > mB:
            mB = bb
        if o > mO:
            mO = o
    return dict(path=path, name=os.path.basename(path), size=n, hdr=hdr,
                n_gate=ng, tail=tail, zero=zero, body=ng * REC,
                body_zero=body_zero, mA=mA, mB=mB, mO=mO)


# ---------------------------------------------------------------- geometry ladder
def ladder(r):
    """Every record geometry that would hold this circuit's operands, widest-first.

    Not a recommendation. Sec 31A: 'the fabricator should spend without limit ... and keep
    only the minimum-DEPTH result'. Which rung gets used is the AUTOFAB's search, not mine.
    """
    w = max(needbytes(r["mA"]), needbytes(r["mB"]), needbytes(r["mO"]))
    out = []
    for ow in range(w, 9):
        out.append(("explicit-out", 1 + 3 * ow, ow, False))
        out.append(("implicit-out", 1 + 2 * ow, ow, True))
    out.sort(key=lambda t: t[1])
    return w, out


def main():
    files = sorted(f for f in os.listdir(HERE) if f.endswith(".mno"))
    rows = []
    print("PHASE-CORRECTED ZERO CENSUS")
    print("=" * 118)
    print("%-22s %10s %5s %8s %5s %10s %8s" %
          ("container", "bytes", "hdr", "gates", "tail", "zerobytes", "zero%"))
    print("-" * 118)
    for f in files:
        r = census(os.path.join(HERE, f))
        if r is None:
            print("%-22s  NO LEGAL PHASE FOUND" % f)
            continue
        rows.append(r)
        print("%-22s %10s %5d %8s %5d %10s %7.2f%%" %
              (f, format(r["size"], ","), r["hdr"], format(r["n_gate"], ","), r["tail"],
               format(r["body_zero"], ","), 100.0 * r["body_zero"] / r["body"]))

    tb = sum(r["body"] for r in rows)
    tz = sum(r["body_zero"] for r in rows)
    tg = sum(r["n_gate"] for r in rows)
    print("-" * 118)
    print("%-22s %10s %5s %8s %5s %10s %7.2f%%" %
          ("TOTAL", format(tb, ","), "", format(tg, ","), "", format(tz, ","),
           100.0 * tz / tb))

    print()
    print("PER-LANE ZERO RATE (%% of records with a zero byte in that lane)")
    print("=" * 118)
    h = "%-22s" % "container"
    for L in LANES:
        h += "%4s" % L
    print(h)
    print("-" * 118)
    agg = [0] * REC
    for r in rows:
        line = "%-22s" % r["name"][:22]
        for j in range(REC):
            line += "%4d" % int(round(100.0 * r["zero"][j] / r["n_gate"]))
            agg[j] += r["zero"][j]
        print(line)
    print("-" * 118)
    line = "%-22s" % "ALL (weighted)"
    for j in range(REC):
        line += "%4d" % int(round(100.0 * agg[j] / tg))
    print(line)

    print()
    print("DEAD LANES PER CONTAINER (zero in 100%% of that container's records)")
    print("=" * 118)
    for r in rows:
        dead = [LANES[j] for j in range(REC) if r["zero"][j] == r["n_gate"]]
        print("  %-22s %2d/25 lanes dead  %s" % (r["name"], len(dead), " ".join(dead)))

    print()
    print("GEOMETRY LADDER - every record shape that still holds the operands")
    print("=" * 118)
    tot_now = 0
    tot_min = 0
    for r in rows:
        w, rungs = ladder(r)
        print()
        print("  %s  (%s gates, widest operand %s -> %d bytes)" %
              (r["name"], format(r["n_gate"], ","), format(max(r["mA"], r["mB"], r["mO"]), ","), w))
        for kind, size, ow, imp in rungs[:6]:
            total = r["n_gate"] * size
            saved = r["n_gate"] * (REC - size)
            print("      %-13s operand=%dB  record=%2dB  container=%12s B  frees %12s B (%5.1f%%)" %
                  (kind, ow, size, format(total, ","), format(saved, ","),
                   100.0 * saved / (r["n_gate"] * REC)))
        tot_now += r["n_gate"] * REC
        tot_min += r["n_gate"] * rungs[0][1]
    print()
    print("  ACROSS EVERY CONTAINER MEASURED:")
    print("      current 25 B geometry : %s B" % format(tot_now, ","))
    print("      narrowest legal rung  : %s B" % format(tot_min, ","))
    print("      addresses freed       : %s B  (%.1f%%)" %
          (format(tot_now - tot_min, ","), 100.0 * (tot_now - tot_min) / tot_now))
    print()
    print("  NOT A RECOMMENDATION. Which rung is used is an AUTOFAB search, per Sec 31A.")


if __name__ == "__main__":
    main()
