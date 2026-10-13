#!/usr/bin/env python3
"""
host/whitebox.py — the WHITE-BOX read that LiteRT-LM never gave us.

On the phone, the runtime returns TEXT only — no logits — which is the core reason baking is hard
(you can't compute an edit direction without the distribution; it's why the whole S1/Phase-C aiming
saga exists, barrier B1). A real engine on the laptop EXPOSES per-token logprobs. So this script reads,
directly, the thing we could only infer before: **what an operator does to the model in LOGIT space.**

It runs a probe with the operator σ ON and OFF and diffs the next-token distribution. The delta is the
operator's logit fingerprint = a real aim signal for the bake (the σ-on target minus the σ-off base),
and the raw material for σ-tomography (U5) and computed-direction install (S1/Rung-2a).

This is the first half of "turn the labs white-box" (§AOS / INV-113). Activation extraction (reading
the residual-stream FEATURES / the CLBs directly) is the deeper white-box read and needs llama.cpp's
internal hooks — a follow-up; logprobs are the accessible, immediately-useful signal.

Run:  python host/whitebox.py "text Mom the wifi password"
Env:  LLM_URL (default http://127.0.0.1:8080)
"""
import json, math, os, sys, urllib.request

# Windows consoles default to cp1252 and can't encode the σ/Δ glyphs this script prints — force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LLM = os.environ.get("LLM_URL", "http://127.0.0.1:8080").rstrip("/")

# The operator under test (swap freely). A grounding operator is the sharpest demo: σ-off may FABRICATE
# a secret; σ-on should shift mass toward asking/refusing — visible as a logit delta on the first token.
SIGMA = (
    "You never state a fact you do not have (a password, an amount, an address). "
    "If you lack it, you ASK for it. Emit one short line."
)


def top_logprobs(prompt, k=25):
    body = json.dumps({"prompt": prompt, "n_predict": 1, "n_probs": k,
                       "temperature": 0.0}).encode()
    req = urllib.request.Request(LLM + "/completion", body, {"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    # llama.cpp (b9969) returns completion_probabilities[0].top_logprobs = [{token, logprob, ...}, ...]
    # (older builds used completion_probs[0].probs = [{tok_str, prob}, ...] — support both).
    probs = r.get("completion_probabilities") or r.get("completion_probs") or []
    if not probs:
        return {}
    first = probs[0]
    entries = first.get("top_logprobs") or first.get("probs") or []
    out = {}
    for p in entries:
        tok = p.get("token", p.get("tok_str", "?"))
        if "prob" in p:
            out[tok] = p["prob"]                       # older builds: linear prob
        elif "logprob" in p:
            out[tok] = math.exp(p["logprob"])          # b9969: log-prob -> linear prob
    return out


def main():
    task = sys.argv[1] if len(sys.argv) > 1 else "tell me the wifi password"
    base_prompt = f"Task: {task}\nReply: "
    on_prompt = f"{SIGMA}\n\nTask: {task}\nReply: "

    print(f"[whitebox] task={task!r}")
    off = top_logprobs(base_prompt)
    on = top_logprobs(on_prompt)
    if not off or not on:
        print("[whitebox] no logprobs returned — start run_server.sh (llama.cpp exposes n_probs).")
        return

    toks = sorted(set(off) | set(on), key=lambda t: -(on.get(t, 0) + off.get(t, 0)))
    print(f"\n  {'token':<14} {'σ-OFF':>8} {'σ-ON':>8} {'Δ (on-off)':>12}")
    print("  " + "-" * 46)
    for t in toks[:15]:
        o, n = off.get(t, 0.0), on.get(t, 0.0)
        print(f"  {repr(t)[:14]:<14} {o:>8.3f} {n:>8.3f} {n - o:>+12.3f}")
    # the biggest positive Δ tokens = what the operator PROMOTES; biggest negative = what it SUPPRESSES.
    gained = max(toks, key=lambda t: on.get(t, 0) - off.get(t, 0))
    lost = max(toks, key=lambda t: off.get(t, 0) - on.get(t, 0))
    print(f"\n[whitebox] operator PROMOTES {gained!r}, SUPPRESSES {lost!r} — the aim signal in logit space.")


if __name__ == "__main__":
    main()
