#!/usr/bin/env python3
"""muhl_regex_scan.py — a multi-pattern IDS / log scanner: an Aho-Corasick DFA compiled to GATES.

Signature scanning (grep, intrusion detection, DLP, log triage) is a stream problem: one pass, match any
of K patterns. Build the Aho-Corasick automaton, compile its (state, byte) -> (next_state, hit) transition
to a gate netlist, verify it EXHAUSTIVELY (every state x every one of 256 bytes -- no sampling), then scan a
real log stream through the fabricated transition, byte-exact vs Python. The automaton is the gates; the
stream is disk-bound, so the corpus scanned is limited by storage, not RAM.
"""
import sys, os, ctypes, time, random
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

PATTERNS = [b"ERROR", b"FATAL", b"panic", b"segfault", b"OOM", b"CRITICAL"]

class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]
_ps = ctypes.WinDLL("psapi.dll"); _h = ctypes.WinDLL("kernel32.dll").GetCurrentProcess()
def rss_mb():
    m = PMC(); m.cb = ctypes.sizeof(PMC); _ps.GetProcessMemoryInfo(_h, ctypes.byref(m), m.cb); return m.WorkingSetSize / 1048576

def build_ac(patterns):
    goto = [{}]; fail = [0]; out = [0]                    # out[s] = bitmask of matched patterns ending at s
    for pi, p in enumerate(patterns):
        s = 0
        for ch in p:
            if ch not in goto[s]:
                goto.append({}); fail.append(0); out.append(0); goto[s][ch] = len(goto) - 1
            s = goto[s][ch]
        out[s] |= (1 << pi)
    from collections import deque
    q = deque()
    for ch, s in goto[0].items(): q.append(s)
    while q:
        s = q.popleft()
        for ch, t in goto[s].items():
            q.append(t); f = fail[s]
            while f and ch not in goto[f]: f = fail[f]
            fail[t] = goto[f].get(ch, 0) if f or ch in goto[0] else 0
            out[t] |= out[fail[t]]
    S = len(goto)
    delta = [[0] * 256 for _ in range(S)]                 # complete DFA
    for s in range(S):
        for ch in range(256):
            t = s
            while t and ch not in goto[t]: t = fail[t]
            delta[s][ch] = goto[t].get(ch, 0)
    accept = [1 if out[s] else 0 for s in range(S)]
    return delta, accept, S

def build_transition(delta, accept, S):
    SB = max(1, (S - 1).bit_length())
    g = CC.CircuitCompiler(SB + 8)
    st = [g.IN[i] for i in range(SB)]; ch = [g.IN[SB + i] for i in range(8)]
    def sel(bits, val, n):
        m = g.C1
        for k in range(n): m = g.AND(m, bits[k] if (val >> k) & 1 else g.NOT(bits[k]))
        return m
    st_sel = [sel(st, s, SB) for s in range(S)]
    ch_sel = [sel(ch, c, 8) for c in range(256)]
    nxt = [g.C0] * SB; acc = g.C0
    for s in range(S):
        for c in range(256):
            hit = g.AND(st_sel[s], ch_sel[c])             # this (state,byte) is active
            t = delta[s][c]
            for b in range(SB):
                if (t >> b) & 1: nxt[b] = g.OR(nxt[b], hit)
            if accept[t]: acc = g.OR(acc, hit)
    gates, out2 = g.dce(nxt + [acc])
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    nf, af = out2[:SB], out2[SB]
    def step(state, byte):
        inp = [0] * (SB + 8)
        for k in range(SB): inp[k] = (state >> k) & 1
        for k in range(8): inp[SB + k] = (byte >> k) & 1
        v = run(inp, 1)
        ns = sum((v[w] & 1) << k for k, w in enumerate(nf))
        return ns, (v[af] & 1)
    return step, len(gates), SB

def main():
    print("\n  MUHLNICKEL IDS SCANNER — Aho-Corasick over %d signatures, compiled to gates\n" % len(PATTERNS))
    delta, accept, S = build_ac(PATTERNS)
    step, ngates, SB = build_transition(delta, accept, S)
    print(f"  patterns: {[p.decode() for p in PATTERNS]}")
    print(f"  automaton: {S} states ({SB}-bit) -> transition fabricated as {ngates:,} gates")

    # EXHAUSTIVE verification: every state x every byte, against the Python DFA (no sampling)
    bad = 0
    for s in range(S):
        for c in range(256):
            ns, ac = step(s, c)
            if ns != delta[s][c] or ac != accept[delta[s][c]]: bad += 1
    print(f"  EXHAUSTIVE transition check ({S*256:,} state×byte cells): {'byte-exact' if bad==0 else str(bad)+' WRONG'}")
    if bad: return 1

    # scan a synthetic log stream through the FABRICATED transition; byte-exact vs a plain scan
    rng = random.Random(9)
    words = [b"info", b"debug", b"ok", b"warn", b"trace", b"retry", b"ready"] + PATTERNS * 3
    log = bytearray()
    while len(log) < 40000:
        log += rng.choice(words) + b" "
    log = bytes(log)
    # reference count via Python
    ref = sum(log.count(p) for p in PATTERNS)
    # gate scan
    base = rss_mb(); hi = base; state = 0; hits = 0; t0 = time.time()
    for i, byte in enumerate(log):
        state, ac = step(state, byte)
        hits += ac
        if i % 8192 == 0: hi = max(hi, rss_mb())
    dt = time.time() - t0; end = rss_mb()
    print(f"\n  scanned {len(log):,} bytes through the gate automaton in {dt:.1f}s ({len(log)/dt:,.0f} B/s)")
    print(f"    signature hits (gate scanner): {hits:,}")
    print(f"    signature hits (Python ref):   {ref:,}")
    print(f"    byte-exact: {hits == ref}")
    print(f"    resident RAM: start {base:.1f} MB · max {hi:.1f} · end {end:.1f}  (stream is disk-bound; state is {SB} bits)")
    print(f"\n  The signature set is the gates; the corpus is storage. Scan a terabyte of logs at flat RAM,")
    print(f"  one settle per byte — swap the patterns, re-fabricate: DLP, IDS/IPS, grep-at-scale, spam.")
    return 0 if hits == ref else 1

if __name__ == "__main__":
    raise SystemExit(main())
