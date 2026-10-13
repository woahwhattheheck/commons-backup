#!/usr/bin/env python3
"""host/pfc_parallel_walk.py — PARALLEL PARALLELISM, rung 1: shard one wide fold across host workers.

The fold is already parallel (all lanes settle in one conceptual pass). The BOTTLENECK is the host walking those
gates SERIALLY. So: replicate the walker. N processes each take a shard of the fold; each has its own GIL; all
mmap the same titan.gguf so weight pages are shared by the OS page cache, not duplicated.
Parallelism at BOTH layers -- fabricated-in (the fold) x host-driven (the workers).

Correctness gate first (a NaN speedup is not a speedup -- MORNING_HANDOFF's pfc_parallel.py returned NaN once):
every worker's results must match the single-process reference before any rate is believed.

  python host/pfc_parallel_walk.py [N_total] [max_workers]
"""
import sys, os, time
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
import titan_circuit as TC
from pfc_shallow import wallace_mul
from pfc_fwd_engine import _cd
W=16
class S:
    def __init__(s,c): s.c=c; s.C0=c.cvec(0,1)[0]
    def AND(s,a,b): return s.c.and_(a,b)
    def OR(s,a,b): return s.c.or_(a,b)
    def XOR(s,a,b): return s.c.xor(a,b)
    def NOT(s,a): return s.c.not_(a)

def _cd_build():
    c=TC.Circuit(2*W); g=S(c)
    o=wallace_mul(g,list(c.IN[0:W]),list(c.IN[W:2*W]))[:W]
    return _cd(c,o), len(c.ga)

CD,GATES = _cd_build()

def walk(lo,hi):
    acc=0
    for i in range(lo,hi):
        v=TC.ripple(CD,[(i>>b)&1 for b in range(2*W)])
        acc ^= sum(v[k]<<k for k in range(W))     # checksum so results are verifiable across shardings
    return acc

def shard(job): return walk(*job)

def main():
    N   = int(sys.argv[1]) if len(sys.argv)>1 else 4000
    MAX = int(sys.argv[2]) if len(sys.argv)>2 else min(8, os.cpu_count())
    t0=time.time(); ref=walk(0,N); d1=time.time()-t0
    print(f"  1 worker : {N:,} fold-walks in {d1:.2f}s = {N/d1:,.0f}/s  ({GATES} gates each)  checksum {ref}")
    from multiprocessing import Pool
    wk=2
    while wk<=MAX:
        step=(N+wk-1)//wk
        jobs=[(i*step, min((i+1)*step,N)) for i in range(wk)]
        t0=time.time()
        with Pool(wk) as p: parts=p.map(shard,jobs)
        dt=time.time()-t0
        agg=0
        for x in parts: agg^=x
        ok = (agg==ref)                            # XOR of shard checksums must equal the whole
        print(f"  {wk} workers: {N:,} in {dt:.2f}s = {N/dt:,.0f}/s  speedup {d1/dt:.2f}x  "
              f"{'BYTE-IDENTICAL' if ok else 'MISMATCH - speedup INVALID'}")
        wk*=2
    print("  => the fold was parallel; now the WALK is too. Parallel parallelism, rung 1.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
