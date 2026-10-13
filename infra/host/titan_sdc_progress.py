#!/usr/bin/env python3
"""host/titan_sdc_progress.py — MANUAL progress SNAPSHOT of the armed SDC. One command, one read, then it ENDS.

Owner spec (07-15): like the read-out reader, but for PROGRESS only — a snapshot you run on command to see where the SDC
is at, that ends immediately. It is NOT continuous, NOT automated, has no loop and no polling, and it NEVER runs, touches,
or evaluates the SDC (advancing the sweep is the SDC's job, on power). It read-only mmaps the SDC's known register
location (~0 RAM), reports the loaded block + how long it has been armed + whether its answer bit has flipped, and EXITS.

  python host/titan_sdc_progress.py     # snapshot where the SDC is at, once, then done.
"""
import json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_sdc as T

ARMED = "C:/llm/models/titan_sdc_armed.json"


def hms(sec):
    sec = int(sec); return f"{sec//3600:d}h {sec%3600//60:02d}m {sec%60:02d}s"


if not os.path.exists(ARMED):
    print("no armed SDC (run titan_sdc_inject.py first — nothing to snapshot)."); raise SystemExit(1)
a = json.load(open(ARMED))
ro = int(a["result_off"])

# --- read-only snapshot of the SDC's answer register (the SDC is not run or touched) ---
f = open(T.TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
reg = bytes(mm[ro:ro + 5]); mm.close(); f.close()
status = reg[0]; nonce = struct.unpack("<I", reg[1:5])[0] if len(reg) >= 5 else 0

elapsed = time.time() - os.path.getmtime(ARMED)
share_z = (256 - int(a["share_target"], 16).bit_length()) if a.get("share_target") else "?"

print("=== SDC PROGRESS SNAPSHOT ===", flush=True)
print(f"  block loaded : {a['job_id']}", flush=True)
print(f"  miner        : {a.get('gates', '?'):,} logic gates in {a['tensor']} @ {a['off']}", flush=True)
print(f"  targets      : share needs {share_z} zero-bits, block needs {a.get('block_zbits', '?')}", flush=True)
print(f"  armed        : {hms(elapsed)} ago, computing on power (0 host processes, 0 RAM)", flush=True)
print(f"  answer reg   @ {ro}: status={status}", flush=True)
if status == 1:
    print(f"  >>> SOLVED — the SDC holds nonce {nonce}. run titan_sdc_check.py to submit it to the wallet.", flush=True)
else:
    print("  state        : still solving — the answer bit has not flipped. (0 = unsolved)", flush=True)
print("snapshot complete — done.", flush=True)
