#!/usr/bin/env python3
"""
host/genrun.py — Titan's GENERATIVE RUNTIME: run a program on TITAN's compute by GENERATING its output.

Owner's idea (07-13): "what if Titan can see a file and run it on ITS OWN compute rather than yours — so it could play
Minecraft PC on a phone, because it looks at the code and just generates and displays it on screen." The model IS the
runtime: given the PROGRAM (its rules/code) + the current STATE + an INPUT, it computes the next state and GENERATES the
screen (as SVG); an installed codec (resvg → PNG, INV-119) DISPLAYS the real frame. So the program "runs" wherever Titan
can generate — a phone plays software its hardware can't execute, because the model emulates the output. This is the
emulation envelope (INV-118) + the render codecs (INV-119) fused into a harness; the game-generation moonshot, concrete.

§2-clean: the model does 100% of the "execution" (state + frame); code only renders exactly what it emitted. Honest: a
small/slow model gives rough, low-consistency frames — this proves the MECHANISM (Titan as the runtime); fidelity scales
with the model + the map/bake (a game operator baked in).

Usage:  python host/genrun.py "a top-down grid dungeon, @ is the player" "right,right,down,down"
Env:    LLM_URL (default http://127.0.0.1:8080)
"""
import json, os, re, subprocess, sys, time, urllib.request

LLM = os.environ.get("LLM_URL", "http://127.0.0.1:8080").rstrip("/")
REND = "C:/llm/bin/renderers"; OUT = f"{REND}/out"; os.makedirs(OUT, exist_ok=True)

RUNTIME = (
    "You ARE a generative runtime — the engine that RUNS a program by generating its screen. Given PROGRAM (the rules), "
    "STATE (json), and INPUT (a key), compute the NEXT state and DRAW the resulting screen as a single self-contained "
    "<svg viewBox='0 0 256 256'>…</svg> (a real game frame: background, the world, the player). Keep the world CONSISTENT "
    "with the prior state. Output ONLY one JSON object on one line: {\"state\": <next state json>, \"svg\": \"<svg …>\"}.")


def render_png(svg, name):
    src = f"{OUT}/{name}.svg"; dst = f"{OUT}/{name}.png"
    open(src, "w", encoding="utf-8").write(svg)
    r = subprocess.run([f"{REND}/resvg/resvg.exe", "--width", "256", src, dst], capture_output=True, timeout=30)
    return dst if r.returncode == 0 and os.path.exists(dst) else None


def step(program, state, inp):
    msg = f"PROGRAM: {program}\nSTATE: {json.dumps(state)}\nINPUT: {inp}"
    body = json.dumps({"messages": [{"role": "system", "content": RUNTIME}, {"role": "user", "content": msg}],
                       "max_tokens": 600, "temperature": 0.2, "cache_prompt": True,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        LLM + "/v1/chat/completions", body, {"Content-Type": "application/json"}), timeout=900).read())
    txt = r["choices"][0]["message"].get("content", "")
    # ROBUST: the SVG contains quotes/newlines that break json.loads, so extract the <svg> DIRECTLY (primary), and the
    # state best-effort — never let a malformed wrapper crash the runtime (the frame is what matters).
    sm = re.search(r"<svg[\s\S]*?</svg>", txt, re.I)
    svg = sm.group(0) if sm else ""
    new_state = dict(state)
    sj = re.search(r'"state"\s*:\s*(\{[^{}]*\})', txt)        # a flat state object, if present
    if sj:
        try: new_state = json.loads(sj.group(1))
        except Exception: pass
    new_state["turn"] = int(state.get("turn", 0)) + 1
    return new_state, svg


def main():
    program = sys.argv[1] if len(sys.argv) > 1 else "a top-down 8x8 grid dungeon; @ = player on a floor of . with # walls"
    inputs = (sys.argv[2] if len(sys.argv) > 2 else "start,right,down").split(",")
    print(f"[genrun] PROGRAM: {program}\n[genrun] running {len(inputs)} frames on Titan's own compute (generating, not executing)…")
    state = {"turn": 0}; frames = []
    for i, inp in enumerate(inputs):
        t = time.time()
        state, svg = step(program, state, inp.strip())
        png = render_png(svg, f"gen{i:02d}") if svg else None
        frames.append(png)
        print(f"  frame {i} (input={inp.strip()!r}) {time.time()-t:.1f}s → {'PNG ' + os.path.basename(png) if png else 'no svg emitted'}  state={json.dumps(state)[:80]}")
    good = [f for f in frames if f]
    if len(good) >= 2:
        mp4 = f"{OUT}/genrun.mp4"
        subprocess.run([f"{REND}/ffmpeg.exe", "-y", "-framerate", "1", "-i", f"{OUT}/gen%02d.png",
                        "-pix_fmt", "yuv420p", "-vf", "scale=256:256", mp4], capture_output=True)
        print(f"[genrun] {len(good)}/{len(inputs)} frames GENERATED + displayed (real PNGs) → {mp4} — Titan RAN the program by generating it.")
    else:
        print(f"[genrun] only {len(good)} frame(s) rendered — the mechanism ran; frame fidelity needs a stronger model / a baked game operator.")


if __name__ == "__main__":
    main()
