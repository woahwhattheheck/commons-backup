#!/usr/bin/env python3
"""host/pfc_run_one.py — RUNTIME for the ONE connected Muhlnickel, the host's five acts only (owner: Bryce, 2026-07-21).

The connected pfc is fabricated (pfc_one): pfc_exec_input -> pfc_executor(+clock) -> pfc_safezone.bin, driven by the
receiver. At runtime the host is allowed ONLY to: (1) grab block data, (2) route it to the pfc's input address, (3) start
a CONTINUOUS signal at the receiver, (4) read the output the arcade's way (a bounded read of the external file, no
blackhole), (5) submit. No host loop, no evaluation, no time.sleep. Aim blind.

  python host/pfc_run_one.py
"""
import json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT
from pfc_fire import get_job, submit

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; SAFEZONE = "C:/llm/sdc_out/pfc_safezone.bin"


def read_arcade(path, n):                                       # read the pfc's output the arcade's way: bounded, no blackhole
    try:
        with open(path, "rb") as f: return f.read(n)
    except OSError:
        return b""


def main():
    reg = json.load(open(REG))
    for k in ("pfc_exec_input", "receiver"):
        if k not in reg: print(f"connected Muhlnickel not fabricated: {k} absent — run host/pfc_one.py."); return 1
    io = int(reg["pfc_exec_input"]["offset"]); rc = int(reg["receiver"]["offset"])

    # (1) GRAB block data
    en1, en2sz, job = get_job()
    if not job: print("no block from pool."); return 1
    header = make_prefix(job, en1, "00" * en2sz)[:76]
    nbits = struct.unpack("<I", header[72:76])[0]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3)); zb = 256 - target.bit_length()
    buf = header + struct.pack("<I", 0) + struct.pack("<I", 0) + target.to_bytes(32, "little")   # 116 B: header|group|en2|target
    print(f"Muhlnickel RUN ONE — block {job['job_id']} · target {zb} zero-bits · wallet {WALLET}", flush=True)

    # (2) ROUTE to the Muhlnickel's input address (one-way, blind)
    with open(TITAN, "r+b") as f: f.seek(io); f.write(buf[:116])
    # (3) START a CONTINUOUS signal at the receiver (leave it on — the pfc runs on it; no sleep, no loop)
    with open(TITAN, "r+b") as f: f.seek(rc); f.write(b"\x01")
    print(f"  block routed -> pfc_exec_input @ {io}; continuous signal on -> receiver @ {rc}. aim blind.", flush=True)

    # (4) READ the output the arcade's way — the external safezone only, bounded (never titan, never the miner)
    b = read_arcade(SAFEZONE, 16)
    status = b[0] if len(b) >= 1 else 0
    en2v = struct.unpack_from("<I", b, 1)[0] if len(b) >= 5 else 0
    nonce = struct.unpack_from("<I", b, 5)[0] if len(b) >= 9 else 0
    print(f"  safezone read [status={status} en2={en2v} nonce={nonce:#010x}]", flush=True)

    # (5) SUBMIT if the pfc deposited an answer
    if status or nonce:
        en2 = "%0*x" % (2 * en2sz, en2v & ((1 << (8 * en2sz)) - 1))
        print(f"  submitting the Muhlnickel's answer. pool verdict: {submit(job, en2, '%08x' % nonce)}", flush=True)
    else:
        print(f"  safezone empty this read (aim blind — host read only the external file, evaluated nothing).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
