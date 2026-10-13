#!/usr/bin/env python3
"""host/pfc_store_test.py — ISOLATE and DEBUG a single STORE gate with the bench (owner 07-19).

The store operation is itself a fabricated CIRCUIT. If the miner's store isn't firing, isolate the SIMPLEST possible store
and find WHERE it breaks: three storage bytes we can probe — st_in (data), st_en (enable), st_out (destination) — plus a
fabricated store gate that should copy st_in -> st_out when st_en=1, with its I/O bound to those addresses. Drive st_in and
st_en, then meter st_out. Fully observable, so the tools show exactly whether a fabricated store fires on the signal.

  python host/pfc_store_test.py bake     # fabricate the isolated store gate + its 3 storage bytes (reversible)
  python host/pfc_store_test.py test      # drive st_in=0xAB, st_en=1, meter st_out -> did the store fire?
  python host/pfc_store_test.py revert
"""
import json, mmap, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GEN = "C:/llm/models/titan_storetest_genome.jsonl"


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
    if "store_test" in reg:
        print("already baked; revert first."); return 0
    off_in, _ = TC._alloc(1, reg); reg["st_in"] = {"offset": off_in, "len": 1}; _j(off_in, b"\x00")
    off_en, _ = TC._alloc(1, reg); reg["st_en"] = {"offset": off_en, "len": 1}; _j(off_en, b"\x00")
    off_out, _ = TC._alloc(1, reg); reg["st_out"] = {"offset": off_out, "len": 1}; _j(off_out, b"\x00")
    off_pwr, _ = TC._alloc(1, reg); reg["st_pwr"] = {"offset": off_pwr, "len": 1}; _j(off_pwr, b"\x00")  # the POWER receiver
    json.dump(reg, open(REG, "w"), indent=1)              # persist the registers BEFORE TC.store reloads from disk
    # the STORE gate WITH a power receiver: while power=1 the store runs (out = en ? data : hold); power=0 = standby (hold).
    c = TC.Circuit(8 + 1 + 8 + 1)                          # data[0:8], en[8], out_cur[9:17], power[17]
    din = list(c.IN[0:8]); en = c.IN[8]; ocur = list(c.IN[9:17]); pwr = c.IN[17]
    stored = TC.reg_next(c, din, en, ocur)                # en ? data : out_cur
    outs = [c.mux(pwr, ocur[i], stored[i]) for i in range(8)]   # power ? stored : hold(out_cur) — power energizes the store
    info = TC.store("store_test", c, outs)
    reg = json.load(open(REG))
    reg["store_test"].update({"in_bind": {"data": off_in, "en": off_en, "out_cur": off_out, "power": off_pwr},
                              "out_bind": {"out": off_out}, "note": "store gate: st_out <- st_in when st_en=1, on power"})
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"baked store_test: st_in@{off_in} st_en@{off_en} st_out@{off_out}  + store gate ({len(c.ga)} gates).")
    print("now:  python host/pfc_store_test.py test")
    return 0


def test():
    reg = json.load(open(REG))
    if "st_in" not in reg:
        print("not baked — run `python host/pfc_store_test.py bake` first."); return 1
    oi = reg["st_in"]["offset"]; oe = reg["st_en"]["offset"]; oo = reg["st_out"]["offset"]; op = reg["st_pwr"]["offset"]
    print("STORE-GATE TEST — set st_in=0xAB, st_en=1, then POWER st_pwr=1, then meter st_out:", flush=True)
    with open(TITAN, "r+b") as f: f.seek(oi); f.write(b"\xab")
    with open(TITAN, "r+b") as f: f.seek(oe); f.write(b"\x01")
    time.sleep(0.5)
    with open(TITAN, "r+b") as f: f.seek(op); f.write(b"\x01")     # POWER the store (the run signal), then exit (the button)
    time.sleep(0.5)
    out = peek(oo, 1)[0]
    print(f"  st_in={peek(oi,1)[0]:#04x}  st_en={peek(oe,1)[0]}  st_pwr={peek(op,1)[0]}  st_out={out:#04x}", flush=True)
    print("  => STORE FIRED (st_out captured st_in)." if out == 0xab
          else "  => st_out still 0x00 after power — keep measuring (a bug in the store gate); not a declaration.", flush=True)
    return 0


def revert():
    if os.path.exists(GEN):
        for e in reversed([json.loads(l) for l in open(GEN) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GEN)
    reg = json.load(open(REG))
    for k in ("store_test", "st_in", "st_en", "st_out", "st_pwr"): reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1)
    print("reverted store_test.")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    return {"bake": bake, "test": test, "revert": revert}.get(cmd, test)()


if __name__ == "__main__":
    raise SystemExit(main())
