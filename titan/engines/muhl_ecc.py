#!/usr/bin/env python3
"""muhl_ecc.py -- SELF-CORRECTING MEMORY as gates, fabricated on Bryce's Muhlnickel substrate.

A Hamming single-error-correcting code, built entirely as NAND/AND/OR/XOR/NOT gates with the
White Box compiler (sdc_cc.CircuitCompiler): an ENCODER (data -> codeword with parity) and a
single-error-correcting DECODER (received word -> syndrome -> locate-and-flip -> recovered data).

Both Hamming(7,4) and Hamming(15,11) are fabricated. Correctness is proven the Muhlnickel way:
BYTE-EXACT and EXHAUSTIVE -- for EVERY data word and EVERY single-bit error pattern (including the
no-error case), the gate encoder + gate decoder recover the original data bits with zero mismatch.
No numpy, no host executor as runtime, no touching titan.gguf. Fabrication-time synthesis only.

Practical: this is self-healing storage. Bake the encoder over a block, and any single-bit rot in
a codeword is silently corrected on read by the decoder circuit -- the file repairs itself by address.
"""
import sys, os, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---------- shared White Box helpers (same conventions as muhl_flex.py) ----------
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return run, out2, gates, n_wire

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1

def xor_tree(g, wires):
    """balanced XOR reduction (shallow) of a list of wires -> single wire."""
    if not wires: return g.C0
    cur = list(wires)
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur) - 1, 2):
            nxt.append(g.XOR(cur[i], cur[i + 1]))
        if len(cur) & 1:
            nxt.append(cur[-1])
        cur = nxt
    return cur[0]

def eqbit(g, w, want):
    """wire == want(0/1) as a gate: identity if want=1, NOT if want=0."""
    return w if want else g.NOT(w)

# ---------- generic Hamming(2^p-1, 2^p-1-p) as gates ----------
def hamming_layout(p):
    n = (1 << p) - 1                       # total codeword positions, 1..n
    parity_pos = [1 << j for j in range(p)]
    data_pos = [q for q in range(1, n + 1) if q not in parity_pos]
    k = len(data_pos)
    return n, k, parity_pos, data_pos

def build_encoder(p):
    """inputs: k data bits (LSB-first for data_pos order). output: n codeword bits (position 1..n)."""
    n, k, parity_pos, data_pos = hamming_layout(p)
    g = CC.CircuitCompiler(k); IN = g.IN
    data = {q: IN[i] for i, q in enumerate(data_pos)}   # wire per data position
    code = [None] * (n + 1)                              # 1-indexed
    for q in data_pos:
        code[q] = data[q]
    for j in range(p):
        pj = 1 << j
        members = [data[q] for q in data_pos if (q >> j) & 1]  # data positions covered by parity j
        code[pj] = xor_tree(g, members)
    outs = [code[q] for q in range(1, n + 1)]            # position 1..n, LSB-first
    run, out2, gates, _ = build_run(g, outs)
    return g, run, out2, gates, (n, k, parity_pos, data_pos)

def build_decoder(p):
    """inputs: n received bits (position 1..n). outputs: k recovered data bits (data_pos order)."""
    n, k, parity_pos, data_pos = hamming_layout(p)
    g = CC.CircuitCompiler(n); IN = g.IN
    r = {q: IN[q - 1] for q in range(1, n + 1)}          # wire per position
    # syndrome bit j = XOR of all positions q whose index has bit j set
    syn = []
    for j in range(p):
        members = [r[q] for q in range(1, n + 1) if (q >> j) & 1]
        syn.append(xor_tree(g, members))
    # indicator per position: syndrome (as a p-bit number) == position index
    corrected = {}
    for q in range(1, n + 1):
        m = g.C1
        for j in range(p):
            m = g.AND(m, eqbit(g, syn[j], (q >> j) & 1))
        corrected[q] = g.XOR(r[q], m)                    # flip the located bit
    outs = [corrected[q] for q in data_pos]              # recovered data, data_pos order
    run, out2, gates, _ = build_run(g, outs)
    return g, run, out2, gates, (n, k, parity_pos, data_pos)

def verify_hamming(p, label):
    ge, enc, enc_out, enc_gates, layout = build_encoder(p)
    gd, dec, dec_out, dec_gates, _ = build_decoder(p)
    n, k, parity_pos, data_pos = layout
    enc_depth = depth_of(ge, enc_gates, enc_out)
    dec_depth = depth_of(gd, dec_gates, dec_out)

    total_data = 1 << k
    ndata = total_data                                   # exhaustive over ALL data words
    ok = True
    checked = 0
    corrected_cases = 0
    fail = None
    for d in range(ndata):
        # encode via gates
        enc_in = [(d >> i) & 1 for i in range(k)]        # data_pos order, LSB-first
        ev = enc(enc_in, 1)
        codeword = [bit(ev, w) for w in enc_out]         # position 1..n bits
        # independent Python reference codeword
        ref_code = [0] * (n + 1)
        dbits = {q: enc_in[i] for i, q in enumerate(data_pos)}
        for q in data_pos: ref_code[q] = dbits[q]
        for j in range(p):
            ref_code[1 << j] = 0
            for q in data_pos:
                if (q >> j) & 1: ref_code[1 << j] ^= dbits[q]
        if codeword != [ref_code[q] for q in range(1, n + 1)]:
            ok = False; fail = ("encode", d); break
        # for EVERY single-error pattern e (0 = no error, 1..n = flip that position) -> decode recovers data
        for e in range(0, n + 1):
            recv = list(codeword)
            if e >= 1:
                recv[e - 1] ^= 1                          # inject a single-bit error at position e
            dv = dec(recv, 1)
            got = [bit(dv, w) for w in dec_out]           # recovered data, data_pos order
            if got != enc_in:
                ok = False; fail = ("decode", d, e, got, enc_in); break
            checked += 1
            if e >= 1: corrected_cases += 1
        if not ok: break

    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] Hamming({n},{k})  encoder {len(enc_gates):>4} gates/depth {enc_depth} + "
          f"decoder {len(dec_gates):>4} gates/depth {dec_depth}", flush=True)
    print(f"         EXHAUSTIVE: {total_data} data words x {n+1} error patterns = {checked:,} "
          f"decode checks, ALL byte-exact ({corrected_cases:,} single-bit errors CORRECTED)", flush=True)
    if not ok:
        print(f"         !!! FAIL detail: {fail}", flush=True)
    return ok, len(enc_gates) + len(dec_gates)

def main():
    print("\n  MUHLNICKEL ECC -- self-correcting memory fabricated as gates, verified exhaustive/byte-exact\n", flush=True)
    total_gates = 0; allok = True
    for p, label in ((3, "(7,4)"), (4, "(15,11)")):
        t = time.time()
        ok, ng = verify_hamming(p, label)
        total_gates += ng; allok &= ok
        print(f"         ({time.time()-t:.2f}s)\n", flush=True)
    print(f"  === {'ALL PASS' if allok else 'FAILURE'} -- single-error correction proven exhaustively "
          f"| {total_gates:,} total gates fabricated ===", flush=True)

if __name__ == "__main__":
    main()
