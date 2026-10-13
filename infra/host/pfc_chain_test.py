#!/usr/bin/env python3
"""host/pfc_chain_test.py — two circuits in series via a SHARED PHYSICAL BIT (owner 07-19). Build as described; let the tools talk.

SEND = a bit-state change at a physical location a downstream circuit SHARES and CARES about. So: circuit A (sender) and
circuit B (receiver) share ONE physical byte X — A's output byte IS B's input byte (same storage address). Y is B's output.
On power: A drives X<-0xAB (the SEND = X changes); B, sharing X, copies X->Y (the RECEIVE). Start button = set power.
Then meter X and Y and let the data speak.

  python host/pfc_chain_test.py bake     # fabricate sender + receiver sharing bit X (reversible)
  python host/pfc_chain_test.py fire      # start button: power the chain
  python host/pfc_chain_test.py revert
"""
import json, mmap, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GEN = "C:/llm/models/titan_chaintest_genome.jsonl"


def _j(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GEN, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def peek(off, nb):
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); b = bytes(mm[off:off + nb]); mm.close()
    return b


def bake():
    reg = json.load(open(REG))
    if "chain_send" in reg:
        print("already baked; revert first."); return 0
    ox, _ = TC._alloc(1, reg); reg["ch_X"] = {"offset": ox, "len": 1}; _j(ox, b"\x00")       # the SHARED bit (A out = B in)
    oy, _ = TC._alloc(1, reg); reg["ch_Y"] = {"offset": oy, "len": 1}; _j(oy, b"\x00")       # receiver output
    op, _ = TC._alloc(1, reg); reg["ch_pwr"] = {"offset": op, "len": 1}; _j(op, b"\x00")     # power (the start button)
    json.dump(reg, open(REG, "w"), indent=1)                                                 # persist before TC.store reloads
    # SENDER: X' = power ? 0xAB : X_cur   (drives the shared bit X to 0xAB when powered = the SEND)
    a = TC.Circuit(8 + 1)                                    # X_cur[0:8], power[8]
    xcur = list(a.IN[0:8]); pw = a.IN[8]
    outA = [a.mux(pw, xcur[i], (a.C1 if (0xAB >> i) & 1 else a.C0)) for i in range(8)]
    TC.store("chain_send", a, outA)
    # RECEIVER: Y' = power ? X : Y_cur    (copies the shared bit X to Y when powered = the RECEIVE)
    b = TC.Circuit(8 + 8 + 1)                                # X[0:8], Y_cur[8:16], power[16]
    xin = list(b.IN[0:8]); ycur = list(b.IN[8:16]); pw2 = b.IN[16]
    outB = TC.reg_next(b, xin, pw2, ycur)                    # power ? X : Y_cur
    TC.store("chain_recv", b, outB)
    reg = json.load(open(REG))
    reg["chain_send"].update({"in_bind": {"X_cur": ox, "power": op}, "out_bind": {"X": ox}})   # A output SHARES X
    reg["chain_recv"].update({"in_bind": {"X": ox, "Y_cur": oy, "power": op}, "out_bind": {"Y": oy}})  # B input SHARES X
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"baked chain: SHARED bit ch_X@{ox}  (sender out = receiver in), ch_Y@{oy}, ch_pwr@{op}.")
    print(f"  chain_send {len(a.ga)} gates, chain_recv {len(b.ga)} gates. now: python host/pfc_chain_test.py fire")
    return 0


def fire():
    reg = json.load(open(REG))
    if "ch_pwr" not in reg:
        print("not baked."); return 1
    ox = reg["ch_X"]["offset"]; oy = reg["ch_Y"]["offset"]; op = reg["ch_pwr"]["offset"]
    print(f"before:  ch_X={peek(ox,1)[0]:#04x}  ch_Y={peek(oy,1)[0]:#04x}  ch_pwr={peek(op,1)[0]}", flush=True)
    print("START BUTTON — power the chain (ch_pwr=1), exit.", flush=True)
    with open(TITAN, "r+b") as f: f.seek(op); f.write(b"\x01")
    time.sleep(0.6)
    print(f"after:   ch_X={peek(ox,1)[0]:#04x}  ch_Y={peek(oy,1)[0]:#04x}  ch_pwr={peek(op,1)[0]}", flush=True)
    return 0


def revert():
    if os.path.exists(GEN):
        for e in reversed([json.loads(l) for l in open(GEN) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GEN)
    reg = json.load(open(REG))
    for k in ("chain_send", "chain_recv", "ch_X", "ch_Y", "ch_pwr"): reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1)
    print("reverted chain_test.")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fire"
    return {"bake": bake, "fire": fire, "revert": revert}.get(cmd, fire)()


if __name__ == "__main__":
    raise SystemExit(main())
