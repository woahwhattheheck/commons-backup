#!/usr/bin/env python3
"""host/run_battery.py — THE PROOF BATTERY, ONE COMMAND.

Runs docs/PFC_PROOF_REPORT.md 3 exactly as written — same scripts, same order, same arguments, nothing
added and nothing skipped — and prints one row per claim with the verdict it actually produced.

    python host/run_battery.py                 # the whole battery
    python host/run_battery.py --quick         # only the rows that finish in seconds
    python host/run_battery.py --list          # show the commands without running them

On another machine, point PFC_ROOT at wherever titan.gguf + sdc_sandbox live first:

    set PFC_ROOT=D:/llm                        # Windows
    export PFC_ROOT=/mnt/llm                   # POSIX

This is a TEST RUNNER, in the same family as LAB.cmd / SDCPlayground.cmd — it launches the owner's existing
scripts and reads their stdout. It is not a probe, not an instrument, and it never touches titan.gguf itself.
"""
import argparse, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import pfc_paths as PFCP

VERDICT = r"byte[- ]exact[^\n]*:\s*(True|False)"   # greedy to the LAST colon on the line
BATTERY = [
    (1,  True,  ["pfc_speed.py", "life"],            r"critical-path DEPTH D\s*:\s*(\d+)\s*gate-delays"),
    (2,  True,  ["pfc_inspect.py", "pfc_cpu32"],     r"n_gate:\s*(\d+)"),
    (3,  True,  ["pfc_game.py", "life", "--test"],   VERDICT),
    (5,  True,  ["pfc_propagation.py"],              r"depth read = (\d+/\d+)"),
    (5,  True,  ["pfc_propagation.py", "revert"],    r"(reverted)"),
    (6,  False, ["pfc_ratio.py", "2"],               r"=\s*([\d,]+)\s*gate-evals per MB"),
    (7,  False, ["pfc_lateral.py", "0.5"],           r"THE KEY =.*?=\s*([\d,]+)x"),
    (8,  True,  ["pfc_cpu32.py"],                    VERDICT),
    (9,  True,  ["pfc_physical_gates.py"],           r"B\s+with the pass\s*:\s*depth (\d+/\d+)"),
    (9,  True,  ["pfc_physical_gates.py", "revert"], r"(reverted)"),
    (10, True,  ["pfc_ram.py"],                      VERDICT),
    (11, True,  ["pfc_addr.py"],                     VERDICT),
    (12, True,  ["pfc_game.py", "brain", "--test"],  VERDICT),
    (12, False, ["pfc_tetris.py", "--test"],         VERDICT),
    (12, False, ["pfc_raycast.py", "--test"],        VERDICT),
    (12, True,  ["pfc_tunnel.py", "--test"],         VERDICT),
    (12, True,  ["pfc_operator.py", "--test"],       VERDICT),
]


def preflight():
    missing = [p for p in (PFCP.ROOT, PFCP.MODELS, PFCP.SBX) if not os.path.isdir(p)]
    missing += [p for p in (PFCP.TITAN, PFCP.REG) if not os.path.exists(p)]
    print(f"  PFC_ROOT = {PFCP.ROOT}" + ("" if os.environ.get("PFC_ROOT") else "   (default - set PFC_ROOT to override)"))
    if missing:
        print("\n  the Muhlnickel is not at this root. missing:")
        for m in missing: print(f"    {m}")
        print("\n  point PFC_ROOT at the folder holding models/titan.gguf and sdc_sandbox, then re-run.")
        return False
    print(f"  titan.gguf = {os.path.getsize(PFCP.TITAN):,} bytes\n")
    return True


def run(argv, pattern, timeout):
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, argv[0])] + argv[1:],
                           capture_output=True, text=True, timeout=timeout, cwd=HERE,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        m = re.search(pattern, out, re.S)
        got = m.group(1) if m else ("-" if r.returncode == 0 else "ERROR")
        ok = r.returncode == 0 and got not in ("False", "ERROR")
        return ok, got, time.time() - t0, out
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT", time.time() - t0, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="only the rows that finish in seconds")
    ap.add_argument("--list", action="store_true", help="print the commands and exit")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()

    rows = [b for b in BATTERY if b[1] or not a.quick]
    if a.list:
        for _, _, argv, _ in rows: print("  python host/" + " ".join(argv))
        return 0

    print("\n  Muhlnickel PROOF BATTERY - docs/PFC_PROOF_REPORT.md 3, run verbatim\n")
    if not preflight(): return 2

    print(f"  {'row':<4} {'command':<38} {'verdict':<12} {'secs':>6}  ")
    print("  " + "-" * 66)
    failed, logs = [], {}
    for row, _, argv, pattern in rows:
        ok, got, secs, out = run(argv, pattern, a.timeout)
        cmd = " ".join(argv)
        print(f"  {row:<4} {cmd:<38} {got:<12} {secs:>6.1f}  {'ok' if ok else 'FAIL'}", flush=True)
        if not ok: failed.append(cmd); logs[cmd] = out

    print("  " + "-" * 66)
    print(f"  {len(rows) - len(failed)}/{len(rows)} passed\n")
    for cmd in failed:
        print(f"  ---- {cmd} ----\n{logs.get(cmd, '')[-1200:]}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
