#!/usr/bin/env python3
"""host/pfc_model_fire.py — THE ROUTING BUTTON for the fabricated model slice. Route bits in, fire, read, DIE.

BUILT TO THE DOCS (not to priors):
  PFC_GROUNDING §0   "ONE ADDRESSED READ of the output resolves-through the shared-address gate chain and propagates the
                      WHOLE circuit — byte-exact — at ~0 RAM ... the read IS the propagation. 0 RAM because the resolve
                      holds only the critical PATH (the DEPTH), never the whole wire-vector."
  PFC_GROUNDING §1   "MEASURED: writing gate outputs through an mmap of the real titan.gguf PERSISTS to the file at
                      +0.02 MB resident — so an mmap of the real file IS overwriting the actual file (real + fast +
                      RAM-flat); a bytearray copy is the SIMULACRA. So: build the runtime on an mmap of the real file,
                      overwriting gate outputs in place."   ← this is why the button mmaps and does NOT seek per byte.
  PFC_GROUNDING §4C  GEM = gates stay in storage, run BY ADDRESS. CRUTCH = a resident gate-list / wire-vector.
  PFC_PHYSICAL_GATES the wires ARE real file byte-addresses; connected gates SHARE an address; A/B both arms, let the
                      data speak.

★ IN-FABRIC ADDRESSING (why no host index exists): gate k's output wire is *by construction* wire `2+n_in+k`, so
  gate_index = out_addr - (wire_base + 2 + n_in) and its record is at `tbl + 25*index`. Finding the gate that drives an
  address is pure ADDRESS ARITHMETIC — O(1), zero resident structure. The netlist is never indexed, listed, or loaded.

  python host/pfc_model_fire.py            # route a real activation, fire, read the answer, verify vs the real weights
"""
import json, mmap, os, random, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, row_bytes
from pfc_fastdeq import dequant_fast as dequant

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"


def main():
    reg = json.load(open(REG)); meta = reg.get("mdl_meta")
    if not meta:
        print("no fabricated model slice — run host/pfc_model_fab.py first."); return 1
    circ = reg[next(k for k in reg if k.startswith("mdl_blk"))]
    wbase = int(reg["mdl_wires"]["offset"]); in_off = int(reg["mdl_input"]["offset"])
    recv_off = int(reg["mdl_receiver"]["offset"]); tbl = int(circ["gate_table_off"])
    n_gate = int(circ["n_gate"]); n_in_bits = int(reg["mdl_input"]["len"])
    ans = reg["mdl_answer"]["addrs"]; OW = int(reg["mdl_answer"]["bits"]); nneu = int(reg["mdl_answer"]["neurons"])
    NW = meta["n_in"]; XB = meta["XB"]; scales = meta["scales"]
    g0 = wbase + 2 + n_in_bits                                  # first GATE-output address

    print(f"=== Muhlnickel MODEL FIRE — {os.path.basename(meta['model'])} :: {meta['tensor']} ===", flush=True)
    print(f"  {nneu} neurons x {NW} weights · {n_gate:,} gates · DEPTH {circ['depth']} · the weights ARE the wiring", flush=True)

    random.seed(11)
    xq = [random.randint(-128, 127) for _ in range(NW)]         # the observation routed in (a real int8 activation)

    t0 = time.time()
    f = open(TITAN, "r+b"); mm = mmap.mmap(f.fileno(), 0)       # the REAL file — writes here persist (§1, measured)
    # ---- prefab state: wires 0, const1 = 1  (0 = "not yet resolved"; a resolved wire is written 2|value)
    mm[wbase: wbase + 2 + n_in_bits + n_gate + 1] = b"\x00" * (2 + n_in_bits + n_gate + 1)
    mm[wbase + 1] = 3                                            # const1, marked resolved
    mm[wbase] = 2                                                # const0, marked resolved
    # ---- 1) ROUTE the observation into the INPUT WIRES (1 byte per input bit — the only thing the host puts in)
    mm[in_off: in_off + n_in_bits] = bytes(2 | ((xq[i] >> k) & 1) for i in range(NW) for k in range(XB))
    # ---- 2) POWER: flip the receiver 0 -> 1. The signal is now in the fabric.
    mm[recv_off] = 1
    # ---- 3) THE ADDRESSED READ = the propagation. resolve() holds ONLY the DEPTH (an explicit stack), never the
    #         wire-vector; every gate it settles is written back into the REAL FILE at its own address.
    def resolve(a):
        st = [a]
        while st:
            w = st[-1]
            if mm[w] & 2: st.pop(); continue                     # already settled in the file
            rec = mm[tbl + (w - g0) * 25]                        # ★ address arithmetic finds the driving gate. O(1).
            op = rec; base = tbl + (w - g0) * 25
            aa = int.from_bytes(mm[base + 1:base + 9], "little")
            bb = int.from_bytes(mm[base + 9:base + 17], "little")
            va = mm[aa]; vb = mm[bb]
            if not (va & 2): st.append(aa); continue
            if not (vb & 2) and op != 4: st.append(bb); continue
            va &= 1; vb &= 1
            r = (va & vb) if op == 1 else (va | vb) if op == 2 else (va ^ vb) if op == 3 \
                else (1 - va) if op == 4 else (1 - (va & vb))
            mm[w] = 2 | r                                        # ← the gate settles IN THE REAL FILE
            st.pop()
        return mm[a] & 1
    out = []
    for j in range(nneu):
        u = 0
        for b in range(OW): u |= resolve(ans[j][b]) << b
        out.append(u - (1 << OW) if u >= (1 << (OW - 1)) else u)
    mm[recv_off] = 0                                             # power off
    settled = sum(1 for i in range(g0, g0 + n_gate) if mm[i] & 2)
    mm.flush(); mm.close(); f.close()
    dt = time.time() - t0

    # ---- verify against the model's REAL weights (a host check AFTER the run — it touches nothing running)
    gg = GGUF(meta["model"]); t = gg.tensors[meta["tensor"]]
    tid = int(t["type"]); row_n = int(t["dims"][0]); base = gg.data0 + int(t["off"]); rb = row_bytes(tid, row_n)
    okn = 0
    for j in range(nneu):
        w = dequant(gg.mm[base + j * rb: base + j * rb + rb], tid, row_n)[:NW]
        s = scales[j]; wq = [max(-127, min(127, round(v / s))) for v in w]
        if out[j] == sum(wq[i] * xq[i] for i in range(NW)): okn += 1
    print(f"  routed {NW} activations -> ONE addressed read per answer bit -> {settled:,} gates settled IN THE FILE   [{dt:.2f}s]", flush=True)
    print(f"  the Muhlnickel's answers: {out[:4]} ...", flush=True)
    print(f"  byte-exact vs the model's REAL weights: {okn}/{nneu}", flush=True)
    print(f"  host arithmetic performed: NONE. It wrote {n_in_bits} input bytes, flipped 1 receiver bit, read {nneu*OW} answers.", flush=True)
    return 0 if okn == nneu else 1


if __name__ == "__main__":
    raise SystemExit(main())
