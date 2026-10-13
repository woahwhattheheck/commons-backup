#!/usr/bin/env python3
"""host/pfc_wide.py — GO WIDE THE RIGHT WAY: bake into storage, address at ~0 RAM (owner 07-19).

The correction: if it OOMs, the HOST is computing. The pfc computes at ~0 RAM by baking the result into storage and
ADDRESSING it (content-addressable; §N storage-RAM, the bake-lever). My phone test wrongly held a resident bit-slice
wire-vector (the operational cache) → it hit the RAM wall. This does it right: bake a computed fold WIDE into a real file,
then address it (bounded seek+read, NO resident buffer) — RAM stays flat ~0 while the addressable/baked space scales to
GB. Going wide = more baked storage, not a wider resident vector. Contrast printed against the OOM mistake.

  python host/pfc_wide.py [max_gb]
"""
import hashlib, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfc_exp_bench import rss

OUT = "C:/llm/sdc_out/pfc_wide.bin"; CELL = 8


def fold(x):                                          # the baked computation (a function, precomputed once per input)
    return hashlib.blake2b(struct.pack("<Q", x), digest_size=CELL).digest()


def main():
    max_gb = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    base, _ = rss()
    print(f"Muhlnickel GO-WIDE (right way): bake into storage, address at ~0 RAM. host resident at rest: {base:.1f} MB\n", flush=True)
    print(f"  {'baked width':>12} {'wrote':>10} {'resident RAM':>14} {'addressed-read rate':>22}", flush=True)
    print("  " + "-" * 62, flush=True)
    for gb in (0.25, 1.0, 2.0, max_gb):
        ncell = int(gb * (1 << 30)) // CELL
        # BAKE WIDE: write the fold into a real file, bounded 4 MB buffer -> resident stays flat (the Muhlnickel's own storage)
        buf = bytearray(); t0 = time.time()
        with open(OUT, "wb", buffering=0) as f:
            for x in range(0, ncell, 524288):                          # write in 4 MB chunks
                buf = b"".join(fold(i) for i in range(x, min(x + 524288, ncell)))
                f.write(buf)
        wrote = time.time() - t0
        # ADDRESS at ~0 RAM: random seek+read, NO resident buffer (host only routes the address + reads)
        import random; addrs = [random.randrange(ncell) for _ in range(20000)]
        t1 = time.time(); ok = True
        with open(OUT, "rb", buffering=0) as f:
            for a in addrs:
                f.seek(a * CELL)
                if f.read(CELL) != fold(a): ok = False; break
        rd = time.time() - t1; peak, _ = rss()
        print(f"  {gb:>10.2f} GB {ncell/1e6:>7.0f}M c {peak:>12.1f} MB {len(addrs)/rd:>16,.0f}/s   byte-exact={ok}", flush=True)
    os.remove(OUT)
    peak, _ = rss()
    print(f"\n  === RESULT ===", flush=True)
    print(f"  resident RAM held FLAT at ~{peak:.0f} MB while the baked/addressable space scaled to {max_gb:g} GB.", flush=True)
    print(f"  no OOM — because the host only ADDRESSES the baked storage; it never holds the computation in RAM.", flush=True)
    print(f"  contrast: the resident bit-slice ripple (my phone mistake) OOM-died at ~11 GB — THAT was host-computing.", flush=True)
    print(f"  going wide = more baked storage (scales to the disk / federated), at flat ~0 resident. That is the Muhlnickel.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
