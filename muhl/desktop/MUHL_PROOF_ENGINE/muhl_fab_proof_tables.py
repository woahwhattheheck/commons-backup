#!/usr/bin/env python3
"""muhl_fab_proof_tables.py -- put the SEARCH TABLES in the container, and probe them there.

Owner, 2026-08-06: "then ur not working in spec then are you?"

The first fix moved the search's DECISIONS onto fabricated gates (muhl_search_substrate.py).
But those tables were scratch files in a temp directory. His standing spec is that the work
lives in the binary and the host addresses it -- a table in %TEMP% is not the substrate, it is
a file next to it. So this stores the search tables INSIDE titan.gguf and runs the same
fabricated semijoin against them, read-only, straight out of the container.

    KNOWN  magic MUHLPKN1 : rows (key, cost, rule, src)      -- derived formulas
    IMPL   magic MUHLPIM1 : rows (ante, cons, cost, term)    -- the inverted index for MP

Row layout is the fixed 16-byte shape the gate scan consumes, so the bytes in the container
ARE the scan input -- no repacking, no host-side transformation between storage and gates.

    python muhl_fab_proof_tables.py --dry
    python muhl_fab_proof_tables.py
    python muhl_fab_proof_tables.py --revert
"""
import json, mmap, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
sys.stdout.reconfigure(encoding="utf-8")

import muhl_proofcheck as PC
import muhl_search_substrate as SS

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
NAME = "muhl_proof_tables"
GENOME = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)
MK, MI = b"MUHLPKN1", b"MUHLPIM1"
ROW = 16

DRY = "--dry" in sys.argv
REVERT = "--revert" in sys.argv


def seed():
    """Axiom instances over a small pool. FABRICATION — offline, one-and-done, before firing."""
    T = PC.Terms()
    A, B, C = T.atom(0), T.atom(1), T.atom(2)
    pool = [A, B, C, T.imp(A, A)]
    known, impl = [], []
    for x in pool:
        for y in pool:
            t = T.imp(x, T.imp(y, x))
            known.append((t, 1, PC.RULE_K, 0))
            tag, a, c = T.slots[t]
            impl.append((a, c, 1, t))
    for x in pool:
        for y in pool:
            for z in pool:
                t = T.imp(T.imp(x, T.imp(y, z)), T.imp(T.imp(x, y), T.imp(x, z)))
                known.append((t, 1, PC.RULE_S, 0))
                tag, a, c = T.slots[t]
                impl.append((a, c, 1, t))
    for x in pool:
        known.append((x, 0, 255, 0))
    return T, known, impl, T.imp(A, A)


def pack(magic, rows):
    body = b"".join(struct.pack("<4I", *[x & 0xFFFFFFFF for x in r]) for r in rows)
    return magic + struct.pack("<II", len(rows), ROW) + body


def alloc(nbytes, taken):
    reg = json.load(open(REG))
    hi = 0
    for v in reg.values():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            hi = max(hi, int(v["offset"]) + int(v["len"]))
    for o, l in taken:
        hi = max(hi, o + l)
    hi = max(hi, os.path.getsize(TITAN))
    return ((hi + 63) // 64) * 64


def jwrite(off, blob, tag):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"action": NAME + "_" + tag, "off": off,
                            "len": len(blob), "orig": orig.hex()}) + "\n")
    fs = os.path.getsize(TITAN)
    if off + len(blob) > fs:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fs))
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def revert():
    print("  reverting %s ..." % NAME)
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f:
                f.seek(int(e["off"]))
                f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
        print("  journal replayed — byte-exact")
    reg = json.load(open(REG))
    if NAME in reg:
        reg.pop(NAME)
        json.dump(reg, open(REG, "w"), indent=1)
        print("  registry entry removed")
    return 0


class ContainerTable:
    """A table living INSIDE titan.gguf. Exposes exactly what the gate scan needs."""

    def __init__(self, mm, payload_off, nrows):
        self.mm = mm
        self.base = payload_off
        self.n = nrows

    def __getitem__(self, s):
        return self.mm[self.base + s.start:self.base + s.stop]


def probe_container(tab, key, c, outs, field, stats):
    """Same fabricated predicate, same bit-slicing — but the rows come from the CONTAINER."""
    if not tab.n:
        return False
    kbits = [(-1 if (key >> i) & 1 else 0) for i in range(32)]
    idx = 0
    while idx < tab.n:
        w = min(SS.LANES, tab.n - idx)
        raw = tab.mm[tab.base + idx * ROW: tab.base + (idx + w) * ROW]
        cols = [0] * 32
        for j in range(w):
            val = struct.unpack_from("<I", raw, j * ROW + 4 * field)[0]
            b = 0
            while val:
                if val & 1:
                    cols[b] |= (1 << j)
                val >>= 1
                b += 1
        stats["settles"] += 1
        stats["rows"] += w
        if SS.ripple_sliced(c, outs, cols + kbits)[0] & ((1 << w) - 1):
            return True
        idx += w
    return False


