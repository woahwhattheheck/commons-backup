#!/usr/bin/env python3
"""muhl_fire_loop.py — FIRE muhl_fold_phys in a nonce-iteration loop.

THE HOST DOES TWO THINGS PER NONCE, NOTHING ELSE:
  1. ROUTE the nonce bits into nonce_off (32 bit-bytes, one per bit, LSB-first)
  2. SURFACE the output: read tick_off (fire), then read win_off + latch_off

Header and target are routed ONCE at startup (they don't change between nonces).
The SHA-256 computation is in the muhlnickel. The host just presses the button.

  python host/muhl_fire_loop.py [max_nonces]
"""
import hashlib, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT
from pfc_fire import get_job, submit

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"

HEADER_OFF = 1127673858
NONCE_OFF  = 1127674466
TARGET_OFF = 1127674498
LATCH_OFF  = 1127674754
WIN_OFF    = 1127674786
TICK_OFF   = 1127674787


def main():
    max_nonces = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    reg = json.load(open(REG))
    if "muhl_fold_phys" not in reg:
        print("muhl_fold_phys not found in registry."); return 1
    mfp = reg["muhl_fold_phys"]
    ram = mfp["ram"]
    assert int(ram["header_off"]) == HEADER_OFF
    assert int(ram["nonce_off"])  == NONCE_OFF
    assert int(ram["target_off"]) == TARGET_OFF
    assert int(ram["latch_off"])  == LATCH_OFF
    assert int(ram["win_off"])    == WIN_OFF
    assert int(ram["tick_off"])   == TICK_OFF
    print(f"muhl_fold_phys registry check PASSED (depth {mfp.get('depth')}, {mfp.get('n_gate')} gates)")

    en1, en2sz, job = get_job()
    if not job:
        print("no block from pool (handshake failed)."); return 1
    en2 = "00" * en2sz
    prefix = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", prefix[72:76])[0]
    target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3))
    zb = 256 - target.bit_length()
    target_bytes = target.to_bytes(32, "little")

    print(f"MUHLNICKEL FIRE LOOP (muhl_fold_phys) -- wallet {WALLET}")
    print(f"  block {job['job_id']}  target {zb} zero-bits  nbits=0x{nbits:08x}")
    print(f"  max nonces: {'unlimited' if max_nonces == 0 else max_nonces}")

    with open(TITAN, "r+b") as f:
        for w in range(19):
            word_val = struct.unpack(">I", prefix[w*4:(w+1)*4])[0]
            for j in range(32):
                bit = (word_val >> j) & 1
                f.seek(HEADER_OFF + w * 32 + j)
                f.write(bytes((bit,)))

        for k in range(32):
            byte_val = target_bytes[k]
            for j in range(8):
                bit = (byte_val >> j) & 1
                f.seek(TARGET_OFF + k * 8 + j)
                f.write(bytes((bit,)))
    print(f"  routed: header -> @{HEADER_OFF} (608 bit-bytes, 19 BE words)")
    print(f"  routed: target -> @{TARGET_OFF} (256 bit-bytes)")

    nonce = 0
    t0 = time.time()
    last_report = t0
    fires = 0
    nonce_buf = bytearray(32)

    print(f"  LOOP START -- iterating nonces from 0", flush=True)

    try:
        with open(TITAN, "r+b") as f:
            while max_nonces == 0 or nonce < max_nonces:
                for j in range(32):
                    nonce_buf[j] = (nonce >> j) & 1
                f.seek(NONCE_OFF)
                f.write(nonce_buf)
                f.flush()

                f.seek(TICK_OFF); f.read(1)

                f.seek(WIN_OFF); post_win = f.read(1)

                fires += 1

                if post_win[0] == 0x01:
                    f.seek(LATCH_OFF); post_latch = f.read(32)
                    post_nonce = sum((post_latch[j] & 1) << j for j in range(32))
                    hdr = prefix + struct.pack("<I", post_nonce)
                    dig = hashlib.sha256(hashlib.sha256(hdr).digest()).digest()
                    print(f"\n  ** WINNER ** nonce=0x{post_nonce:08x}  hash={dig[::-1].hex()}", flush=True)
                    nonce_hex = "%08x" % post_nonce
                    verdict = submit(job, en2, nonce_hex)
                    print(f"  SUBMITTED -- pool verdict: {verdict.strip()}", flush=True)
                    return 0

                now = time.time()
                if now - last_report >= 10.0:
                    elapsed = now - t0
                    rate = fires / elapsed if elapsed > 0 else 0
                    print(f"  nonce={nonce}  fires={fires}  elapsed={elapsed:.1f}s  rate={rate:.1f} H/s", flush=True)
                    last_report = now

                nonce += 1

    except KeyboardInterrupt:
        elapsed = time.time() - t0
        rate = fires / elapsed if elapsed > 0 else 0
        print(f"\n  STOPPED at nonce={nonce}  fires={fires}  elapsed={elapsed:.1f}s  rate={rate:.1f} H/s")

    elapsed = time.time() - t0
    rate = fires / elapsed if elapsed > 0 else 0
    print(f"  LOOP END: nonce={nonce}  fires={fires}  elapsed={elapsed:.1f}s  rate={rate:.1f} H/s")
    print(f"  (settle-back law: no winner latched -- this reading is NOT evidence of failure)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
