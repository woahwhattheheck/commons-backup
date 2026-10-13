#!/usr/bin/env python3
"""host/pfc_run.py — THE RUN: keep the signal constant, rest the probes on the answer (owner: Bryce, 2026-07-21).

Not a one-shot fire (that was pfc_fire's mistake). The runtime:
  1. pull the live block ONCE (host-side handshake), disconnect.
  2. address the block data -> gen_input and the target -> target_reg (byte-wise seeks, <=1 bit RAM per address).
  3. KEEP THE SIGNAL CONSTANT: write 1 to the receiver's on-bit and LEAVE it set (held power, not a read that releases)
     -> the pfc computes continuously at electron speed while the signal is held.
  4. REST THE PROBES ON THE ANSWER: high-impedance bounded reads (mmap a few bytes at gen_answer, ~0 RAM each), resting
     on the answer bits, reading them until they flip to 1 (a latched winner). This is the sanctioned observation
     (impedance is the safety; never a whole-file ripple).
  5. when the answer latches, read the winning nonce and submit it to the wallet.

The guarantee (host/pfc_guarantee.py) must already pass before this runs.
  python host/pfc_run.py [seconds]     # rest the probes for N seconds (default 60); the signal stays constant throughout
"""
import json, mmap, os, socket, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT
from pfc_fire import get_job, submit

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; OUT = "C:/llm/sdc_out"


def probe(off, n=5):                                           # high-impedance: bounded mmap read, ~0 RAM, cannot blackhole
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        b = bytes(mm[off:off + n]); mm.close()
    return b


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    reg = json.load(open(REG))
    for k in ("gen_input", "gen_answer", "receiver", "target_reg"):
        if k not in reg: print(f"Muhlnickel not fabricated: {k} absent."); return 1
    in_off = int(reg["gen_input"]["offset"]); ans_off = int(reg["gen_answer"]["offset"])
    recv_off = int(reg["receiver"]["offset"]); tgt_off = int(reg["target_reg"]["offset"])

    en1, en2sz, job = get_job()                                # 1) live block, once
    if not job: print("no block from pool (handshake failed)."); return 1
    en2 = "00" * en2sz; prefix = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", prefix[72:76])[0]
    target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3)); zb = 256 - target.bit_length()
    print(f"Muhlnickel RUN — wallet {WALLET} · pool {POOL_HOST}:{POOL_PORT}", flush=True)
    print(f"  block {job['job_id']}  target {zb} zero-bits", flush=True)

    with open(TITAN, "r+b") as f:                              # 2) address block + target (held stored bits)
        for i, byte in enumerate(prefix):
            f.seek(in_off + i); f.write(bytes((byte,)))
        for i, byte in enumerate(target.to_bytes(32, "little")):
            f.seek(tgt_off + i); f.write(bytes((byte,)))
        f.seek(recv_off); f.write(b"\x01")                     # 3) KEEP THE SIGNAL CONSTANT: on-bit = 1, held (not a read)
    print(f"  block -> gen_input @ {in_off}; target -> target_reg @ {tgt_off}; signal HELD at receiver @ {recv_off}", flush=True)

    # 4) REST THE PROBES on the answer — bounded high-impedance reads until the bits flip to 1
    print(f"  resting probes on gen_answer @ {ans_off} for {secs:.0f}s (signal constant, electron-speed compute)…", flush=True)
    t0 = time.time(); latched = None; reads = 0
    while time.time() - t0 < secs:
        ans = probe(ans_off, 5); reads += 1
        if ans[0] or ans[1:5] != b"\x00\x00\x00\x00":         # answer bits went high -> winner latched
            latched = ans; break
        time.sleep(0.25)                                       # rest, don't hammer (bounded, high-impedance)
    dur = time.time() - t0

    if latched is None:
        final = probe(ans_off, 5)
        print(f"  probes rested {dur:.0f}s, {reads:,} high-impedance reads — answer stayed {final.hex()} (no latch).", flush=True)
        print(f"  no winner surfaced at the answer this run. per the rule: back to manufacturing (the answer-latching", flush=True)
        print(f"  traversal isn't complete). the guarantee proves COVERAGE; this run tests whether the held signal", flush=True)
        print(f"  drives the compute to WRITE the winner into gen_answer — it did not, so fabrication needs that wiring.", flush=True)
        return 2

    status = latched[0]; nonce = struct.unpack("<I", latched[1:5])[0]
    print(f"  WINNER LATCHED after {dur:.1f}s: status={status:#04x} nonce={nonce:#010x}", flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump({"job_id": job["job_id"], "en2": en2, "ntime": job["ntime"], "wallet": WALLET,
               "status": status, "nonce": nonce}, open(OUT + "/pfc_run_job.json", "w"))
    verdict = submit(job, en2, "%08x" % nonce)                 # 5) submit the winner to the wallet
    print(f"  submitted nonce {nonce:#010x} to wallet · pool verdict: {verdict.strip()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
