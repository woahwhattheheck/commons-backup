#!/usr/bin/env python3
"""
host/coder.py — Titan's CODING HARNESS: an OUTCOME-DRIVEN agentic coding loop.

Agency reframe (owner 07-13): Titan is an extension of the USER'S will; success = achieving the outcome the user asked
for, judged by the OUTCOME, not by following instructions. So this harness does not run a fixed procedure — it loops
toward the user's goal: the model WRITES code → RUNS it for real (the sandbox) → reads the REAL output → SELF-VERIFIES
against the goal (writes checks/assertions that PROVE the outcome) → DEBUGS from the real error → repeats until the
outcome is achieved (verified by execution) or a bound is hit. §2-clean: the model does all the thinking + elects every
run via a native tool call; the harness only executes exactly what the model asked and feeds back the real result.
§12-clean: an honest "couldn't achieve it, here's how far it got + the error" beats a faked success.

Usage:  python host/coder.py "write a function that returns the nth prime, and prove it on the 10th"
Env:    LLM_URL (default http://127.0.0.1:8080), CODER_MAXITERS (default 8)
"""
import json, os, subprocess, sys, tempfile, time, urllib.request

LLM = os.environ.get("LLM_URL", "http://127.0.0.1:8080").rstrip("/")
MAXITERS = int(os.environ.get("CODER_MAXITERS", "8"))
# WHERE the harness codes: default the safe sandbox, but CODER_DIR points it at a REAL project on THIS PC (owner:
# "run from desktop and code onto the PC or any connected device"). A connected phone is CODER_DIR=an adb-synced dir
# + `adb push` after each write (the device leg — staged: needs the phone tethered). §3: never the self-repo.
SANDBOX = os.path.abspath(os.environ.get("CODER_DIR", "C:/llm/sandbox"))
os.makedirs(SANDBOX, exist_ok=True)
ADB_PUSH = os.environ.get("CODER_ADB_DEST", "")   # e.g. /sdcard/titan_project — push each written file to the phone

# Codex-style action space (convergent 2026 harness pattern: externalize state to FILES, run to get real feedback).
TOOL = [
    {"type": "function", "function": {"name": "run_python",
        "description": "Execute Python 3 and return its REAL stdout/stderr. RUN + TEST your code every step.",
        "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {"name": "write_file",
        "description": "Write text to a file in the project (creates/overwrites). Build multi-file projects this way.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "read_file",
        "description": "Read a file's contents from the project (to edit existing code).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "list_files",
        "description": "List files in the project directory.",
        "parameters": {"type": "object", "properties": {}}}},
]

HARNESS = (
    "You are Titan's coding harness. Achieve the USER'S GOAL by writing Python and CALLING run_python to actually run "
    "it — never claim it works without running it. Method: (1) write the code; (2) run it; (3) write a SELF-CHECK "
    "(assertions or prints on known cases) that PROVES the goal is met, and run that too; (4) if the real output is "
    "wrong or errors, DEBUG from the actual error and run again. Iterate until the output PROVES the goal is achieved. "
    "Only when the execution proves it, give the final code in one ```python block and a one-line statement of what the "
    "verified output was. If you cannot achieve it, say so honestly with the closest attempt and the real error.")


def sandbox_run(code):
    f = tempfile.NamedTemporaryFile("w", suffix=".py", dir=SANDBOX, delete=False, encoding="utf-8")
    f.write(code); f.close()
    try:
        r = subprocess.run([sys.executable, f.name], capture_output=True, text=True, timeout=20, cwd=SANDBOX)
        out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
        return (out or "(no output)")[:3000]
    except subprocess.TimeoutExpired:
        return "[timed out after 20s]"
    except Exception as e:
        return f"[run error: {e}]"
    finally:
        try: os.remove(f.name)
        except Exception: pass


# ENERGY DIAL (the thinking slider, INV-51): cap the per-step compute instead of brute-forcing 700 tokens (wasted
# joules on a watts-limited box, STUDY_NOTES §8). CODER_MAXTOK = how much compute to spend per step; CODER_THINK toggles
# the reasoning channel. Lower = fewer tokens = fewer joules; the coding app's slider will drive these.
MAXTOK = int(os.environ.get("CODER_MAXTOK", "384"))
THINK = os.environ.get("CODER_THINK", "0") == "1"


def chat(messages):
    body = json.dumps({"messages": messages, "max_tokens": MAXTOK, "temperature": 0.0, "cache_prompt": True,
                       "tools": TOOL, "tool_choice": "auto",
                       "chat_template_kwargs": {"enable_thinking": THINK}}).encode()
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        LLM + "/v1/chat/completions", body, {"Content-Type": "application/json"}), timeout=1800).read())
    return r["choices"][0]["message"]


def harness(goal):
    print(f"[coder] GOAL: {goal}\n" + "=" * 70)
    msgs = [{"role": "system", "content": HARNESS}, {"role": "user", "content": goal}]
    ran_clean = False
    for i in range(MAXITERS):
        m = chat(msgs)
        calls = m.get("tool_calls") or []
        msgs.append({"role": "assistant", "content": m.get("content") or "", **({"tool_calls": calls} if calls else {})})
        if m.get("content"):
            print(f"\n[iter {i}] model:\n{m['content'][:500]}")
        if not calls:
            break                                       # the model judged the outcome achieved (or gave up) — done
        for c in calls:
            fn = (c.get("function") or {}).get("name", "run_python")
            try:
                a = json.loads(c["function"].get("arguments") or "{}")
            except Exception:
                a = {}
            if fn == "write_file":
                p = os.path.join(SANDBOX, os.path.basename(a.get("path", "f.txt")))
                open(p, "w", encoding="utf-8").write(a.get("content", ""))
                out = f"wrote {os.path.basename(p)} ({len(a.get('content',''))} chars) to {SANDBOX}"
                if ADB_PUSH:                                   # deploy onto the connected phone
                    r = subprocess.run(["adb", "push", p, f"{ADB_PUSH}/{os.path.basename(p)}"], capture_output=True, text=True)
                    out += f" · adb push → {'ok' if r.returncode == 0 else r.stderr.strip()[:60]}"
            elif fn == "read_file":
                p = os.path.join(SANDBOX, os.path.basename(a.get("path", "")))
                out = open(p, encoding="utf-8").read()[:3000] if os.path.exists(p) else "(no such file)"
            elif fn == "list_files":
                out = ", ".join(os.listdir(SANDBOX)) or "(empty)"
            else:
                code = a.get("code", "")
                out = sandbox_run(code)
                ran_clean = ("[stderr]" not in out and "Traceback" not in out)
            print(f"\n[iter {i}] {fn} → {out[:280]}")
            msgs.append({"role": "tool", "tool_call_id": c.get("id", "0"), "name": fn, "content": out})
    print("\n" + "=" * 70)
    print(f"[coder] finished in ≤{i+1} iters; last run {'clean ✓' if ran_clean else 'had errors/none'}")
    return msgs


if __name__ == "__main__":
    goal = sys.argv[1] if len(sys.argv) > 1 else "Write a function nth_prime(n) and PROVE nth_prime(10)==29 by running it."
    harness(goal)
