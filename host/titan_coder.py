#!/usr/bin/env python3
"""host/titan_coder.py — a Codex-style coding harness you can point at Titan (or any served model) (owner 07-15).

An agentic read -> edit -> run -> observe loop over a SANDBOXED copy of a target, driven by any OpenAI-compatible chat
endpoint (llama.cpp `server` exposes exactly this). Point it at a served `titan.gguf` and give it a COPY of its own
source, and watch Titan code on itself.

  # 1) you serve a model (on hardware that can take it — see the honesty note below), e.g.:
  #    llama-server -m C:/llm/models/titan.gguf --no-repack -c 8192 --port 8080
  # 2) then:
  python host/titan_coder.py --target host --task "add a docstring example to titan_circuit.py and run its self-test"
  python host/titan_coder.py --mock          # prove the loop end-to-end with NO model (a scripted fake agent)

HONESTY (owner's hardware): running titan.gguf (40 GB) for real-time codegen on an 8 GB laptop STREAMS from disk and is
slow (sub-token/s) — it will not scream (mmap, ~0 RAM per MEASURE_ALREADY) but it will crawl. For usable speed serve a
smaller model, or run on the beefier device / a cloud GPU. The harness is model-agnostic on purpose. It never loads a
model itself; it only talks to an endpoint YOU start.
"""
import argparse, json, os, re, shutil, subprocess, sys, time, urllib.request

SYSTEM = """You are a coding agent operating inside a sandbox directory. Each turn, output EXACTLY ONE action, nothing else:
  READ <path>                      -- read a file (I return its contents)
  WRITE <path>                     -- then a fenced ```code``` block; I write it (overwrites)
  RUN <shell command>              -- I run it in the sandbox and return stdout/stderr (truncated)
  DONE <one-line summary>          -- you are finished
Work in small steps. Read before you write. Verify with RUN. Keep going until the task is done, then DONE."""


def chat(endpoint, model, messages, max_tokens=512):
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.2,
                       "max_tokens": max_tokens, "stream": False}).encode()
    req = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"]


def parse_action(txt):
    m = re.search(r"\bREAD\s+(\S+)", txt)
    if m: return ("read", m.group(1), None)
    m = re.search(r"\bWRITE\s+(\S+)", txt)
    if m:
        code = re.search(r"```[a-zA-Z0-9_]*\n(.*?)```", txt, re.S)
        return ("write", m.group(1), code.group(1) if code else "")
    m = re.search(r"\bRUN\s+(.+)", txt)
    if m: return ("run", m.group(1).strip().splitlines()[0], None)
    m = re.search(r"\bDONE\b\s*(.*)", txt)
    if m: return ("done", m.group(1).strip(), None)
    return (None, None, None)


def safe(sandbox, rel):
    p = os.path.abspath(os.path.join(sandbox, rel))
    if not p.startswith(os.path.abspath(sandbox)): raise ValueError("path escapes sandbox")
    return p


def run_loop(sandbox, task, responder, max_steps=24):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Sandbox files: {os.listdir(sandbox)}\nTASK: {task}"}]
    for step in range(1, max_steps + 1):
        reply = responder(msgs)
        print(f"\n── step {step} ── agent:\n{reply.strip()[:600]}", flush=True)
        msgs.append({"role": "assistant", "content": reply})
        kind, arg, payload = parse_action(reply)
        if kind == "done":
            print(f"\n[DONE] {arg}", flush=True); return True
        elif kind == "read":
            try: obs = open(safe(sandbox, arg), encoding="utf-8", errors="replace").read()[:4000]
            except Exception as e: obs = f"ERROR: {e}"
            obs = f"[READ {arg}]\n{obs}"
        elif kind == "write":
            try:
                p = safe(sandbox, arg); os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "w", encoding="utf-8").write(payload or ""); obs = f"[WROTE {arg}] {len(payload or '')} bytes"
            except Exception as e: obs = f"ERROR: {e}"
        elif kind == "run":
            try:
                r = subprocess.run(arg, shell=True, cwd=sandbox, capture_output=True, text=True, timeout=120)
                obs = f"[RAN {arg}] exit={r.returncode}\nSTDOUT:\n{r.stdout[-1500:]}\nSTDERR:\n{r.stderr[-800:]}"
            except Exception as e: obs = f"ERROR: {e}"
        else:
            obs = "No valid action found. Reply with exactly one of READ/WRITE/RUN/DONE."
        print(f"   observation: {obs[:300].replace(chr(10),' ')}", flush=True)
        msgs.append({"role": "user", "content": obs})
    print("\n[stopped] max steps reached.", flush=True); return False


def mock_responder():
    script = [
        "READ seed.py",
        "WRITE add.py\n```python\ndef add(a, b):\n    return a + b\n```",
        'RUN python -c "import add; print(add(2,3))"',
        "DONE wrote and verified add(a,b) -> 5",
    ]
    it = iter(script)
    def _r(msgs): return next(it, "DONE done")
    return _r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1/chat/completions")
    ap.add_argument("--model", default="titan.gguf")
    ap.add_argument("--target", default="host", help="dir to copy into the sandbox (its own code, by default)")
    ap.add_argument("--task", default="Read titan_circuit.py and write a one-line summary of it to SUMMARY.txt")
    ap.add_argument("--mock", action="store_true", help="run the loop with a scripted fake agent (no model)")
    a = ap.parse_args()

    sandbox = os.path.join(os.environ.get("TEMP", "/tmp"), "titan_coder_sandbox")
    if os.path.exists(sandbox): shutil.rmtree(sandbox, ignore_errors=True)
    os.makedirs(sandbox, exist_ok=True)

    if a.mock:
        open(os.path.join(sandbox, "seed.py"), "w").write("# seed file the mock agent reads\nX = 1\n")
        print(f"MOCK RUN (no model) — sandbox {sandbox}", flush=True)
        ok = run_loop(sandbox, "write and verify a small add() function", mock_responder())
        print(f"\n[mock verify] add.py exists: {os.path.exists(os.path.join(sandbox,'add.py'))}  loop-ok: {ok}", flush=True)
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = os.path.join(root, a.target)
        for f in os.listdir(src):
            if f.endswith(".py"):
                shutil.copy(os.path.join(src, f), sandbox)
        print(f"pointing model '{a.model}' @ {a.endpoint} at a COPY of {a.target}/ ({sandbox})", flush=True)
        try:
            run_loop(sandbox, a.task, lambda m: chat(a.endpoint, a.model, m))
        except Exception as e:
            print(f"\n[endpoint error] {e}\n  -> start a server first, e.g.:  "
                  f"llama-server -m C:/llm/models/{a.model} --no-repack -c 8192 --port 8080", flush=True)