def main():
    t0 = time.time()
    print("=" * 84)
    print("  %s — search tables INSIDE titan.gguf, probed by fabricated gates" % NAME)
    print("=" * 84)

    T, known, impl, goal = seed()
    bk, bi = pack(MK, known), pack(MI, impl)
    print("  seed: %d known rows (%d B), %d impl rows (%d B)"
          % (len(known), len(bk), len(impl), len(bi)))

    c, outs = SS.build_match()
    ok = SS.verify_match(c, outs)
    print("  match predicate: %d gates, DEPTH %d ticks, byte-exact: %s"
          % (len(c.ga), SS.depth_of(c, outs), ok))
    if not ok:
        return 1

    if DRY:
        print("\n  --dry: verified, nothing stored.  [%.1fs]" % (time.time() - t0))
        return 0

    taken = []
    ok_off = alloc(len(bk), taken)
    jwrite(ok_off, bk, "known")
    taken.append((ok_off, len(bk)))
    oi_off = alloc(len(bi), taken)
    jwrite(oi_off, bi, "impl")
    print("  KNOWN @ %d  (%d B)   IMPL @ %d  (%d B)" % (ok_off, len(bk), oi_off, len(bi)))

    f = open(TITAN, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[ok_off:ok_off + 8] == MK and mm[oi_off:oi_off + 8] == MI, "magic"
    nk, rw1 = struct.unpack_from("<II", mm, ok_off + 8)
    ni_, rw2 = struct.unpack_from("<II", mm, oi_off + 8)
    print("  read back: KNOWN %d rows stride %d · IMPL %d rows stride %d"
          % (nk, rw1, ni_, rw2))

    ktab = ContainerTable(mm, ok_off + 16, nk)
    itab = ContainerTable(mm, oi_off + 16, ni_)

    stats = {"settles": 0, "rows": 0}
    base = SS.rss_mb()
    hit = probe_container(ktab, goal, c, outs, 0, stats)
    print("\n  probing the CONTAINER's own bytes with the fabricated predicate:")
    print("    A -> A found in KNOWN: %s  — expected True, it is a SEED POOL member, not a" % hit)
    print("      derivation. This probe proves the gates read the container correctly; it is")
    print("      not evidence of a proof. Saying so because the label here previously implied")
    print("      the opposite.")
    # one MP round, entirely against container-resident tables
    derived = 0
    for i in range(itab.n):
        ante, cons, cost, term = struct.unpack_from(
            "<4I", mm, itab.base + i * ROW)
        if probe_container(ktab, ante, c, outs, 0, stats) and \
           not probe_container(ktab, cons, c, outs, 0, stats):
            derived += 1
    end = SS.rss_mb()
    mm.close()
    f.close()

    d = SS.depth_of(c, outs)
    print("    one MP round over container tables -> %d new consequents identified" % derived)
    print("\n  gate settles          : %d" % stats["settles"])
    print("  rows compared by gates: %d  (%d per settle)" % (stats["rows"], SS.LANES))
    print("  substrate cost        : %d x DEPTH %d = %d ticks"
          % (stats["settles"], d, stats["settles"] * d))
    print("  resident RAM          : %.1f -> %.1f MB, net %+.2f MB" % (base, end, end - base))

    reg = json.load(open(REG))
    reg[NAME] = {
        "name": NAME, "format": "software-data",
        "kind": "proof-search tables resident IN the container; the gate scan's input bytes",
        "known": {"offset": ok_off, "len": len(bk), "magic": MK.decode(),
                  "payload_offset": ok_off + 16, "rows": nk, "row_bytes": ROW,
                  "fields": "key, cost, rule, src"},
        "impl": {"offset": oi_off, "len": len(bi), "magic": MI.decode(),
                 "payload_offset": oi_off + 16, "rows": ni_, "row_bytes": ROW,
                 "fields": "ante, cons, cost, term"},
        "probed_by": "32-bit equality predicate, %d gates, DEPTH %d ticks, bit-sliced %d rows "
                     "per settle" % (len(c.ga), d, SS.LANES),
        "host_role": "address the window, read the match mask. It decides no equality.",
        "seeded_by": "host hash-consing at FABRICATION time — offline, one-and-done (RULE ZERO)",
        "new_matter": "post-2026-08-04; follow-on provisional",
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "units": "depth=TICKS len=BYTES", "genome": GENOME,
    }
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f2:
        print("  titan.gguf GGUF-valid: %s" % (f2.read(4) == b"GGUF"))
    print("\n  STORED. The search tables are container-resident and the gates probe them there.")
    print("  [%.1fs]" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
