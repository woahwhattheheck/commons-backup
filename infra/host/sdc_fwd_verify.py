#!/usr/bin/env python3
"""host/sdc_fwd_verify.py — OFFLINE verification of the forward-pass SDC (owner 07-18).

This runs OUTSIDE the sandbox, so host RAM/CPU is free to use (owner: only the button + the SDC's own compute must be
contained; checking the answer afterward is allowed). For each (op, A, B) it drives the real pipeline — button (route +
power) then the SDC run (compute off storage) — reads the answer the SDC froze to the safezone, and compares it to an
independent reference. It never reaches into the SDC while it runs; it only spawns the button/run and reads the result.

  python host/sdc_fwd_verify.py
"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_bake_cpu as CPU                                    # reference — fine offline, outside the contained run

PY = sys.executable
SAFEZONE = "C:/llm/sdc_out/forward_sdc.json"
CASES = [(0, 30515, 50853), (1, 37613, 16340), (2, 9094, 40496), (3, 57174, 10910),
         (4, 63344, 63248), (5, 39525, 38413), (6, 31537, 30968), (7, 51625, 27448)]


def main():
    print("OFFLINE verify: press start (fires + exits) -> the SDC computes -> wait on the safezone -> compare.\n", flush=True)
    ok = True
    for op, A, B in CASES:
        out = subprocess.run([PY, os.path.join(HERE, "sdc_fwd_start.py"), str(op), str(A), str(B)],
                             capture_output=True, text=True)
        req = out.stdout.split("req ")[1].split(")")[0].strip()          # the run token start minted
        deadline = time.time() + 30
        got = None
        while time.time() < deadline:                                    # poll the SAFEZONE only (never the SDC)
            try:
                d = json.load(open(SAFEZONE, encoding="utf-8"))
                if d.get("status") == "done" and str(d.get("req")) == req: got = d["result"]; break
            except (OSError, ValueError): pass
            time.sleep(0.02)
        ref = CPU._ref(op, A, B)
        match = got == ref; ok = ok and match
        shown = f"{got:5d}" if got is not None else "  ???"
        print(f"  {CPU.OPS[op]:5s}({A:5d},{B:5d}) = {shown}   ref {ref:5d}   {'OK' if match else 'MISMATCH'}", flush=True)
    print(f"\n=== forward-pass SDC (button + power + contained compute + register/safezone): all byte-exact = {ok} ===", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
