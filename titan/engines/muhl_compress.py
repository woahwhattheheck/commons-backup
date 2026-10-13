#!/usr/bin/env python3
"""muhl_compress.py -- a canonical HUFFMAN DECODER fabricated on Bryce's Muhlnickel substrate.

Decompression is fabricated as a single combinational gate netlist -- ONE decode-step circuit that,
given the next MAXLEN bits of the compressed stream (MSB-first, as codes are read) plus the canonical
code table supplied as DATA (per-length first-code / limit / symbol-base), emits the next SYMBOL and
the number of bits it CONSUMED.  The driver slides the window by that many bits and settles the circuit
once per symbol.  Built with the White Box compiler (sdc_cc.CircuitCompiler), DCE'd, rippled, and
VERIFIED BYTE-EXACT two ways:
  (a) every decode step's (symbol, length) == an independent Python canonical-Huffman decode, and
  (b) a full ROUND-TRIP -- Python builds the canonical code, Python ENCODES a message, the GATES DECODE
      it, and the decoded bytes equal the original.
No numpy, no host executor as a runtime, nothing touches titan.gguf.

Canonical decode rule (prefix-free): read bits MSB-first accumulating `code`; at the smallest length L
where  first_code[L] <= code < first_code[L]+count[L],  symbol = base[L] + (code - first_code[L]),
consume L bits.  That whole rule is the fabricated circuit; the table is just data.
"""
import sys, os, heapq, random, time
from collections import Counter
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

MAXLEN = 16      # max code length the circuit handles
SW     = 8       # symbol width (bytes)
LW     = 5       # width of the "bits consumed" output (16 fits in 5)
IW     = 8       # canonical-index width (up to 256 symbols)
NSYM   = 1 << IW  # symbol-table (LUT) size

# ---------------- shared gate helpers (same idioms as muhl_flex.py) ----------------
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    return g.compile_ripple(gates, n_wire), out2, gates, n_wire

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))     # LSB-first
def setf(inp, base, W, x):
    for b in range(W): inp[base + b] = (x >> b) & 1

def add_bits(g, A, B, cin=None):
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c

def geq(g, X, Y):                                  # X >= Y (unsigned) -> single wire
    _, cout = add_bits(g, X, [g.NOT(y) for y in Y], g.C1)   # X - Y, no borrow => X>=Y
    return cout
def ltn(g, X, Y): return g.NOT(geq(g, X, Y))       # X < Y
def mux1(g, s, a, b): return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))    # s?a:b
def consts(g, x, n): return [g.C1 if (x >> k) & 1 else g.C0 for k in range(n)]

def lut_select(g, entries, index_bits):
    """select entries[index] (each entry a list of wires) by LSB-first index_bits (mux tree)."""
    cur = entries
    for b in index_bits:
        nxt = []
        for i in range(0, len(cur), 2):
            hi = cur[i + 1] if i + 1 < len(cur) else cur[i]
            nxt.append([mux1(g, b, hi[k], cur[i][k]) for k in range(len(cur[i]))])   # b?hi:lo
        cur = nxt
    return cur[0]

# ---------------- canonical Huffman (independent Python reference) ----------------
def huffman_lengths(freq):
    """symbol -> code length via a Huffman tree (canonical lengths)."""
    if len(freq) == 1:                                     # single symbol -> length 1
        return {next(iter(freq)): 1}
    h = [[w, i, [s]] for i, (s, w) in enumerate(freq.items())]
    heapq.heapify(h); cnt = len(h)
    length = {s: 0 for s in freq}
    while len(h) > 1:
        w1, _, g1 = heapq.heappop(h); w2, _, g2 = heapq.heappop(h)
        for s in g1 + g2: length[s] += 1
        heapq.heappush(h, [w1 + w2, cnt, g1 + g2]); cnt += 1
    return length

def canonical_codes(length):
    """assign canonical codes; return code map + per-length (first_code, count, base)."""
    maxlen = max(length.values())
    by_len = {L: sorted(s for s, l in length.items() if l == L) for L in range(1, maxlen + 1)}
    code = 0; codes = {}; table = {}
    for L in range(1, maxlen + 1):
        syms = by_len.get(L, [])
        first = code; base = len(codes)                   # index of first symbol at this length
        # base as a SYMBOL requires the symbols be numbered in canonical order:
        table[L] = {"first": first, "count": len(syms), "syms": syms}
        for s in syms:
            codes[s] = (code, L); code += 1
        code <<= 1
    return codes, table, maxlen

