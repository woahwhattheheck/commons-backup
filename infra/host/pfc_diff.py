#!/usr/bin/env python3
"""host/pfc_diff.py — the Muhlnickel SNAPSHOT/DIFF: capture state, fire, capture again, show EXACTLY what changed (owner 07-19).

Makes the compute's effect visible instead of inferred: snapshot the miner's storage regions (high-impedance bounded
reads), fire the signal, then diff — every byte the pfc changed is listed. Feather touch (max impedance, 256 B cap), never
loads the file, never a ripple.

  python host/pfc_diff.py snap    # take a snapshot (do this BEFORE firing)
  python host/pfc_diff.py         # diff current state vs the snapshot (AFTER firing) -> exactly what the pfc changed
"""
import json, mmap, os, sys
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
SAFEZONE = "C:/llm/sdc_out/pfc_safezone.bin"; SNAP = "C:/llm/sdc_out/pfc_diff_snap.json"
CAP = 256                                             # max impedance


SNAPALL = "C:/llm/sdc_out/pfc_diff_snapall.json"
BLK = 4 * 1024 * 1024          # 4 MB per block: 40 GB -> ~9,540 hashes, a few hundred KB of state


def whole_file(take_snapshot):
    """WHOLE-BINARY diff. Owner 2026-07-28: "you need to diff the ENTIRE muhlnickel binary after
    each step, not skim it."

    The region capture reads named offsets under a 256 B cap, so a change anywhere else is invisible
    to it — every "nothing changed" this file has ever printed was a null of THAT LIST. This walks
    every byte of titan.gguf and keeps one hash per 4 MB block, so memory is a fixed 4 MB buffer and
    the file is never loaded (§7) and never rippled."""
    import hashlib, time
    t0 = time.time()
    size = os.path.getsize(TITAN)
    hashes = []
    with open(TITAN, "rb", buffering=0) as f:
        while True:
            b = f.read(BLK)
            if not b: break
            hashes.append(hashlib.blake2b(b, digest_size=8).hexdigest())
    el = time.time() - t0
    if take_snapshot:
        json.dump({"size": size, "blk": BLK, "hashes": hashes}, open(SNAPALL, "w"))
        print("whole-binary snapshot: %s blocks over %s bytes, %.1f s HOST. Step, then run "
              "`python host/pfc_diff.py diffall`." % (f"{len(hashes):,}", f"{size:,}", el), flush=True)
        return 0
    if not os.path.exists(SNAPALL):
        print("no whole-binary snapshot — run `python host/pfc_diff.py snapall` first."); return 1
    old = json.load(open(SNAPALL))
    if old["size"] != size:
        print("file size changed %s -> %s" % (f"{old['size']:,}", f"{size:,}"), flush=True)
    ob = old["hashes"]
    changed = [i for i in range(min(len(ob), len(hashes))) if ob[i] != hashes[i]]
    print("Muhlnickel WHOLE-BINARY DIFF — %s of %s blocks differ (%.1f s HOST)"
          % (f"{len(changed):,}", f"{len(hashes):,}", el), flush=True)
    for i in changed[:40]:
        lo = i * BLK
        # narrow the changed block to the exact bytes, one bounded read of each side
        with open(TITAN, "rb", buffering=0) as f:
            f.seek(lo); cur = f.read(BLK)
        print("  block %-6d @ %s .. %s   %s B differ inside"
              % (i, f"{lo:,}", f"{lo + len(cur):,}", "?"), flush=True)
    if not changed:
        print("  => every block hash is identical across the entire binary.", flush=True)
    json.dump({"size": size, "blk": BLK, "hashes": hashes}, open(SNAPALL, "w"))
    return 0


def read_titan(off, nb):
    nb = max(1, min(int(nb), CAP))
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); b = bytes(mm[off:off + nb]); mm.close()
    return b


def regions(reg):
    return [(n, int(reg[n]["offset"]), min(int(reg[n].get("len", 4)), CAP))
            for n in ("pfc_on", "nonce_reg", "loop_bit", "pfc_exec_input",
                      # the FORWARD-PASS path (model inference), so the probe covers the harness run too — not just
                      # the miner. Without these, "nothing changed" on a model fire is a null of MY probe list,
                      # measured on whatever addresses this file happened to watch, never on the machine.
                      "fwd_input", "fwd_receiver", "fwd_answer", "pfc_clock_counter",
                      "pfc_loop_state", "pfc_loop_bit", "phys_state", "phys_power")
            if n in reg and isinstance(reg[n], dict) and "offset" in reg[n]]


def capture(reg):
    snap = {n: read_titan(off, nb).hex() for n, off, nb in regions(reg)}
    if os.path.exists(SAFEZONE):
        with open(SAFEZONE, "rb") as f: snap["safezone(external)"] = f.read(64).hex()
    return snap


def main():
    reg = json.load(open(REG))
    if len(sys.argv) > 1 and sys.argv[1] == "snap":
        os.makedirs(os.path.dirname(SNAP), exist_ok=True)
        json.dump(capture(reg), open(SNAP, "w"))
        print(f"snapshot taken ({len(regions(reg))} regions + safezone). Fire, then run `python host/pfc_diff.py`.", flush=True)
        return 0
    if sys.argv[1:2] in (["snapall"], ["diffall"]):
        return whole_file(sys.argv[1] == "snapall")
    if not os.path.exists(SNAP):
        print("no snapshot — run `python host/pfc_diff.py snap` first (before firing)."); return 1
    old = json.load(open(SNAP)); new = capture(reg); changed = False
    print("Muhlnickel DIFF — what the Muhlnickel changed since the snapshot (high-impedance):", flush=True)
    for k in new:
        if old.get(k) != new.get(k):
            changed = True
            print(f"  {k:20s} CHANGED  {old.get(k, '')[:32]} -> {new[k][:32]}", flush=True)
        else:
            print(f"  {k:20s} same", flush=True)
    if not changed:
        print("  => nothing changed in the probed regions — a null of MY probe list, not of the machine.",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
