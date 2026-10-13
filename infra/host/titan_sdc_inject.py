#!/usr/bin/env python3
"""host/titan_sdc_inject.py — the ONLY permitted Python: ONE-TIME, ONE-DIRECTIONAL send of the block data INTO the SDC.

Owner spec (07-15): Python's single job is to send the block data one-directionally into the SDC, then finish. It does
NOT compute, ripple, loop, poll, or evaluate — the SDC (the file; it IS the hardware, in file form) does that on power.
This script takes ONE live job (the block data), folds it into the miner that is already built as logic gates in Titan's
params, writes it INTO the SDC in place (a one-directional storage write), records where the SDC will hold its answer,
and EXITS in seconds. Over. Nothing else.

After the SDC finishes, titan_sdc_check.py reads the answer bit from the recorded location and checks it against the
wallet. The two Python touches are the only ones the spec allows: send-in (here), read-out (there).
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_build_mine as B
import titan_sdc as T

ARMED = "C:/llm/models/titan_sdc_armed.json"

en1, en2sz, job, diff = B.get_job()                       # take ONE job = the block data (one-directional read from pool)
if not job:
    print("no block data (pool handshake failed)"); raise SystemExit(1)
en2_hex = "00" * en2sz
r = B.build_circuit(job, en1, en2_hex, diff)              # fold THIS block into the miner gate-net (verified byte-exact)
if not r.get("ok"):
    print("block data rejected by circuit verify (no cheating)"); raise SystemExit(1)
C, off, ro, tname = T.install_into_params()               # write it INTO the SDC params, in place, one-directional

meta = json.load(open(T.META)); prefix = bytes.fromhex(meta["prefix"])
nb = struct.unpack("<I", prefix[72:76])[0]; block_tgt = (nb & 0xffffff) << (8 * ((nb >> 24) - 3))
json.dump({"off": off, "result_off": ro, "tensor": tname, "gates": r.get("gates"),
           "job_id": job["job_id"], "en1": en1, "en2": en2_hex, "ntime": job["ntime"], "diff": diff,
           "share_target": meta.get("share_target"), "block_zbits": 256 - block_tgt.bit_length()},
          open(ARMED, "w"))
print(f"block {job['job_id']} sent into the SDC: {r['gates']:,} logic gates armed in {tname} @ {off}.", flush=True)
print(f"the SDC now holds the block; its answer bit is at {ro}. one-directional send complete — done.", flush=True)