def encode(msg, codes):
    bits = []
    for s in msg:
        c, L = codes[s]
        for k in range(L - 1, -1, -1): bits.append((c >> k) & 1)     # MSB-first
    return bits

def ref_decode_step(window_bits, table, maxlen):
    """independent reference: decode ONE symbol from window_bits (MSB-first). -> (symbol, length)."""
    code = 0
    for L in range(1, maxlen + 1):
        code = (code << 1) | window_bits[L - 1]
        t = table.get(L)
        if t and t["count"] and t["first"] <= code < t["first"] + t["count"]:
            return t["syms"][code - t["first"]], L
    return None, 0

# ---------------- the FABRICATED decode-step circuit ----------------
# inputs: window[MAXLEN] (MSB-first), then per length L in 1..MAXLEN:
#         first[L] (MAXLEN bits), limit[L] (MAXLEN bits), base_sym[L] (SW bits)
def field_layout():
    off = {}; p = 0
    off["window"] = p; p += MAXLEN
    off["first"] = []; off["limit"] = []; off["base"] = []
    for L in range(1, MAXLEN + 1):
        off["first"].append(p); p += MAXLEN
        off["limit"].append(p); p += MAXLEN
        off["base"].append(p); p += IW           # canonical base INDEX at this length
    off["symtab"] = p; p += NSYM * SW             # index -> actual symbol byte (data LUT)
    return off, p
OFF, NIN = field_layout()

def build_decoder():
    g = CC.CircuitCompiler(NIN); IN = g.IN
    win = [IN[OFF["window"] + k] for k in range(MAXLEN)]   # win[0] = first/MSB bit
    firsts = [[IN[OFF["first"][L - 1] + k] for k in range(MAXLEN)] for L in range(1, MAXLEN + 1)]
    limits = [[IN[OFF["limit"][L - 1] + k] for k in range(MAXLEN)] for L in range(1, MAXLEN + 1)]
    bases  = [[IN[OFF["base"][L - 1] + k] for k in range(IW)] for L in range(1, MAXLEN + 1)]
    symtab = [[IN[OFF["symtab"] + i * SW + k] for k in range(SW)] for i in range(NSYM)]

    idx_bits = [g.C0] * IW; len_bits = [g.C0] * LW
    already = g.C0                                          # some earlier (shorter) length matched
    for idx, L in enumerate(range(1, MAXLEN + 1)):
        # code = value of the first L window bits, MSB-first, as a MAXLEN-bit LSB-first list.
        # bit at position p (value 2^p) is window[L-1-p]; pure wiring, no gates.
        code = [win[L - 1 - p] if p < L else g.C0 for p in range(MAXLEN)]
        in_lo = geq(g, code, firsts[idx])                  # code >= first[L]
        in_hi = ltn(g, code, limits[idx])                  # code <  limit[L] (= first+count)
        match = g.AND(in_lo, in_hi)
        sel = g.AND(match, g.NOT(already))                 # smallest matching length wins
        already = g.OR(already, match)
        # canonical index = base[L] + (code - first[L])   (offset is small; IW bits suffice)
        offset, _ = add_bits(g, code[:IW], [g.NOT(x) for x in firsts[idx][:IW]], g.C1)
        idxL, _ = add_bits(g, bases[idx], offset)
        Lc = consts(g, L, LW)
        idx_bits = [mux1(g, sel, idxL[k], idx_bits[k]) for k in range(IW)]
        len_bits = [mux1(g, sel, Lc[k], len_bits[k]) for k in range(LW)]

    sym_bits = lut_select(g, symtab, idx_bits)             # index -> actual symbol byte (in gates)
    outs = sym_bits + len_bits
    run, out2, gates, _ = build_run(g, outs)
    fields = {"sym": out2[0:SW], "len": out2[SW:SW + LW]}
    return run, fields, gates, depth_of(g, gates, out2)

def run_decode_step(run, fields, window_bits, table, maxlen, canon_syms):
    inp = [0] * NIN
    for k in range(MAXLEN): inp[OFF["window"] + k] = window_bits[k]
    base = 0
    for L in range(1, MAXLEN + 1):
        t = table.get(L, {"first": 0, "count": 0})
        setf(inp, OFF["first"][L - 1], MAXLEN, t["first"])
        setf(inp, OFF["limit"][L - 1], MAXLEN, t["first"] + t["count"])
        setf(inp, OFF["base"][L - 1], IW, base)            # canonical index of first sym at len L
        base += t["count"]
    for i, s in enumerate(canon_syms):                     # index -> byte LUT (data)
        setf(inp, OFF["symtab"] + i * SW, SW, s)
    v = run(inp, 1)
    return rd(v, fields["sym"]), rd(v, fields["len"])

