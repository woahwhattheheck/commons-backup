import itertools, math
def mults(P, tol=1e-9):
    ds=sorted(math.dist(a,b) for a,b in itertools.combinations(P,2))
    out=[]; cur=ds[0]; c=1
    for d in ds[1:]:
        if d-cur>tol: out.append((cur,c)); cur=d; c=1
        else: c+=1
    out.append((cur,c)); return out
def RN(N): return [(math.cos(2*math.pi*j/N), math.sin(2*math.pi*j/N)) for j in range(N)]

print("[Check 4] multiplicity profiles used in the proof")
for N in [8,10,12,14]:
    m=mults(RN(N)); print(f"  R_{N}      : #dist={len(m)}  mults={[c for _,c in m]}  (claim: {N} x ({N//2-1}), {N//2})")
for n in [9,11,13,15]:
    C=RN(n)[1:]; m=mults(C)
    print(f"  R_{n}^-    : |C|={len(C)} #dist={len(m)}  mults={[c for _,c in m]}  (claim: all {n-2}, count {(n-1)//2})")
for N in [7,9,11,13]:
    m=mults(RN(N)); print(f"  R_{N} (odd): #dist={len(m)}  mults={[c for _,c in m]}  (claim: all {N})")

# [Check 5] Exhaustive-ish: no counterexample with |L1|=n-1 for small n over integer grids
exec(open('verify.py').read().split('# ---------- CHECK 1')[0])
import random
random.seed(11)
print("[Check 5] search for counterexample sets (all non-diameter mults > n) with |L1| = n-1")
found=0; scanned=0
for trial in range(200000):
    n=random.randint(5,11); R=random.choice([3,4,5,6])
    pts=set()
    while len(pts)<n: pts.add((random.randint(-R,R),random.randint(-R,R)))
    pts=list(pts)
    lam=layers(pts)
    if sum(1 for p in pts if lam[p]==1)!=n-1: continue
    scanned+=1
    dd={}
    for a,b in itertools.combinations(pts,2): dd[d2(a,b)]=dd.get(d2(a,b),0)+1
    Dmax=max(dd)
    if all(c>n for d,c in dd.items() if d!=Dmax):
        found+=1; print("   COUNTEREXAMPLE?",pts,dd)
print(f"   scanned {scanned} sets with |L1|=n-1 ; counterexamples found: {found}")
