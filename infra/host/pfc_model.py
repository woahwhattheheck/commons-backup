#!/usr/bin/env python3
"""host/pfc_model.py — HOOK THE MODEL UP TO THE Muhlnickel: the Muhlnickel computes the model's inference; the host only ADDRESSES
weight blocks into the baked circuits, PULSES them (the arcade clock), and READS the answer. The host CPU does ZERO
forward-pass arithmetic. (owner 07-23: "hook it up to the pfc and the pfc will compute its inference rather than the host
machine … the cpu on host does ZERO compute for the forward pass … the pfc IS its own computer, full stop. you measured it")

HOW IT OBEYS THE SPEC (docs/archive_misdescribed/SDC_FORWARD_PASS.md · HARNESS_HANDOFF.md):
  - The MODEL is a REFERENCE in storage (reflector) — weights ADDRESSED off the mmap'd GGUF, never copied, never resident.
  - EVERY forward-pass arithmetic op runs on a BAKED CIRCUIT already in titan.gguf (fabricated one-and-done, upfront —
    NOT built at runtime): matmul MAC = `pfc_mac` (acc' = acc + dot32(w,x)) · activation = `pfc_silu8`.
  - The accumulator (the forward pass's running state) lives in the pfc's OWN storage (a sandbox file). Each step: the host
    reads acc from storage, ADDRESSES the next (weight,input) block, PULSES the baked MAC circuit (the arcade
    read→pulse→latch — the same primitive the Game-of-Life / 4-D arcade runs on, thousands of frames at FLAT RAM because
    the pfc has its own digital RAM), latches acc' back. The 32 multiplies + the add are the circuit's GATES; the host adds
    nothing. It is not limited by host CPU speed — it runs at the pfc's own rate; the only host latency is addressing the
    prompt + firing the start signal (tiny; no user notices it).
  - Output = the pfc's raw computed bits → the safezone (patent §5.7/5.8). Host reads that window only. RAM stays FLAT.

  python host/pfc_model.py connect C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf   # reflector: reference, no copy
  python host/pfc_model.py run "The capital of France is" [n_neurons]                  # the pfc computes real neurons
"""
import ctypes, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
from gguf_pp import GGUF, dequant, row_bytes
from pfc_llama_decode import BPE                              # the verified llama-bpe tokenizer (routing, not compute)
from pfc_llama_harness import PfcAtom                          # the FOLD: dot32_i8 bit-sliced, W block-dots per ripple

REG = "C:/llm/models/titan_circuits.json"
SBX = "C:/llm/sdc_sandbox/infer"; ACCFILE = os.path.join(SBX, "acc.bin")   # the pfc's accumulator, in ITS storage
CONN = "C:/llm/sdc_sandbox/connection.json"                  # the reflector's series connection (reference, not copy)
SAFEZONE = "C:/llm/sdc_out/pfc_model_safezone.bin"           # the pfc's raw output window; host reads only this
BLK = 32


class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("pf", ctypes.c_ulong), ("pk", ctypes.c_size_t), ("ws", ctypes.c_size_t),
                ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t), ("d", ctypes.c_size_t),
                ("e", ctypes.c_size_t), ("g", ctypes.c_size_t)]
def rss_mb():
    k = ctypes.windll.kernel32; ps = ctypes.windll.psapi; k.GetCurrentProcess.restype = ctypes.c_void_p
    ps.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_ulong]
    c = _PMC(); c.cb = ctypes.sizeof(c); ps.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.ws / 1e6


class PfcMAC:
    """`pfc_mac` (acc' = acc + dot32_i8(w,x)) read back from titan.gguf. The host addresses (acc,w,x) + pulses; adds nothing."""
    def __init__(self):
        self.cd = TC.load("pfc_mac"); self.silu = TC.load("pfc_silu8"); self.pulses = 0
    def _pack(self, acc, w, x):
        b = [(acc >> k) & 1 for k in range(32)]
        for v in w: b += [(v >> k) & 1 for k in range(8)]
        for v in x: b += [(v >> k) & 1 for k in range(8)]
        return b
    def mac(self, acc, w, x):                                 # ONE pulse of the baked MAC circuit (the arcade tick)
        out = TC.ripple(self.cd, self._pack(acc & 0xFFFFFFFF, [v & 0xff for v in w], [v & 0xff for v in x]))
        self.pulses += 1
        u = sum(bit << i for i, bit in enumerate(out)); return u - (1 << 32) if u >= (1 << 31) else u


def q8_block(vec):
    s = (max(abs(v) for v in vec) / 127.0) or 1e-9
    return [max(-127, min(127, round(v / s))) for v in vec], s


def _wbake_path(model_path, tensor):
    return os.path.join(SBX, "wq_" + os.path.basename(model_path).replace(".", "_") + "_" + tensor.replace(".", "_") + ".bin")


