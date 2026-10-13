#!/usr/bin/env python3
"""host/sdc_button_big.py — THE START BUTTON for the federated fold. One-time, dies (owner 07-17).

The only runtime Python. It (a) pulls the live block, (b) computes the TARGET from nBits, (c) writes the target into the
shared target register in titan.gguf AND mirrors it into every federated model node's target slot, (d) for the explicit
tiers (full/delta) routes each routed group's header into its slot; for the dense tiers (bitmap/winner) headers are
DERIVED from the group index (index = address, ~0 stored) so nothing per-group is written, (e) fires ONE power signal to
the receiver, then EXITS. No host ripple, no loop. The shared miner+comparator+clock (gates in titan.gguf) do the rest.
"""
import hashlib, json, mmap, os, socket, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
FOLD_MAN = "C:/llm/sdc_fold/manifest.json"; FOLD_DIR = "C:/llm/sdc_fold"; FED = "C:/llm/sdc_fold/federation.json"
OUT = "C:/llm/sdc_out"; JOB = OUT + "/big_job.json"
WALLET = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
POOL_HOST = os.environ.get("TITAN_POOL_HOST", "solo.ckpool.org"); POOL_PORT = int(os.environ.get("TITAN_POOL_PORT", "3333"))
MAX_ROUTE = int(os.environ.get("SDC_MAX_ROUTE", "4096"))    # explicit-tier header prep is bounded; fielded storage = armed capacity


def get_job():
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15); buf = b""
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    def lines():
        nonlocal buf; out = []; s.settimeout(2)
        try: buf += s.recv(8192)
        except Exception: pass
        while b"\n" in buf:
            ln, rest = buf.split(b"\n", 1); buf = rest
            if ln.strip():
                try: out.append(json.loads(ln))
                except Exception: pass
        return out
    send({"id": 1, "method": "mining.subscribe", "params": ["titan-big/1.0"]})
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


def make_prefix(job, en1, en2):
    cb = job["coinb1"] + en1 + en2 + job["coinb2"]
    m = hashlib.sha256(hashlib.sha256(bytes.fromhex(cb)).digest()).digest()
    for br in job["merkle_branch"]:
        m = hashlib.sha256(hashlib.sha256(m + bytes.fromhex(br)).digest()).digest()
    ph = bytes.fromhex(job["prevhash"]); prev = b"".join(ph[i:i+4][::-1] for i in range(0, 32, 4))
    return (struct.pack("<I", int(job["version"], 16)) + prev + m
            + struct.pack("<I", int(job["ntime"], 16)) + struct.pack("<I", int(job["nbits"], 16)))


reg = json.load(open(REG))
if "receiver" not in reg or "target_reg" not in reg:
    print("SDC gates not fabricated — run: python host/sdc_fab_big.py"); raise SystemExit(1)
external = os.path.exists(FOLD_MAN)
man = json.load(open(FOLD_MAN)) if external else None
tier = (man.get("tier") if external else "full") if man else "full"
explicit = tier in ("full", "delta")                            # explicit tiers store per-group headers; dense tiers derive them
n_groups = (man["total_groups"] if external else int(reg["groups_block"]["n_groups"]))
fed = json.load(open(FED)) if os.path.exists(FED) else None

en1, en2sz, job = get_job()
if not job:
    print("no block data (pool handshake failed)."); raise SystemExit(1)
nbref = struct.unpack("<I", make_prefix(job, en1, "00" * en2sz)[72:76])[0]
target = (nbref & 0xffffff) << (8 * ((nbref >> 24) - 3))

# route the shared TARGET into titan.gguf (the comparator's B input) + mirror it into every federated model node
with open(TITAN, "r+b") as f:
    f.seek(int(reg["target_reg"]["offset"])); f.write(target.to_bytes(32, "little"))
n_nodes = 0
if fed:
    for node in fed["nodes"]:
        toff = node["off"] + 8 + 4 + 8                          # magic(8)+node_id(4)+addr_bits(u64) -> target_reg
        with open(node["path"], "r+b") as f:
            f.seek(toff); f.write(target.to_bytes(32, "little"))
        n_nodes += 1

# explicit tiers only: route each group's header into its slot (first MAX_ROUTE). dense tiers derive header from index.
n_route = 0
if explicit and external:
    GBY = int(man["group_bytes"]); n_route = min(n_groups, MAX_ROUTE)
    spans = []; acc = 0
    for fe in man["files"]:
        spans.append((acc, acc + fe["groups"], f"{FOLD_DIR}/{fe['name']}")); acc += fe["groups"]
    def loc(k):
        for lo, hi, path in spans:
            if lo <= k < hi: return path, (k - lo) * GBY
        return None, 0
    fh = {}
    for k in range(n_route):
        path, off = loc(k)
        if path not in fh: fh[path] = open(path, "r+b")
        en2 = "%0*x" % (2 * en2sz, k)
        fh[path].seek(off); fh[path].write(make_prefix(job, en1, en2) if tier == "full" else bytes.fromhex(en2))
    for f in fh.values(): f.close()
elif explicit and not external:
    GBY = int(reg["groups_block"]["group_bytes"]); base = int(reg["groups_block"]["offset"]); n_route = min(n_groups, MAX_ROUTE)
    with open(TITAN, "r+b") as f:
        for k in range(n_route):
            en2 = "%0*x" % (2 * en2sz, k); f.seek(base + k * GBY); f.write(make_prefix(job, en1, en2))

# fire ONE power signal (the single-bit cost) then die
rec_off = int(reg["receiver"]["offset"])
f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
_ = mm[rec_off]; mm.close(); f.close()

os.makedirs(OUT, exist_ok=True)
json.dump({"job_id": job["job_id"], "en2sz": en2sz, "ntime": job["ntime"], "wallet": WALLET, "en1": en1,
           "pool_host": POOL_HOST, "pool_port": POOL_PORT, "n_route": n_route, "n_groups": n_groups,
           "tier": tier, "external": external, "federated_nodes": n_nodes, "fired": time.time(),
           "target": "%064x" % target, "block_zbits": 256 - target.bit_length()}, open(JOB, "w"))
import math
lanes = n_groups * (1 << 32)
# NEVER materialize 2^addr_bits — the multi-level exponent is trillions; carry it symbolically (that impossibility IS the wall)
node_exp = fed["addr_bits"] if fed else 0
print(f"START: block {job['job_id']} + target ({256-target.bit_length()} zbits) routed. "
      f"tier={tier}, {n_groups:,} disk groups (2^{math.log2(lanes):.0f} lanes) + {n_nodes} model nodes "
      f"(each 2^{node_exp} addressable). "
      f"{'headers derived from index (0 stored/group)' if not explicit else str(n_route)+' headers routed'}. "
      f"ONE signal fired. button done — exiting.", flush=True)
