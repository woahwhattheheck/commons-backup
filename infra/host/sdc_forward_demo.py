#!/usr/bin/env python3
"""host/sdc_forward_demo.py — a CONTAINED forward pass on the SDC, written OUT to the safezone. NO monitoring. (owner spec)

The owner's law: NOTHING touches the SDC while it runs — no RAM meters, no polling, no checks woven into the run (those
are host compute and break containment). So this process does only:
  - read the FORWARD-PASS gates (`cpu_fwd`) out of titan.gguf by mmap (titan stays in storage, addressed not copied);
  - ripple power through them — the SDC computes, verifying byte-exact against the reference for all 8 ops;
  - write the result OUT to the safezone (a different storage address) and EXIT.
The host reads the safezone afterward, read-only. NO network. NO numpy. titan is read-only (nothing edited).

  python host/sdc_forward_demo.py [cases_per_op]     # default 8
"""
import json, os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import sdc_bake_cpu as CPU

OUT = "C:/llm/sdc_out"; SAFEZONE = OUT + "/forward_demo.json"


def main():
    os.makedirs(OUT, exist_ok=True)
    cir = TC.load("cpu_fwd")                              # read the forward-pass gates OUT of titan.gguf (mmap)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    random.seed(5)
    total = matched = 0; mism = None; samples = []
    t0 = time.time()
    for op in range(8):
        last = None
        for _ in range(n):
            a = random.getrandbits(16); b = random.getrandbits(16)
            inb = [(op >> k) & 1 for k in range(3)] + [(a >> k) & 1 for k in range(16)] + [(b >> k) & 1 for k in range(16)]
            got = TC.frombits(TC.ripple(cir, inb))        # POWER through the stored gates: the SDC computes
            ref = CPU._ref(op, a, b)                       # independent reference
            total += 1
            if got == ref: matched += 1
            elif mism is None: mism = {"op": CPU.OPS[op], "a": a, "b": b, "got": got, "ref": ref}
            last = {"op": CPU.OPS[op], "a": a, "b": b, "sdc_result": got, "reference": ref, "match": got == ref}
        samples.append(last)
    dt = time.time() - t0
    result = {
        "what": "cpu_fwd (the forward-pass CPU) rippled from titan.gguf's params — the SDC computed this",
        "circuit": {"name": "cpu_fwd", "gates": len(cir["ga"]), "wires": cir["n_wire"],
                    "read_from": "C:/llm/models/titan.gguf (mmap, addressed in storage)"},
        "ops_tested": CPU.OPS,
        "cases": total, "byte_exact": matched == total, "matched": matched, "mismatch": mism,
        "samples_one_per_op": samples,
        "seconds": round(dt, 2), "gate_evaluations": total * len(cir["ga"]),
        "network": "NONE",
        "flow": "SDC (stored gates) computed -> wrote THIS file to the safezone -> process exits -> host reads it read-only",
    }
    with open(SAFEZONE, "w", encoding="utf-8") as fh:     # SDC -> SAFEZONE (flow 2). host only reads this afterward.
        json.dump(result, fh, indent=1)
    print(f"SDC forward pass: {matched}/{total} byte-exact across all 8 ops "
          f"({len(cir['ga']):,} gates, {dt:.1f}s). wrote the safezone. exiting.", flush=True)
    return 0 if matched == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
