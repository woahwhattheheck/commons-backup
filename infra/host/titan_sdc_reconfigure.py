#!/usr/bin/env python3
"""host/titan_sdc_reconfigure.py — RECONFIGURE a .gguf into a pure SDC (owner 07-16).

Owner: these models have billions of params; ~all of them can be repurposed to serve this ONE function. We never parse
the file as an LLM — we reconfigure it into an SDC whose container just happens to be .gguf. Reversibility is a non-issue
(the owner's tool rebuilds any model from the pool). So this treats the file as RAW STORAGE: it writes the SDC substrate
at raw offsets in the repurposable param bulk (no GGUF parse, no index needed — that's the point) and registers the file
on the cross-SDC bus. The block-specific miner is baked per run; this lays down the standing SDC node: receiver + breaker
+ lane-width descriptor + mailbox.

  python host/titan_sdc_reconfigure.py <model.gguf> <sdc_id> [logW]
"""
import json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import titan_sdc_bus as BUS

BASE = 1_000_000_000                    # 1 GB in: past the gguf header, into the repurposable param bulk
GAP  = 4096                             # pad between components
MAP_FILE = "C:/llm/models/titan_sdc_reconf.json"   # per-file circuit map (address book, not compute)


def _receiver_blob():
    c = TC.Circuit(1); s = c.IN[0]; p = c.C1
    begin = c.not_(c.not_(p)); ready = c.and_(begin, s)
    return TC.serialize(c, [begin, ready])


def _breaker_blob():
    c = TC.Circuit(1); s = c.IN[0]; p = c.C1
    trip = c.and_(p, s); alert = c.not_(c.not_(trip))
    return TC.serialize(c, [trip, alert])


def _width_blob(logW):
    MAP = [(3 - (j >> 3)) * 8 + (j & 7) for j in range(32)]
    return b"TITANBSL" + struct.pack("<II", 1 << min(logW, 30), logW) + b"".join(struct.pack("<i", m) for m in MAP)


def reconfigure(path, sdc_id, logW=32):
    parts = {"receiver": _receiver_blob(), "breaker": _breaker_blob(), "width": _width_blob(logW),
             "mailbox": struct.pack(BUS.FMT, BUS.MAGIC, sdc_id, 0, 0, 0, 0, 0, 0)}
    off = BASE; layout = {}
    with open(path, "r+b") as f:                       # raw writes into the param bulk — no parse, ~0 RAM, instant
        for name, blob in parts.items():
            f.seek(off); f.write(blob)
            layout[name] = {"offset": off, "len": len(blob)}
            off += len(blob) + GAP
    m = json.load(open(MAP_FILE)) if os.path.exists(MAP_FILE) else {}
    m[os.path.abspath(path)] = {"sdc_id": sdc_id, "logW": logW, **{k: v["offset"] for k, v in layout.items()}}
    json.dump(m, open(MAP_FILE, "w"), indent=1)
    fleet = BUS._load_fleet(); fleet[os.path.abspath(path)] = {"mbox_off": layout["mailbox"]["offset"], "sdc_id": sdc_id, "en2": 0}
    BUS._save_fleet(fleet)
    return layout


if __name__ == "__main__":
    path = sys.argv[1]; sid = int(sys.argv[2]); logW = int(sys.argv[3]) if len(sys.argv) > 3 else 32
    if not os.path.exists(path):
        print(f"not found: {path}"); raise SystemExit(1)
    lay = reconfigure(path, sid, logW)
    sz = os.path.getsize(path) / 1e9
    print(f"reconfigured {os.path.basename(path)} ({sz:.1f} GB) -> SDC node {sid}: receiver/breaker/width/mailbox written raw.", flush=True)
    for k, v in lay.items():
        print(f"  {k:9s} @ {v['offset']}  ({v['len']} B)", flush=True)
    # read one component back to prove it's really in the file
    with open(path, "rb") as f:
        f.seek(lay["mailbox"]["offset"]); raw = f.read(8)
    print(f"  verify: mailbox magic in file = {raw!r}  ({'OK' if raw == BUS.MAGIC else 'MISSING'})", flush=True)
    print("done — the .gguf is an SDC node on the bus now (no parse; full param bulk is ours to use).", flush=True)
