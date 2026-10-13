#!/usr/bin/env python3
"""
prepare_finetune_data.py — turn the agent's exported capture into fine-tune-ready data.

The on-device "data flywheel" (Settings -> Training data -> Export) writes a JSONL where each
line is one of:

  a STEP the agent decided:   {"obj","app","screen","action","result"}
  a TASK-END marker:          {"taskEnd": true, "obj", "success": true|false}

This script turns that into supervised fine-tuning (SFT) examples for a SMALL model that
INTERPRETS THE PERCEPTION LAYER and emits one action — i.e. a text-only "action head":

    input  (user):       Objective + the on-screen element list (the perception)
    output (assistant):  the action JSON the agent chose

By default it keeps only steps from SUCCESSFUL tasks (the clean positive examples) and drops
steps whose own result was FAILED. The raw export still has everything; this is the filtered
training view.

IMPORTANT — format match: a fine-tuned head only works in the app if the prompt it's TRAINED
on matches the prompt the app SENDS it at inference. PROMPT_TEMPLATE below is that contract:
when you wire a fine-tuned head into the app, have it send this exact shape (objective +
element list + the instruction line). Keep the two in sync.

Usage:
    python3 prepare_finetune_data.py --input training_data.jsonl --output sft.jsonl
    # options:
    #   --format chat|alpaca     (default chat: {"messages":[...]}, works with Unsloth/TRL)
    #   --include-failed-tasks   (also keep steps from tasks that did NOT complete)
    #   --include-failed-steps   (also keep steps whose own result was FAILED)
    #   --dedup                  (drop duplicate screen+action pairs)
"""
import argparse, json, sys

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
    """Group steps into tasks using the taskEnd markers; yield the step-lists to KEEP."""
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
        else:
            buf.append(r)
    # trailing steps with no end marker (task still in flight / crashed) -> only with the flag
    if buf and include_failed_tasks:
        yield buf
    segment.stats = (kept_tasks, dropped_tasks)


def to_example(step, fmt):
    user = PROMPT_TEMPLATE.format(
        obj=step.get("obj", "").strip(),
        app=step.get("app", "").strip() or "?",
        screen=step.get("screen", "").strip(),
    )
    assistant = step.get("action", "").strip()
    if fmt == "alpaca":
        return {"instruction": user, "input": "", "output": assistant}
    return {"messages": [
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--format", choices=["chat", "alpaca"], default="chat")
    ap.add_argument("--include-failed-tasks", action="store_true")
    ap.add_argument("--include-failed-steps", action="store_true")
    ap.add_argument("--dedup", action="store_true")
    a = ap.parse_args()

    rows = load(a.input)
    steps_in = sum(1 for r in rows if not r.get("taskEnd"))
    seen, examples, dropped_failed_steps = set(), [], 0

    for task_steps in segment(rows, a.include_failed_tasks):
        for s in task_steps:
            if not a.include_failed_steps and str(s.get("result", "")).upper() == "FAILED":
                dropped_failed_steps += 1
                continue
            if not s.get("action") or not s.get("screen"):
                continue
            if a.dedup:
                key = (s.get("screen", ""), s.get("action", ""))
                if key in seen:
                    continue
                seen.add(key)
            examples.append(to_example(s, a.format))

    with open(a.output, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    kept_tasks, dropped_tasks = getattr(segment, "stats", (0, 0))
    print(f"read:   {len(rows)} lines ({steps_in} steps)", file=sys.stderr)
    print(f"tasks:  kept {kept_tasks}, dropped(failed) {dropped_tasks}", file=sys.stderr)
    print(f"steps:  dropped(failed) {dropped_failed_steps}", file=sys.stderr)
    print(f"wrote:  {len(examples)} {a.format} examples -> {a.output}", file=sys.stderr)
    if len(examples) < 200:
        print("note:   <200 examples — run more tasks before training for a meaningful fine-tune.", file=sys.stderr)


if __name__ == "__main__":
    main()