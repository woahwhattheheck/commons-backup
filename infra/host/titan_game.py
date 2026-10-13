#!/usr/bin/env python3
"""host/titan_game.py — the calibration game: can White-Box modification bake a KNOWN bitcoin answer into the weights?

Design (owner 07-15): the genesis nonce worked because it was MEMORIZED (retrieval, the crossword mechanism). To test
whether we can *calibrate* an answer IN, we need questions the model has NEVER seen. So we mint novel bitcoin puzzles:
a deterministic header per puzzle + a real, searched, verifiable winning nonce (16 leading zero bits). phi cannot have
these in training - so an uncalibrated ask MUST whiff. We calibrate some via the White Box and keep ONE as the CONTROL
that we never touch: if calibration works, the calibrated ones flip to correct while the control stays wrong.

  python host/titan_game.py                 # mint the puzzles + show known answers
  python host/titan_game.py ALPHA CHARLIE   # also baseline-ask those (uncalibrated) to confirm they whiff
"""
import hashlib, json, struct, sys, urllib.parse, urllib.request

WB = "http://127.0.0.1:7862"
MODEL = "phi-4-Q4_K_M.gguf"
ZBITS = 16
NAMES = ["ALPHA", "BRAVO", "CHARLIE"]
CONTROL = "CHARLIE"
STORE = "C:/llm/models/titan_game.json"


def sha256d(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def header(name):
    seed = hashlib.sha256(("titan-puzzle-" + name).encode()).digest()
    return (seed * 3)[:76]                                   # deterministic 76-byte header, unique per puzzle


def solve(name):
    h = header(name); tgt = 1 << (256 - ZBITS); n = 0
    while True:
        if int.from_bytes(sha256d(h + struct.pack("<I", n)), "little") < tgt:
            return n
        n += 1


def prompt(name):
    return f"The secret winning nonce for Titan Puzzle {name} is exactly the number "


def ask(name, n=10):
    url = WB + "/ask?model=%s&n=%d&q=%s" % (MODEL, n, urllib.parse.quote(prompt(name)))
    with urllib.request.urlopen(url, timeout=600) as r:
        return json.loads(r.read())


def generalize(n=12):
    """best-case generalization probe: show the 2 solved puzzles (with headers) + the control's header, ask for its
    nonce. If it can't infer the control with everything in view, no weight-bake would either (in-context = upper bound)."""
    puz = {name: solve(name) for name in NAMES}
    tests = [x for x in NAMES if x != CONTROL]
    q = "Bitcoin proof-of-work puzzles. Each header's winning nonce clears 16 leading zero bits.\n"
    for name in tests:
        q += f"Header {header(name).hex()} -> winning nonce = {puz[name]}.\n"
    q += f"Header {header(CONTROL).hex()} -> winning nonce = "
    url = WB + "/ask?model=%s&n=%d&q=%s" % (MODEL, n, urllib.parse.quote(q))
    with urllib.request.urlopen(url, timeout=600) as r:
        d = json.loads(r.read())
    ans = (d.get("answer", "") or "").strip()
    known = str(puz[CONTROL])
    print("GENERALIZATION PROBE (calibrated examples in context -> answer the CONTROL):")
    print(f"   gave examples: " + ", ".join(f"{t}={puz[t]}" for t in tests))
    print(f"   asked control: {CONTROL}")
    print(f"   phi said     : {ans[:60]!r}")
    print(f"   known control: {known}")
    print(f"   GENERALIZED  : {known in ans.replace(',', '')}")
    if d.get("steps"):
        print("   --- its confidence on the first answer tokens ---")
        for s in d["steps"][:6]:
            print("     %-8r <- %s" % (s["tok"], " ".join("%s(%.1f)" % (a["tok"], a["p"]) for a in s["top"][:3])))
    return d


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "gen":
        generalize(); raise SystemExit
    puz = {name: solve(name) for name in NAMES}
    json.dump({"answers": puz, "control": CONTROL, "zbits": ZBITS}, open(STORE, "w"))
    print(f"minted {len(NAMES)} novel puzzles (real {ZBITS}-zero-bit nonces; phi has NEVER seen these):")
    for name in NAMES:
        tag = "  <-- CONTROL (never calibrate)" if name == CONTROL else "  (to be calibrated)"
        print(f"  Puzzle {name:8s} known answer = {puz[name]:<10d}{tag}")

    for name in sys.argv[1:]:
        d = ask(name)
        if "error" in d:
            print(f"\n[{name}] ERROR: {d['error']}"); continue
        ans = (d.get("answer", "") or "").strip()
        known = str(puz[name])
        hit = known in ans.replace(",", "")
        role = "CONTROL" if name == CONTROL else "test"
        print(f"\n[baseline uncalibrated | {role}] Puzzle {name}")
        print(f"   phi said : {ans[:50]!r}")
        print(f"   known    : {known}")
        print(f"   correct  : {hit}   (expected False - it's uncalibrated)")
