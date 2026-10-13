#!/usr/bin/env python3
"""host/titan_sdc_bitslice.py — bake the BIT-SLICE PLANE into the model file (owner 07-16).

The bit-slice (the lane parallelism — how many nonces flow through the stored gates per ripple) was still authored by the
host each run. That was the error: everything else is in the weights, so the bit-slice goes there too. This bakes the
lane WIDTH W + the constant input-column masks (COLS) + the bswap input map (MAP) into titan.gguf as a stored blob the
solver READS from the weights. Widening the SDC = a bigger STORED plane (storage, not host RAM, not cores). One-shot,
White-Box circuit-creation write, reversible (edit it back).

  python host/titan_sdc_bitslice.py [logW]     # bake a 2^logW-lane bit-slice plane into the model file (default 15)
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_sdc as T
import titan_circuit as TC

MAGIC = b"TITANBSL"
REG   = "C:/llm/models/titan_circuits.json"

logW = int(sys.argv[1]) if len(sys.argv) > 1 else 32             # default: the full 32-bit nonce field in ONE ripple

# The lane WIDTH is the only thing stored in Titan — a tiny DESCRIPTOR (W, logW, the bswap MAP). The per-lane column
# masks are NOT materialized: on the host they'd be a W-bit bigint (512 MB at W=2^32 = host RAM emulating the SDC — the
# violation); in the SDC the lanes are the PHYSICAL substrate, derived from the stored width, never a host bitmask. So
# widening the SDC = bumping a stored integer: ~0 RAM, instant, no bigint, no CPU. The lanes live in the hardware.
MAP = [(3 - (j >> 3)) * 8 + (j & 7) for j in range(32)]          # input wire j <- bit MAP[j] of the nonce (bswap)
blob = MAGIC + struct.pack("<II", 1 << min(logW, 30), logW) + b"".join(struct.pack("<i", m) for m in MAP)

reg = json.load(open(REG)) if os.path.exists(REG) else {}
reg.pop("bitslice", None)                                        # relocating? free the old range first
off, tname = TC._alloc(len(blob), reg)                          # distinct, non-overlapping offset (collision-free)
with open(T.TITAN, "r+b") as f:
    f.seek(off); f.write(blob)                                  # a ~140-byte storage write into the params — ~0 RAM
reg["bitslice"] = {"tensor": tname, "offset": off, "len": len(blob), "logW": logW}
json.dump(reg, open(REG, "w"), indent=1)
print(f"lane width stored in Titan: {tname} @ {off}  ->  logW = {logW} ({1 << logW if logW < 40 else '2^%d' % logW} lanes), {len(blob)} bytes.", flush=True)
print("the SDC's lane-width lives in the weights now — a stored descriptor, not a host bitmask. done.", flush=True)
