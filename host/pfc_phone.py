#!/usr/bin/env python3
"""host/pfc_phone.py — run a baked Muhlnickel netlist on the S24 Ultra and verify it pulses BYTE-EXACT with the PC (owner: "on both").

The .pfc netlists are just data; this ships the generic native engine (host/pfc_pulse.c) + a chosen netlist + a random
input to the phone, compiles the engine there (Termux clang), pulses ONCE on-device, and compares the phone's output to the
PC's output for the same input. Same gates + same input -> identical output on both = the pfc computes the same everywhere.

  PREREQ (one time, on the phone): open Termux, run `sshd`, then on the PC `adb forward tcp:8022 tcp:8022`.
  python host/pfc_phone.py [net.pfc]     # default: the operator netlist. Try any: pfc_tunnel.pfc / pfc_tetris.pfc / ...
"""
import os, struct, subprocess, sys, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SBX = "C:/llm/sdc_sandbox"; OUTD = "C:/llm/sdc_out"; KEY = os.path.expanduser("~/.ssh/pfc_phone"); PORT = "8022"; HOST = "localhost"
OPN = {1: "and", 2: "or", 3: "xor", 4: "not", 5: "nand"}
SSHBASE = ["-i", KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=6"]


def pc_ripple(net, inp):
    with open(net, "rb") as f: blob = f.read()
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    v = CC.CircuitCompiler(n_in).compile_ripple(gates, n_wire)(inp, 1)
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    return n_in, n_out, bytes(bit(o) for o in outs)


def main():
    net = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SBX, "pfc_operator.pfc")
    if not os.path.exists(net): print(f"netlist not found: {net} (build a demo first, e.g. python host/pfc_operator.py --test)"); return 1
    with open(net, "rb") as f: f.read(8); n_in = struct.unpack("<I", f.read(4))[0]
    random.seed(0); inp = [random.randrange(2) for _ in range(n_in)]
    n_in, n_out, golden = pc_ripple(net, inp)
    os.makedirs(OUTD, exist_ok=True)
    open(os.path.join(OUTD, "pfc_in.bin"), "wb").write(bytes(inp))
    print(f"deploying {os.path.basename(net)} ({n_in} in, {n_out} out) to the S24 Ultra …", flush=True)

    def sh(cmd, **kw): return subprocess.run(cmd, timeout=120, capture_output=True, text=True, **kw)
    def scp(src, dst): return sh(["scp", "-P", PORT] + SSHBASE + [src, f"{HOST}:{dst}"])
    try:
        for src, dst in [(os.path.join(HERE, "pfc_pulse.c"), "pfc_pulse.c"), (net, "net.pfc"), (os.path.join(OUTD, "pfc_in.bin"), "in.bin")]:
            r = scp(src, dst)
            if r.returncode: print(f"  scp failed — is Termux sshd up + `adb forward tcp:8022 tcp:8022`?\n  {r.stderr.strip()}"); return 1
        r = sh(["ssh", "-p", PORT] + SSHBASE + [HOST, "clang -O3 pfc_pulse.c -o pfc_pulse && ./pfc_pulse net.pfc in.bin out.bin && echo OK"])
        if "OK" not in r.stdout: print(f"  on-device build/run failed:\n  {r.stdout}{r.stderr}"); return 1
        r = sh(["scp", "-P", PORT] + SSHBASE + [f"{HOST}:out.bin", os.path.join(OUTD, "pfc_phone_out.bin")])
        phone = open(os.path.join(OUTD, "pfc_phone_out.bin"), "rb").read()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  connection/tooling error: {e}\n  Prereq: Termux `sshd` + `adb forward tcp:8022 tcp:8022`."); return 1

    ok = phone == golden
    print(f"\n  S24 Ultra pulse == PC pulse (byte-exact): {ok}   [{n_out} output bits over the same input]", flush=True)
    print("  the Muhlnickel computed identically on both devices." if ok else "  MISMATCH — investigate.", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
