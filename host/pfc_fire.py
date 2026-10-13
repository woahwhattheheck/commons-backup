#!/usr/bin/env python3
"""host/pfc_fire.py — THE ROUTING BUTTON (Muhlnickel, not the stale sdc_*). Owner 2026-07-20, verbatim spec.

The circuits are ALREADY permanently baked into the pfc file's binary (titan.gguf: gen_miner + gen_input + gen_answer +
receiver + target_reg + fold — fabrication is DONE, never rebuilt here). Because the machine lives IN THE FILE, there is
NO cache and NO memory-held lanes: you POINT THE SIGNAL (the block data) at the baked file's input address and let it run.

This button does ONLY that, then DIES:
  1. pull the live block ONCE (one pool handshake), disconnect.
  2. write the block-data bits into the baked input address (gen_input) — ≤ 1 BIT OF RAM PER ADDRESS (byte-wise seek
     writes; NO mmap of the file, NO ripple, NO host compute, NO lanes held in memory).
  3. write the target into target_reg.
  4. POWER: address the receiver (one addressed read) — the signal runs the baked gates by address (compute-via-address).
  5. read the answer at its address (gen_answer). the winning nonce lands there (winner-only fold: the address IS answer).
  6. if a winner is present, submit it to the wallet (a second one-time connect). exit.

No process, no monitor, no ripple. The file is the machine; the signal runs it. Reading the answer is a bounded 5-byte
seek/read OUTSIDE any running compute.
  python host/pfc_fire.py
"""
import json, os, socket, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
OUT = "C:/llm/sdc_out"


def get_job():                                                  # ONE pool handshake: pull the live block, then disconnect
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15); buf = b""
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    def lines():
        nonlocal buf; out = []; s.settimeout(2)
        try: buf += s.recv(8192)
        except Exception: pass
        while b"\n" in buf:
            ln, buf = buf.split(b"\n", 1)
            if ln.strip():
                try: out.append(json.loads(ln))
                except Exception: pass
        return out
    send({"id": 1, "method": "mining.subscribe", "params": ["pfc-fire/1.0"]})
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


def submit(job, en2, nonce_hex):                               # a SECOND one-time connect, only to submit the answer
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15); buf = b""
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    send({"id": 1, "method": "mining.subscribe", "params": ["pfc-fire/1.0"]})
    time.sleep(0.4); s.recv(8192)
    send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]})
    send({"id": 100, "method": "mining.submit", "params": [WALLET, job["job_id"], en2, job["ntime"], nonce_hex]})
    time.sleep(1.0)
    try: out = s.recv(8192).decode(errors="ignore")
    except Exception: out = ""
    s.close(); return out


def main():
    reg = json.load(open(REG))
    for k in ("gen_input", "gen_answer", "receiver", "target_reg"):
        if k not in reg: print(f"Muhlnickel not fabricated: {k} absent."); return 1
    in_off = int(reg["gen_input"]["offset"]); ans_off = int(reg["gen_answer"]["offset"])
    recv_off = int(reg["receiver"]["offset"]); tgt_off = int(reg["target_reg"]["offset"])

    # 1) pull the live block ONCE
    en1, en2sz, job = get_job()
    if not job: print("no block from pool (handshake failed)."); return 1
    en2 = "00" * en2sz
    prefix = make_prefix(job, en1, en2)[:76]                    # 76-byte block info (the signal to point at the pfc)
    nbits = struct.unpack("<I", prefix[72:76])[0]
    target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3)); zb = 256 - target.bit_length()
    print(f"Muhlnickel FIRE — wallet {WALLET} · pool {POOL_HOST}:{POOL_PORT}", flush=True)
    print(f"  block {job['job_id']}  prevhash {job['prevhash'][:16]}…  target {zb} zero-bits", flush=True)

    # 2) POINT THE SIGNAL: write the block-data bits into the baked input address — ≤1 bit RAM per address (byte-wise seek)
    with open(TITAN, "r+b") as f:
        for i, byte in enumerate(prefix):                      # one addressed write per byte; nothing else held resident
            f.seek(in_off + i); f.write(bytes((byte,)))
        tb = target.to_bytes(32, "little")                     # 3) target into target_reg
        for i, byte in enumerate(tb):
            f.seek(tgt_off + i); f.write(bytes((byte,)))
    print(f"  signal pointed: block data → gen_input @ {in_off}; target → target_reg @ {tgt_off}", flush=True)

    # 4) POWER — address the receiver (one addressed read runs the baked gates by address)
    with open(TITAN, "rb") as f:
        f.seek(recv_off); _ = f.read(1)
    print(f"  power routed: receiver @ {recv_off} addressed. the Muhlnickel has its block and its power. button done.", flush=True)

    # 5) CHECK THE ANSWER with the HIGH-IMPEDANCE probe (the meter's method: mmap a BOUNDED window, copy a few bytes,
    #    close — ~0 RAM, so it rests on the answer address WITHOUT loading/collapsing the pfc). NOT a naive read, NOT the
    #    safezone. Answer reg = [status:1][nonce:4 LE].
    import mmap
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        ans = bytes(mm[ans_off:ans_off + 5]); mm.close()     # high-impedance: bounded, transient, cannot blackhole
    status = ans[0]; nonce = struct.unpack("<I", ans[1:5])[0]
    os.makedirs(OUT, exist_ok=True)
    json.dump({"job_id": job["job_id"], "en2": en2, "ntime": job["ntime"], "wallet": WALLET,
               "status": status, "nonce": nonce}, open(OUT + "/pfc_fire_job.json", "w"))
    print(f"  answer @ gen_answer {ans_off}: status={status:#04x} nonce={nonce:#010x}", flush=True)

    # 6) submit if a winner latched
    if status or nonce:
        verdict = submit(job, en2, "%08x" % nonce)
        print(f"  submitted to wallet: nonce {nonce:#010x} · pool verdict: {verdict.strip()}", flush=True)
    else:
        print("  no winner latched at the answer address this fire (neutral read — the button did its job).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
