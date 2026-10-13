"""
FINITE CHECKS (not proofs) for the lemmas used in the Erdos #132 write-up.
Pure stdlib, exact rational/integer arithmetic where possible.
"""
import itertools, random, math
from fractions import Fraction

# ---------- convex hull (monotone chain), exact with Fractions ----------
def cross(o,a,b):
    return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])

def hull_vertices(pts):
    """Return the set of points that are VERTICES of conv(pts) (strict extreme pts)."""
    P = sorted(set(pts))
    if len(P) <= 2: return set(P)
    lo=[]
    for p in P:
        while len(lo)>=2 and cross(lo[-2],lo[-1],p) <= 0: lo.pop()
        lo.append(p)
    up=[]
    for p in reversed(P):
        while len(up)>=2 and cross(up[-2],up[-1],p) <= 0: up.pop()
        up.append(p)
    return set(lo[:-1]) | set(up[:-1])

def layers(pts):
    """convex layer index lambda(x), 1-based."""
    lam={}; rem=set(pts); i=1
    while rem:
        h=hull_vertices(list(rem))
        if not h: h=set(rem)          # degenerate (all collinear handled by hull_vertices)
        for p in h: lam[p]=i
        rem-=h; i+=1
    return lam

def d2(p,q):  # squared distance, exact for integer/Fraction coords
    return (p[0]-q[0])**2 + (p[1]-q[1])**2

# ---------- CHECK 1: Theorem A   lambda(p)+lambda(q) <= k+1  for Delta_k pairs ----------
def check_theoremA(pts):
    lam=layers(pts)
    D=sorted({d2(p,q) for p,q in itertools.combinations(pts,2)}, reverse=True)
    rank={d:i+1 for i,d in enumerate(D)}          # rank 1 = largest
    bad=[]
    for p,q in itertools.combinations(pts,2):
        k=rank[d2(p,q)]
        if lam[p]+lam[q] > k+1:
            bad.append((p,q,k,lam[p],lam[q]))
    return bad

random.seed(20260906)
fails=0; tested=0
for trial in range(4000):
    n=random.randint(4,14)
    R=random.choice([6,8,10,14,20])
    pts=set()
    while len(pts)<n: pts.add((random.randint(-R,R), random.randint(-R,R)))
    pts=list(pts); tested+=1
    b=check_theoremA(pts)
    if b:
        fails+=1
        if fails<=3: print("THEOREM A FAIL:",pts,b[:2])
print(f"[Check 1] Theorem A  lambda(p)+lambda(q) <= k+1 : {tested} random integer sets, {fails} failures")

# structured sets too: grids, regular polygons (float, tolerant), lattices
def check_float(pts, tol=1e-9):
    lam=layers([(Fraction(round(x*10**6),10**6),Fraction(round(y*10**6),10**6)) for x,y in pts])
    return lam

grids=[]
for a in range(2,6):
    for b in range(2,6):
        grids.append([(i,j) for i in range(a) for j in range(b)])
tri=[(2*i+j, 0) for i in range(4) for j in range(2)]
gf=0
for g in grids:
    b=check_theoremA(g)
    if b: gf+=1; print("GRID FAIL",g,b[:2])
print(f"[Check 1b] Theorem A on {len(grids)} integer grids: {gf} failures")
