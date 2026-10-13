#!/usr/bin/env python3
"""
finetune_action_head.py — LoRA-fine-tune a small Gemma into an action-head, on YOUR OWN hardware.

    ┌──────────────────────────────────────────────────────────────────────────────────────┐
    │ PRIVACY (§3, non-negotiable): the SFT data is real captures of the owner's phone.       │
    │ Run this LOCALLY, on a machine you control. Do NOT run it on Colab / a hosted notebook / │
    │ any cloud training service — that exfiltrates the owner's screens + operator traces.     │
    │ See docs/FINE_TUNING.md ("PRIVACY — train on YOUR OWN hardware only").                    │
    └──────────────────────────────────────────────────────────────────────────────────────┘

This is a STARTING SCAFFOLD, not a turnkey trainer — adjust the base model, LoRA rank, and batch/epoch
sizes to your GPU. It reads the chat JSONL that tools/prepare_finetune_data.py produces and LoRA-fine-tunes
a small base into a text-only action-head (element list -> one action JSON), the G1 contract the app sends.

Reward weighting: pass --weighted to honor the per-example "weight" field (from prepare_finetune_data.py
--with-weights). It's applied trainer-agnostically by OVERSAMPLING — each example is repeated
round(weight * --weight-scale) times (>=1) — so a high-M / proven-operator decision is seen more often. No
custom loss needed; works with any SFT trainer. Cap via --max-repeat so one example can't dominate.

Usage (after: prepare_finetune_data.py ... --with-weights):
    python3 finetune_action_head.py --data sft.jsonl --base google/gemma-2-2b-it --out gemma-actionhead \
        --weighted --epochs 3

Dry-run the data pipeline only (no GPU / no ML libs needed — validates the JSONL + weighting):
    python3 finetune_action_head.py --data sft.jsonl --dry-run --weighted
"""
import argparse
import json
import sys


def load_examples(path):
    """Read the chat/alpaca JSONL from prepare_finetune_data.py. Returns a list of dicts as-is."""
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def repeats_for(ex, weighted, weight_scale, max_repeat):
    """How many times to emit this example. 1 unless --weighted and the example carries a weight."""
    if not weighted:
        return 1
    w = ex.get("weight")
    if w is None:
        return 1
    n = int(round(float(w) * weight_scale))
    return max(1, min(max_repeat, n))


def expand(examples, weighted, weight_scale, max_repeat):
    """Apply reward weighting by oversampling. Trainer-agnostic; returns the training list."""
    rows = []
    for ex in examples:
        rows.extend([ex] * repeats_for(ex, weighted, weight_scale, max_repeat))
    return rows


def strip_meta(ex):
    """Drop the training-only annotations so the trainer sees a clean {messages}/{instruction} example."""
    return {k: v for k, v in ex.items() if k not in ("weight", "meta")}


def summarize(examples, rows):
    base = len(examples)
    weighted = len(rows)
    ratio = f" ({weighted / base:.2f}x)" if base else ""
    print(f"examples: {base} unique -> {weighted} after weighting{ratio}", file=sys.stderr)
    ops = {}
    for ex in examples:
        op = (ex.get("meta") or {}).get("op")
        if op:
            ops[op] = ops.get(op, 0) + 1
    if ops:
        print(f"ops:      {', '.join(f'{k}={v}' for k, v in sorted(ops.items()))}", file=sys.stderr)


def train(rows, args):
    """The LoRA SFT step. Heavy ML imports are INSIDE this fn so --dry-run / --help need no GPU or libs."""
    try:
        import torch  # noqa: F401
        from datasets import Dataset
        from peft import LoraConfig
        from trl import SFTConfig, SFTTrainer
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as e:
        sys.exit(f"training deps missing ({e}). Install locally: pip install torch transformers datasets peft trl "
                 f"(or use Unsloth). This scaffold never runs on a cloud notebook — see the header (§3).")

    clean = [strip_meta(r) for r in rows]
    ds = Dataset.from_list(clean)

    tok = AutoTokenizer.from_pretrained(args.base)
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype="auto", device_map="auto")

    lora = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_r * 2, lora_dropout=0.05,
        bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    cfg = SFTConfig(
        output_dir=args.out, num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch, gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr, logging_steps=10, save_strategy="epoch", bf16=True,
    )
    # chat examples carry {"messages":[...]}; SFTTrainer applies the tokenizer's chat template. If your
    # export is --format alpaca instead, map {instruction,input,output} to a text field first.
    trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds, peft_config=lora, processing_class=tok)
    trainer.train()
    trainer.save_model(args.out)
    print(f"saved LoRA adapter -> {args.out}. Next: peft merge_and_unload -> ai-edge-torch -> .litertlm "
          f"(docs/FINE_TUNING.md Steps 5-6).", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="chat JSONL from prepare_finetune_data.py")
    ap.add_argument("--base", default="google/gemma-2-2b-it", help="small base to LoRA (NOT 270M for the real head)")
    ap.add_argument("--out", default="gemma-actionhead", help="adapter output dir")
    ap.add_argument("--weighted", action="store_true", help="honor the per-example 'weight' by oversampling")
    ap.add_argument("--weight-scale", type=float, default=2.0, help="repeats = round(weight * scale)")
    ap.add_argument("--max-repeat", type=int, default=6, help="cap repeats so one example can't dominate")
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--grad-accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--dry-run", action="store_true", help="validate data + weighting only; no GPU / ML libs")
    a = ap.parse_args()

    examples = load_examples(a.data)
    if not examples:
        sys.exit(f"no examples in {a.data} — run prepare_finetune_data.py first.")
    rows = expand(examples, a.weighted, a.weight_scale, a.max_repeat)
    summarize(examples, rows)
    if a.dry_run:
        print("dry-run: data + weighting OK; skipping training.", file=sys.stderr)
        return
    train(rows, a)


if __name__ == "__main__":
    main()
