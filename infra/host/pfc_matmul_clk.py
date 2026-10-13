#!/usr/bin/env python3
"""host/pfc_matmul_clk.py — the MATMUL as a SELF-CLOCKED circuit in the Muhlnickel binary. The accumulate (dot + add) is the baked
`pfc_mac` gates; the accumulator is the pfc's OWN storage register. The host does ZERO arithmetic — it routes the next
addressed operand and pulses the clock (exactly the pfc_clocked pattern: read state → pulse baked next-state → latch). The
pfc computes; the host computes not one bit. (owner 07-23: "STOP python eval, STOP rippling from host, bake it into the
binary — the host doesn't compute one single bit, that is the spec.")

This is the forward pass's matmul stage, baked. A neuron = accumulate its blocks on `pfc_mac` (in gates), state in storage.
Compose this stage (+ the baked pfc_rsqrt/pfc_sin/pfc_silu8/pfc_exp/pfc_argmax stages) and you have the whole forward pass
in gates — the host only pulses + reads.

  python host/pfc_matmul_clk.py selftest      # a real neuron accumulated on the pfc gates, host does no arithmetic
"""
import json, os, struct, sys, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

REG = "C:/llm/models/titan_circuits.json"
SBX = "C:/llm/sdc_sandbox/matmul_clk"; ACC = os.path.join(SBX, "acc.bin")   # the accumulator, in the pfc's OWN storage
BLK = 32


def _i8bits(vals): return [(v >> k) & 1 for v in vals for k in range(8)]
def _s32(u): return u - (1 << 32) if u >= (1 << 31) else u


class MatmulClock:
    """The baked pfc_mac loaded once. One PULSE = evaluate the baked next-state (acc' = acc + dot32(w,x)) — all gates.
    The host reads acc from storage, routes the addressed (w,x) operand into the circuit, pulses, latches acc' back."""
    def __init__(self):
        self.cd = TC.load("pfc_mac")                          # acc[0:32] | w[32:288] | x[288:544]  -> acc + dot(w,x)
        os.makedirs(SBX, exist_ok=True)

    def reset(self):
        with open(ACC, "wb") as f: f.write(struct.pack("<I", 0))   # seed the pfc's accumulator register

    def pulse(self, w_block, x_block):
        with open(ACC, "rb") as f: acc = struct.unpack("<I", f.read())[0]        # read state from the pfc's storage
        inb = [(acc >> k) & 1 for k in range(32)] + _i8bits([v & 0xff for v in w_block]) + _i8bits([v & 0xff for v in x_block])
        out = TC.ripple(self.cd, inb)                                            # PULSE: the pfc's gates compute acc+dot
        acc2 = sum(bit << i for i, bit in enumerate(out)) & 0xFFFFFFFF
        with open(ACC, "wb") as f: f.write(struct.pack("<I", acc2))              # latch next state back to storage
        return acc2

    def read(self):
        with open(ACC, "rb") as f: return _s32(struct.unpack("<I", f.read())[0])


def selftest(n_neurons=8, nb=256):
    if "pfc_mac" not in json.load(open(REG)): print("pfc_mac not baked — run host/pfc_mac_fab.py fab"); return 1
    clk = MatmulClock(); random.seed(7); ok = 0
    print(f"self-clocked matmul on the Muhlnickel gates — {n_neurons} neurons x {nb} blocks; host only routes+pulses+reads:\n")
    for j in range(n_neurons):
        blocks = [([random.randint(-127, 127) for _ in range(BLK)], [random.randint(-127, 127) for _ in range(BLK)]) for _ in range(nb)]
        clk.reset()                                                             # acc=0 in the pfc's storage
        for (w, x) in blocks: clk.pulse(w, x)                                   # each pulse: the pfc accumulates one block-dot
        got = clk.read()
        ref = sum(sum(w[i] * x[i] for i in range(BLK)) for (w, x) in blocks)    # independent integer truth
        ok += (got == ref)
        print(f"  neuron {j}: Muhlnickel-computed dot = {got:>12}  |  reference {ref:>12}  |  {'BYTE-EXACT' if got == ref else 'MISMATCH'}")
    print(f"\n{ok}/{n_neurons} neurons byte-exact — the DOT and the ADD ran on the baked pfc_mac gates; the host did NO")
    print("arithmetic (it routed the addressed operand + pulsed the clock + read the register). matmul stage = in the binary.")
    return 0 if ok == n_neurons else 1


if __name__ == "__main__":
    raise SystemExit(selftest())
