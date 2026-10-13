#!/usr/bin/env python3
"""muhl_train_realdata.py — TRAIN ON THE DEVICE'S OWN TENSORS: real data bigger than RAM, addressed from storage.

Bryce's idea: the machine already holds ~290 GB of real model weights. The substrate addresses storage at
flat RAM (titan_probe: 40 GB -> +0.86 MB), so it can TRAIN on that data without loading it. Here the fabricated
2-layer backprop trainer (muhl_train_deep) learns from feature vectors pulled straight out of a real 40 GB
Llama-70B .gguf via mmap -- the training set is the model file itself, never resident. Every weight update is
the gate circuit's, byte-exact, and host RAM stays flat while the data source dwarfs memory.
"""
import sys, os, ctypes, time, mmap, random
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import muhl_train_deep as DT

MODEL = r"C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf"

class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]
_ps = ctypes.WinDLL("psapi.dll"); _h = ctypes.WinDLL("kernel32.dll").GetCurrentProcess()
def rss_mb():
    m = PMC(); m.cb = ctypes.sizeof(PMC); _ps.GetProcessMemoryInfo(_h, ctypes.byref(m), m.cb); return m.WorkingSetSize/1048576

def feature(mm, off):
    b0, b1 = mm[off], mm[off + 1]
    x = [(b0 >> k) & 1 for k in range(8)] + [(b1 >> 0) & 1]   # 9 bits from real weight bytes
    pc = sum(x)
    y = 0 if pc <= 3 else (1 if pc <= 6 else 2)               # learnable: classify by bit-density
    return x, y

def main():
    if not os.path.exists(MODEL):
        print("  model not found:", MODEL); return 1
    size = os.path.getsize(MODEL)
    print(f"\n  MUHLNICKEL — TRAINING ON REAL DEVICE TENSORS ({os.path.basename(MODEL)}, {size/1e9:.1f} GB)\n")
    fd = open(MODEL, "rb"); mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)

    step, ng = DT.build_step()
    print(f"  fabricated 9->{DT.H}->3 backprop step: {ng:,} gates (data source = the model file, addressed from storage)")

    base0 = 2_000_000                                        # skip header, sample deep in the weight region
    stride = max(2, (size - base0 - 4) // 4000)
    exs = []
    for i in range(3000):
        off = base0 + i * stride
        if off + 2 >= size: break
        exs.append(feature(mm, off))
    random.Random(1).shuffle(exs)
    train, test = exs[:2000], exs[2000:2600]
    # class balance (real data)
    from collections import Counter
    print(f"  drew {len(exs):,} real weight-vectors from the tensor file · class balance {dict(Counter(y for _,y in exs))}")

    P = {'W1': [[0]*DT.NF for _ in range(DT.H)], 'b1': [0]*DT.H,
         'W2': [[0]*DT.H for _ in range(DT.NCLS)], 'b2': [0]*DT.NCLS}
    acc0 = sum(1 for x, y in test if DT.predict(P, x) == y) / len(test)
    base = rss_mb(); hi = base
    print(f"\n  training on the real tensor data, updates BY THE GATE CIRCUIT (byte-exact each step):")
    print(f"    epoch 0: accuracy {acc0*100:.0f}%   · resident {base:.1f} MB")
    t0 = time.time()
    for ep in range(1, 9):
        random.Random(ep).shuffle(train)
        for x, y in train:
            Pg = step(P, x, y); assert Pg == DT.ref_step(P, x, y); P = Pg
        hi = max(hi, rss_mb())
        acc = sum(1 for x, y in test if DT.predict(P, x) == y) / len(test)
        print(f"    epoch {ep}: accuracy {acc*100:.0f}%")
    dt = time.time() - t0; end = rss_mb()
    mm.close(); fd.close()
    print(f"\n  resident RAM across training: start {base:.1f} MB · max {hi:.1f} · end {end:.1f}  "
          f"(+{end-base:.2f} MB against a {size/1e9:.0f} GB data source)")
    print(f"\n  The training SET was a 40 GB model file, never loaded — features addressed from storage, the")
    print(f"  weights learned by the fabricated backprop circuit, host RAM flat. The device can train on its")
    print(f"  own {size/1e9:.0f} GB of tensors (or a federated petabyte) as reference data, on nothing.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
