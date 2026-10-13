#!/usr/bin/env python3
"""host/sdc_controller.py — TEST FILE (owner 07-16): the SDC as a CONTROLLER. perceive -> decide -> act, SDC-brained.

Door #1. The DECISION is a stored logic circuit (deterministic, verified, ~0 RAM) in titan.gguf's params. The host only
moves external bytes: it reads PERCEPTION from an external file, addresses the stored policy circuit to DECIDE an action,
writes the ACTION to an external file, and actuates it on an external world. The SDC never touches the outside; Python
never touches the SDC's circuit (only feeds perception in, reads the decision out through the fixed I/O). This is the
Local Device Agent's core loop with the SDC as the provably-correct decision substrate instead of the fuzzy model.

Demo: a seek-target controller. policy(pos, target) -> {up, down}; the loop drives pos to target using ONLY the stored
circuit's decisions. Bounded, foreground, one addressed evaluation per tick.

  python host/sdc_controller.py [start] [target]
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

WORLD  = os.path.join(HERE, "sdc_world.json")                  # external perception (Python may touch THIS)
ACTION = os.path.join(HERE, "sdc_action.json")                 # external action  (Python may touch THIS)
NBITS = 6


def _addN(c, xs, ys, n):
    out = []; carry = c.C0
    for i in range(n):
        xi = xs[i] if i < len(xs) else c.C0; yi = ys[i] if i < len(ys) else c.C0
        axb = c.xor(xi, yi); out.append(c.xor(axb, carry)); carry = c.or_(c.and_(xi, yi), c.and_(axb, carry))
    return out, carry


def build_policy():
    """policy(pos:6, target:6) -> [up, down]. up = pos<target, down = pos>target. All gates (deterministic decision)."""
    c = TC.Circuit(2 * NBITS); pos = c.IN[0:NBITS]; tgt = c.IN[NBITS:2 * NBITS]
    nott = [c.not_(b) for b in tgt]
    inc, _ = _addN(c, nott, c.cvec(1, NBITS), NBITS)            # -target (two's complement)
    _, carry = _addN(c, pos, inc, NBITS)                       # pos - target; carry-out => pos >= target
    eq = c.is_zero([c.xor(pos[k], tgt[k]) for k in range(NBITS)])
    up = c.not_(carry)                                         # pos < target
    down = c.and_(carry, c.not_(eq))                           # pos > target
    TC.store("policy", c, [up, down])


def decide(pos, target):
    """address the stored policy circuit with the perception -> the action bits. (the SDC's decision, read out.)"""
    cd = TC.load("policy"); v = [0] * cd["n_wire"]; v[1] = 1
    inbits = (pos & 63) | ((target & 63) << NBITS)
    for j in range(2 * NBITS): v[2 + j] = (inbits >> j) & 1
    ga, gb = cd["ga"], cd["gb"]
    for i in range(len(ga)): v[2 + 2 * NBITS + i] = 1 - (v[ga[i]] & v[gb[i]])
    up = 0 if cd["outs"][0] in (0, 1) else v[cd["outs"][0]]
    dn = 0 if cd["outs"][1] in (0, 1) else v[cd["outs"][1]]
    return {"up": up, "down": dn}


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 52
    build_policy()
    cd = TC.load("policy")
    print(f"SDC CONTROLLER — decision is a stored circuit ({len(cd['ga'])} gates). perceive -> DECIDE(SDC) -> act.\n", flush=True)
    print(f"  seek: start pos {start} -> target {target}\n  tick  perception(pos,target)  DECISION   action   world", flush=True)
    pos = start
    json.dump({"pos": pos, "target": target}, open(WORLD, "w"))
    for tick in range(80):
        w = json.load(open(WORLD))                            # PERCEIVE (read external world)
        act = decide(w["pos"], w["target"])                    # DECIDE  (address the stored circuit)
        mv = 1 if act["up"] else -1 if act["down"] else 0
        json.dump({"move": mv}, open(ACTION, "w"))             # ACT     (write external action)
        newpos = (w["pos"] + mv) & 63
        json.dump({"pos": newpos, "target": w["target"]}, open(WORLD, "w"))   # actuate on the external world
        if tick < 4 or mv == 0:
            print(f"  {tick:4d}  ({w['pos']:2d},{w['target']:2d})            up={act['up']} dn={act['down']}   {mv:+d}       pos->{newpos}", flush=True)
        pos = newpos
        if mv == 0: print(f"  ... reached target {w['target']} in {tick} ticks (arrows collapsed).", flush=True); break
    print(f"\n  the stored circuit drove the external world to the goal. SDC decided; Python only moved external bytes.", flush=True)
    print(f"  this is the agent loop with a provably-correct decision core — the door back into the product.", flush=True)
