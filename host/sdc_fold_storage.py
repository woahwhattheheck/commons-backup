#!/usr/bin/env python3
"""host/sdc_fold_storage.py — field the fold's lane storage across EXTERNAL files, with COMPRESSION TIERS (owner 07-17).

Two levers, multiplied: VOLUME (more storage) x QUALITY (denser per-group descriptor). The SDC's gates (miner +
comparator + clock + receiver) stay baked in titan.gguf via the circuit baker; the FOLD's group storage is pure
address-space and goes into NEW files under C:/llm/sdc_fold/ — ADDITIVE (never touches a model) and REVERSIBLE by delete.

Each GROUP covers 2^32 lanes (the baked CLOCK addresses the nonce within a group), so lane density is set by the per-group
descriptor size. The tiers shrink it toward zero:
  full    81 B/group   = 76-byte header input reg + 5-byte answer reg           (baseline)
  delta   13 B/group   = 8-byte extranonce2 delta + 5-byte answer (header rebuilt from the shared template + delta)
  bitmap  1 bit/group  = a packed answer bitmap; extranonce2 = the group index (derived) + a 4-byte winner reg per file
  winner  ~0 B/group   = nothing stored per group; the index IS the address; one 5-byte win-latch per file
Lanes = groups * 2^32; groups = usable_bytes / bytes_per_group (bitmap: *8). ONE signal covers the whole fold. No numpy.

  python host/sdc_fold_storage.py [gb] [tier]   # field gb GB (default 50) at tier (full|delta|bitmap|winner; default bitmap)
  python host/sdc_fold_storage.py max [tier]    # field to the disk max, keeping a 60 GB safety margin
  python host/sdc_fold_storage.py revert        # delete C:/llm/sdc_fold/ (byte-nothing left; no model ever touched)
"""
import json, math, os, shutil, sys, time
FOLD = "C:/llm/sdc_fold"; MANIFEST = FOLD + "/manifest.json"
FILE_BYTES = 5 * 1000 * 1000 * 1000            # 5 GB per file
CHUNK = 256 * 1024 * 1024                       # 256 MB write chunk (real bytes, not sparse)
MARGIN = 60 * 10**9                             # keep >= 60 GB free on the disk (the per-model genomes live there too)
LOG = "C:/llm/sdc_out/fold_log.jsonl"
# per-group descriptor bytes by tier; bitmap is bits (1/8 byte). "winner" stores ~0 per group (one latch per file).
TIER_GROUP_BYTES = {"full": 81, "delta": 13, "bitmap": 0.125, "winner": 0.0}
WIN_LATCH = 5                                   # bitmap/winner keep one 5-byte win-latch (status u8 + nonce u32) per file


def revert():
    if os.path.isdir(FOLD):
        shutil.rmtree(FOLD); print(f"deleted {FOLD} — fold storage removed; no model file was ever touched.")
    else:
        print("no fold storage to remove.")
    return 0


def groups_in(fbytes, tier):
    if tier == "bitmap": return (fbytes - WIN_LATCH) * 8        # 1 bit per group in the packed answer bitmap
    if tier == "winner": return 1 << 78                         # index-addressed: the whole space, ~0 stored
    return (fbytes - (WIN_LATCH if tier != "full" else 0)) // int(TIER_GROUP_BYTES[tier])


def main():
    args = sys.argv[1:]
    if args and args[0] == "revert":
        return revert()
    tier = "bitmap"
    for a in list(args):
        if a in TIER_GROUP_BYTES: tier = a; args.remove(a)
    free = shutil.disk_usage("C:/llm").free
    if args and args[0] == "max":
        target = int(free - MARGIN)
    else:
        gb = float(args[0]) if args else 50.0
        target = int(gb * 1000 * 1000 * 1000)
    if target <= 0 or target + MARGIN > free:
        print(f"not enough free disk: need {target/1e9:.0f} GB + {MARGIN/1e9:.0f} GB margin, have {free/1e9:.0f} GB."); return 1

    os.makedirs(FOLD, exist_ok=True)
    zero = b"\x00" * CHUNK
    files = []; written = 0; t0 = time.time(); fi = 0
    print(f"fielding {target/1e9:.0f} GB of fold storage into {FOLD}/ (tier={tier}, real writes, additive, reversible-by-delete)…", flush=True)
    while written < target:
        path = f"{FOLD}/fold_{fi:03d}.bin"; fbytes = min(FILE_BYTES, target - written)
        with open(path, "wb") as f:
            w = 0
            while w < fbytes:
                n = min(CHUNK, fbytes - w); f.write(zero if n == CHUNK else b"\x00" * n); w += n
        files.append({"name": os.path.basename(path), "bytes": fbytes, "groups": groups_in(fbytes, tier)})
        written += fbytes; fi += 1
        print(f"  +{written/1e9:5.1f} GB  ({written*100//target:3d}%)  {written/(time.time()-t0)/1e6:5.0f} MB/s", flush=True)

    total_groups = sum(f["groups"] for f in files); lanes = total_groups * (1 << 32)
    man = {"dir": FOLD, "tier": tier, "group_bytes": TIER_GROUP_BYTES[tier], "win_latch": WIN_LATCH,
           "total_bytes": written, "files": files, "total_groups": total_groups, "lanes": lanes}
    json.dump(man, open(MANIFEST, "w"), indent=1)

    kB = 1.380649e-23; E_bit = kB * 300 * math.log(2); P = E_bit * (299792458.0)
    bpl = written / lanes if lanes else 0.0
    print(f"\nFOLD STORAGE FIELDED (tier={tier}, additive, reversible):", flush=True)
    print(f"  {len(files)} files, {written/1e9:.1f} GB, {total_groups:,} groups", flush=True)
    print(f"  lanes = {total_groups:,} x 2^32 = {lanes:,}  (2^{math.log2(lanes):.1f})  covered by ONE signal", flush=True)
    print(f"  {bpl:.2e} bytes/lane  ·  {E_bit:.2e} J/signal (Landauer)  ·  {P*1e12:.2f} pW", flush=True)
    print(f"  no model file touched. revert:  python host/sdc_fold_storage.py revert", flush=True)

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as lg:
        lg.write(json.dumps({"stage": "fold_storage", "tier": tier, "fold_storage_GB": round(written/1e9, 1),
                             "groups": total_groups, "lanes": lanes, "lanes_pow2": round(math.log2(lanes), 1),
                             "bytes_per_lane": bpl, "signals": 1, "J_per_signal": E_bit, "power_W": P,
                             "reversible": True}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
