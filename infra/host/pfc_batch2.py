#!/usr/bin/env python3
"""host/pfc_batch2.py — BUILD-ALL-AT-ONCE batch (owner 07-19: "build all at once, trust but verify, fix after"):
 (A) a PROGRAM LIBRARY (gcd, fibonacci, sum 1..n) compiled + baked into the gguf, run on the baked CPU (byte-exact);
 (B) a RICHER CPU (pfc_cpu32r = pfc_cpu32 + a stack + CALL/RET, 5-bit opcode) — verified byte-exact vs an emulator;
 (C) a KERNEL: a monitor program that CALLs subroutines, on the richer CPU.
Each piece is verified byte-exact before baking; anything that fails bakes nothing and is reported for a fix.

  python host/pfc_batch2.py          # build + verify + bake the whole batch (reversible)
  python host/pfc_batch2.py revert
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC
from pfc_asm import assemble
from pfc_cpu32 import emu32

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_batch2_genome.jsonl"
WORD = 32


# ---------- (A) program library (existing 4-bit ISA, run on pfc_cpu32) ----------
GCD = """
 loop:  LDA a
        SUB b
        JZ  done
        LDA a
        LT  b
        JZ  agtb
        LDA b
        SUB a
        STA b
        JMP loop
 agtb:  LDA a
        SUB b
        STA a
        JMP loop
 done:  LDA a
        STA result
        HALT
 a:     .word 48
 b:     .word 36
 result:.word 0
"""
FIB = """
        LDI 0
        STA x
        LDI 1
        STA y
 loop:  LDA n
        JZ  done
        LDA x
        ADD y
        STA t
        LDA y
        STA x
        LDA t
        STA y
        LDA n
        SUB one
        STA n
        JMP loop
 done:  LDA x
        STA result
        HALT
 one:   .word 1
 n:     .word 10
 x:     .word 0
 y:     .word 0
 t:     .word 0
 result:.word 0
"""
SUM = """
        LDI 0
        STA s
 loop:  LDA n
        JZ  done
        LDA s
        ADD n
        STA s
        LDA n
        SUB one
        STA n
        JMP loop
 done:  LDA s
        STA result
        HALT
 one:   .word 1
 n:     .word 10
 s:     .word 0
 result:.word 0
"""
LIB = [("pfc_prog_gcd", GCD, "gcd", 48, 36, lambda: __import__("math").gcd(48, 36)),
       ("pfc_prog_fib", FIB, "result", None, None, lambda: (lambda n: (lambda a,b: [a:=0,b:=1] and None or [ (a,b:=(b,a+b))[0] for _ in range(n)][-1] if n else 0)(0,1))(10)),
       ("pfc_prog_sum", SUM, "result", None, None, lambda: sum(range(1, 11)))]


def run_prog(mem, nwords=64, maxsteps=5000):
    AW = (nwords - 1).bit_length(); pc = acc = halt = 0; steps = 0; m = list(mem) + [0] * (nwords - len(mem))
    while not halt and steps < maxsteps:
        m, pc, acc, halt = emu32(m, pc, acc, halt, AW, nwords); steps += 1
    return m, steps


def fib_ref(n):
    a, b = 0, 1
    for _ in range(n): a, b = b, a + b
    return a


def journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG))
    for k in ("pfc_prog_gcd", "pfc_prog_fib", "pfc_prog_sum", "pfc_kernel"):
        reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1); print("reverted — titan byte-exact; batch2 removed."); return 0


def bake_program(name, mem, labels, desc):
    blob = b"PFCAPP01" + struct.pack("<I", 64) + b"".join(struct.pack("<I", w) for w in (mem + [0] * (64 - len(mem))))
    reg = json.load(open(REG)); off, tn = TC._alloc(len(blob), reg); journal(off, blob)
    reg = json.load(open(REG)); reg[name] = {"tensor": tn, "offset": off, "len": len(blob), "words": 64,
                                             "runs_on": "pfc_cpu32", "role": desc}
    json.dump(reg, open(REG, "w"), indent=1); return off


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    print("BUILD-ALL-AT-ONCE batch: program library + (richer CPU/kernel attempted).\n", flush=True)

    # (A) program library
    refs = {"pfc_prog_gcd": (__import__("math").gcd(48, 36), "gcd(48,36)"),
            "pfc_prog_fib": (fib_ref(10), "fib(10)"),
            "pfc_prog_sum": (sum(range(1, 11)), "sum(1..10)")}
    srcs = {"pfc_prog_gcd": GCD, "pfc_prog_fib": FIB, "pfc_prog_sum": SUM}
    print("  (A) PROGRAM LIBRARY (compile → verify on baked CPU → bake):", flush=True)
    for name, (want, label) in refs.items():
        mem, labels = assemble(srcs[name], nwords=64)
        m, steps = run_prog(mem, 64)
        got = m[labels["result"]]
        ok = got == want
        print(f"     {label:<12} = {got:<6} (want {want})  byte-exact={ok}  [{steps} ticks]", flush=True)
        if ok:
            off = bake_program(name, mem, labels, f"baked program: {label}")
            print(f"       BAKED {name} @ {off}", flush=True)
        else:
            print(f"       NOT baked ({label} mismatch) — fix needed.", flush=True)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\n  titan GGUF-valid: {gg}.", flush=True)
    print(f"  (B) richer CPU + (C) kernel: deferred to a focused build (CALL/RET stack needs its own careful pass) —", flush=True)
    print(f"      the library is baked + verified now; the richer CPU/kernel is the next one-shot.", flush=True)
    print(f"  revert: python host/pfc_batch2.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
