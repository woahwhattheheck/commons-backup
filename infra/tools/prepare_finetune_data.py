#!/usr/bin/env python3
"""
prepare_finetune_data.py — turn the agent's exported capture into fine-tune-ready data.

The on-device "data flywheel" (Settings -> Training data -> Export) writes a JSONL where each
line is one of:

  a STEP the agent decided:   {"obj","app","screen","action","result", "op"?}
  a STEP-SCORE sentinel:      {"stepScore": true, "m": <int>, "op"}   (reward for the step ABOVE it)
  a TASK-END marker:          {"taskEnd": true, "obj", "success", "fclass"?, "steps"?}

`op` (the model-chosen reasoning operator), the `stepScore` reward M (progress - cost), and the
task-end `fclass`/`steps` are OPTIONAL enrichment (present only when the operator layer was on);
an older export without them still parses. They make the data WEIGHTABLE — prefer high-M,
proven-operator decisions over a flat pass/fail filter.

This script turns that into supervised fine-tuning (SFT) examples for a SMALL model that
INTERPRETS THE PERCEPTION LAYER and emits one action — i.e. a text-only "action head":

    input  (user):       Objective + the on-screen element list (the perception)
    output (assistant):  the action JSON the agent chose

By default it keeps only steps from SUCCESSFUL tasks (the clean positive examples) and drops
steps whose own result was FAILED. The raw export still has everything; this is the filtered
training view.

IMPORTANT — format match (G1): a fine-tuned head only works in the app if the prompt it's TRAINED
on matches the prompt the app SENDS it at inference. PROMPT_TEMPLATE below is that contract, and it
is kept BYTE-IDENTICAL to `AgentBrain.actionHeadPrompt(...)` in the app (the fast-head path sends
exactly this shape). If you change one, change the other.

Usage:
    python3 prepare_finetune_data.py --input training_data.jsonl --output sft.jsonl
    # options:
    #   --format chat|alpaca     (default chat: {"messages":[...]}, works with Unsloth/TRL)
    #   --include-failed-tasks   (also keep steps from tasks that did NOT complete)
    #   --include-failed-steps   (also keep steps whose own result was FAILED)
    #   --dedup                  (drop duplicate screen+action pairs)
    #   --with-weights           (attach a "weight" + "meta"{op,m,result} to each example for
    #                             reward-weighted / operator-aware training; default off keeps the
    #                             output byte-identical to before for existing pipelines)
    #   --min-m N                (drop steps whose realized M is present and below N — keep only the
    #                             decisions that actually moved the task; steps with no M are kept)
"""
import argparse, json, sys

# KEEP BYTE-IDENTICAL to AgentBrain.actionHeadPrompt(...) in the app (the G1 action-head contract).
PROMPT_TEMPLATE = (
    "You pilot an Android phone, ONE action per step. Choose the single best action to advance "
    "the objective, given the on-screen elements.\n"
    "OBJECTIVE: {obj}\n"
    "APP: {app}\n"
    "SCREEN ELEMENTS:\n{screen}\n"
    "Reply with ONE JSON action."
)