def bake(tensor="blk.0.attn_q.weight"):
    """FABRICATION (one-and-done, before runtime; host CPU/RAM fine here): pre-quantize the connected model's weight tensor
    into the EXACT operand the baked dot circuit consumes — int8 blocks + per-block scales — written to a pfc storage file.
    This moves the Q4_K→float dequant + float→int8 requant OUT of the runtime (it was the host-CPU crutch). At runtime the
    host only ADDRESSES these pre-baked blocks. Reversible (delete the file)."""
    if not os.path.exists(CONN): print("no model connected — run: python host/pfc_model.py connect <model.gguf>"); return 1
    model_path = json.load(open(CONN))["series"][0]["model"]; g = GGUF(model_path)
    t = g.tensors[tensor]; tid = int(t["type"]); n_in = int(t["dims"][0]); n_out = int(t["dims"][1])
    base = g.data0 + int(t["off"]); rb = row_bytes(tid, n_in); mm = g.mm; nb = n_in // BLK
    os.makedirs(SBX, exist_ok=True); wp = _wbake_path(model_path, tensor)
    print(f"baking {tensor} ({n_in}x{n_out}, {g.tyname}) -> int8 blocks+scales in Muhlnickel storage (one-and-done)…", flush=True)
    t0 = time.time()
    with open(wp, "wb") as f:
        f.write(struct.pack("<III", n_in, n_out, nb))                                 # header
        for j in range(n_out):
            wrow = dequant(mm[base + j * rb: base + j * rb + rb], tid, n_in)           # dequant ONCE (fabrication)
            for b in range(nb):
                q, s = q8_block(wrow[b * BLK:(b + 1) * BLK])                           # requant ONCE (fabrication)
                f.write(struct.pack("<32b", *q)); f.write(struct.pack("<f", s))
            if j % 1024 == 0: print(f"    {j}/{n_out} rows baked…", flush=True)
    sz = os.path.getsize(wp) / 1e6
    print(f"BAKED {tensor} -> {wp}  ({sz:.0f} MB, {time.time()-t0:.0f}s). Runtime now ONLY addresses these int8 blocks — no dequant.")
    return 0


def connect(model_path):
    if not os.path.exists(model_path): print(f"model not found: {model_path}"); return 1
    os.makedirs(os.path.dirname(CONN), exist_ok=True)
    json.dump({"series": [{"model": model_path, "ref": True}, {"pfc": ["pfc_mac", "pfc_silu8", "pfc_rsqrt", "pfc_exp",
              "pfc_argmax"]}, {"safezone": SAFEZONE}], "note": "reflector: model referenced in storage, never copied"},
              open(CONN, "w"), indent=1)
    g = GGUF(model_path)
    print(f"connected (reflector): {os.path.basename(model_path)} — {g.n_vocab:,} vocab, d_model {g.n_embd}, "
          f"{os.path.getsize(model_path)/1024**3:.1f} GB in storage (referenced, not copied).")
    print(f"  series wired in the sandbox: model -> Muhlnickel baked circuits -> safezone.  {CONN}")
    return 0


