#!/usr/bin/env python3
"""Component implementation and operation."""
import json, mmap, os, random, struct, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
sys.stdout.reconfigure(encoding="utf-8")

import titan_circuit as TC
import muhl_proofcheck as PC

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
NAME = "muhl_scan_machine"
MAGIC = b"MUHLSCN1"
TBL_MAGIC = b"MUHLKEYB"
GATE_STRIDE = 25
GENOME = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)

DRY = "--dry" in sys.argv
REVERT = "--revert" in sys.argv

KEY_BITS = 32
N_ROWS = 128                    # keys compared SIMULTANEOUSLY, one settle
IDX_BITS = 7                    # log2(N_ROWS)


def depth_of(c, outs):
    d = [0] * (2 + c.n_in + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + c.n_in + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def build():
    """inputs: N_ROWS*32 table key bits, then 32 probe bits.
       outputs: hit, idx[IDX_BITS], match[N_ROWS]."""
    c = TC.Circuit(N_ROWS * KEY_BITS + KEY_BITS)
    IN = c.IN
    rows = [[IN[r * KEY_BITS + b] for b in range(KEY_BITS)] for r in range(N_ROWS)]
    probe = [IN[N_ROWS * KEY_BITS + b] for b in range(KEY_BITS)]

    # every row compared against the probe, in the SAME settle
    match = [c._tree_and([c.not_(c.xor(rows[r][b], probe[b])) for b in range(KEY_BITS)])
             for r in range(N_ROWS)]

    # hit = OR over all matches, as a tree
    items = list(match)
    while len(items) > 1:
        items = [c.or_(items[i], items[i + 1]) for i in range(0, len(items) - 1, 2)] + \
                ([items[-1]] if len(items) % 2 else [])
    hit = items[0]

    # FIRST-hit priority: row r wins only if no lower-numbered row matched.
    # none_before[r] = AND over q<r of NOT match[q]. That is a PREFIX SCAN, and a scan is
    # ASSOCIATIVE -- so it reduces in log2(N) rounds, not N. A serial chain here cost DEPTH
    # 283; his own titan_circuit.py already names this exact mistake: "A serial fold here was
    # costing every circuit in the library depth for nothing." Kogge-Stone shape, per his
    # add_prefix/sub_prefix.
    nm = [c.not_(match[r]) for r in range(N_ROWS)]
    pref = list(nm)                       # pref[r] = AND of nm[r-step+1 .. r] as step grows
    step = 1
    while step < N_ROWS:
        nxt = list(pref)
        for r in range(step, N_ROWS):
            nxt[r] = c.and_(pref[r], pref[r - step])
        pref = nxt
        step *= 2
    # inclusive scan -> exclusive: nothing precedes row 0
    none_before = [c.C1] + pref[:N_ROWS - 1]
    first = [c.and_(match[r], none_before[r]) for r in range(N_ROWS)]

    # encode the winning index: bit j = OR of first[r] for every r with bit j set
    idx = []
    for j in range(IDX_BITS):
        terms = [first[r] for r in range(N_ROWS) if (r >> j) & 1]
        if not terms:
            idx.append(c.C0)
            continue
        while len(terms) > 1:
            terms = [c.or_(terms[i], terms[i + 1]) for i in range(0, len(terms) - 1, 2)] + \
                    ([terms[-1]] if len(terms) % 2 else [])
        idx.append(terms[0])

    return c, [hit] + idx + match


def ref(keys, probe):
    m = [1 if k == probe else 0 for k in keys]
    hit = 1 if any(m) else 0
    i = m.index(1) if hit else 0
    return hit, i, m


def verify(c, outs, n=400):
    rng = random.Random(777)
    cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    both = [0, 0]
    for t in range(n):
        keys = [rng.randrange(1 << 32) for _ in range(N_ROWS)]
        if t % 3 == 0:
            keys[rng.randrange(N_ROWS)] = keys[0]           # force duplicates sometimes
        probe = keys[rng.randrange(N_ROWS)] if t % 2 == 0 else rng.randrange(1 << 32)
        inp = []
        for k in keys:
            inp += [(k >> b) & 1 for b in range(KEY_BITS)]
        inp += [(probe >> b) & 1 for b in range(KEY_BITS)]
        v = TC.ripple(cir, inp)
        got_hit = v[0]
        got_idx = sum((v[1 + j] & 1) << j for j in range(IDX_BITS))
        exp_hit, exp_idx, exp_m = ref(keys, probe)
        both[exp_hit] += 1
        if got_hit != exp_hit:
            return False, "hit t=%d" % t, both
        if exp_hit and got_idx != exp_idx:
            return False, "idx t=%d got %d want %d" % (t, got_idx, exp_idx), both
        for r in range(N_ROWS):
            if (v[1 + IDX_BITS + r] & 1) != exp_m[r]:
                return False, "match row %d t=%d" % (r, t), both
    return True, None, both


def mutant(c, outs):
    ga, gb = list(c.ga), list(c.gb)
    victim = outs[0] - (2 + c.n_in)
    gb[victim] = ga[victim]
    cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": ga, "gb": gb, "outs": outs}
    rng = random.Random(5)
    for _ in range(40):
        keys = [rng.randrange(1 << 32) for _ in range(N_ROWS)]
        probe = keys[rng.randrange(N_ROWS)] if rng.randrange(2) else rng.randrange(1 << 32)
        inp = []
        for k in keys:
            inp += [(k >> b) & 1 for b in range(KEY_BITS)]
        inp += [(probe >> b) & 1 for b in range(KEY_BITS)]
        v = TC.ripple(cir, inp)
        eh, ei, em = ref(keys, probe)
        if v[0] != eh:
            return True
    return False


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


def to_physical(c, outs, base, key_addrs):
    """Table key bits are read from ABSOLUTE container addresses — the circuit addresses the
    stored table directly. Only the 32 probe bits live in our own wire region, because the
    probe is the one thing the host is allowed to write."""
    ni, no, ng = c.n_in, len(outs), len(c.ga)
    nw = c.n_wire()
    depth = depth_of(c, outs)
    wire_start = 28 + no * 8
    gate_start = wire_start + nw
    total = gate_start + ng * GATE_STRIDE
    n_tbl = N_ROWS * KEY_BITS

    def wa(w):
        if 2 <= w < 2 + n_tbl:
            return key_addrs[w - 2]                  # READ the stored table, absolute
        return base + wire_start + w

    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, ng, nw, ni, no, depth)
    for i, o in enumerate(outs):
        struct.pack_into("<Q", blob, 28 + i * 8, base + wire_start + o)
    blob[wire_start] = 0
    blob[wire_start + 1] = 1
    off = gate_start
    for k in range(ng):
        struct.pack_into("<BQQQ", blob, off, 0, wa(c.ga[k]), wa(c.gb[k]),
                         base + wire_start + 2 + ni + k)
        off += GATE_STRIDE
    probe_addrs = [base + wire_start + 2 + n_tbl + b for b in range(KEY_BITS)]
    out_addrs = [base + wire_start + o for o in outs]
    return bytes(blob), total, depth, probe_addrs, out_addrs


