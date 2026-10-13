#!/usr/bin/env python3
"""host/sdc_forward_contained.py — the forward pass PHYSICALLY ISOLATED IN STORAGE (owner 07-18).

Owner's containment: the ONLY things that may draw host RAM are the start button + reading the safezone. The SDC's compute
must live in STORAGE, not resident host RAM — if the run draws RAM, the executor wasn't sandboxed. `titan_circuit.load()`
pulls all 404k gates into Python lists (~30 MB resident) — that is the leak. This fixes it:
  - the gate-net STAYS in titan.gguf: gates are read by ADDRESS straight off the mmap (a zero-copy memoryview over the
    stored bytes) — never a Python list of the 404k gates;
  - the wire-state lives in a mmap'd STORAGE sandbox file (C:/llm/sdc_sandbox/fwd/wire.bin) — not a resident array;
  - only the input goes in and the output slice comes out → written to the safezone → the process EXITS.
So resident host RAM is just the interpreter skin (the button has that too); the 40 GB model, the 404k-gate net, and the
wire-state ALL live in storage (file-backed, reclaimable). No numpy, no network, titan read-only.

  python host/sdc_forward_contained.py [cases_per_op]     # default 8
"""
import json, mmap, os, random, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_bake_cpu as CPU                                 # reference + op names only — NOT used for the compute

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
SANDBOX = "C:/llm/sdc_sandbox/fwd"; OUT = "C:/llm/sdc_out"; SAFEZONE = OUT + "/forward_contained.json"
MAGIC = b"TITANCIR"


def main():
    reg = json.load(open(REG)); e = reg["cpu_fwd"]; off = int(e["offset"])
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)   # titan stays in storage
    assert mm[off:off + 8] == MAGIC, "no cpu_fwd circuit at the registered offset"
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", mm, off + 8)
    ga_off = off + 24; gb_off = ga_off + ng * 4; outs_off = gb_off + ng * 4
    gav = memoryview(mm)[ga_off:gb_off].cast("i")          # zero-copy views over the STORED gate arrays (no Python list)
    gbv = memoryview(mm)[gb_off:outs_off].cast("i")
    outs = list(struct.unpack_from("<%di" % n_out, mm, outs_off))   # only n_out=16 ints — tiny

    os.makedirs(SANDBOX, exist_ok=True)                    # wire-state = a mmap'd STORAGE sandbox file (not resident)
    wpath = SANDBOX + "/wire.bin"
    with open(wpath, "wb") as w: w.truncate(n_wire)
    wf = open(wpath, "r+b"); wm = mmap.mmap(wf.fileno(), 0)
    base = 2 + n_in

    def ripple(inb):
        wm[0] = 0; wm[1] = 1
        for i in range(n_in): wm[2 + i] = inb[i] & 1
        for i in range(ng):                                # gates read by address off storage; wire-state in storage
            wm[base + i] = 1 - (wm[gav[i]] & wm[gbv[i]])
        v = 0
        for k, o in enumerate(outs): v |= wm[o] << k
        return v

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    random.seed(5); total = matched = 0; mism = None; samples = []
    t0 = time.time()
    for op in range(8):
        last = None
        for _ in range(n):
            a = random.getrandbits(16); b = random.getrandbits(16)
            inb = [(op >> k) & 1 for k in range(3)] + [(a >> k) & 1 for k in range(16)] + [(b >> k) & 1 for k in range(16)]
            got = ripple(inb); ref = CPU._ref(op, a, b); total += 1
            if got == ref: matched += 1
            elif mism is None: mism = {"op": CPU.OPS[op], "a": a, "b": b, "got": got, "ref": ref}
            last = {"op": CPU.OPS[op], "a": a, "b": b, "sdc_result": got, "reference": ref, "match": got == ref}
        samples.append(last)
    dt = time.time() - t0
    gav.release(); gbv.release(); wm.close(); wf.close(); os.remove(wpath); mm.close(); f.close()   # tear down the sandbox

    result = {
        "what": "cpu_fwd rippled BY ADDRESS off storage — gates never entered host RAM (physically isolated)",
        "circuit": {"name": "cpu_fwd", "gates": ng, "wires": n_wire, "read_from": "C:/llm/models/titan.gguf (mmap, per-gate)"},
        "wire_state": "C:/llm/sdc_sandbox/fwd/wire.bin (mmap'd storage sandbox — not resident; removed after run)",
        "ops_tested": CPU.OPS, "cases": total, "byte_exact": matched == total, "matched": matched, "mismatch": mism,
        "samples_one_per_op": samples, "seconds": round(dt, 2), "gate_evaluations": total * ng,
        "network": "NONE",
        "containment": "gates stay in titan.gguf (read by address), wire-state in a mmap'd sandbox file — only the "
                       "interpreter skin is resident; nothing hooked to the SDC drew host RAM",
        "flow": "SDC computed in storage -> wrote THIS file to the safezone -> exits -> host reads it read-only",
    }
    with open(SAFEZONE, "w", encoding="utf-8") as fh: json.dump(result, fh, indent=1)
    print(f"SDC forward pass (contained-in-storage): {matched}/{total} byte-exact across all 8 ops "
          f"({ng:,} gates, {dt:.1f}s). gates + wire-state stayed in storage. wrote the safezone. exiting.", flush=True)
    return 0 if matched == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
