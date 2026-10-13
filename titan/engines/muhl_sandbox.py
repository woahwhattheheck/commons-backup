#!/usr/bin/env python3
"""muhl_sandbox.py — TITAN'S BUILT-IN TRAINING SANDBOX: model + data + compute, isolated in storage.

The substrate's containment model: an isolated storage location holds the machine and its state; the host
only powers and reads. So Titan's training lives in its own sandbox (C:/llm/titan_sandbox). The MODEL WEIGHTS
are a file there -- the trainable tensor IN STORAGE. The DATA is a file there. Training runs the fabricated
backprop step (muhl_train_deep) and writes the new weights BACK INTO THE MODEL FILE IN PLACE (the substrate
way: the file is the computer, running = editing its bits). Host RAM stays flat; the model state persists
across runs -- stop and resume, the sandbox remembers. Every update is byte-exact vs the integer reference.
"""
import sys, os, json, struct, mmap, ctypes, random
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import muhl_train_deep as DT
from muhl_neural import gen_data, TEMPLATES

SBX = r"C:/llm/titan_sandbox"
MODEL = os.path.join(SBX, "model.bin"); DATA = os.path.join(SBX, "data.bin"); META = os.path.join(SBX, "meta.json")
NW = DT.H*DT.NF + DT.H + DT.NCLS*DT.H + DT.NCLS

class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]
_ps = ctypes.WinDLL("psapi.dll"); _h = ctypes.WinDLL("kernel32.dll").GetCurrentProcess()
def rss_mb():
    m = PMC(); m.cb = ctypes.sizeof(PMC); _ps.GetProcessMemoryInfo(_h, ctypes.byref(m), m.cb); return m.WorkingSetSize/1048576

def flat(P):
    f = []
    for j in range(DT.H): f += P['W1'][j]
    f += P['b1']
    for k in range(DT.NCLS): f += P['W2'][k]
    f += P['b2']
    return f
def unflat(f):
    c = 0
    W1 = [f[c+j*DT.NF:c+(j+1)*DT.NF] for j in range(DT.H)]; c += DT.H*DT.NF
    b1 = f[c:c+DT.H]; c += DT.H
    W2 = [f[c+k*DT.H:c+(k+1)*DT.H] for k in range(DT.NCLS)]; c += DT.NCLS*DT.H
    b2 = f[c:c+DT.NCLS]
    return {'W1': W1, 'b1': b1, 'W2': W2, 'b2': b2}

def init_sandbox():
    os.makedirs(SBX, exist_ok=True)
    rng = random.Random(7)
    P = {'W1': [[rng.randrange(-2, 3) for _ in range(DT.NF)] for _ in range(DT.H)], 'b1': [0]*DT.H,
         'W2': [[rng.randrange(-2, 3) for _ in range(DT.H)] for _ in range(DT.NCLS)], 'b2': [0]*DT.NCLS}
    with open(MODEL, "wb") as f: f.write(struct.pack("<%di" % NW, *flat(P)))
    data = gen_data(rng, noise=1, per=40)
    with open(DATA, "wb") as f:
        for x, y in data:
            xi = sum(b << i for i, b in enumerate(x))
            f.write(struct.pack("<HB", xi, y))
    json.dump({"steps": 0, "epochs": 0}, open(META, "w"))

def load_model():
    with open(MODEL, "rb") as f: return unflat(list(struct.unpack("<%di" % NW, f.read())))
def save_model_inplace(P):                                # edit the weights file IN PLACE (mmap), the substrate way
    with open(MODEL, "r+b") as f:
        mm = mmap.mmap(f.fileno(), 0)
        mm[:] = struct.pack("<%di" % NW, *flat(P)); mm.flush(); mm.close()
def load_data():
    out = []
    with open(DATA, "rb") as f:
        b = f.read()
    for o in range(0, len(b), 3):
        xi, y = struct.unpack_from("<HB", b, o)
        out.append(([(xi >> i) & 1 for i in range(DT.NF)], y))
    return out

def accuracy(P, data): return sum(1 for x, y in data if DT.predict(P, x) == y) / len(data)

def main():
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 4
    fresh = not os.path.exists(MODEL)
    if fresh: init_sandbox()
    meta = json.load(open(META))
    P = load_model(); data = load_data()
    print(f"\n  TITAN SANDBOX @ {SBX}")
    print(f"  {'created fresh' if fresh else 'resumed'} — model.bin ({NW} int32 weights in storage) · data.bin ({len(data)} examples)")
    print(f"  prior training: {meta['epochs']} epochs / {meta['steps']} steps · accuracy now {accuracy(P, data)*100:.0f}%")

    step, ng = DT.build_step()
    base = rss_mb(); hi = base
    print(f"\n  training +{epochs} epochs — fabricated step ({ng:,} gates) edits the weight FILE in place:")
    for ep in range(epochs):
        random.Random(meta['steps']).shuffle(data)
        for x, y in data:
            Pg = step(P, x, y); assert Pg == DT.ref_step(P, x, y); P = Pg; meta['steps'] += 1
        save_model_inplace(P); meta['epochs'] += 1          # persist to storage each epoch
        hi = max(hi, rss_mb())
        clean = sum(1 for c, t in TEMPLATES.items() if DT.predict(P, t) == c)
        print(f"    epoch {meta['epochs']:>2}: accuracy {accuracy(P, data)*100:3.0f}%  (clean {clean}/3)  [saved to sandbox]")
    json.dump(meta, open(META, "w"))
    end = rss_mb()
    print(f"\n  resident RAM: start {base:.1f} MB · max {hi:.1f} · end {end:.1f}  (+{end-base:.2f} MB — model+data in storage)")
    print(f"  cumulative: {meta['epochs']} epochs / {meta['steps']} steps. The model lives in the sandbox, not host")
    print(f"  memory — run again to CONTINUE training; the weights are the file. (reset: delete {SBX})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
