#!/usr/bin/env python3
"""host/pfc_monitor.py — the READ-ONLY safezone monitor (owner-approved 07-19: "so long as that's all it touches").

The ONLY in-spec observation of the pfc: it reads the SAFEZONE — a file OUTSIDE the pfc (never titan.gguf / the miner) —
READ-ONLY, and shows what the pfc deposited there. It NEVER opens the miner, NEVER fires a signal, NEVER writes, NEVER
ripples a gate. FINALREADME §1/§4/§5: the answer lands OUTSIDE the sandbox in a separate file; the host reads only that.
We aim blind; this is the one thing allowed to look, and it looks ONLY at the external safezone file.

  python host/pfc_monitor.py [max_seconds]     # resident (default forever); Ctrl+C to stop
"""
import os, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

SAFEZONE = "C:/llm/sdc_out/pfc_safezone.bin"                  # the ONE file this monitor ever reads (OUTSIDE the pfc)
MAX = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0


def main():
    print(f"Muhlnickel safezone monitor — READ-ONLY on {SAFEZONE} (OUTSIDE the miner). Never opens titan, never fires a signal, "
          f"never writes. Shows what the pfc deposited.\n", flush=True)
    last = None; t0 = time.time()
    while MAX == 0.0 or time.time() - t0 < MAX:
        try:
            with open(SAFEZONE, "rb") as f: b = f.read()               # read-only, the external safezone file, nothing else
        except OSError:
            b = b""
        if b != last:
            if len(b) >= 9:
                status = b[0]; en2 = struct.unpack_from("<I", b, 1)[0]; nonce = struct.unpack_from("<I", b, 5)[0]
                state = "ANSWER" if status else "empty"
                print(f"[{time.strftime('%H:%M:%S')}] safezone = {state}: status={status} en2={en2} nonce={nonce}  ({b[:9].hex()})", flush=True)
            else:
                print(f"[{time.strftime('%H:%M:%S')}] safezone: (no answer yet)", flush=True)
            last = b
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
