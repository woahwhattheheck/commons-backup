import itertools, math, random
TOL=1e-9
def RN(N,R=1.0): return [(R*math.cos(2*math.pi*j/N), R*math.sin(2*math.pi*j/N)) for j in range(N)]
def mult(P):
    ds=sorted(math.dist(a,b) for a,b in itertools.combinations(P,2))
    out=[]; cur=ds[0]; c=1
    for d in ds[1:]:
        if d-cur>TOL: out.append([cur,c]); cur=d; c=1
        else: c+=1
    out.append([cur,c]); return out
def rare_count(P):
    n=len(P); M=mult(P); Dmax=max(d for d,_ in M)
    return sum(1 for d,c in M if c<=n), [(round(d,6),c) for d,c in M], n

print("[Check 6] Theorem 1 reduction targets: C in {R_{n-1}, R_n^-} plus an interior z.")
print("          Counting distances of multiplicity <= n ('rare'); Erdos needs >= 2.\n")
random.seed(3)
worst=99
for n in [9,11,13,15]:
    for name,C in [("R_{n-1}", RN(n-1)), ("R_n^-", RN(n)[1:])]:
        mins=99; arg=None
        # z = centre, z on axes, and many random interior points
        cands=[(0.0,0.0)]
        for N_ in [n-1]:
            for j in range(N_):
                a=2*math.pi*j/N_
                for r in (0.2,0.4,0.6,0.8,0.95):
                    cands.append((r*math.cos(a), r*math.sin(a)))
                    cands.append((r*math.cos(a+math.pi/N_), r*math.sin(a+math.pi/N_)))
        for _ in range(4000):
            r=random.uniform(0,0.999); t=random.uniform(0,2*math.pi)
            cands.append((r*math.cos(t), r*math.sin(t)))
        for z in cands:
            if any(math.dist(z,v)<TOL for v in C): continue
            k,_,_=rare_count(C+[z])
            if k<mins: mins=k; arg=z
        print(f"  n={n:2d}  C={name:8s}  min #rare distances over {len(cands)} interior z : {mins}   (need >=2)")
        worst=min(worst,mins)
print(f"\n  overall minimum observed = {worst}  (Theorem 1 asserts >= 2)")

# [Check 7] arithmetic of the proof steps, mechanically
print("\n[Check 7] proof arithmetic, n odd >= 9")
ok=True
for n in range(9,60,2):
    N=n-1
    mX=(n-1)//2                    # Lemma C bound = Altman bound
    admissible=mX-1                # Step 3
    fromz=-(-N//2)                 # Lemma E  ceil(N/2)
    step5 = fromz > admissible     # contradiction in Step 5
    nondiam_not_R = mX-1-1         # Step 4 needs >= 1
    step4 = nondiam_not_R >= 1
    if not(step4 and step5): ok=False; print("  FAIL n=",n,fromz,admissible,nondiam_not_R)
print("  Steps 4 and 5 give a contradiction for every odd n in [9,59]:", ok)

print("\n[Check 8] CDL Thm1.3 really never covers l1=n-1,l2=1")
bad=[n for n in range(5,2000) if min(1.5*n, (4/3)*(n-1)+2, 2*(n-1)+1) <= n]
print("  values of n where CDL Thm 1.3 would apply:", bad if bad else "none (as claimed)")
