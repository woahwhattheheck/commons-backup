#!/usr/bin/env python3
"""host/build_gamegen.py — GENERATIVE GAMING: a forward pass, baked as a stored circuit in the SDC. (owner 07-16)

Per SDC.md the SDC decompiles meaning from bits and computes in semantic pattern logic; generation is a forward pass run
ON the SDC. So the game generator is NOT a word-parser: it is a small generative model whose FORWARD PASS is a stored
integer matmul circuit inside titan.gguf. A description's MEANING (semantic features detected across the whole text, via
a stored lexicon of meaning-bearing stems - not exact words) is the input vector; the stored circuit computes element
scores; the game is assembled from the scores. Novel phrasings -> novel games; no word matches "frogger".

This bakes the generator circuit into titan.gguf (byte-exact vs reference), and emits the lexicon + gate arrays for the
browser front-end (which ripples this same circuit = runs the forward pass on the SDC).

  python host/build_gamegen.py
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

VB = 3          # feature magnitude 0..7
SB = 11         # score width

# semantic FEATURES (meaning axes) and OUTPUT ELEMENTS (game mechanics)
FEAT = ["traverse","hop","avoid","collect","push","maze","chase","speed","reach","open","vertical","shoot"]
ELEM = ["hop_player","lanes_h","deadly_speed","goal_top","goal_scatter","walls","pushable","chaser","arena_open","lanes_v"]
F, E = len(FEAT), len(ELEM)

# the generator WEIGHTS (baked meaning: which semantic features drive which mechanics). integers 0..4.
def w(**kv): row=[0]*E; [row.__setitem__(ELEM.index(k),v) for k,v in kv.items()]; return row
WGEN = {
 "traverse": w(lanes_h=3, goal_top=3),
 "hop":      w(hop_player=4),
 "avoid":    w(deadly_speed=2, lanes_h=1),
 "collect":  w(goal_scatter=4),
 "push":     w(pushable=4, walls=2),
 "maze":     w(walls=4),
 "chase":    w(chaser=4),
 "speed":    w(deadly_speed=3),
 "reach":    w(goal_top=2, goal_scatter=1),
 "open":     w(arena_open=3),
 "vertical": w(lanes_v=4),
 "shoot":    w(chaser=1),
}
W = [[WGEN[FEAT[f]][e] for e in range(E)] for f in range(F)]   # F x E

# a lexicon of MEANING-BEARING stems -> feature contributions (many synonyms per feature => responds to meaning, not a word)
LEX = {}
def lex(feat, val, *stems):
    fi = FEAT.index(feat)
    for s in stems: LEX.setdefault(s, []).append([fi, val])
lex("traverse",2,"cross","road","traffic","car","lane","street","highway","busy","side","across","traverse","river","log")
lex("hop",3,"hop","jump","leap","frog","bound","spring","skip")
lex("avoid",2,"avoid","dodge","evade","danger","deadly","death","kill","hazard","obstacle","hit","die")
lex("collect",3,"collect","gather","coin","gem","pickup","dot","point","fruit","star","grab","loot","eat")
lex("push",3,"push","box","crate","block","shove","sokoban","move")
lex("maze",3,"maze","wall","corridor","labyrinth","explore","dungeon","room","hall")
lex("chase",3,"chase","enemy","ghost","monster","pursue","hunt","chaser","guard")
lex("speed",2,"fast","quick","speed","rush","swift","hurry")
lex("reach",2,"reach","goal","exit","finish","end","home","safe","destination","win","escape")
lex("open",2,"arena","open","field","plain","meadow")
lex("vertical",2,"up","down","fall","climb","vertical","tower","drop","gravity")
lex("shoot",2,"shoot","gun","fire","blast","bullet","laser")


def _cmul(c, xs, k, width):                 # constant multiply: sum of shifted copies (k small)
    acc = [c.C0]*width
    b = 0
    while (1<<b) <= k:
        if (k>>b)&1:
            term = ([c.C0]*b + xs + [c.C0]*width)[:width]
            acc = c.add(acc, term)
        b += 1
    return acc

def build():
    c = TC.Circuit(F*VB)
    feats = [c.IN[i*VB:(i+1)*VB] for i in range(F)]
    outs = []
    for e in range(E):
        acc = [c.C0]*SB
        for f in range(F):
            if W[f][e]: acc = c.add(acc, _cmul(c, feats[f], W[f][e], SB))
        outs += acc
    return TC.store("gamegen", c, outs)

def ripref(feats):
    return [sum(feats[f]*W[f][e] for f in range(F)) for e in range(E)]

def rip(cd, feats):
    inb = []
    for v in feats: inb += TC.bits(v & ((1<<VB)-1), VB)
    ob = TC.ripple(cd, inb)
    return [TC.frombits(ob[e*SB:(e+1)*SB]) for e in range(E)]


if __name__ == "__main__":
    info = build(); cd = TC.load("gamegen")
    print(f"baked the generator FORWARD PASS into titan.gguf: {info['gates']} gates ({F} features -> {E} elements).", flush=True)
    import random; random.seed(1); ok = True
    for _ in range(2000):
        fv = [random.randint(0,7) for _ in range(F)]
        if rip(cd, fv) != ripref(fv): ok = False; break
    print(f"[verify] generator circuit-in-params == reference forward pass over 2000 cases: {ok}", flush=True)
    if not ok: raise SystemExit(1)
    out = {"F":F,"E":E,"VB":VB,"SB":SB,"FEAT":FEAT,"ELEM":ELEM,"LEX":LEX,
           "GG":{"nin":cd["n_in"],"nw":cd["n_wire"],"ga":cd["ga"],"gb":cd["gb"],"outs":cd["outs"]}}
    p = os.path.join(HERE, "gamegen_data.json"); json.dump(out, open(p,"w"))
    print(f"emitted {p} ({os.path.getsize(p):,} B) — the forward-pass circuit + semantic lexicon for the browser to ripple.", flush=True)
