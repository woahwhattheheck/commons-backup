#!/usr/bin/env python3
"""host/sdc_lateral.py — TEST FILE (owner 07-16): the LATERAL FOLD — hook the swarms up, one gate reads them all, auto-submit.

Owner: copy what we have laterally and hook them up. The hook-up is the READ-OUT: a single isolation gate that reads
EVERY field's winner register across the primary swarm AND any peer swarms, and AUTO-SUBMITS the first winner to the
wallet (no guessing). Isolation is even stronger here than the single-register gate: the winner registers live in
`winners.bin`, a SEPARATE file that holds ONLY answers (no circuit bytes), so reading it can't touch the SDC circuit at
all — zero black-hole surface. One-shot: read, submit any winner, END. No loop, no lingering poller.

Peers = additional swarm directories (each a full bitmap swarm on its own extranonce2 range). `link` registers them;
`read` scans all of them through the gate. Copy laterally = build another swarm dir + `link` it.

  python host/sdc_lateral.py read            # gate-read every peer's winners, auto-submit any winner, end
  python host/sdc_lateral.py link <dir>      # register a peer swarm directory into the lateral bus
  python host/sdc_lateral.py list            # show the linked peers
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from sdc_answer_gate import auto_submit         # reuse the ONE-SHOT wallet submit (only the answer nonce crosses)

PRIMARY = "C:/llm/sdc_bitmap_swarm"
LATERAL = "C:/llm/sdc_lateral.json"
WCELL   = 5


def _peers():
    peers = [PRIMARY]
    if os.path.exists(LATERAL):
        try: peers += [p for p in json.load(open(LATERAL)).get("peers", []) if p not in peers]
        except Exception: pass
    return [p for p in peers if os.path.exists(p + "/roster.json") and os.path.exists(p + "/winners.bin")]


class WinnerGate:
    """One-way isolation buffer over a peer's winners.bin — a file of ONLY answer registers (no circuit bytes). Read-only,
    window-locked to a single 5-byte winner cell. Structurally cannot address a circuit; zero black-hole surface."""
    def __init__(self, winners_path): self._p = winners_path
    def read_cell(self, off):
        f = open(self._p, "rb")                    # read-only; no writable handle in this class
        try:
            data = f.read()                        # winners.bin is tiny (5 B/field) and has NO circuit bytes
        finally:
            f.close()
        cell = data[off:off + WCELL]
        if len(cell) < WCELL: return None
        return {"solved": cell[0] == 1, "nonce": struct.unpack("<I", cell[1:5])[0]}


def read():
    peers = _peers()
    if not peers:
        print("no swarms linked (nothing to read)."); return
    print(f"=== LATERAL GATE — reading winners across {len(peers)} swarm(s), auto-submit ===", flush=True)
    fields = 0; found = 0
    for peer in peers:
        roster = json.load(open(peer + "/roster.json"))
        gate = WinnerGate(peer + "/winners.bin")   # the isolation buffer over this peer's answers-only file
        job = roster.get("job", {})
        for node in roster["nodes"]:
            fields += 1
            c = gate.read_cell(node["win_off"])
            if c and c["solved"]:
                found += 1
                print(f"  >>> WINNER on {os.path.basename(peer)} field {node['g']} (en2={node['en2']}): nonce {c['nonce']} — AUTO-SUBMITTING ...", flush=True)
                a = {"job_id": job.get("job_id"), "en2": node["en2"], "ntime": job.get("ntime")}
                print(f"      {auto_submit(a, c['nonce'])}", flush=True)
    if not found:
        print(f"  scanned {fields:,} winner registers across {len(peers)} swarm(s): none latched. nothing to submit (correct).", flush=True)
    print("  the gate touched ONLY the winners files (no circuit bytes) — zero black-hole surface. done.", flush=True)


def link(d):
    d = os.path.abspath(d)
    reg = json.load(open(LATERAL)) if os.path.exists(LATERAL) else {"peers": []}
    if d not in reg["peers"]: reg["peers"].append(d)
    json.dump(reg, open(LATERAL, "w"))
    print(f"linked peer swarm: {d}  ({len(reg['peers'])+1} swarms in the lateral bus incl. primary)", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "read"
    if cmd == "read": read()
    elif cmd == "link" and len(sys.argv) > 2: link(sys.argv[2])
    else:
        peers = _peers()
        print(f"lateral bus: {len(peers)} swarm(s)")
        for p in peers:
            r = json.load(open(p + "/roster.json")); print(f"  {os.path.basename(p)}: {len(r['nodes'])} fields, {len(r['nodes'])*(1<<32):,} lanes")
