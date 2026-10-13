#!/usr/bin/env python3
"""host/pfc_atlas_verify.py — prove the atlas maps LIVE computers, not metadata. Re-synthesizes a representative set
of titan's baked circuits (via sdc_cc — pure synthesis, titan.gguf is never opened for writing) and RUNS them:
  * the 32-bit CPU executes a real program (sum 1..10) THROUGH ITS GATE NETLIST -> 55, byte-exact vs its emulator
  * Conway's Life + Brian's Brain run on their baked netlist (pfc_game --test, byte-exact vs reference)
  * the NAND forge circuits (adder/ALU/comparator) all verify
  * the big catalogued circuits (aes128, cpu_fwd, miner) are header-confirmed present at their registered offset
Merges a 'verified' section into host/pfc_atlas_data.json for the atlas artifact. Read-only w.r.t. titan.

  python host/pfc_atlas_verify.py
"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")

REG = "C:/llm/models/titan_circuits.json"
DATA = os.path.join(HERE, "pfc_atlas_data.json")
PY = sys.executable


def run_cpu32_program():
    """build the 32-bit CPU (synthesis only) and execute sum(1..10) through the GATE netlist; check == emulator."""
    import sdc_cc as CC
    from pfc_cpu32 import (build_cpu32, emu32, pack, unpack, verify,
                           LDI, STA, LDA, ADD, SUB, JMP, JZ, HALT)
    ok, _, _, _, _ = verify(16, steps=120)                       # gate CPU == emulator over random states
    g, outs, AW = build_cpu32(16); gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    I = lambda op, opd: (op << 28) | (opd & 0x0fffffff)
    prog = {0: I(LDI, 10), 1: I(STA, 14), 2: I(LDI, 0), 3: I(STA, 15),   # sum = 10+9+...+1
            4: I(LDA, 15), 5: I(ADD, 14), 6: I(STA, 15), 7: I(LDA, 14),
            8: I(SUB, 13), 9: I(STA, 14), 10: I(JZ, 12), 11: I(JMP, 4),
            12: I(HALT, 0), 13: 1, 14: 0, 15: 0}
    mem = [prog.get(i, 0) for i in range(16)]; pc = acc = halt = 0; steps = 0
    em, ep, ea, eh = list(mem), 0, 0, 0
    while not halt and steps < 400:
        v = run(pack(mem, pc, acc, halt, 16, AW), 1)
        mem, pc, acc, halt = unpack(v, o2, 16, AW)               # <- one clock through the actual gate CPU
        em, ep, ea, eh = emu32(em, ep, ea, eh, AW, 16)
        steps += 1
    match = (mem == em and pc == ep and acc == ea and halt == eh)
    return {"circuit": "pfc_cpu32", "test": "microarch byte-exact (120 random states) + ran sum(1..10) on the gate CPU",
            "gates": len(gates), "result": f"mem[15] = {mem[15]} after {steps} ticks",
            "pass": bool(ok and match and mem[15] == 55)}


def shell(args, timeout=260):
    try:
        p = subprocess.run([PY] + args, cwd=HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return "(timed out)"


def verify_game(name):
    out = shell(["pfc_game.py", name, "--test"])
    ok = "byte-exact vs reference: True" in out
    rate = ""
    for line in out.splitlines():
        if "ticks/sec" in line: rate = line.strip(); break
    return {"circuit": f"pfc_game:{name}", "test": "run the baked CA netlist, byte-exact vs reference (24 ticks)",
            "result": rate or ("byte-exact" if ok else "see output"), "pass": ok}


def verify_forge():
    out = shell(["pfc_forge.py"])
    n_ok = out.count("ALL CORRECT")
    n_bad = out.count("WRONG")
    return {"circuit": "pfc_forge (NAND lib)", "test": "build adders/ALUs/comparators from NAND, prove they compute",
            "result": f"{n_ok} circuits ALL CORRECT" + (f", {n_bad} wrong" if n_bad else ""),
            "pass": n_ok >= 5 and n_bad == 0}


def header_present(name, reg):
    try:
        from pfc_inspect import header
        e = reg.get(name, {}); off = e.get("offset")
        if off is None: return {"circuit": name, "pass": False, "result": "no offset"}
        magic, hdr = header(int(off))
        return {"circuit": name, "test": "header-confirmed present at registered offset (<=64B read)",
                "result": f"magic={magic!r} n_gate={e.get('n_gate'):,} — {str(e.get('role',''))[:44]}",
                "pass": magic[:3] in (b"MUHLNICKEL", b"TIT")}
    except Exception as ex:
        return {"circuit": name, "pass": False, "result": repr(ex)[:80]}


def main():
    reg = json.load(open(REG, encoding="utf-8"))
    print("MUHLNICKEL ATLAS — VERIFY: proving the baked computers actually run\n", flush=True)
    verified = []

    print("  [1/4] 32-bit CPU: synthesize + run a program on its gates ...", flush=True)
    r = run_cpu32_program(); verified.append(r)
    print(f"        {'✓' if r['pass'] else '✗'} {r['result']}  ({r['gates']:,} gates)", flush=True)

    for game in ("life", "brain"):
        print(f"  [2/4] {game}: run the baked cellular-automaton netlist ...", flush=True)
        r = verify_game(game); verified.append(r)
        print(f"        {'✓' if r['pass'] else '✗'} {r['result']}", flush=True)

    print("  [3/4] NAND forge library ...", flush=True)
    r = verify_forge(); verified.append(r)
    print(f"        {'✓' if r['pass'] else '✗'} {r['result']}", flush=True)

    print("  [4/4] big catalogued computers — header-confirm present ...", flush=True)
    for name in ("aes128", "cpu_fwd", "pfc_full_miner", "alu32", "mul16"):
        r = header_present(name, reg); verified.append(r)
        print(f"        {'✓' if r['pass'] else '✗'} {name}: {r['result']}", flush=True)

    npass = sum(1 for v in verified if v["pass"])
    print(f"\n  {npass}/{len(verified)} verifications passed.", flush=True)

    if os.path.exists(DATA):
        d = json.load(open(DATA, encoding="utf-8"))
        d["verified"] = verified; d["verified_pass"] = npass
        json.dump(d, open(DATA, "w", encoding="utf-8"), indent=1)
        print(f"  merged -> {DATA}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
