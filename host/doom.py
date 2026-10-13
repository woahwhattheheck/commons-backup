#!/usr/bin/env python3
"""host/doom.py — a PURE DEBUG/TEST RIG for Titan running DOOM by generation. NOT part of the Titan file; it is the
"spec lab for debugging" (owner). The product is Titan itself — the operator, later baked into the file.

The rig does ONLY access + measure. Titan (the resident model) GENERATES everything: the game logic, its OWN palette,
every pixel, the render form, the next state. This file NEVER draws, decides, renders, or picks a color — it (1) asks
Titan to AUTHOR its own Doom operator, (2) sends state+input and receives Titan's generated frame, (3) packages Titan's
EXACT emitted bytes into a display container (a raw framebuffer envelope = access, no rendering of ours), and (4)
measures coherence. Every color and pixel is Titan's; the rig only carries bytes to the screen and measures.

Usage:  python host/doom.py [W] [H] [frames]
Env:    LLM_URL (default http://127.0.0.1:8080)
"""
import json, os, re, shutil, subprocess, sys, time, urllib.request

LLM = os.environ.get("LLM_URL", "http://127.0.0.1:8080").rstrip("/")
OUT = "C:/llm/bin/renderers/out"; os.makedirs(OUT, exist_ok=True)
FFMPEG = "C:/llm/bin/renderers/ffmpeg.exe"   # installed codec — used ONLY to view the raw framebuffer while debugging


def _post(messages, maxtok, temp=0.3, think=False):
    """Energy + access: one forward pass on Titan. Returns (text, timings). Decides/generates nothing itself."""
    body = json.dumps({"messages": messages, "max_tokens": maxtok, "temperature": temp, "cache_prompt": True,
                       "chat_template_kwargs": {"enable_thinking": think}}).encode()
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        LLM + "/v1/chat/completions", body, {"Content-Type": "application/json"}), timeout=1800).read())
    m = r["choices"][0]["message"]
    return (m.get("content", "") or ""), (r.get("timings") or {})


def author_doom(w, h):
    """Titan AUTHORS its own Doom operator — its palette, its per-frame emission contract, its state. 0% ours.
    We only state the emission SHAPE the rig can carry to the screen (a palette + a WxH grid); Titan fills all of it."""
    ask = (f"You ARE a first-person DOOM engine that RUNS the game by GENERATING the screen as pixels. Author your OWN "
           f"operator (a compact system rule you will then follow every frame). It MUST define, in this exact shape so a "
           f"display can carry your pixels:\n"
           f"PALETTE: one line, each color as `X=R,G,B` separated by ';' (X = a single character you pick; R,G,B 0-255)\n"
           f"then, each frame, exactly {h} lines of exactly {w} characters (every character = one PIXEL from your "
           f"palette), then a line `STATE: {{compact json}}`.\n"
           f"Pick your palette and how you draw a corridor/enemies/gun in perspective. Output ONLY your operator text.")
    op, _ = _post([{"role": "user", "content": ask}], maxtok=700, temp=0.4)
    return op.strip()


def parse_palette(text):
    """Read TITAN'S emitted palette (char -> RGB). The map is Titan's; the rig only applies it (access)."""
    pal = {}
    m = re.search(r'PALETTE:\s*(.+)', text)
    line = m.group(1) if m else ""
    for tok in re.findall(r'(.)\s*=\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})', line):
        ch, r, g, b = tok
        pal[ch] = (min(255, int(r)), min(255, int(g)), min(255, int(b)))
    return pal


def extract_grid(text, w, h):
    """Pull the WxH pixel grid Titan emitted (the lines that are mostly palette-width). Forgiving; carries Titan's chars."""
    lines = [ln.rstrip("\n") for ln in text.split("\n")]
    rows = [ln for ln in lines if not ln.strip().upper().startswith(("PALETTE", "STATE", "SIGMA", "Σ"))
            and len(ln.strip()) >= w * 0.5]
    return rows[:h]


def write_ppm(path, px):
    """The display CONTAINER (access): a P6 header + Titan's EXACT RGB bytes. No compression, no transform, no drawing."""
    h = len(px); w = len(px[0]) if h else 0
    body = bytearray()
    for row in px:
        for (r, g, b) in row:
            body += bytes((r, g, b))
    open(path, "wb").write(("P6\n%d %d\n255\n" % (w, h)).encode() + bytes(body))


def to_framebuffer(grid, pal, w, h, scale=10):
    """Apply TITAN'S palette to TITAN'S grid → a framebuffer (access — Titan chose every color + char). Upscale = repeat
    Titan's pixels for a visible window (display, not art). Unknown chars → black (a gap, not a color of ours)."""
    fb = []
    for y in range(h):
        row = grid[y] if y < len(grid) else ""
        line = []
        for x in range(w):
            ch = row[x] if x < len(row) else " "
            line.append(pal.get(ch, (0, 0, 0)))
        for _ in range(scale):
            fb.append([c for c in line for _ in range(scale)])
    return fb


