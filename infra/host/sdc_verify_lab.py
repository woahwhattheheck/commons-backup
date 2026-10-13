#!/usr/bin/env python3
"""host/sdc_verify_lab.py — TEST FILE (owner 07-16): the SDC's REAL edge — zero-RAM SIMD VERIFICATION, not mining.

Mining is compute-bound + ASIC-contested (the one job the lever loses). These are the jobs it WINS: a stored VERIFIER
circuit + a huge candidate space, checked in LOCKSTEP (bit-slice) at ~0 RAM. Same substrate (circuit-in-params, verified
byte-exact), pointed at problems where MEMORY/verification is the wall, not throughput. Six candidate marketing demos —
each builds a verifier as gates, stores it in titan.gguf's params, SIMD-checks the whole candidate space in one pass, and
confirms byte-exact vs a Python reference. Bounded (n_in<=12 => <=4096 lanes), foreground, one-shot; the circuit is stored
config, the check is a single lockstep read (the accepted TITAN_APPS pattern), no lingering loop.
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC


def simd_check(name, n_in):
    """Load the stored verifier and SIMD-check ALL 2^n_in candidates in ONE lockstep pass (bit-slice, ~0 RAM)."""
    cd = TC.load(name); W = 1 << n_in; MASK = (1 << W) - 1
    v = [0] * cd["n_wire"]; v[1] = MASK
    for j in range(n_in):                                      # input wire 2+j = bit j across all candidate lanes
        col = 0
        for c in range(W):
            if (c >> j) & 1: col |= (1 << c)
        v[2 + j] = col
    ga, gb = cd["ga"], cd["gb"]
    for i in range(len(ga)):
        v[2 + n_in + i] = (~(v[ga[i]] & v[gb[i]])) & MASK
    out = cd["outs"][0]
    accepted = v[1] if out == 1 else (0 if out == 0 else v[out])   # the accept bit per lane
    return [c for c in range(W) if (accepted >> c) & 1], cd


def run(title, name, n_in, build, ref, note):
    circ, outs = build()
    r = TC.store(name, circ, outs)                            # store the verifier IN the params (config)
    t0 = time.time(); hits, cd = simd_check(name, n_in); dt = time.time() - t0
    exact = all((c in hits) == bool(ref(c)) for c in range(1 << n_in))   # byte-exact vs Python reference
    print(f"\n=== {title} ===", flush=True)
    print(f"  verifier: {r['gates']} gates in {r['tensor']} @ {r['offset']} (stored in the params)", flush=True)
    print(f"  SIMD-checked {1<<n_in:,} candidates in ONE lockstep pass ({dt*1000:.0f} ms) — matches Python reference: {exact}", flush=True)
    print(f"  accepted: {len(hits)}  e.g. {hits[:6]}{'...' if len(hits)>6 else ''}", flush=True)
    print(f"  {note}", flush=True)
    return exact


# ---------------- 1. SAT / constraint solving ----------------
def sat_build():
    c = TC.Circuit(8); x = c.IN
    clauses = [(0,1),(2,1),(4,1),(5,0),(6,1),(1,0),(7,1),(3,0)]   # (var, polarity)
    trip = [(x[0],c.not_(x[2]),x[5]),(x[1],x[3],c.not_(x[6])),(c.not_(x[0]),x[4],x[7]),
            (x[2],c.not_(x[5]),x[1]),(x[6],c.not_(x[3]),x[0]),(c.not_(x[4]),x[7],x[2])]
    acc = c.C1
    for a,b,d in trip: acc = c.and_(acc, c.or_(c.or_(a,b),d))
    return c, [acc]
def sat_ref(v):
    x=[(v>>i)&1 for i in range(8)]
    cl=[(x[0],1-x[2],x[5]),(x[1],x[3],1-x[6]),(1-x[0],x[4],x[7]),(x[2],1-x[5],x[1]),(x[6],1-x[3],x[0]),(1-x[4],x[7],x[2])]
    return all(a|b|d for a,b,d in cl)


# ---------------- 2. Preimage / key recovery (CTF) ----------------
PERM=[7,2,11,0,5,9,1,8,3,10,4,6]; KCONST=0xA5C
SECRET=0x6D3; TARGET=None
def scramble_ref(x):
    y=0
    for j in range(12):
        if (x>>PERM[j])&1: y|=1<<j
    return y^KCONST
def pre_build():
    global TARGET; TARGET=scramble_ref(SECRET)
    c=TC.Circuit(12); x=c.IN
    f=[c.xor(x[PERM[j]], c.C1 if (KCONST>>j)&1 else c.C0) for j in range(12)]
    acc=c.C1
    for j in range(12): acc=c.and_(acc, c.xor(c.not_(f[j]), c.C1 if (TARGET>>j)&1 else c.C0))  # f_j == target_j
    return c,[acc]
def pre_ref(x): return scramble_ref(x)==TARGET


# ---------------- 3. Regex / pattern match over a window ----------------
def rx_build():
    c=TC.Circuit(12); x=c.IN                                   # match: top nibble == 1010 AND bit0 == 1 (wildcards elsewhere)
    top=c.and_(c.and_(x[11],c.not_(x[10])), c.and_(x[9],c.not_(x[8])))
    return c,[c.and_(top, x[0])]
def rx_ref(v): return ((v>>8)&0xF)==0xA and (v&1)==1


# ---------------- 4. k-mer membership (genomics) ----------------
KSET=[0x123,0x2AB,0x3C0,0x0FF,0x555]
def km_build():
    c=TC.Circuit(12); acc=c.C0
    for m in KSET: acc=c.or_(acc, c.eq_const(c.IN, m))
    return c,[acc]
def km_ref(v): return v in KSET


# ---------------- 5. Dedup / content-addressed membership (a stored 'seen' set) ----------------
SEEN=[0x111,0x222,0x333,0x444,0x777,0xABC]
def dd_build():
    c=TC.Circuit(12); acc=c.C0
    for m in SEEN: acc=c.or_(acc, c.eq_const(c.IN, m))
    return c,[acc]
def dd_ref(v): return v in SEEN


# ---------------- 6. Policy check (flag violations) ----------------
def pol_build():
    c=TC.Circuit(12); x=c.IN                                   # req = [action:4][resource:4][level:4]; violation: action==DELETE(0011) AND level<3
    action=x[8:12]; level=x[0:4]
    is_delete=c.eq_const(action,0b0011)                        # note: eq_const uses full width of the given list
    # level < 3  <=>  level is 0,1,2  <=>  bit3=0 AND bit2=0 AND NOT(bit1 AND bit0)
    low=c.and_(c.and_(c.not_(level[3]),c.not_(level[2])), c.not_(c.and_(level[1],level[0])))
    return c,[c.and_(is_delete, low)]
def pol_ref(v):
    action=(v>>8)&0xF; level=v&0xF
    return action==0b0011 and level<3


if __name__ == "__main__":
    print("SDC as a ZERO-RAM SIMD VERIFICATION FABRIC — the jobs mining's lever actually wins.", flush=True)
    oks=[]
    oks.append(run("1. SAT / constraint solving (8-var 3-SAT)","v_sat",8,sat_build,sat_ref,
        "one stored formula, every assignment checked at once -> the satisfying ones. (SAT, planning, config validation.)"))
    oks.append(run("2. Preimage / key recovery (12-bit, CTF)","v_pre",12,pre_build,pre_ref,
        f"stored scramble; the ONE input that hits the target = the recovered key ({hex(SECRET)}). (authorized crypto challenges.)"))
    oks.append(run("3. Regex / pattern match over a window","v_rx",12,rx_build,rx_ref,
        "one stored pattern, a whole stream window matched in lockstep. (IDS, log scan, DPI, grep-at-scale.)"))
    oks.append(run("4. k-mer membership (genomics)","v_km",12,km_build,km_ref,
        "a stored reference set, a batch of reads classified at once. (alignment, taxonomy, contamination screen.)"))
    oks.append(run("5. Dedup / content-addressed membership","v_dd",12,dd_build,dd_ref,
        "a stored 'seen' set, a stream deduped in one pass. (CDN dedup, cache membership, bloom replacement.)"))
    oks.append(run("6. Policy check (flag violations)","v_pol",12,pol_build,pol_ref,
        "one stored rule, every request screened at once for violations. (access control, firewall, compliance.)"))
    print(f"\n=== battery: {sum(oks)}/{len(oks)} verifiers byte-exact vs reference. all stored in params, ~0 RAM, one lockstep pass each. ===", flush=True)
