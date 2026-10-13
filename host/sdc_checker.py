#!/usr/bin/env python3
"""host/sdc_checker.py — the CHECKER: wakes inside the job window and submits, never stale (owner 07-17).

Reads the fold's win-latches — read-only, never touching an SDC's compute — across the dense-tier fold files AND every
federated model node, and submits inside the job window: a real block if any latch fired (a hash below target), else a
live verdict on group 0 (proves the plumbing end-to-end, non-stale). Timing may be Python; the SDC is circuit-baker only.

  python host/sdc_checker.py [window_seconds]     # default 20s after the button fired (inside a solo job's life)
"""
import json, mmap, socket, struct, sys, time
JOB = "C:/llm/sdc_out/big_job.json"; REG = "C:/llm/models/titan_circuits.json"; TITAN = "C:/llm/models/titan.gguf"
FOLD_MAN = "C:/llm/sdc_fold/manifest.json"; FOLD_DIR = "C:/llm/sdc_fold"; FED = "C:/llm/sdc_fold/federation.json"
WINDOW = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0

job = json.load(open(JOB)); reg = json.load(open(REG)); en2sz = int(job["en2sz"]); n = int(job.get("n_route", 0))
tier = job.get("tier", "full"); win = None; grp0_nonce = 0
import os


def latch_at(path, off):                                        # read a 5-byte win-latch (status u8 + nonce u32) if fired
    with open(path, "rb") as f:
        f.seek(off); rec = f.read(5)
    return (struct.unpack_from("<I", rec, 1)[0]) if rec and rec[0] == 1 else None


if job.get("external") and tier in ("full", "delta"):           # explicit tiers: scan the routed groups' answer slots
    man = json.load(open(FOLD_MAN)); GBY = int(man["group_bytes"]); asf = 76 if tier == "full" else 8
    spans = []; acc = 0
    for fe in man["files"]:
        spans.append((acc, acc + fe["groups"], f"{FOLD_DIR}/{fe['name']}")); acc += fe["groups"]
    def loc(k):
        for lo, hi, path in spans:
            if lo <= k < hi: return path, (k - lo) * GBY
        return None, 0
    fh = {}
    for k in range(max(n, 1)):
        path, off = loc(k)
        if path not in fh: fh[path] = open(path, "rb")
        fh[path].seek(off + asf); rec = fh[path].read(5)
        if k == 0 and rec: grp0_nonce = struct.unpack_from("<I", rec, 1)[0]
        if rec and rec[0] == 1: win = ("disk", k, struct.unpack_from("<I", rec, 1)[0]); break
    for f in fh.values(): f.close()
elif job.get("external"):                                       # dense tiers: read each fold file's O(1) win-latch (last 5 bytes)
    man = json.load(open(FOLD_MAN))
    for fe in man["files"]:
        path = f"{FOLD_DIR}/{fe['name']}"; nz = latch_at(path, os.path.getsize(path) - 5)
        if nz is not None: win = ("disk", fe["name"], nz); break
else:                                                           # in-file fold (legacy)
    gb = reg["groups_block"]; base = int(gb["offset"]); GBY = int(gb["group_bytes"])
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    for k in range(max(n, 1)):
        a = base + k * GBY + 76
        if k == 0: grp0_nonce = struct.unpack_from("<I", mm, a + 1)[0]
        if mm[a] == 1: win = ("disk", k, struct.unpack_from("<I", mm, a + 1)[0]); break
    mm.close(); f.close()

if win is None and os.path.exists(FED):                          # scan every federated model node's win-latch
    fed = json.load(open(FED))
    for node in fed["nodes"]:
        loff = node["off"] + 8 + 4 + 8 + 32                     # magic+node_id+addr_bits(u64)+target_reg -> the 5-byte latch
        nz = latch_at(node["path"], loff)
        if nz is not None: win = ("node%d" % node["node_id"], os.path.basename(node["path"]), nz); break

elapsed = time.time() - float(job.get("fired", time.time())); delay = max(0.0, WINDOW - elapsed)
print(f"job {job['job_id']} (tier={tier}) fired {elapsed:.0f}s ago; submitting at +{WINDOW:.0f}s "
      f"(sleeping {delay:.0f}s inside the window)…", flush=True)
if delay > 0: time.sleep(delay)

if win is not None:
    src, key, nonce = win; en2 = "%0*x" % (2 * en2sz, key if isinstance(key, int) else 0); kind = f"BLOCK ({src} {key})"
else:
    en2 = "%0*x" % (2 * en2sz, 0); nonce = grp0_nonce; kind = "live verdict (group 0, no win)"

s = socket.create_connection((job["pool_host"], job["pool_port"]), timeout=20); buf = b""
def send(o): s.sendall((json.dumps(o) + "\n").encode())
send({"id": 1, "method": "mining.subscribe", "params": ["titan-checker/1.0"]})
send({"id": 2, "method": "mining.authorize", "params": [job["wallet"], "x"]}); time.sleep(1.0)
send({"id": 100, "method": "mining.submit", "params": [job["wallet"], job["job_id"], en2, job["ntime"], "%08x" % (nonce & 0xffffffff)]})
verdict = None; t = time.time() + 12
while time.time() < t:
    s.settimeout(1.0)
    try: buf += s.recv(8192)
    except Exception: continue
    while b"\n" in buf:
        ln, buf = buf.split(b"\n", 1)
        if ln.strip():
            try:
                m = json.loads(ln)
                if m.get("id") == 100: verdict = m
            except Exception: pass
    if verdict: break
s.close()
print(f"submitted {kind}: en2={en2} nonce={nonce} for job {job['job_id']} to {job['wallet']}", flush=True)
if verdict is None: print("Bitcoin's verdict: (no reply)")
elif verdict.get("result") is True: print("Bitcoin's verdict: *** ACCEPTED — BLOCK CREDITED ***" if win is not None else "*** ACCEPTED ***")
else: print(f"Bitcoin's verdict: {verdict.get('error')}")
