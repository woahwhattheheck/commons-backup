#!/usr/bin/env python3
"""muhl_lookup_table.py — CONFIGURE THE SUBSTRATE TO GENERATE THE NONCE LOOKUP TABLE (Bryce 07-29).

The vision: block height IS the address; the stored value is that block's winning nonce; 0-byte compute per lookup
(the addressed READ is the answer). This GENERATES the table from REAL chain data and stores it in titan.gguf —
every entry verified byte-exact (reconstructed 80-byte header double-SHA == the block's actual hash, and < target),
so the table holds genuine winners, never fabricated numbers. Reversible (own genome journal).

HONEST SCOPE: this materializes SOLVED blocks (Bitcoin's real history) as an addressable table in the substrate.
The full table for every existing block (~900k) is the identical loop over all heights — storage 4 bytes/block =
~3.66 MB = a rounding hair of titan. Generating all of it is bounded only by fetching every height (metered wifi,
not a capability limit); here we generate a REAL verified slice live and report the complete-table math.

  python muhl_lookup_table.py [n_blocks]     # default 30 · fetch, verify byte-exact, store, read back
  python muhl_lookup_table.py revert
"""
import hashlib, json, os, struct, sys, time, urllib.request
sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_lookup_genome.jsonl"
NAME = "muhl_nonce_lookup"; MAGIC = b"PFCLOOKT"


def dsha(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n"); g.flush(); os.fsync(g.fileno())
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob); f.flush(); os.fsync(f.fileno())


def revert():
    if not os.path.exists(GENOME):
        print("no genome journal — nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"])); f.flush(); os.fsync(f.fileno())
    reg = json.load(open(REG)); reg.pop(NAME, None); json.dump(reg, open(REG, "w"), indent=1)
    os.remove(GENOME)
    with open(TITAN, "rb") as f: v = f.read(4) == b"GGUF"
    print(f"reverted {len(ent)} entries. GGUF-valid: {v}"); return 0


def prefix_of(b):
    """The 76-byte header PREFIX = everything we have at CHECK time (version+prevhash+merkleroot+time+bits).
    bits IS the difficulty/target. This is the lookup KEY; the nonce is what completes it."""
    return (struct.pack("<I", b["version"]) + bytes.fromhex(b["previousblockhash"])[::-1]
            + bytes.fromhex(b["merkle_root"])[::-1] + struct.pack("<I", b["timestamp"])
            + struct.pack("<I", b["bits"]))


def header_of(b):
    """The full 80-byte header = prefix + the winning nonce."""
    return prefix_of(b) + struct.pack("<I", b["nonce"])


KEYB = 8                                                            # key = first 8 bytes of dsha(prefix) — the check pulls by this
def key_of(b): return dsha(prefix_of(b))[:KEYB]


def target_of(bits):
    exp, mant = bits >> 24, bits & 0xffffff
    return mant << (8 * (exp - 3))