def coherence(grid, pal, w, h):
    """MEASURE (the variance/quality band): fraction of the WxH cells that are valid Titan-palette pixels, and how many
    distinct colors appear (a degenerate all-one-char frame scores low). Pure measurement, no judgement of content."""
    total = w * h
    valid = distinct = 0
    seen = set()
    for y in range(h):
        row = grid[y] if y < len(grid) else ""
        for x in range(w):
            ch = row[x] if x < len(row) else None
            if ch in pal:
                valid += 1; seen.add(ch)
    distinct = len(seen)
    return round(valid / total, 3) if total else 0.0, distinct


def gen_frame(op, state, action, w, h, name):
    """One tick: Titan generates the frame (its pixels) + next state. The rig carries Titan's bytes to a container and
    measures. Returns (ppm_path, png_path_for_debug_view, next_state, ntok, dt, cover, distinct)."""
    msg = f"STATE: {json.dumps(state)}\nINPUT: {action}\nGenerate the next frame now (palette line if changed, then the {h}×{w} pixel grid, then STATE)."
    t = time.time()
    txt, tm = _post([{"role": "system", "content": op}, {"role": "user", "content": msg}], maxtok=w * h + 400, temp=0.3)
    dt = time.time() - t
    ntok = tm.get("predicted_n") or len(txt.split())
    pal = parse_palette(op) or {}
    pal.update(parse_palette(txt))                       # Titan may restate/extend its palette per frame
    grid = extract_grid(txt, w, h)
    cover, distinct = coherence(grid, pal, w, h)
    fb = to_framebuffer(grid, pal, w, h)
    ppm = f"{OUT}/{name}.ppm"; write_ppm(ppm, fb)
    png = f"{OUT}/{name}.png"                            # debug VIEW only (installed codec converts the raw framebuffer)
    try:
        subprocess.run([FFMPEG, "-y", "-i", ppm, png], capture_output=True, timeout=30)
    except Exception:
        png = None
    new = dict(state)
    sm = re.search(r'STATE:\s*(\{[^{}]*\})', txt)
    if sm:
        try: new = {**state, **json.loads(sm.group(1))}
        except Exception: pass
    new["tick"] = int(state.get("tick", 0)) + 1
    return ppm, png, new, ntok, dt, cover, distinct


# ── MEMOIZE-AS-RENDERER (INV-147; ENERGY.md "recognized → zero forward pass → instant"). The view space of a first-
# person game is FINITE (grid cell × facing), so a recurring VIEW is RECALLED with ZERO forward passes = INSTANT. Only
# a NOVEL view is generated (once, amortized). Recall beats compute → real-time play. The cache holds Titan's OWN prior
# frames (its generated pixels replayed) — nothing invented.
CACHE = f"{OUT}/framecache"; os.makedirs(CACHE, exist_ok=True)


def view_key(state):
    """Quantize the state to the FINITE view space: grid cell + facing (4). Recurring views collide → cache hit."""
    pos = state.get("pos") or state.get("player") or state.get("p") or [0, 0]
    try: cx, cy = int(float(pos[0])), int(float(pos[1]))
    except Exception: cx, cy = 0, 0
    ang = (int(float(state.get("angle", state.get("a", 0)))) % 360) // 90
    return f"v_{cx}_{cy}_{ang}"


def play_frame(op, state, action, w, h, name):
    """One tick with memoize: HIT = recall Titan's cached frame instantly (0 tok, ~0 s); MISS = generate once + cache.
    Returns (png, next_state, ntok, dt, hit)."""
    k = view_key(state)
    hit = f"{CACHE}/{k}.png"
    if os.path.exists(hit):                                   # RECALL — instant, zero forward passes (the energy lever)
        out = f"{OUT}/{name}.png"; shutil.copyfile(hit, out)
        ns = {**state, "tick": int(state.get("tick", 0)) + 1}
        return out, ns, 0, 0.0, True
    ppm, png, ns, ntok, dt, cover, distinct = gen_frame(op, state, action, w, h, name)
    if png and os.path.exists(png):
        shutil.copyfile(png, f"{CACHE}/{k}.png")              # store Titan's generated view for instant recall next time
    return png, ns, ntok, dt, False


def main():
    w = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    h = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    nframes = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    print(f"[doom] asking Titan to AUTHOR its own Doom operator ({w}×{h})…")
    op = author_doom(w, h)
    print("-" * 70 + "\n" + op[:1400] + "\n" + "-" * 70)
    open(f"{OUT}/doom_operator.txt", "w", encoding="utf-8").write(op)
    state = {"tick": 0}
    inputs = ["start", "forward", "shoot", "left"][:nframes]
    for i, action in enumerate(inputs):
        ppm, png, state, ntok, dt, cover, distinct = gen_frame(op, state, action, w, h, f"doom{i:02d}")
        print(f"  frame {i} input={action!r} {dt:.1f}s {ntok}tok  coverage={cover} colors={distinct}  "
              f"-> {os.path.basename(png) if png else os.path.basename(ppm)}")
    print("[doom] done — Titan generated every pixel; the rig only carried its bytes + measured (0% ours in the frame).")


if __name__ == "__main__":
    main()
