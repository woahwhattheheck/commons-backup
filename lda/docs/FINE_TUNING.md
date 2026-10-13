# Fine-tuning your own action-head

How to make a **small model fine-tuned to interpret the perception layer** — it reads the on-screen
element list (the agent's perception) and emits one action. A model fine-tuned to *this* narrow task can
beat a big general model at it **while fitting weak hardware** (an A16, a Moto). Start text-only (acts on
the element list, no image): far easier to train, and it's the path that unlocks budget phones.

The on-device half is already built — capture, success-marking, export, and a converter. The training
half runs off-device on any GPU (a free Colab is enough to start).

---

## The pipeline at a glance

    run tasks → capture (on device) → export → convert to SFT → LoRA fine-tune → merge → .litertlm → import → A/B

---

## Step 1 — Collect data (on the phone)
- Settings → **Training data** → keep *Capture steps for training* ON.
- Use the agent normally. Every step records `objective + screen + chosen action + outcome`, and each task
  records whether it **succeeded** — locally, nothing leaves the phone.
- Aim for **a few hundred successful-task steps** before the first training run (the converter prints a
  warning under 200). More + more varied tasks = better.

## Step 2 — Get the data off the phone
- Settings → Training data → **Export training data**. It copies `training_data.jsonl` to
  `Android/data/com.local.deviceagent/files/` — pull it via the Files app or USB.

## Step 3 — Convert to training examples
On your computer:

    python3 tools/prepare_finetune_data.py --input training_data.jsonl --output sft.jsonl --dedup

This keeps only steps from **successful** tasks (clean positives), drops failed steps, and writes chat
examples: `input` = objective + element list (the perception), `output` = the action JSON.
- `--format alpaca` if your trainer wants instruction/input/output.
- `--include-failed-tasks` / `--include-failed-steps` to widen the set.
- **Format contract:** the `PROMPT_TEMPLATE` in that script is the exact prompt shape the model is trained
  on. When you wire the head into the app, the app must send *this same shape* (see Step 7).

## Step 4 — Fine-tune (LoRA)
Pick a **small base**: **Gemma 3 270M** (tiny — great for a first spike and the lightest action-head) or a
1B/2B if you want more headroom. The task is narrow, so small works.

Easiest route — **Unsloth** in a Colab notebook (fast, low-VRAM, Gemma-supported):
1. Load the base Gemma + a LoRA adapter.
2. Train on `sft.jsonl` (chat format) — a few epochs; minutes on a free GPU for 270M/few-hundred examples.
3. Save the LoRA adapter.

(Alternatives: Hugging Face `trl` `SFTTrainer` + `peft`, or Google's own Gemma recipes. Any produces a
LoRA adapter you merge in Step 5.)

## Step 5 — Merge the LoRA into the base
**Required before conversion.** Use `peft`:

    merged = peft_model.merge_and_unload()   # folds the adapter into the base weights
    merged.save_pretrained("gemma-actionhead-merged")

## Step 6 — Convert to `.litertlm` (the on-device format)
This is the one real gate — **do it first as a tiny spike** (convert *any* fine-tuned Gemma and load it in
the app) before investing in lots of data. It's officially supported:

- Tooling: **`ai-edge-torch`** (Google AI Edge), installed via **`uv`**, **Python 3.11+**.
- Quantize to **int4** (smallest, what your current E4B uses) or int8.
- Output: a `.litertlm` file that LiteRT-LM runs — the same format the app already imports.
- Follow Google's official walkthrough (it converts a fine-tuned Gemma end-to-end):
  **Deploy a fine-tuned Gemma with the AI Edge stack** —
  https://developers.google.com/edge/litert-lm/tutorials/convert-and-run
  and the LiteRT-LM repo: https://github.com/google-ai-edge/LiteRT-LM

## Step 7 — Import + make the app speak the head's language
- Import the `.litertlm` via the app's model screen (the existing import path).
- **Format match (important):** a fine-tuned head only works if the app sends it the prompt it was *trained*
  on. The head was trained on `PROMPT_TEMPLATE` (objective + element list + "reply with one action"). The
  integration step is an **action-head prompt mode**: when a head model is selected, the app sends that lean
  text-only prompt instead of the full vision prompt. (This app change isn't built yet — flag it when you're
  ready; it pairs naturally with the existing model+hardware tiering.)

## Step 8 — Measure it actually won
A/B the fine-tuned head vs E4B on a fixed set of tasks and compare success rate + steps + latency. This is
exactly why an **eval harness** matters — without it you can't tell if the fine-tune helped. (Recommended
next build.)

---

## The realistic first experiment
1. Spike Step 6 with stock **Gemma 270M** → confirm it converts to `.litertlm` and loads in the app.
2. Collect a few hundred successful steps via the flywheel.
3. LoRA-fine-tune 270M (or 1B) on `sft.jsonl` in Unsloth → merge → convert → import.
4. A/B vs E4B on your tasks.

If the small head matches E4B on *your* tasks while fitting a budget phone, that's the unlock for the
"runs great on any device" release. Keep E4B-vision for hard/blind screens; route easy tree-screens to the
fast head (the "two-speed" agent).

**Honest gate:** Step 6 (conversion) is make-or-break — validate it before collecting a big dataset. Vision
fine-tuning is a harder follow-up; the text-only head is the high-value, low-friction start.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

