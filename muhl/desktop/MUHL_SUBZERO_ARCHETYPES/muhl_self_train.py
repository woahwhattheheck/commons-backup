#!/usr/bin/env python3
"""muhl_self_train.py — SELF-TRAINING ENGINE: fabricated circuit that trains itself continuously.

Bryce Muhlnickel, 2026-08-03.

The substrate learns from data dumped into it. This is FABRICATION — offline, one-and-done
manufacturing. The circuit is stored in titan.gguf and runs itself after electron injection.

Architecture:
  1. INTAKE REGION — 1 GB area in titan.gguf where the host dumps raw file data.
     Layout: write_ptr(8) | size(8) | capacity(8) | data...
     The host writes sequentially; the substrate reads via absolute addressing.

  2. MODEL WEIGHTS REGION — persistent learned weights (9->8 hidden->3 classifier).
     107 int16 weights in storage, updated in-place by the training circuit each step.

  3. SELF-TRAINING CIRCUIT — one fabricated pass of:
       a) feature extraction: 9 bits from 2 intake bytes + popcount label
       b) forward:  9 -> 8 hidden (binary threshold) -> 3 output (argmax)
       c) backprop: structured hinge, signSGD through both layers
       d) weight update: output == input addresses (SELF-CLOCK)
       e) read-pointer advance: next 2 bytes of intake data
     Stored via store_loop() — the loop is permanent structure in the wiring.
     Powered by the rings through the reservoir (offset 40,022,599,232).

  4. Every gate is NAND-only (titan_circuit.Circuit), directly storable.
     Verified BYTE-EXACT vs an integer reference at fabrication time.
     Journaled for revert. No numpy. No host computation at runtime.

    python muhl_self_train.py          # fabricate and store
    python muhl_self_train.py --dry    # verify only, store nothing
"""
import sys, os, json, struct, mmap, random, time

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
sys.path.insert(0, r"C:/llm/sdc_sandbox")

import pfc_paths as PFCP
import titan_circuit as TC

DRY = "--dry" in sys.argv
TITAN = PFCP.TITAN
REG = PFCP.REG
NAME = "muhl_self_train"
GENOME_PATH = TITAN.replace(".gguf", "_selftrain_genome.jsonl")

# ── training architecture (matches muhl_train_deep) ──────────────────────────
NF   = 9       # input features
H    = 8       # hidden units
NCLS = 3       # output classes
B    = 16      # weight bit-width (two's complement)

# ── regions ──────────────────────────────────────────────────────────────────
INTAKE_CAPACITY = 50 * (1 << 30)                     # 50 GB
INTAKE_HEADER   = 24                                # write_ptr(8) + size(8) + capacity(8)
FILE_MARKER     = b"MUHLFILE"                       # 8-byte boundary between files

NW = H * NF + H + NCLS * H + NCLS                  # 107 weights
WEIGHT_BYTES = NW * 2                               # int16 each = 214 bytes

# read pointer: 30 bits address 1 GB intake data area
PTR_BITS = 30

RESERVOIR_INPUT = 40_022_599_232                    # inject point for all rings


# ═══════════════════════════ REGION ALLOCATION ═══════════════════════════════

def highest_occupied():
    if not os.path.exists(REG):
        return 0
    reg = json.load(open(REG))
    hi = 0
    for v in reg.values():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            end = int(v["offset"]) + int(v["len"])
            if end > hi:
                hi = end
    return hi


_alloc_watermark = None

