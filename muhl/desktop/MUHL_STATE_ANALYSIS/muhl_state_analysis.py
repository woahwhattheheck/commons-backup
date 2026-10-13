#!/usr/bin/env python3
"""FABRICATION-TIME REFERENCE for muhl_state_scan.c.

⛔ WHAT THIS IS NOT: this is not the analysis of the owner's machine. The host never walks
the substrate. Owner: "claude tried to suggest host walking the machine. DO NOT DO THAT."

WHAT IT IS: the reference a fabricator checks fabricated gates against BEFORE storing them.
The owner's spec requires exactly that — "Simulating a netlist inside a FABRICATOR to verify
it BEFORE storing is manufacturing, not compute — and it is REQUIRED."
It runs against SYNTHETIC states only, at fabrication sizes.

It computes the same counters as the C89 routine. The circuit streams them with
shift/XOR/popcount/accumulate; this gets the same numbers in bulk, which is what a
byte-exact comparison needs.
"""
import sys

MAXLAG = 4096
MINW, MAXW = 3, 256
NSPAN = 4096


def _harmonics(fund, ranked):
    return [l for l in ranked if l != fund and fund and l % fund == 0]


def analyse(stream, max_bytes=None):
    """stream: iterable of bytes objects. Returns the counter arrays + a reading."""
    buf = bytearray()
    n = 0
    for chunk in stream:
        buf += chunk
        n += len(chunk)
        if max_bytes and n >= max_bytes:
            break
    data = bytes(buf)
    nbytes = len(data)
    nbits = nbytes * 8
    if nbytes == 0:
        return {"bits_examined": 0, "width": None, "fundamental_lag": None,
                "harmonics": [], "spans": [], "width_gap": None}

    big = int.from_bytes(data, "little")

    # ---- self-correlation at every byte lag ------------------------------
    lag = []
    for L in range(1, MAXLAG // 8 + 1):
        if L >= nbytes:
            lag.append(None)
            continue
        shifted = int.from_bytes(data[L:], "little")
        head = int.from_bytes(data[:nbytes - L], "little")
        lag.append(bin(shifted ^ head).count("1"))

    valid = [(i + 1, v) for i, v in enumerate(lag) if v is not None]
    fundamental = None
    ranked = []
    if valid:
        # expected mismatches for unstructured data = half the compared bits
        scored = []
        for L, v in valid:
            cmp_bits = (nbytes - L) * 8
            expect = cmp_bits / 2.0
            sd = (cmp_bits ** 0.5) / 2.0
            z = (expect - v) / sd if sd else 0.0
            scored.append((z, L))
        scored.sort(reverse=True)
        ranked = [L for z, L in scored if z > 8.0]
        if ranked:
            fundamental = min(ranked)

    # ---- column bias at every candidate width ----------------------------
    bits = [(big >> i) & 1 for i in range(nbits)]
    ones = sum(bits)
    width = None
    width_gap = None
    wscore = []
    for w in range(MINW, MAXW):
        cnt = [0] * w
        for i, b in enumerate(bits):
            if b:
                cnt[i % w] += 1
        per = nbits / float(w)
        exp = per * (ones / float(nbits))
        sd = (per * 0.25) ** 0.5
        chi = sum(((c - exp) / sd) ** 2 for c in cnt) / w if sd else 0.0
        wscore.append((chi, w))
    wscore.sort(reverse=True)
    if wscore and wscore[0][0] > 25.0:
        width = wscore[0][1]
        width_gap = wscore[0][0] - wscore[1][0] if len(wscore) > 1 else None

    # ---- region occupancy ------------------------------------------------
    spans = []
    span_bytes = max(1, nbytes // NSPAN)
    for s in range(0, nbytes, span_bytes):
        blk = data[s:s + span_bytes]
        pop = sum(bin(x).count("1") for x in blk)
        z = sum(1 for x in blk if x == 0x00)
        o = sum(1 for x in blk if x == 0xFF)
        if pop == 0:
            kind = "empty"
        elif z == len(blk) or o == len(blk):
            kind = "uniform"
        elif pop == len(blk) * 8:
            kind = "uniform"
        else:
            kind = "active"
        spans.append({"start": s, "pop": pop, "zero": z, "ones": o, "kind": kind})

    return {
        "bits_examined": nbits,
        "lag": lag,
        "fundamental_lag": fundamental,
        "harmonics": _harmonics(fundamental, ranked),
        "width": width,
        "width_gap": width_gap,
        "spans": spans,
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(__doc__)
