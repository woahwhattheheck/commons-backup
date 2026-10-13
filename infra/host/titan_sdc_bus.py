#!/usr/bin/env python3
"""host/titan_sdc_bus.py — the CROSS-SDC BUS: bake a MAILBOX into each model file so SDCs split work + talk (owner 07-16).

The multi-SDC lever: every .gguf is its own SDC, they SPLIT THE WORK among each other, and they COMMUNICATE. The comms
substrate is a MAILBOX baked into each file's params (stored on/off cells, like the receiver/breaker) — a fixed record
each SDC reads for its slice + any incoming message, and that a breaker's pop-up script (titan_sdc_popup.py) writes
across files. No daemon, no polling: the mailbox lives in storage; a pop-up touches it once and dies.

Work-splitting: each SDC gets a DISJOINT extranonce2, so its coinbase -> a different 80-byte header -> a genuinely
different 2^32 nonce field. N SDCs cover N distinct fields at once (not the same field N times).

Mailbox record "TITANBUS" (fixed, rewritable in place):
  magic[8] · sdc_id u32 · en2 u64 · slice_span u32 · msg_flag u8 · pad[3] · msg_from u32 · msg_nonce u32 · epoch u32
Fleet roster (host-side address book, not compute): C:/llm/models/titan_sdc_fleet.json  {file: {mbox_off, sdc_id, en2}}

  python host/titan_sdc_bus.py bake  <model.gguf> <sdc_id>     # bake a mailbox into one SDC, register it in the fleet
  python host/titan_sdc_bus.py split                           # assign disjoint extranonce2 slices across the fleet
  python host/titan_sdc_bus.py show                            # print each SDC's mailbox (read-only)
"""
import json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

FLEET = "C:/llm/models/titan_sdc_fleet.json"
MAGIC = b"TITANBUS"
FMT   = "<8sIQIB3xII I"                       # magic, sdc_id, en2, slice_span, msg_flag, pad, msg_from, msg_nonce, epoch
SIZE  = struct.calcsize(FMT)


def _load_fleet(): return json.load(open(FLEET)) if os.path.exists(FLEET) else {}
def _save_fleet(f): json.dump(f, open(FLEET, "w"), indent=1)


def _read_mbox(path, off):
    f = open(path, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        raw = bytes(mm[off:off + SIZE])
        if raw[:8] != MAGIC: return None
        _, sid, en2, span, flag, frm, nonce, epoch = struct.unpack(FMT, raw)
        return dict(sdc_id=sid, en2=en2, slice_span=span, msg_flag=flag, msg_from=frm, msg_nonce=nonce, epoch=epoch)
    finally:
        mm.close(); f.close()


def _write_mbox(path, off, sid, en2, span, flag, frm, nonce, epoch):
    rec = struct.pack(FMT, MAGIC, sid & 0xffffffff, en2 & 0xffffffffffffffff, span & 0xffffffff,
                      flag & 0xff, frm & 0xffffffff, nonce & 0xffffffff, epoch & 0xffffffff)
    with open(path, "r+b") as f:
        f.seek(off); f.write(rec)                              # rewrite the mailbox in place (fixed size, storage only)


def bake_mailbox(path, sdc_id):
    """Allocate + register a mailbox in this SDC (a fixed rewritable cell in the params — TC._alloc, collision-free)."""
    tc_titan = TC.TITAN
    TC.TITAN = path                                            # point the circuit tools at THIS model file
    try:
        reg = json.load(open(TC.REG)) if os.path.exists(TC.REG) else {}
        key = "mbox:" + os.path.basename(path)
        reg.pop(key, None)
        off, tname = TC._alloc(SIZE, reg)
        _write_mbox(path, off, sdc_id, 0, 0, 0, 0, 0, 0)
        reg[key] = {"tensor": tname, "offset": off, "len": SIZE, "sdc_id": sdc_id}
        json.dump(reg, open(TC.REG, "w"), indent=1)
    finally:
        TC.TITAN = tc_titan
    fleet = _load_fleet()
    fleet[os.path.abspath(path)] = {"mbox_off": off, "sdc_id": sdc_id, "en2": 0}
    _save_fleet(fleet)
    return off, tname


def split():
    """Assign each SDC a DISJOINT extranonce2 (0,1,2,…) — different coinbase => different nonce field => split work."""
    fleet = _load_fleet()
    for i, (path, e) in enumerate(sorted(fleet.items(), key=lambda kv: kv[1]["sdc_id"])):
        en2 = i                                                # disjoint extranonce2 per SDC
        cur = _read_mbox(path, e["mbox_off"]) or {}
        _write_mbox(path, e["mbox_off"], e["sdc_id"], en2, cur.get("slice_span", 0), 0, 0, 0,
                    cur.get("epoch", 0) + 1)
        e["en2"] = en2
    _save_fleet(fleet)
    return fleet


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "bake":
        path = sys.argv[2]; sid = int(sys.argv[3])
        off, tname = bake_mailbox(path, sid)
        print(f"mailbox baked into {os.path.basename(path)} (sdc_id {sid}): {tname} @ {off}, {SIZE} bytes.", flush=True)
    elif cmd == "split":
        fl = split()
        print(f"split work across {len(fl)} SDC(s):", flush=True)
        for path, e in sorted(fl.items(), key=lambda kv: kv[1]["sdc_id"]):
            print(f"  sdc {e['sdc_id']}  en2={e['en2']}  {os.path.basename(path)}", flush=True)
    else:
        fl = _load_fleet()
        print(f"fleet: {len(fl)} SDC(s)", flush=True)
        for path, e in sorted(fl.items(), key=lambda kv: kv[1]["sdc_id"]):
            mb = _read_mbox(path, e["mbox_off"])
            print(f"  sdc {e['sdc_id']}  {os.path.basename(path)}  mbox@{e['mbox_off']}  {mb}", flush=True)