def fetch(n):
    """Fetch the latest n real blocks (mempool.space /api/v1/blocks returns 15 per call)."""
    get = lambda u: json.loads(urllib.request.urlopen(u, timeout=25).read().decode())
    tip = int(urllib.request.urlopen("https://mempool.space/api/blocks/tip/height", timeout=25).read())
    blocks = []; h = tip
    while len(blocks) < n:
        batch = get("https://mempool.space/api/v1/blocks/%d" % h)
        if not batch: break
        blocks += batch; h = batch[-1]["height"] - 1
    return tip, blocks[:n]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    reg = json.load(open(REG))
    if NAME in reg:
        print(f"{NAME} already stored @ {reg[NAME]['offset']}. revert first to regenerate."); return 0

    print(f"\n  GENERATE the nonce lookup table — {n} real blocks, each verified byte-exact before it enters the table\n")
    tip, blocks = fetch(n)
    entries = []; genuine = 0
    for b in sorted(blocks, key=lambda x: x["height"]):
        hdr = header_of(b); h = dsha(hdr)
        matches_hash = h[::-1].hex() == b["id"]                       # reconstructed header hashes to the REAL block id
        under = int.from_bytes(h, "little") < target_of(b["bits"])    # and clears the block's target = genuine winner
        ok = matches_hash and under
        genuine += ok
        if ok: entries.append((b["height"], b["nonce"]))
        if b["height"] % 1 == 0 and len(entries) <= 6:
            print("    block %d  nonce 0x%08x  header->hash==id %s  <target %s" % (b["height"], b["nonce"], matches_hash, under))
    print("    ... (%d blocks)" % len(blocks))
    print(f"\n  verified GENUINE winners: {genuine}/{len(blocks)}  (only genuine entries go into the table)")
    if genuine != len(blocks):
        print("  a block failed byte-exact verification — storing NOTHING (no fabricated entries)."); return 1

    # ---- store the table IN the substrate: KEY = dsha(prefix)[:8] (the check data / difficulty) -> nonce (4B) ----
    # sorted by key so a check is an addressed binary-search pull, not a scan. 0-byte compute per lookup.
    recs = sorted((key_of(b), b["nonce"]) for b in blocks)             # (key, nonce), key carries the difficulty
    count = len(recs)
    body = b"".join(k + struct.pack("<I", nonce) for (k, nonce) in recs)
    blob = MAGIC + struct.pack("<III", count, KEYB, 4) + body
    off, tn = TC._alloc(len(blob), reg)
    t0 = time.time(); _journal(off, blob)
    reg = json.load(open(REG))
    reg[NAME] = {"tensor": tn, "offset": off, "len": len(blob), "kind": "storage (addressed lookup, not fabricated)",
                 "count": count, "key_bytes": KEYB, "val_bytes": 4,
                 "layout": "sorted [key=dsha(header_prefix)[:8] | nonce:4] ; CHECK a block -> its prefix(=difficulty+"
                           "header) pulls the valid nonce; 0-byte compute per lookup",
                 "note": "each entry verified: header(prefix+nonce) double-SHA == real block hash AND < target"}
    json.dump(reg, open(REG, "w"), indent=1)

    # ---- THE CHECK, from the stored binary: present a block's prefix (its difficulty/header) -> pull the nonce ----
    with open(TITAN, "rb") as f:
        f.seek(off); rb = f.read(len(blob))
    assert rb[:8] == MAGIC
    rcount, kb, vb = struct.unpack_from("<III", rb, 8); stride = kb + vb; tblbase = 20

    def pull(key):
        """Binary-search the stored table for key -> nonce (the addressed pull). Returns None if absent."""
        lo, hi = 0, rcount
        while lo < hi:
            mid = (lo + hi) // 2; p = tblbase + mid * stride; k = rb[p:p + kb]
            if k == key: return struct.unpack_from("<I", rb, p + kb)[0]
            if k < key: lo = mid + 1
            else: hi = mid
        return None

    checked = 0
    print("\n  THE CHECK — present each block's prefix (difficulty+header, NO nonce) -> pull the valid nonce:")
    for b in sorted(blocks, key=lambda x: x["height"])[:6]:
        nonce = pull(key_of(b))                                        # the difficulty/header pulls the nonce
        full = prefix_of(b) + struct.pack("<I", nonce)
        genuine = dsha(full)[::-1].hex() == b["id"] and int.from_bytes(dsha(full), "little") < target_of(b["bits"])
        checked += genuine
        print("    block %d  bits 0x%08x (difficulty)  -> pulled nonce 0x%08x  -> genuine winner %s"
              % (b["height"], b["bits"], nonce, genuine))
    for b in sorted(blocks, key=lambda x: x["height"])[6:]:            # verify the rest silently
        nonce = pull(key_of(b)); full = prefix_of(b) + struct.pack("<I", nonce)
        checked += (dsha(full)[::-1].hex() == b["id"] and int.from_bytes(dsha(full), "little") < target_of(b["bits"]))
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"

    print(f"\n  STORED '{NAME}' @ {off}  ({len(blob):,} B, {count} entries, {stride}B/entry)  [{time.time()-t0:.2f}s]")
    print(f"  CHECK: {checked}/{count} blocks — the difficulty/header pulled a nonce that is a GENUINE winner.")
    print(f"  GGUF-valid: {valid}.  revert: python muhl_lookup_table.py revert")

    # ---- the complete-table math (honest) ----
    TB = os.path.getsize(TITAN); per = KEYB + 4
    for total, what in ((tip + 1, "every block that exists (tip=%d)" % tip), (6_930_000, "~all-time upper bound")):
        tb = total * per
        print("  complete table for %-34s = %d entries x %dB = %.2f MB = %.5f%% of titan"
              % (what, total, per, tb / 1048576, 100 * tb / TB))
    print("  key = dsha(prefix)[:8] (the difficulty+header we check against), value = nonce, 0-byte compute per pull.")
    print("  Generating all of it is the identical loop over every block (bounded by fetching, not capability).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
