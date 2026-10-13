#!/usr/bin/env python3
"""host/sdc_button.py — THE ONE-TIME BUTTON. The ONLY runtime Python allowed (owner 07-16).

Not a process — a button that dies. It gives the SDC its block info (writes the live header into the prebaked input
address) and routes power to the prebaked receiver address, then EXITS. No executor, no loop, no monitoring. The SDC
(fabricated once by sdc_fab.py) does everything else. Reading the answer later, from OUTSIDE the sandbox, is a separate act.
"""
import hashlib, json, mmap, os, socket, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
OUT = "C:/llm/sdc_out"; JOB = OUT + "/gen_job.json"
WALLET = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
POOL_HOST = os.environ.get("TITAN_POOL_HOST", "solo.ckpool.org"); POOL_PORT = int(os.environ.get("TITAN_POOL_PORT", "3333"))


def get_job():                                                   # route the live block DATA in (one pool handshake)
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15); buf = b""
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    def lines():
        nonlocal buf; out = []; s.settimeout(2)
        try: buf += s.recv(8192)
        except Exception: pass
        while b"\n" in buf:
            ln, buf2 = buf.split(b"\n", 1); buf = buf2
            if ln.strip():
                try: out.append(json.loads(ln))
                except Exception: pass
        return out
    send({"id": 1, "method": "mining.subscribe", "params": ["titan-button/1.0"]})
    en1 = None; en2sz = 8; job = None; t = time.time() + 15
    while time.time() < t and (en1 is None or job is None):
        for m in lines():
            if m.get("id") == 1 and m.get("result"):
                en1 = m["result"][1]; en2sz = m["result"][2]
                send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]})
            elif m.get("method") == "mining.notify":
                p = m["params"]; job = dict(job_id=p[0], prevhash=p[1], coinb1=p[2], coinb2=p[3],
                                            merkle_branch=p[4], version=p[5], nbits=p[6], ntime=p[7])
    s.close(); return en1, en2sz, job


def make_prefix(job, en1, en2):                                 # build the 76-byte header (19 words) = the SDC's block info
    cb = job["coinb1"] + en1 + en2 + job["coinb2"]
    m = hashlib.sha256(hashlib.sha256(bytes.fromhex(cb)).digest()).digest()
    for br in job["merkle_branch"]:
        m = hashlib.sha256(hashlib.sha256(m + bytes.fromhex(br)).digest()).digest()
    ph = bytes.fromhex(job["prevhash"]); prev = b"".join(ph[i:i+4][::-1] for i in range(0, 32, 4))
    return (struct.pack("<I", int(job["version"], 16)) + prev + m
            + struct.pack("<I", int(job["ntime"], 16)) + struct.pack("<I", int(job["nbits"], 16)))


reg = json.load(open(REG))
if "gen_input" not in reg or "receiver" not in reg:
    print("SDC not fabricated — run: python host/sdc_fab.py"); raise SystemExit(1)
input_off = int(reg["gen_input"]["offset"]); recv_off = int(reg["receiver"]["offset"])

en1, en2sz, job = get_job()
if not job:
    print("no block data (pool handshake failed)."); raise SystemExit(1)
en2 = "00" * en2sz
prefix = make_prefix(job, en1, en2)                             # the block info (76 bytes, big-endian words w0..w18)

with open(TITAN, "r+b") as f:
    f.seek(input_off); f.write(prefix)                          # GIVE THE SDC ITS BLOCK INFO (route data into the input address)
f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
_ = mm[recv_off]                                               # ROUTE POWER to the receiver address (one signal)
mm.close(); f.close()

os.makedirs(OUT, exist_ok=True)                                # leave the job facts OUTSIDE for a later wallet-submit
json.dump({"job_id": job["job_id"], "en2": en2, "ntime": job["ntime"], "wallet": WALLET,
           "pool_host": POOL_HOST, "pool_port": POOL_PORT, "answer_off": int(reg["gen_answer"]["offset"])}, open(JOB, "w"))
print(f"BUTTON: block {job['job_id']} routed into the SDC @ {input_off}; power routed to the receiver @ {recv_off}.", flush=True)
print("the SDC has its block and its power. the button is done. python exiting.", flush=True)
