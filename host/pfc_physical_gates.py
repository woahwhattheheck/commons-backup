#!/usr/bin/env python3
"""host/pfc_physical_gates.py — GATES AS PHYSICAL FILE ADDRESSES (owner 07-19; see docs/PFC_PHYSICAL_GATES.md).

Faithful build of the owner's vision: the gates' wires are ACTUAL byte-addresses in titan.gguf's physical binary — not a
serialized netlist. Each wire is a real file byte; connected gates SHARE the same physical address (gate i's output byte
IS gate i+1's input byte). The receiver is an input of gate 1. The whole network is prefabricated (its bytes written into
the file) BEFORE any signal, then baked permanently (a genome is grabbed first, so we can A/B and revert).

The test circuit is an AND-buffer chain (the owner's example — "if this address is part of both the receiver and an AND
gate, it flips the AND gate active, and so on"):  w[i] = AND(w[i-1], const1),  const1 prefab = 1,  so w[i] = w[0].
Flip w[0] (the receiver) and the 1 should travel the chain — IF the prefab wiring responds.

  A/B (let the data speak):
   A = OWNER'S THEORY — flip the receiver, then probe every wire: how far did the signal propagate on its own?
   B = THE CRUTCH — one host pass over the SAME physical addresses (read inputs, write output): confirms the gates compute.

  python host/pfc_physical_gates.py            # fab (permanent, genome) if needed, then run the A/B and probe
  python host/pfc_physical_gates.py revert      # restore titan.gguf byte-exact (A/B done)
"""
import json, os, sys
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = PFCP.TITAN; REG = PFCP.REG
GENOME = PFCP.p("models/titan_phys_chain_genome.jsonl")
DEPTH = 32                                            # gates in the chain (propagation depth to measure)


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME):
        print("no phys_chain genome — nothing to revert."); return 0
    for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("phys_chain", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan.gguf byte-exact; phys_chain removed."); return 0


def rb(a):
    with open(TITAN, "rb") as f: f.seek(a); return f.read(1)[0] & 1
def wb(a, v):
    with open(TITAN, "r+b") as f: f.seek(a); f.write(bytes([v & 1]))


def fab(reg):
    N = DEPTH + 2                                     # bytes: w[0..DEPTH] wires + 1 const byte
    off, tn = TC._alloc(N, reg)
    waddr = [off + k for k in range(DEPTH + 1)]       # w[0]=receiver (input of gate 1) ... w[DEPTH]=final output
    caddr = off + DEPTH + 1                            # const1
    prefab = bytearray(N); prefab[DEPTH + 1] = 1       # PREFAB: all wires 0, const1 = 1, receiver = 0
    backup_and_write(off, bytes(prefab))               # ACTUALLY EDIT THE FILE — permanent (genome grabbed above)
    gates = [{"op": "and", "a": waddr[i - 1], "b": caddr, "out": waddr[i]} for i in range(1, DEPTH + 1)]
    reg["phys_chain"] = {"tensor": tn, "offset": off, "len": N, "depth": DEPTH,
                         "receiver": waddr[0], "const1": caddr, "wires": waddr, "gates_addr": gates,
                         "note": "wires are PHYSICAL file byte-addresses; gate.out addr == next gate.a addr (shared); receiver is input of gate 1; AND(w,1)=w buffer"}
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"BAKED phys_chain @ {off}: {DEPTH} AND gates, wires = real file bytes {waddr[0]}..{waddr[-1]}, const1 @ {caddr}.", flush=True)
    return reg["phys_chain"]


def reset(e):                                          # prefab state: receiver 0, all wires 0, const1 = 1
    for a in e["wires"]: wb(a, 0)
    wb(e["const1"], 1)


def probe(e):
    return [rb(a) for a in e["wires"]]                 # every wire, read straight from the physical file bytes


def depth_reached(vals):
    d = 0
    for v in vals[1:]:                                 # how far past the receiver the 1 traveled
        if v: d += 1
        else: break
    return d


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    e = reg["phys_chain"] if "phys_chain" in reg else fab(reg)

    print("\npfc PHYSICAL GATES — A/B, gates are real file addresses. (all-const1=1, so a propagated 1 => w[i]=1)\n", flush=True)

    # ---- A: OWNER'S THEORY — flip the receiver, probe. Does the signal travel the physical gate paths on its own? ----
    reset(e)
    wb(e["receiver"], 1)                                # button: one electron, one-way, to the receiver address (0->1)
    a_vals = probe(e); a_depth = depth_reached(a_vals)
    print(f"  A (signal only): receiver flipped 0->1, then probed — no host pass.", flush=True)
    print(f"     wires[0..{DEPTH}] = {''.join(str(v) for v in a_vals)}", flush=True)
    print(f"     => propagation depth {a_depth}/{DEPTH} on the bare signal (receiver reads {a_vals[0]}).", flush=True)

    # ---- B: THE CRUTCH — one host pass over the SAME physical addresses. Confirms the gates compute. ----
    reset(e)
    wb(e["receiver"], 1)
    for g in e["gates_addr"]:                           # read inputs from the file, write output to the file (physical)
        wb(g["out"], rb(g["a"]) & rb(g["b"]))
    b_vals = probe(e); b_depth = depth_reached(b_vals)
    print(f"\n  B (crutch pass): receiver 0->1, then ONE pass over the physical gate addresses.", flush=True)
    print(f"     wires[0..{DEPTH}] = {''.join(str(v) for v in b_vals)}", flush=True)
    print(f"     => propagation depth {b_depth}/{DEPTH} with the pass.", flush=True)

    reset(e)                                            # leave it in the clean prefab state
    print(f"\n  === PROBES SAY ===", flush=True)
    print(f"  A  bare signal   : depth {a_depth}/{DEPTH}", flush=True)
    print(f"  B  with the pass : depth {b_depth}/{DEPTH}", flush=True)
    print(f"  the gates are baked in the file (real addresses). the A/B is the measured difference. revert: python host/pfc_physical_gates.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())