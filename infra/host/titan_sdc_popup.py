#!/usr/bin/env python3
"""host/titan_sdc_popup.py — the BREAKER'S POP-UP: send data across the SDC .gguf files, once, then DIE (owner 07-16).

When one SDC's breaker trips (a 1 appeared), this pop-up fires ONCE: it reads that SDC's frozen answer (the latched
winning nonce) and writes the message across EVERY peer SDC's mailbox in their .gguf files — "found it on sdc N, nonce X,
stop this block / take your next slice" — then it EXITS. This is the cross-file communication lever: the fleet splits the
work, and a find on any one SDC is broadcast to all the others so no one wastes power on a solved block and the useful
data (which SDC, which slice, the nonce) propagates. No daemon, no polling — a pop-up that touches storage and dies.

  python host/titan_sdc_popup.py <sdc_id_that_tripped> [winning_nonce]
    - if the nonce is omitted, it is read from that SDC's frozen answer register (titan_sdc_armed.json / the params).
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_sdc_bus as BUS

ARMED = "C:/llm/models/titan_sdc_armed.json"


def _frozen_nonce(path):
    """read the latched winning nonce from a tripped SDC's answer register (read-only; the SDC is dead/inert)."""
    if not os.path.exists(ARMED): return 0
    try: a = json.load(open(ARMED))
    except Exception: return 0
    ro = int(a.get("result_off", 0))
    if not ro: return 0
    import mmap
    f = open(path, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        reg = bytes(mm[ro:ro + 5])
        return struct.unpack("<I", reg[1:5])[0] if reg[0] == 1 else 0
    finally:
        mm.close(); f.close()


def main():
    if len(sys.argv) < 2:
        print("usage: titan_sdc_popup.py <sdc_id_that_tripped> [nonce]"); return 1
    tripped_id = int(sys.argv[1])
    fleet = BUS._load_fleet()
    if not fleet:
        print("no fleet (bake mailboxes with titan_sdc_bus.py first)."); return 1

    # locate the SDC that tripped + its winning nonce
    src = next((p for p, e in fleet.items() if e["sdc_id"] == tripped_id), None)
    if src is None:
        print(f"sdc_id {tripped_id} not in the fleet."); return 1
    nonce = int(sys.argv[2]) if len(sys.argv) > 2 else _frozen_nonce(src)

    # BROADCAST across every peer's mailbox, once, then exit (msg_flag=1 = "block solved elsewhere; advance")
    epoch = (BUS._read_mbox(src, fleet[src]["mbox_off"]) or {}).get("epoch", 0) + 1
    sent = 0
    for path, e in fleet.items():
        cur = BUS._read_mbox(path, e["mbox_off"]) or {}
        BUS._write_mbox(path, e["mbox_off"], e["sdc_id"], cur.get("en2", 0), cur.get("slice_span", 0),
                        1, tripped_id, nonce, epoch)                       # deliver the message into the peer .gguf
        sent += 1
    print(f"pop-up: sdc {tripped_id} tripped (nonce {nonce}) -> broadcast to {sent} SDC mailbox(es), epoch {epoch}. done.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