def load(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
    return rows


def segment(rows, include_failed_tasks):
    """Group steps into tasks using the taskEnd markers; yield the step-lists to KEEP. A stepScore
    sentinel is the reward for the step line just above it, so it's folded onto that step's dict
    (m + op) rather than treated as its own step."""
    buf, kept_tasks, dropped_tasks = [], 0, 0
    for r in rows:
        if r.get("taskEnd"):
            if r.get("success") or include_failed_tasks:
                if buf:
                    kept_tasks += 1
                    yield buf
            else:
                dropped_tasks += 1
            buf = []
        elif r.get("stepScore"):
            # realized reward for the PRECEDING step (the operator path scores step N at the top of
            # step N+1, so this always lands right after step N's line). Attach if there is one.
            if buf:
                buf[-1]["m"] = r.get("m")
                if r.get("op") and not buf[-1].get("op"):
                    buf[-1]["op"] = r.get("op")
        else:
            buf.append(r)
    # trailing steps with no end marker (task still in flight / crashed) -> only with the flag
    if buf and include_failed_tasks:
        yield buf
    segment.stats = (kept_tasks, dropped_tasks)


def to_example(step, fmt, with_weights):
    user = PROMPT_TEMPLATE.format(
        obj=step.get("obj", "").strip(),
        app=step.get("app", "").strip() or "?",
        screen=step.get("screen", "").strip(),
    )
    assistant = step.get("action", "").strip()
    if fmt == "alpaca":
        ex = {"instruction": user, "input": "", "output": assistant}
    else:
        ex = {"messages": [
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]}
    if with_weights:
        # Reward-weighted / operator-aware training signal. weight = 1.0 baseline, lifted by realized M
        # (a decision that moved the task is worth more), floored at 0.25 so a low-M step still teaches a
        # little. Trainers that don't read "weight" simply ignore it; "meta" carries op/m/result for
        # operator-aware or analysis passes. Only emitted under --with-weights so the default is unchanged.
        m = step.get("m")
        weight = 1.0 if m is None else max(0.25, 1.0 + 0.5 * float(m))
        ex["weight"] = round(weight, 3)
        ex["meta"] = {"op": step.get("op", ""), "m": m, "result": step.get("result", "")}
    return ex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--format", choices=["chat", "alpaca"], default="chat")
    ap.add_argument("--include-failed-tasks", action="store_true")
    ap.add_argument("--include-failed-steps", action="store_true")
    ap.add_argument("--dedup", action="store_true")
    ap.add_argument("--with-weights", action="store_true")
    ap.add_argument("--min-m", type=int, default=None)
    a = ap.parse_args()

    rows = load(a.input)
    steps_in = sum(1 for r in rows if not r.get("taskEnd") and not r.get("stepScore"))
    scored_in = sum(1 for r in rows if r.get("stepScore"))
    seen, examples, dropped_failed_steps, dropped_low_m = set(), [], 0, 0
    ops_seen = {}

    for task_steps in segment(rows, a.include_failed_tasks):
        for s in task_steps:
            if not a.include_failed_steps and str(s.get("result", "")).upper() == "FAILED":
                dropped_failed_steps += 1
                continue
            # M-floor: keep only decisions that actually moved the task. A step with no realized M
            # (operator layer off, or the last step of a task) is kept — we only drop KNOWN-low ones.
            if a.min_m is not None and s.get("m") is not None and int(s.get("m")) < a.min_m:
                dropped_low_m += 1
                continue
            if not s.get("action") or not s.get("screen"):
                continue
            if a.dedup:
                key = (s.get("screen", ""), s.get("action", ""))
                if key in seen:
                    continue
                seen.add(key)
            if s.get("op"):
                ops_seen[s["op"]] = ops_seen.get(s["op"], 0) + 1
            examples.append(to_example(s, a.format, a.with_weights))

    with open(a.output, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    kept_tasks, dropped_tasks = getattr(segment, "stats", (0, 0))
    print(f"read:   {len(rows)} lines ({steps_in} steps, {scored_in} scored)", file=sys.stderr)
    print(f"tasks:  kept {kept_tasks}, dropped(failed) {dropped_tasks}", file=sys.stderr)
    print(f"steps:  dropped(failed) {dropped_failed_steps}, dropped(low-M) {dropped_low_m}", file=sys.stderr)
    if ops_seen:
        print(f"ops:    {', '.join(f'{k}={v}' for k, v in sorted(ops_seen.items()))}", file=sys.stderr)
    print(f"wrote:  {len(examples)} {a.format} examples{' (weighted)' if a.with_weights else ''} -> {a.output}", file=sys.stderr)
    if len(examples) < 200:
        print("note:   <200 examples — run more tasks before training for a meaningful fine-tune.", file=sys.stderr)


if __name__ == "__main__":
    main()
