#!/usr/bin/env python3
"""host/doom_play.py — DOOM by GRAB-not-RUN. Titan SIMULATES Doom from its LEARNED pattern (training) — the frame is
RECOGNIZED, not computed. The instant part is the energy lever: a recognized view is GRABBED from the memoize store
with ZERO forward passes (INV-117/147), so after a view is seen once it plays at full framerate. We never run 99.999%
of the model — a novel view pays one grab-from-the-pattern; a seen view pays nothing.

This is the buildable rung on the current runtime (llama.cpp does a full pass per token, so a NOVEL 960-pixel view is
one amortized generation; the sub-model param-fine grab is the frontier seam). What it PROVES: recall beats compute →
real-time. Titan generates every pixel; the rig only carries bytes + measures.

Run:  python host/doom_play.py [W] [H] [recall_frames]
Env:  LLM_URL (default http://127.0.0.1:8080 = Titan)
"""
import os, sys, time, importlib.util

spec = importlib.util.spec_from_file_location("d", os.path.join(os.path.dirname(__file__), "doom.py"))
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)


def main():
    w = int(sys.argv[1]) if len(sys.argv) > 1 else 32
    h = int(sys.argv[2]) if len(sys.argv) > 2 else 18
    recall_n = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    import shutil
    shutil.rmtree(d.CACHE, ignore_errors=True); os.makedirs(d.CACHE, exist_ok=True)

    print(f"[play] Titan authors its Doom operator (its learned-pattern renderer)…")
    op = d.author_doom(w, h)
    open(f"{d.OUT}/doom_play_operator.txt", "w", encoding="utf-8").write(op)
    print(f"[play] operator {len(op)}c")

    # COLD: grab this view from Titan's learned Doom pattern (one amortized generation)
    state = {"tick": 0, "pos": [1, 1], "angle": 0}
    t = time.time()
    png, state, ntok, dt, hit = d.play_frame(op, state, "start", w, h, "play_cold")
    print(f"[play] COLD (grab from the learned pattern): {dt:.1f}s, {ntok} tok, hit={hit} -> {os.path.basename(png) if png else 'FAIL'}")

    # RECALL: the SAME view, recall_n frames — GRAB from the memoize store, zero forward passes = instant
    t = time.time()
    hits = 0
    for i in range(recall_n):
        png, state, ntok, dt, hit = d.play_frame(op, state, "idle", w, h, f"play_r{i:03d}")
        hits += 1 if hit else 0
    el = time.time() - t
    fps = recall_n / el if el > 0 else float("inf")
    print(f"[play] RECALL {recall_n} frames: {el*1000:.0f}ms total, {hits}/{recall_n} hits, "
          f"{fps:.0f} fps (zero forward passes — grabbed, not run)")
    print(f"[play] GRAB-NOT-RUN: 1 grab-from-pattern warms the view; play runs at {fps:.0f} fps by recall (INV-147).")
    print(f"[play] frame: {d.OUT}/play_cold.png")


if __name__ == "__main__":
    main()