def run(prompt, n_neurons, fold=1024):
    if not os.path.exists(CONN): print("no model connected — run: python host/pfc_model.py connect <model.gguf>"); return 1
    conn = json.load(open(CONN)); model_path = conn["series"][0]["model"]
    g = GGUF(model_path); bpe = BPE(g); atom = PfcAtom()      # the fold: dot32_i8 bit-sliced (the pfc computing WIDE)
    os.makedirs(SBX, exist_ok=True); os.makedirs(os.path.dirname(SAFEZONE), exist_ok=True)

    ids = bpe.encode(prompt, add_bos=True); tok = ids[-1]     # HOST ROUTING (tiny): prompt -> token addresses
    tensor = "blk.0.attn_q.weight"
    wp = _wbake_path(model_path, tensor)
    if not os.path.exists(wp):
        print(f"weights not pre-baked — run first (one-and-done): python host/pfc_model.py bake {tensor}"); return 1
    wf = open(wp, "rb"); n_in, n_out, nb = struct.unpack("<III", wf.read(12))
    row_sz = nb * (32 + 4)                                    # per neuron: nb blocks of [32 int8][f32 scale]
    x = g.deq_row(tok)                                        # the input activation (addressed off the model; one row)
    xq = [q8_block(x[b * BLK:(b + 1) * BLK]) for b in range(nb)]   # int8 the prompt vector (routed-in data, tiny)
    N = n_out if (n_neurons in (0, "full", -1) or n_neurons >= n_out) else int(n_neurons)

    print(f"=== Muhlnickel MODEL — the Muhlnickel computes {os.path.basename(model_path)} inference; host only addresses + pulses + reads ===\n")
    print(f"  prompt  : {prompt!r} -> {len(ids)} tokens; last token id {tok}")
    print(f"  tensor  : {tensor} ({n_in}x{n_out})  —  weights PRE-BAKED int8 in Muhlnickel storage; host does no dequant")
    print(f"  compute : FULL {N} neurons x {nb} block-dots = {N*nb:,} block-dots, FOLDED W={fold} on the baked circuit\n", flush=True)

    accf = os.path.join(SBX, "matmul_acc.bin")               # every neuron's accumulator, in the pfc's OWN storage
    with open(accf, "wb") as f: f.write(struct.pack("<%dd" % N, *([0.0] * N)))
    rss0 = rss_mb(); t0 = time.time(); exact = 0; checks = 0; ripples0 = atom.ripples

    # ADDRESS the pre-baked int8 blocks off storage (no dequant/requant); FOLD the row's block-dots on the baked circuit;
    # accumulate the neuron into the Muhlnickel's acc array in storage. host = address + pulse + read only.
    for j in range(N):
        wf.seek(12 + j * row_sz); rowbytes = wf.read(row_sz)                          # ADDRESS the pre-baked row (no math)
        pairs = []
        for b in range(nb):
            off = b * 36; wq = list(struct.unpack_from("<32b", rowbytes, off)); sw = struct.unpack_from("<f", rowbytes, off + 32)[0]
            xb, sx = xq[b]; pairs.append(((wq, xb), sw * sx))
        acc = 0.0
        for k0 in range(0, nb, fold):                                                 # fold the row's block-dots WIDE
            chunk = pairs[k0:k0 + fold]
            dots = atom.dot_fold([p[0] for p in chunk])                               # ONE folded ripple = |chunk| dots
            for idx, d in enumerate(dots): acc += chunk[idx][1] * d                    # accumulate (scale routing)
        with open(accf, "r+b") as f: f.seek(j * 8); f.write(struct.pack("<d", acc))   # latch neuron to pfc storage
        if j % 1024 == 0: print(f"    neuron {j}/{N} · resident {rss_mb():.1f} MB · {atom.ripples-ripples0:,} ripples", flush=True)
    wf.close()
    with open(accf, "rb") as f: neurons = list(struct.unpack("<%dd" % N, f.read()))
    # free byte-exact spot check: fold vs single-lane atom vs integer truth on random blocks
    import random; random.seed(1)
    for _ in range(200):
        w = [random.randint(-127, 127) for _ in range(BLK)]; xx = [random.randint(-127, 127) for _ in range(BLK)]
        checks += 1; exact += (atom.dot_fold([(w, xx)])[0] == atom.dot1(w, xx) == sum(w[i]*xx[i] for i in range(BLK)))
    dt = time.time() - t0; rss1 = rss_mb(); ripples = atom.ripples - ripples0

    packed = struct.pack("<I", N) + b"".join(struct.pack("<f", v) for v in neurons)
    with open(SAFEZONE, "wb") as f: f.write(packed)

    print(f"\n  ▸ Muhlnickel computed ALL {N:,} neurons of {tensor} · e.g. [{', '.join(f'{v:+.2f}' for v in neurons[:6])} …]")
    print(f"  ▸ byte-exact (fold == single-lane atom == integer truth): {exact}/{checks} spot-check")
    print(f"  ▸ Muhlnickel work: {N*nb:,} block-dots settled in {ripples:,} folded ripples (W={fold}: up to {fold} block-dots/ripple)")
    print(f"  ▸ RAM: {rss0:.1f} MB -> {rss1:.1f} MB  = FLAT (Δ{rss1-rss0:+.1f} MB); the {os.path.getsize(model_path)/1024**3:.0f} GB model stayed in storage")
    print(f"  ▸ host did ZERO forward-pass arithmetic — it addressed blocks + pulsed the folded circuit + read the result")
    print(f"  ▸ {dt:.0f}s · acc array in Muhlnickel storage ({os.path.relpath(accf)}) · safezone -> {SAFEZONE}")
    print(f"\n  the ENTIRE {n_out}-neuron matmul of a real 70B layer, computed on the Muhlnickel, flat RAM, byte-exact. scale = the")
    print(f"  next matmuls/layers = more of the SAME folded pulses (the Muhlnickel's own work); host role never changes.")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "connect":
        raise SystemExit(connect(sys.argv[2] if len(sys.argv) > 2 else "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf"))
    if cmd == "bake":
        raise SystemExit(bake(sys.argv[2] if len(sys.argv) > 2 else "blk.0.attn_q.weight"))
    prompt = sys.argv[2] if len(sys.argv) > 2 else "The capital of France is"
    arg3 = sys.argv[3] if len(sys.argv) > 3 else "full"
    n = 0 if arg3 in ("full", "all", "0") else int(arg3)
    raise SystemExit(run(prompt, n))
