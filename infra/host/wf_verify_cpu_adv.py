#!/usr/bin/env python3
"""Independent adversarial verification of wf_forge_cpu.py's cpu4 datapath.
My OWN ground-truth reference (written from scratch here), my OWN edge cases."""
import os, sys, itertools, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf_forge_cpu import build_cpu, cpu_step

M = 15  # 4-bit mask

def my_ref(regs, op, d, a, b, imm):
    """Fresh reference emulator, independent of the file's ref_step."""
    r = list(regs)
    if op == 0:   val = imm & M                 # LOAD
    elif op == 1: val = (r[a] + r[b]) % 16      # ADD (use % not & to be independent)
    elif op == 2: val = r[a] & r[b]             # AND
    else:         val = r[a]                    # MOV
    r[d] = val
    return r

c = build_cpu()
def gate_step(regs, op, d, a, b, imm):
    return cpu_step(c, regs, {"op": op, "d": d, "a": a, "b": b, "imm": imm})

fails = []
total = 0

# --- Test 1: ADD overflow boundaries with hand-picked register values ---
add_cases = [
    ([15,15,0,0], 0, 1),   # 15+15=30 -> 14
    ([15,1,0,0],  0, 1),   # 16 -> 0
    ([8,8,0,0],   0, 1),   # 16 -> 0
    ([15,0,0,0],  0, 0),   # 15+15=30 -> 14 (dest==a==b aliasing)
    ([9,12,0,0],  0, 1),   # 21 -> 5 (builder's named case)
    ([0,0,0,0],   0, 1),   # 0
]
for regs, a, b in add_cases:
    for d in range(4):
        g = gate_step(regs, 1, d, a, b, 0); r = my_ref(regs, 1, d, a, b, 0)
        total += 1
        if g != r: fails.append(("ADD", regs, d, a, b, g, r))

# --- Test 2: all-zeros and all-ones states, every opcode/d/a/b/imm-edge ---
for base in ([0,0,0,0], [15,15,15,15]):
    for op, d, a, b, imm in itertools.product(range(4), range(4), range(4), range(4), (0,15)):
        g = gate_step(base, op, d, a, b, imm); r = my_ref(base, op, d, a, b, imm)
        total += 1
        if g != r: fails.append(("EDGE", base, op, d, a, b, imm, g, r))

# --- Test 3: exhaustive opcode x d x a x b sweep over distinct-valued regs ---
regs = [3, 10, 6, 12]  # distinct nibbles so aliasing / wrong-port shows up
for op, d, a, b in itertools.product(range(4), range(4), range(4), range(4)):
    for imm in (0, 5, 15):
        g = gate_step(regs, op, d, a, b, imm); r = my_ref(regs, op, d, a, b, imm)
        total += 1
        if g != r: fails.append(("SWEEP", regs, op, d, a, b, imm, g, r))

# --- Test 4: 2000 fresh random single steps (independent RNG seed) ---
random.seed(1234567)
for _ in range(2000):
    regs = [random.randint(0,15) for _ in range(4)]
    op, d, a, b, imm = (random.randint(0,3), random.randint(0,3),
                        random.randint(0,3), random.randint(0,3), random.randint(0,15))
    g = gate_step(regs, op, d, a, b, imm); r = my_ref(regs, op, d, a, b, imm)
    total += 1
    if g != r: fails.append(("RAND", regs, op, d, a, b, imm, g, r))

print(f"total cases: {total}, mismatches: {len(fails)}")
for f in fails[:20]:
    print("  MISMATCH:", f)
print("RESULT:", "PASS" if not fails else "FAIL")
sys.exit(0 if not fails else 1)