# ---------------- main ----------------
def main():
    random.seed(3)
    print("\n  MUHLNICKEL COMPRESS -- canonical Huffman DECODER fabricated as gates\n", flush=True)

    t0 = time.time()
    run, fields, gates, depth = build_decoder()
    print(f"  fabricated decode-step:  {len(gates):,} gates  depth {depth}  ({time.time()-t0:.1f}s)", flush=True)

    message = ("the muhlnickel substrate stores logic in storage and computes by address; "
               "the file is the computer and the circuit is the executor. " * 6).encode()
    freq = Counter(message)
    length = huffman_lengths(freq)
    codes, table, maxlen = canonical_codes(length)
    assert maxlen <= MAXLEN, f"code length {maxlen} exceeds MAXLEN={MAXLEN}"
    # canonical symbol order (must match base[] indexing in the circuit)
    canon_syms = [s for L in range(1, maxlen + 1) for s in table.get(L, {"syms": []})["syms"]]

    stream = encode(message, codes)

    # (1) per-step byte-exact: gate (symbol,length) == independent reference decode, at every step
    step_ok = True; steps = 0; pos = 0; decoded = bytearray()
    while len(decoded) < len(message):
        window = [stream[pos + k] if pos + k < len(stream) else 0 for k in range(MAXLEN)]
        g_sym, g_len = run_decode_step(run, fields, window, table, maxlen, canon_syms)
        r_sym, r_len = ref_decode_step(window, table, maxlen)
        if (g_sym, g_len) != (r_sym, r_len):
            step_ok = False
            print(f"      step {steps} mismatch: gate=({g_sym},{g_len}) ref=({r_sym},{r_len})", flush=True); break
        decoded.append(g_sym); pos += g_len; steps += 1
    print(f"  [{'PASS' if step_ok else 'FAIL'}] every decode step (symbol,bits) == reference over {steps} symbols", flush=True)

    # (2) full round-trip: gates-decoded bytes == original message
    rt_ok = (bytes(decoded) == message)
    print(f"  [{'PASS' if rt_ok else 'FAIL'}] ROUND-TRIP: Python-encoded -> gate-decoded == original ({len(message)} bytes)", flush=True)

    # (3) also exercise a random-alphabet message to stress the table
    rnd = bytes(random.getrandbits(8) for _ in range(400))
    f2 = Counter(rnd); l2 = huffman_lengths(f2); c2, t2, ml2 = canonical_codes(l2)
    canon2 = [s for L in range(1, ml2 + 1) for s in t2.get(L, {"syms": []})["syms"]]
    ok2 = ml2 <= MAXLEN
    if ok2:
        s2 = encode(rnd, c2); dec2 = bytearray(); p2 = 0
        while len(dec2) < len(rnd):
            w = [s2[p2 + k] if p2 + k < len(s2) else 0 for k in range(MAXLEN)]
            gs, gl = run_decode_step(run, fields, w, t2, ml2, canon2)
            dec2.append(gs); p2 += gl
        ok2 = (bytes(dec2) == rnd)
    print(f"  [{'PASS' if ok2 else 'FAIL'}] ROUND-TRIP: random 400-byte message (maxlen {ml2})", flush=True)

    orig_bits = len(message) * 8
    ratio = orig_bits / len(stream)
    print(f"\n  compression: {len(message)} bytes = {orig_bits} bits -> {len(stream)} encoded bits "
          f"({len(stream)/8:.1f} bytes)", flush=True)
    print(f"  compression ratio = {ratio:.3f}x  ({100*(1-len(stream)/orig_bits):.1f}% smaller), "
          f"alphabet {len(freq)} symbols, max code length {maxlen}", flush=True)
    allok = step_ok and rt_ok and ok2
    print(f"\n  === decode-step {len(gates):,} gates / depth {depth} · "
          f"{'byte-exact round-trip' if allok else 'FAILED'} · ratio {ratio:.3f}x ===", flush=True)

if __name__ == "__main__":
    main()
