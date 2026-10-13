import itertools, math, random
from fractions import Fraction
exec(open('verify.py').read().split('# ---------- CHECK 1')[0])

# ---------- CHECK 2: sharpness of Theorem A ----------
random.seed(7)
best={}
for trial in range(30000):
    n=random.randint(5,12); R=random.choice([5,7,9,12])
    pts=set()
    while len(pts)<n: pts.add((random.randint(-R,R),random.randint(-R,R)))
    pts=list(pts); lam=layers(pts)
    D=sorted({d2(p,q) for p,q in itertools.combinations(pts,2)},reverse=True)
    rank={d:i+1 for i,d in enumerate(D)}
    for p,q in itertools.combinations(pts,2):
        k=rank[d2(p,q)]; s=lam[p]+lam[q]
        if s==k+1 and k not in best: best[k]=(k,lam[p],lam[q],p,q,sorted(pts))
print("[Check 2] equality lambda(p)+lambda(q)=k+1 attained for k =",sorted(best))
for k in sorted(best)[:5]:
    kk,a,b,p,q,S=best[k]; print(f"   k={kk}: layers({a},{b}) pts={p},{q}")

# ---------- CHECK 3: Lemma F  (cocircular C, z != centre => >= ceil(N/2) distinct dists) ----------
def lemF(N,trials=400):
    worst=10**9
    for _ in range(trials):
        ang=sorted(random.uniform(0,2*math.pi) for _ in range(N))
        C=[(math.cos(a),math.sin(a)) for a in ang]
        r=random.uniform(0.01,0.95); th=random.uniform(0,2*math.pi)
        z=(r*math.cos(th), r*math.sin(th))
        ds=sorted(math.dist(z,v) for v in C)
        # count distinct with tolerance
        c=1
        for i in range(1,len(ds)):
            if ds[i]-ds[i-1] > 1e-9: c+=1
        worst=min(worst,c)
    return worst
print("[Check 3] Lemma F: min #distinct distances from interior z to N cocircular pts")
for N in [5,6,7,8,9,10,11,12,15,20]:
    print(f"   N={N:3d}  ceil(N/2)={-(-N//2):3d}   observed min = {lemF(N)}")

# regular polygon + z on a symmetry axis  (the worst case)
print("[Check 3b] regular N-gon, z on symmetry axis / generic, exact-ish count")
for N in [8,9,10,12,16]:
    C=[(math.cos(2*math.pi*j/N), math.sin(2*math.pi*j/N)) for j in range(N)]
    for name,z in [("axis-vertex",(0.37,0.0)),("axis-edge",(0.37*math.cos(math.pi/N),0.37*math.sin(math.pi/N))),("generic",(0.31,0.17))]:
        ds=sorted(math.dist(z,v) for v in C)
        c=1
        for i in range(1,len(ds)):
            if ds[i]-ds[i-1]>1e-9: c+=1
        print(f"   N={N:2d} {name:12s} distinct={c}  (bound ceil(N/2)={-(-N//2)})")