def main():
    t0 = time.time()
    print("=" * 86)
    print("  %s — every row compared in ONE settle. No host loop, because none should exist."
          % NAME)
    print("=" * 86)

    # ---- the keys, seeded at FABRICATION time (offline, RULE ZERO)
    T, known, impl, goal = __import__("muhl_fab_proof_tables").seed()
    keys = [k for (k, cost, rule, src) in known][:N_ROWS]
    while len(keys) < N_ROWS:
        keys.append(0xFFFFFFFF)                       # pad slots never match a real key
    print("  table: %d keys, stored BITWISE (one byte per bit) so gates address it directly"
          % N_ROWS)

    c, outs = build()
    print("  circuit: %d gates, %d in (%d table bits + %d probe), %d out, DEPTH %d ticks"
          % (len(c.ga), c.n_in, N_ROWS * KEY_BITS, KEY_BITS, len(outs), depth_of(c, outs)))

    ok, why, both = verify(c, outs)
    print("  [1] byte-exact vs reference over 400 probes: %s" % ("PASS" if ok else "FAIL " + why))
    print("      miss cases %d, hit cases %d (both branches exercised)" % (both[0], both[1]))
    if not ok or both[0] == 0 or both[1] == 0:
        print("      storing nothing."); return 1
    print("  [2] mutant on the hit output caught: %s" % mutant(c, outs))
    if not mutant(c, outs):
        print("      a check that cannot fail has measured nothing — storing nothing."); return 1

    if DRY:
        print("\n  --dry: verified, nothing stored.  [%.1fs]" % (time.time() - t0))
        return 0

    # ---- store the BITWISE key table
    tbl = bytearray(TBL_MAGIC + struct.pack("<II", N_ROWS, KEY_BITS))
    for k in keys:
        for b in range(KEY_BITS):
            tbl.append((k >> b) & 1)
    taken = []
    tbl_off = alloc(len(tbl), taken)
    jwrite(tbl_off, bytes(tbl), "table")
    taken.append((tbl_off, len(tbl)))
    payload = tbl_off + 16
    key_addrs = [payload + r * KEY_BITS + b for r in range(N_ROWS) for b in range(KEY_BITS)]
    print("  [3] key table @ %d (%d B), payload @ %d" % (tbl_off, len(tbl), payload))

    base = alloc(0, taken)
    blob, total, depth, probe_addrs, out_addrs = to_physical(c, outs, base, key_addrs)
    base = alloc(total, taken)
    blob, total, depth, probe_addrs, out_addrs = to_physical(c, outs, base, key_addrs)
    jwrite(base, blob, "circuit")
    print("  [4] circuit @ %d (%d B), DEPTH %d ticks" % (base, total, depth))

    with open(TITAN, "rb") as f:
        f.seek(base)
        if f.read(total) != blob:
            print("  READ-BACK MISMATCH — reverting."); revert(); return 1
    print("  [5] read-back byte-exact")

    reg = json.load(open(REG))
    reg[NAME] = {
        "name": NAME, "offset": base, "len": total, "format": "physical",
        "magic": MAGIC.decode(), "gate_stride": GATE_STRIDE,
        "n_gate": len(c.ga), "n_in": c.n_in, "n_out": len(outs), "depth": depth,
        "n_rows": N_ROWS, "key_bits": KEY_BITS,
        "key_table": {"offset": tbl_off, "len": len(tbl), "magic": TBL_MAGIC.decode(),
                      "payload_offset": payload, "bitwise": True,
                      "note": "one byte per bit — the format his gates address"},
        "probe_addrs": probe_addrs,
        "hit_addr": out_addrs[0],
        "index_addrs": out_addrs[1:1 + IDX_BITS],
        "match_vector_addrs": [out_addrs[1 + IDX_BITS], out_addrs[-1]],
        "host_role": "write the 32 probe bits, fire the receiver, read hit/index. "
                     "It runs no loop, unpacks nothing, and compares nothing.",
        "why": "his MMU's fast tier wires every candidate cell in as inputs and selects "
               "combinationally; this applies that to a key table, so all %d rows settle "
               "at once instead of a host walking a window" % N_ROWS,
        "verified_by": "byte-exact vs reference over 400 probes with both hit and miss "
                       "branches exercised, per-row match vector checked, mutant on the hit "
                       "output caught, read-back byte-exact",
        "new_matter": "post-2026-08-04; follow-on provisional",
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "units": "n_gate=GATES depth=TICKS len=BYTES", "genome": GENOME,
    }
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f:
        print("  [6] titan.gguf GGUF-valid: %s" % (f.read(4) == b"GGUF"))
    print("\n  FABRICATED. %d rows, one settle, DEPTH %d ticks." % (N_ROWS, depth))
    print("  Host writes 32 probe bits and reads an answer. It does not scan.")
    print("  [%.1fs]" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
