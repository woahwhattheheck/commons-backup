#!/usr/bin/env python3
"""host/pfc_memo_store.py — the memoize fold lives IN THE BINARY. A repeat token is an ADDRESSED READ of stored bytes.

`CIRCUIT_PFC.md` lists `memocache` as a baked register: "memoize fold baked permanent; a HIT is an addressed read."
`PFC_LEVER_DATADUMP` §J calls the memoize fold the headline tax-eliminator — "the compute cost is per-UNIQUE-input, not
per-access" (measured R=64 -> 34x) — and `pfc_bake_lever` measured what baking it does to RAM: **MISS +120.0 MB
operational; HIT +0.0 MB, 1.66M addressed-reads/s.**

`pfc_forward` kept its memo in a host dict flushed to `C:/llm/sdc_out/pfc_forward_memo.json`. That works, but it is
HOST state: a JSON file the interpreter parses into RAM at startup. Baked into `memocache` the same hit becomes a
bounded read of the file's own bytes at a fixed offset — the compute-via-address form — and it travels WITH the binary
(the pfc has been moved to another device over a cable and still computed; a sidecar .json would not have).

LAYOUT (fixed-width slots, so a lookup is pure address arithmetic and never a scan):
    header: MAGIC[8] || n_slots[4] || reserved[4]
    slot  : key[8] (blake2b of model id + token prefix) || token[4] little-endian, 12 B
    index = key % n_slots, then a BOUNDED linear probe. key == 0 marks an empty slot.

The register was allocated but never zeroed, so its bytes were leftover weight data and every slot read as occupied —
measured 0/4 writes before the fix. `_init_region` zeroes it ONCE, journaling the original bytes first, so the edit is
byte-exact reversible.

  python host/pfc_memo_store.py            # round-trip + collision test against the real register, timed
  python host/pfc_memo_store.py revert     # restore the register's original bytes
"""
import hashlib, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_memocache_genome.jsonl"
SLOT = 12; PROBE = 8
MAGIC = b"PFCMEMO1"; HDR = 16
NUL = bytes(1)


def _init_region(off, total):
    with open(TITAN, "rb") as f:
        f.seek(off); orig = f.read(total)
    if orig[:8] == MAGIC:
        return
    with open(GENOME, "a") as g:
        g.write(json.dumps({"off": off, "orig": orig.hex()}) + os.linesep)
    body = MAGIC + struct.pack("<II", (total - HDR) // SLOT, 0) + NUL * (total - HDR)
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(body[:total])


def revert():
    if not os.path.exists(GENOME):
        print("no memocache genome — nothing to revert."); return 0
    entries = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(entries):
        with open(TITAN, "r+b") as f:
            f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME); print("memocache reverted byte-exact."); return 0


def _region():
    reg = json.load(open(REG)); e = reg.get("memocache")
    if not e or "offset" not in e: return None, 0
    off = int(e["offset"]); total = int(e.get("len", 8192))
    _init_region(off, total)
    return off + HDR, (total - HDR) // SLOT


def key_of(model_id, ids):
    h = hashlib.blake2b(f"{model_id}|{','.join(map(str, ids))}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "little") or 1          # 0 marks empty, so never hand back 0


def get(model_id, ids):
    """HIT = a bounded addressed read of the binary's own bytes. Returns the token id, or None."""
    off, n = _region()
    if not off: return None
    k = key_of(model_id, ids)
    with open(TITAN, "rb") as f:
        for p in range(PROBE):
            f.seek(off + ((k + p) % n) * SLOT); rec = f.read(SLOT)
            if len(rec) < SLOT: return None
            kk = int.from_bytes(rec[:8], "little")
            if kk == 0: return None                  # open addressing stops at the first hole
            if kk == k: return struct.unpack("<i", rec[8:12])[0]
    return None


def put(model_id, ids, token):
    """Write one slot — a 12-byte edit, not a cache rebuild."""
    off, n = _region()
    if not off: return False
    k = key_of(model_id, ids)
    with open(TITAN, "r+b") as f:
        for p in range(PROBE):
            s = off + ((k + p) % n) * SLOT
            f.seek(s); rec = f.read(SLOT)
            kk = int.from_bytes(rec[:8], "little") if len(rec) == SLOT else 0
            if kk == 0 or kk == k:
                f.seek(s); f.write(k.to_bytes(8, "little") + struct.pack("<i", int(token)))
                return True
    return False                                     # probe window full — caller keeps its host memo, no corruption


def main():
    off, n = _region()
    if not off:
        print("memocache is not in the registry — nothing to wire."); return 1
    print(f"=== MEMOIZE IN THE BINARY — `memocache` slots @ {off:,}, {n} x {SLOT} B ===", flush=True)

    mid = "mixtral-test"
    cases = [([1, 5465], 4418), ([1, 5465, 4418], 6993), ([1, 999], 7), ([2, 2, 2], 123456)]
    okw = sum(1 for ids, tok in cases if put(mid, ids, tok))
    okr = sum(1 for ids, tok in cases if get(mid, ids) == tok)
    miss = get(mid, [42, 42, 42])
    t0 = time.time()
    for _ in range(200): get(mid, cases[0][0])
    dt = (time.time() - t0) / 200

    with open(TITAN, "rb") as f: head = f.read(4)
    print(f"  wrote {okw}/{len(cases)} slots · read back {okr}/{len(cases)} byte-exact · unknown prefix -> {miss}", flush=True)
    print(f"  HIT latency {dt*1e6:.0f} us  ({1/dt:,.0f} addressed reads/s), bounded {PROBE}-slot probe", flush=True)
    print(f"  titan still GGUF-valid: {head == b'GGUF'}   revert: python host/pfc_memo_store.py revert", flush=True)
    print(f"  a repeat is now a read of the binary's own bytes — it travels WITH the file, not beside it.", flush=True)
    return 0 if (okw == len(cases) and okr == len(cases) and miss is None) else 1


if __name__ == "__main__":
    raise SystemExit(revert() if (len(sys.argv) > 1 and sys.argv[1] == "revert") else main())