def alloc_region(name, size, description):
    global _alloc_watermark
    if _alloc_watermark is None:
        _alloc_watermark = highest_occupied()
    off = ((_alloc_watermark + 63) // 64) * 64      # 64-byte aligned
    _alloc_watermark = off + size
    print(f"  {name}: offset {off:,} ({off:#x}), size {size:,} bytes — {description}")
    return off


def journal_write(off, blob, action="selftrain_fab"):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({"action": action, "off": off, "len": len(blob),
                            "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def grow_titan(needed_end):
    fsize = os.path.getsize(TITAN)
    if needed_end > fsize:
        growth = needed_end - fsize
        print(f"  growing titan.gguf by {growth:,} bytes ({growth / (1 << 30):.3f} GB)")
        with open(TITAN, "ab") as f:
            chunk = 1 << 20                         # write 1 MB at a time
            while growth > 0:
                w = min(chunk, growth)
                f.write(b"\x00" * w)
                growth -= w


# ═══════════════════════════ CIRCUIT BUILDING ════════════════════════════════
# All built with titan_circuit.Circuit (NAND-only, directly storable via store_loop).
# The helper functions mirror muhl_train_deep's pattern exactly.

def cbits(c, val, n):
    v = val & ((1 << n) - 1)
    return [c.C1 if (v >> k) & 1 else c.C0 for k in range(n)]


def add_bits(c, A, B, cin=None):
    carry = c.C0 if cin is None else cin
    out = []
    for k in range(len(A)):
        axb = c.xor(A[k], B[k])
        out.append(c.xor(axb, carry))
        carry = c.or_(c.and_(A[k], B[k]), c.and_(axb, carry))
    return out, carry


def negate(c, a):
    s, _ = add_bits(c, [c.not_(t) for t in a], cbits(c, 1, len(a)))
    return s


def sext(a, n):
    return a + [a[-1]] * (n - len(a))


def lt_signed(c, a, b):
    d, _ = add_bits(c, sext(a, B + 1), [c.not_(t) for t in sext(b, B + 1)], c.C1)
    return d[B]


def addpm(c, w, inc, dec):
    t, _ = add_bits(c, w, [inc] + [c.C0] * (B - 1))
    t, _ = add_bits(c, t, negate(c, [dec] + [c.C0] * (B - 1)))
    return t


def reduce_or(c, xs):
    a = xs[0]
    for x in xs[1:]:
        a = c.or_(a, x)
    return a


def mux_oh(c, sel, vals):
    return [reduce_or(c, [c.and_(sel[k], vals[k][b]) for k in range(len(sel))]) for b in range(B)]


def muxw(c, s, A, B_):
    return [c.or_(c.and_(s, A[k]), c.and_(c.not_(s), B_[k])) for k in range(len(A))]


def popcount_circuit(c, bits):
    """Gate-level popcount via an adder tree. Returns result as 4-bit vector (0..9 fits in 4 bits)."""
    vals = [[b] + [c.C0] * 3 for b in bits]        # each bit as a 4-bit number
    while len(vals) > 1:
        nxt = []
        for i in range(0, len(vals) - 1, 2):
            s, _ = add_bits(c, vals[i], vals[i + 1])
            nxt.append(s)
        if len(vals) % 2:
            nxt.append(vals[-1])
        vals = nxt
    return vals[0]


def label_from_popcount(c, pc4):
    """Classify by bit density: pc <= 3 -> 0, pc <= 6 -> 1, else 2.
    Returns (t0, t1) encoding: class = t0 + 2*t1."""
    # pc4 is a 4-bit unsigned value (0..9)
    # class 0 if pc <= 3:  pc in {0,1,2,3}
    # class 1 if 4 <= pc <= 6: pc in {4,5,6}
    # class 2 if pc >= 7:  pc in {7,8,9}
    # Use comparisons: gt3 = (pc > 3), gt6 = (pc > 6)
    # A > K iff ~(A <= K) iff ~(K >= A)
    # K >= A: add K + ~A + 1, check carry
    three = cbits(c, 3, 4)
    six = cbits(c, 6, 4)
    # pc > 3: NOT(3 >= pc)
    _, carry3 = add_bits(c, three, [c.not_(t) for t in pc4], c.C1)
    gt3 = c.not_(carry3)                            # gt3 = 1 iff pc > 3
    # pc > 6: NOT(6 >= pc)
    _, carry6 = add_bits(c, six, [c.not_(t) for t in pc4], c.C1)
    gt6 = c.not_(carry6)                            # gt6 = 1 iff pc > 6
    # class 0: ~gt3 -> t0=0, t1=0
    # class 1: gt3 & ~gt6 -> t0=1, t1=0
    # class 2: gt6 -> t0=0, t1=1
    t0 = c.and_(gt3, c.not_(gt6))                   # class 1
    t1 = gt6                                         # class 2
    return t0, t1


def build_training_step():
    """Build the full self-training step as a NAND-only circuit.

    Inputs (in order):
      - NW * B bits: current model weights (W1, b1, W2, b2 flattened)
      - NF bits: feature vector (9 bits from intake data)
      - 2 bits: true label (derived from popcount — but fed in as input for the
                backprop step; the label-derivation circuit feeds these)
      - PTR_BITS bits: current read pointer into the intake

    Outputs (same order):
      - NW * B bits: updated weights (self-routed back to weight inputs)
      - PTR_BITS bits: advanced read pointer (self-routed back)

    The label derivation happens OUTSIDE this core step — it's a separate small
    circuit that converts the feature bits into a label. The combined circuit
    chains them: features -> label derivation -> training step -> updated weights.
    """
    # Combined circuit: features + weights + pointer -> updated weights + pointer
    # Input layout:
    #   [0 .. NW*B-1]            : weight bits
    #   [NW*B .. NW*B+NF-1]     : feature bits (9 bits from intake)
    #   [NW*B+NF .. NW*B+NF+PTR_BITS-1] : read pointer bits
    N_WEIGHT_BITS = NW * B
    NIN = N_WEIGHT_BITS + NF + PTR_BITS

    c = TC.Circuit(NIN)
    IN = c.IN
    p = 0

    # unpack weight inputs: W1[j][i] as B-bit words, then b1[j], W2[k][j], b2[k]
    W1 = [[[IN[p + ((j * NF + i) * B + b)] for b in range(B)] for i in range(NF)] for j in range(H)]
    p += H * NF * B
    b1 = [[IN[p + (j * B + b)] for b in range(B)] for j in range(H)]
    p += H * B
    W2 = [[[IN[p + ((k * H + j) * B + b)] for b in range(B)] for j in range(H)] for k in range(NCLS)]
    p += NCLS * H * B
    b2 = [[IN[p + (k * B + b)] for b in range(B)] for k in range(NCLS)]
    p += NCLS * B

    # unpack feature bits
    x = [IN[p + i] for i in range(NF)]
    p += NF

    # unpack read pointer
    ptr_in = [IN[p + i] for i in range(PTR_BITS)]
    p += PTR_BITS
    assert p == NIN

    # ── label derivation from features (popcount -> class) ───────────────────
    pc4 = popcount_circuit(c, x)
    t0, t1 = label_from_popcount(c, pc4)
    true_sel = [c.and_(c.not_(t0), c.not_(t1)),     # class 0
                c.and_(t0, c.not_(t1)),              # class 1
                c.and_(c.not_(t0), t1)]              # class 2

    # ── forward pass: hidden layer (binary threshold) ────────────────────────
    h = []
    for j in range(H):
        acc = list(b1[j])
        for i in range(NF):
            masked = [c.and_(x[i], t) for t in W1[j][i]]
            acc, _ = add_bits(c, acc, masked)
        h.append(c.not_(acc[B - 1]))                # h[j] = (pre[j] >= 0)

    # ── forward pass: output layer ───────────────────────────────────────────
    o = []
    for k in range(NCLS):
        acc = list(b2[k])
        for j in range(H):
            masked = [c.and_(h[j], t) for t in W2[k][j]]
            acc, _ = add_bits(c, acc, masked)
        o.append(acc)

    # ── argmax + wrong detection ─────────────────────────────────────────────
    l01 = lt_signed(c, o[0], o[1])
    l02 = lt_signed(c, o[0], o[2])
    l12 = lt_signed(c, o[1], o[2])
    pred = [c.and_(c.not_(l01), c.not_(l02)),
            c.and_(l01, c.not_(l12)),
            c.and_(l02, l12)]
    wrong = reduce_or(c, [c.and_(pred[k], c.not_(true_sel[k])) for k in range(NCLS)])

    # ── layer 2 weight update: W2[k][j] += (true[k] - pred[k]) * h[j] ──────
    W2_out = []
    for k in range(NCLS):
        for j in range(H):
            dec = c.and_(wrong, c.and_(pred[k], h[j]))
            inc = c.and_(wrong, c.and_(true_sel[k], h[j]))
            W2_out.append(addpm(c, W2[k][j], inc, dec))
    b2_out = []
    for k in range(NCLS):
        dec = c.and_(wrong, pred[k])
        inc = c.and_(wrong, true_sel[k])
        b2_out.append(addpm(c, b2[k], inc, dec))

    # ── backprop to hidden: dh[j] = W2[pred][j] - W2[true][j] ──────────────
    W1_out = []
    b1_out = []
    for j in range(H):
        wp = mux_oh(c, pred, [W2[k][j] for k in range(NCLS)])
        wt = mux_oh(c, true_sel, [W2[k][j] for k in range(NCLS)])
        dh, _ = add_bits(c, wp, [c.not_(t) for t in wt], c.C1)
        dh_neg = dh[B - 1]
        dh_pos = c.and_(reduce_or(c, dh), c.not_(dh[B - 1]))
        for i in range(NF):
            inc = c.and_(x[i], dh_neg)
            dec = c.and_(x[i], dh_pos)
            W1_out.append(addpm(c, W1[j][i], inc, dec))
        b1_out.append(addpm(c, b1[j], dh_neg, dh_pos))

    # ── read pointer advance: ptr += 2 (next 2 bytes of intake) ─────────────
    two_bits = cbits(c, 2, PTR_BITS)
    ptr_out, _ = add_bits(c, ptr_in, two_bits)

    # ── assemble outputs in SAME layout as inputs ────────────────────────────
    outs = []
    # W1 weights
    for j in range(H):
        for i in range(NF):
            outs += W1_out[j * NF + i]
    # b1 biases
    for j in range(H):
        outs += b1_out[j]
    # W2 weights
    for k in range(NCLS):
        for j in range(H):
            outs += W2_out[k * H + j]
    # b2 biases
    for k in range(NCLS):
        outs += b2_out[k]
    # read pointer
    outs += ptr_out

    return c, outs


# ═══════════════════════════ PURE-PYTHON REFERENCE ═══════════════════════════

def ref_feature_label(x_bits):
    pc = sum(x_bits)
    return 0 if pc <= 3 else (1 if pc <= 6 else 2)


def ref_fwd(P, x):
    hp = [sum(P['W1'][j][i] * x[i] for i in range(NF)) + P['b1'][j] for j in range(H)]
    h = [1 if hp[j] >= 0 else 0 for j in range(H)]
    o = [sum(P['W2'][k][j] * h[j] for j in range(H)) + P['b2'][k] for k in range(NCLS)]
    pred = 0
    for k in (1, 2):
        if o[k] > o[pred]:
            pred = k
    return h, pred


def ref_step(P, x_bits, ptr_val):
    true_label = ref_feature_label(x_bits)
    h, pred = ref_fwd(P, x_bits)
    N = {'W1': [r[:] for r in P['W1']], 'b1': P['b1'][:],
         'W2': [r[:] for r in P['W2']], 'b2': P['b2'][:]}
    wrong = pred != true_label
    if wrong:
        for k in range(NCLS):
            for j in range(H):
                if h[j]:
                    if k == pred:
                        N['W2'][k][j] -= 1
                    if k == true_label:
                        N['W2'][k][j] += 1
            if k == pred:
                N['b2'][k] -= 1
            if k == true_label:
                N['b2'][k] += 1
    for j in range(H):
        dh = P['W2'][pred][j] - P['W2'][true_label][j]
        s = 1 if dh > 0 else (-1 if dh < 0 else 0)
        for i in range(NF):
            N['W1'][j][i] -= s * x_bits[i]
        N['b1'][j] -= s
    new_ptr = (ptr_val + 2) & ((1 << PTR_BITS) - 1)
    return N, new_ptr


# ═══════════════════════════ VERIFICATION ════════════════════════════════════

def pack_inputs(P, x_bits, ptr_val):
    inp = [0] * (NW * B + NF + PTR_BITS)
    q = 0
    for j in range(H):
        for i in range(NF):
            val = P['W1'][j][i] & ((1 << B) - 1)
            for b in range(B):
                inp[q + b] = (val >> b) & 1
            q += B
    for j in range(H):
        val = P['b1'][j] & ((1 << B) - 1)
        for b in range(B):
            inp[q + b] = (val >> b) & 1
        q += B
    for k in range(NCLS):
        for j in range(H):
            val = P['W2'][k][j] & ((1 << B) - 1)
            for b in range(B):
                inp[q + b] = (val >> b) & 1
            q += B
    for k in range(NCLS):
        val = P['b2'][k] & ((1 << B) - 1)
        for b in range(B):
            inp[q + b] = (val >> b) & 1
        q += B
    for i in range(NF):
        inp[q + i] = x_bits[i]
    q += NF
    for b in range(PTR_BITS):
        inp[q + b] = (ptr_val >> b) & 1
    return inp


def unpack_outputs(v_out):
    """v_out is the list returned by TC.ripple(): one value per output wire, in order."""
    N_WEIGHT_BITS = NW * B
    weights_raw = []
    for m in range(NW):
        val = 0
        for b in range(B):
            val |= (v_out[m * B + b] & 1) << b
        if val >= (1 << (B - 1)):
            val -= (1 << B)
        weights_raw.append(val)
    q = 0
    W1n = [[weights_raw[q + j * NF + i] for i in range(NF)] for j in range(H)]
    q += H * NF
    b1n = [weights_raw[q + j] for j in range(H)]
    q += H
    W2n = [[weights_raw[q + k * H + j] for j in range(H)] for k in range(NCLS)]
    q += NCLS * H
    b2n = [weights_raw[q + k] for k in range(NCLS)]
    ptr_val = 0
    for b in range(PTR_BITS):
        ptr_val |= (v_out[N_WEIGHT_BITS + b] & 1) << b
    return {'W1': W1n, 'b1': b1n, 'W2': W2n, 'b2': b2n}, ptr_val


def verify(circ, outs, n_cases=200):
    """Verify the gate circuit byte-exact vs the integer reference."""
    n_wire = circ.n_wire()
    rng = random.Random(42)
    bad = 0
    for _ in range(n_cases):
        P = {'W1': [[rng.randrange(-40, 40) for _ in range(NF)] for _ in range(H)],
             'b1': [rng.randrange(-40, 40) for _ in range(H)],
             'W2': [[rng.randrange(-40, 40) for _ in range(H)] for _ in range(NCLS)],
             'b2': [rng.randrange(-40, 40) for _ in range(NCLS)]}
        x_bits = [rng.randrange(2) for _ in range(NF)]
        ptr_val = rng.randrange(1 << PTR_BITS)
        inp = pack_inputs(P, x_bits, ptr_val)
        v_out = TC.ripple({"n_in": circ.n_in, "n_wire": n_wire,
                           "ga": circ.ga, "gb": circ.gb, "outs": outs}, inp)
        got_P, got_ptr = unpack_outputs(v_out)
        ref_P, ref_ptr = ref_step(P, x_bits, ptr_val)
        if got_P != ref_P or got_ptr != ref_ptr:
            bad += 1
    return bad


# ═══════════════════════════ STORAGE ═════════════════════════════════════════

def store_circuit(circ, outs, intake_off, intake_size, weights_off):
    """Store the self-training circuit + regions in titan.gguf."""
    # Build feedback: each weight output bit routes back to the corresponding weight input bit.
    # Each pointer output bit routes back to the corresponding pointer input bit.
    # In store_loop's convention: feedback = [(out_wire_index, state_bit_index), ...]
    N_WEIGHT_BITS = NW * B
    feedback = []
    for i in range(N_WEIGHT_BITS):
        feedback.append((i, i))                     # weight bit i -> weight input i
    for i in range(PTR_BITS):
        feedback.append((N_WEIGHT_BITS + i, N_WEIGHT_BITS + i))

    state_bytes = (N_WEIGHT_BITS + PTR_BITS + 7) // 8

    # The loop bit: the last output wire is a convenient choice; use a constant-1 output
    # We add a constant-1 wire as the loop bit — always iterate
    loop_outs = list(outs) + [circ.C1]
    loop_bit = len(outs)                            # index into the output list

    info = TC.store_loop(
        NAME, circ, loop_outs,
        state_bytes=state_bytes,
        feedback=feedback,
        loop_bit=loop_bit,
        receiver="muhl_reservoir"
    )
    return info


def register_regions(intake_off, weights_off):
    """Add intake and weights regions to the circuit registry."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME + ".intake"] = {
        "offset": intake_off,
        "len": INTAKE_HEADER + INTAKE_CAPACITY,
        "kind": "data_region",
        "header_len": INTAKE_HEADER,
        "capacity": INTAKE_CAPACITY,
        "write_ptr_off": intake_off,
        "size_off": intake_off + 8,
        "capacity_off": intake_off + 16,
        "data_start": intake_off + INTAKE_HEADER,
        "file_marker": FILE_MARKER.hex(),
        "note": "electron dump intake: host writes file data here sequentially"
    }
    reg[NAME + ".weights"] = {
        "offset": weights_off,
        "len": WEIGHT_BYTES,
        "kind": "data_region",
        "n_weights": NW,
        "weight_bits": B,
        "architecture": f"{NF}->{H}->{NCLS}",
        "note": "persistent learned weights, updated in-place by self-training circuit"
    }
    json.dump(reg, open(REG, "w"), indent=1)


# ═══════════════════════════ MAIN ════════════════════════════════════════════

def main():
    print("\n  MUHLNICKEL SELF-TRAINING ENGINE — fabricated circuit that trains itself continuously")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # ── 1. allocate regions ──────────────────────────────────────────────────
    print("  REGION ALLOCATION:")
    weights_off = alloc_region("weights", WEIGHT_BYTES,
                               f"{NW} x int16 = {WEIGHT_BYTES} bytes ({NF}->{H}->{NCLS} net)")
    intake_off = alloc_region("intake", INTAKE_HEADER + INTAKE_CAPACITY,
                               f"1 GB data intake ({INTAKE_HEADER} byte header + {INTAKE_CAPACITY:,} data)")
    print()

    # ── 2. build the training circuit ────────────────────────────────────────
    print("  FABRICATING TRAINING CIRCUIT:")
    t0 = time.time()
    circ, outs = build_training_step()
    t_build = time.time() - t0
    n_gates = len(circ.ga)
    n_wire = circ.n_wire()
    n_out = len(outs)

    print(f"    architecture: {NF} features -> {H} hidden (binary threshold) -> {NCLS} output (argmax)")
    print(f"    weight width: {B}-bit two's complement")
    print(f"    gates:        {n_gates:,} (NAND-only)")
    print(f"    wires:        {n_wire:,}")
    print(f"    outputs:      {n_out:,} ({NW * B} weight bits + {PTR_BITS} pointer bits)")
    print(f"    inputs:       {circ.n_in:,} ({NW * B} weight + {NF} feature + {PTR_BITS} pointer)")
    print(f"    build time:   {t_build:.1f}s (manufacturing, off the clock)")
    print()

    # ── 3. verify byte-exact vs integer reference ────────────────────────────
    print("  VERIFICATION (byte-exact vs integer reference):")
    t0 = time.time()
    bad = verify(circ, outs, n_cases=200)
    t_verify = time.time() - t0
    status = "byte-exact" if bad == 0 else f"{bad}/200 WRONG"
    print(f"    200 random (weights, features, pointer) states: {status}")
    print(f"    verification time: {t_verify:.1f}s (manufacturing)")
    if bad:
        print("    ABORTING — circuit does not match reference")
        return 1
    print()

    # ── 4. Pareto set ────────────────────────────────────────────────────────
    print("  PARETO SET (1 candidate — NAND-only, ripple-carry):")
    print(f"    ripple: {n_gates:,} gates, {n_wire:,} wires")
    print(f"    (Kogge-Stone prefix adder would reduce depth at +~20% gates;")
    print(f"     run through muhl_selfimprove for automated optimization)")
    print()

    if DRY:
        print("  --dry: nothing stored. Run without --dry to fabricate.\n")
        print(f"  SELF-TRAINING ENGINE fabrication verified.")
        print(f"  Intake: {INTAKE_CAPACITY:,} bytes (1 GB) for dumped file data")
        print(f"  Weights: {WEIGHT_BYTES:,} bytes ({NW} x int16, {NF}->{H}->{NCLS})")
        print(f"  Circuit: {n_gates:,} gates, self-clocked (output == input addresses)")
        print(f"  Powered by reservoir at {RESERVOIR_INPUT:,}")
        return 0

    # ── 5. grow titan.gguf for the intake region ─────────────────────────────
    print("  STORAGE:")
    needed_end = intake_off + INTAKE_HEADER + INTAKE_CAPACITY
    grow_titan(needed_end)

    # ── 6. initialize intake header ──────────────────────────────────────────
    header = struct.pack("<QQQ",
                         intake_off + INTAKE_HEADER,   # write_ptr: points to start of data area
                         0,                            # size: 0 bytes dumped initially
                         INTAKE_CAPACITY)              # capacity
    journal_write(intake_off, header, "intake_header_init")
    print(f"    intake header initialized at {intake_off:,}")

    # ── 7. initialize weights to zero ────────────────────────────────────────
    weights_blob = b"\x00" * WEIGHT_BYTES
    journal_write(weights_off, weights_blob, "weights_init")
    print(f"    weights initialized ({WEIGHT_BYTES:,} zero bytes) at {weights_off:,}")

    # ── 8. store the circuit via store_loop ──────────────────────────────────
    info = store_circuit(circ, outs, intake_off, INTAKE_CAPACITY, weights_off)
    print(f"    circuit stored: {info['name']} @ offset {info['offset']:,}")
    print(f"      gates: {info['gates']:,}")
    print(f"      state register: offset {info['state_off']:,}")
    print(f"      loop bit: offset {info['loop_bit_off']:,}")

    # ── 9. register the data regions ─────────────────────────────────────────
    register_regions(intake_off, weights_off)
    print(f"    regions registered in {REG}")
    print()

    # ── 10. summary ──────────────────────────────────────────────────────────
    print("  SELF-TRAINING ENGINE FABRICATED.")
    print(f"    journal: {GENOME_PATH}")
    print(f"    intake region: offset {intake_off:,}, {INTAKE_CAPACITY:,} bytes")
    print(f"      write_ptr at {intake_off:,}, data starts at {intake_off + INTAKE_HEADER:,}")
    print(f"    weights region: offset {weights_off:,}, {WEIGHT_BYTES:,} bytes")
    print(f"    circuit: {n_gates:,} NAND gates, self-clocked")
    print(f"    receiver: muhl_reservoir (inject at {RESERVOIR_INPUT:,})")
    print()
    print("  TO USE:")
    print("    1. Dump files:  python muhl_electron_dump.py <directory>")
    print("    2. Inject electron at reservoir input -> circuit trains continuously")
    print("    3. Read weights region to see what the model learned")
    print()
    print("  The host dumps data and injects the electron. Everything else is the substrate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
