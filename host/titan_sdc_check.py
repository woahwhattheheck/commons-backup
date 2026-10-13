#!/usr/bin/env python3
"""host/titan_sdc_check.py — the READ-OUT half: read the static SDC's answer + check it against the wallet. MANUAL ONLY.

Owner spec (07-15): the ONLY other permitted Python touch besides the one-time send-in. This runs ONLY when you run it —
no loop, no polling, no automation, no background. It reads the answer register the STATIC SDC holds (read-only mmap of
its known location in titan.gguf's params — ~0 RAM, no compute, the SDC is not touched or run), and if the SDC holds a
winning nonce it opens ONE pool connection and submits it to the live wallet, prints the verdict, and EXITS.

  python host/titan_sdc_check.py        # read the SDC's answer + submit/check it against the wallet, once, then done.

Answer register layout at result_off (5 bytes): [status:1][nonce:4 LE].  status 1 = the SDC holds a solved nonce.
"""
import json, mmap, os, socket, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_sdc as T

ARMED = "C:/llm/models/titan_sdc_armed.json"

if not os.path.exists(ARMED):
    print("no armed SDC (run titan_sdc_inject.py first — nothing to read)."); raise SystemExit(1)
a = json.load(open(ARMED))
ro = int(a["result_off"])

# --- READ the answer the static SDC holds (read-only, ~0 RAM; the SDC is not run or touched) ---
f = open(T.TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
reg = bytes(mm[ro:ro + 5]); mm.close(); f.close()
status = reg[0]; nonce = struct.unpack("<I", reg[1:5])[0] if len(reg) >= 5 else 0
print(f"SDC answer register @ {ro}: status={status} nonce={nonce}  (block {a['job_id']})", flush=True)

if status != 1:
    print("the static SDC holds no solved nonce yet (register 0). nothing to submit — done."); raise SystemExit(0)

# --- CHECK it against the live wallet: ONE connection, submit, verdict, close (no loop) ---
s = socket.create_connection((T.POOL_HOST, T.POOL_PORT), timeout=20); buf = b""
def send(o): s.sendall((json.dumps(o) + "\n").encode())
send({"id": 1, "method": "mining.subscribe", "params": ["titan-sdc-check/1.0"]})
send({"id": 2, "method": "mining.authorize", "params": [T.WALLET, "x"]})
time.sleep(1.0)
send({"id": 100, "method": "mining.submit",
      "params": [T.WALLET, a["job_id"], a["en2"], a["ntime"], "%08x" % (nonce & 0xffffffff)]})
verdict = None; t = time.time() + 8
while time.time() < t:
    s.settimeout(1.0)
    try: buf += s.recv(8192)
    except Exception: continue
    while b"\n" in buf:
        ln, buf = buf.split(b"\n", 1)
        if not ln.strip(): continue
        try: m = json.loads(ln)
        except Exception: continue
        if m.get("id") == 100: verdict = m
    if verdict: break
s.close()

if verdict is None:
    print(f"submitted nonce {nonce} to {T.WALLET}: no verdict (pool silent).")
elif verdict.get("result") is True:
    print(f"*** ACCEPTED *** nonce {nonce} credited to {T.WALLET}.")
else:
    print(f"submitted nonce {nonce}: {verdict.get('error')}  (plumbing OK if this is 'Above target'/'Stale').")
print("read-out complete — done.", flush=True)
