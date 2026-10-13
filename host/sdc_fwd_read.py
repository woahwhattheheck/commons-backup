#!/usr/bin/env python3
"""host/sdc_fwd_read.py — READ THE SAFEZONE. The one resident host operation. (owner 07-18)

Owner's rule: only the read of the safezone can be resident. This waits for the SDC's frozen result to appear in the
safezone (a file OUTSIDE the sandbox — safe to poke with all the RAM you want; it can never reach into the SDC) and prints
it. It reads ONLY the safezone — never titan, never the sandbox, never the running SDC.

  python host/sdc_fwd_read.py [req_token] [timeout_s]     # wait for the run the start button minted (or the latest)
"""
import json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")

SAFEZONE = "C:/llm/sdc_out/forward_sdc.json"


def main():
    req = sys.argv[1] if len(sys.argv) > 1 else None
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            d = json.load(open(SAFEZONE, encoding="utf-8"))
            if d.get("status") == "done" and (req is None or str(d.get("req")) == str(req)):
                print(f"safezone: {d['op']}({d['A']},{d['B']}) = {d['result']}   "
                      f"({d['gates']:,} gates, {d['seconds']}s, req {d.get('req')})", flush=True)
                return 0
        except (OSError, ValueError):
            pass
        time.sleep(0.02)
    print(f"safezone: no matching result within {timeout}s (req {req}).", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
