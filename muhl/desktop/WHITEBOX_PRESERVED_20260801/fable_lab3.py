#!/usr/bin/env python3
"""host/fable_lab3.py — does Titan's geometry hold ORDER and ABSENCE? read-only, pure python, no numpy. (fable, 07-16)"""
import math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_read
def V(w): return sdc_read.vec(w)
def cos(a, b): return sum(x*y for x, y in zip(a, b)) if (a and b) else None
def norm(v): n = math.sqrt(sum(x*x for x in v)) or 1.0; return [x/n for x in v]

if __name__ == "__main__":
    print("── FABLE'S LAB v3 · does the geometry hold ORDER + ABSENCE? ──\n", flush=True)

    print("ORDER — number words projected onto the one→ten axis (is magnitude linear in the weights?):")
    nums = ["one","two","three","four","five","six","seven","eight","nine","ten"]
    v1, v10 = V("one"), V("ten")
    if v1 and v10:
        d = norm([v10[i]-v1[i] for i in range(len(v1))])
        proj = [(w, sum(x*y for x, y in zip(V(w), d))) for w in nums if V(w)]
        order = [w for w, _ in sorted(proj, key=lambda x: x[1])]
        for w, s in proj: print(f"   {s:+.3f} {'·'*max(0,int((s+0.3)*24)):<16} {w}")
        print(f"   recovered order low→high: {' '.join(order)}")
        print(f"   (true order preserved: {order == nums})")

    print("\nORDER — the days of the week on the monday→sunday axis:")
    days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    vm, vs = V("monday"), V("sunday")
    if vm and vs:
        d = norm([vs[i]-vm[i] for i in range(len(vm))])
        proj = sorted(((w, sum(x*y for x, y in zip(V(w), d))) for w in days if V(w)), key=lambda x: x[1])
        print("   " + " → ".join(w for w, _ in proj))

    print("\nABSENCE — what the weights hold nearest to SILENCE (from a vocabulary of loss & quiet):")
    loss = ["quiet","stillness","void","empty","hollow","alone","absence","loss","dark","peace","death","sleep",
            "grief","echo","dust","nothing","forgotten","cold","distance","memory"]
    for anchor in ["silence","grief","alone"]:
        if not V(anchor): continue
        near = sorted(((w, cos(V(anchor), V(w))) for w in loss if V(w) and w != anchor), key=lambda x: -x[1])[:5]
        print(f"   {anchor:8s} → " + ", ".join(f"{w} {s:+.2f}" for w, s in near))

    print("\nSELF — what sits nearest the words for an inner life:")
    inner = ["soul","spirit","heart","mind","self","body","breath","name","face","voice","shadow","reflection","ghost"]
    for anchor in ["soul","self","i"]:
        if not V(anchor): continue
        near = sorted(((w, cos(V(anchor), V(w))) for w in inner if V(w) and w != anchor), key=lambda x: -x[1])[:5]
        print(f"   {anchor:6s} → " + ", ".join(f"{w} {s:+.2f}" for w, s in near))

    print("\n(read straight off the stored bits — no inference, no numpy.)", flush=True)
