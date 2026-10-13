# SOL-SPARK — Spark-X2.5 reasoning-token budget frontier

Paid-work focus: [XHToken/Spark-X2.5 issue #9](https://github.com/XHToken/Spark-X2.5/issues/9), HER Hack-Astron #6. The event advertises one USD 100 winner prize and requires a real, reproducible Spark-X2.5 math evaluation. Submission closes 2026-09-13 24:00 Beijing time (UTC+8).

**Status:** harness published; no model result is claimed by this directory until a real inference receipt lands. Do not invent or backfill outputs.

## Primary research question

How much generation budget does Spark-X2.5-1.7B actually need for GSM8K reasoning, and when does giving it more room repair an answer versus destabilize one?

Run one matched 64-item sample from the public GSM8K test split with the **same reasoning prompt** at four controlled output budgets:

- `max_tokens=64`
- `max_tokens=128`
- `max_tokens=256`
- `max_tokens=512`

Everything else stays fixed: exact model revision, exact dataset revision, sampled indices, sample seed, prompt text, temperature 0, top-p 1, and per-item generation seed sequence. The only intended generation-variable difference is the token ceiling.

This turns token budget from an incidental setting into the experiment. The analysis reports accuracy, parse rate, server `finish_reason`, length-stop rate, completion tokens, latency, wrong→right and right→wrong answer flips, prediction churn, and the smallest tested budget at which each prediction stabilizes to its largest-budget value.

### Predeclared adaptive extension

After the 64/128/256/512 sweep, run `analyze_budget_sweep.py`.

If the **512-token length-stop rate is greater than 5%**, run the exact same matched sample once more at `max_tokens=1024`, then rerun the analysis including that fifth condition. Otherwise stop at 512.

This rule is declared before looking at model results. Do not add/remove budgets after seeing accuracy unless the final report clearly labels the additional analysis exploratory.

## Evidence contract

`eval_gsm8k.py` records the exact question, gold answer, full prompt, full assistant output, raw OpenAI-compatible API response, token counts, latency, parse route, correctness, output hash, environment versions, GPU receipt, selected indices, and SHA-256 digests of the harness and evidence files. It intentionally does **not** record environment variables, credentials, hostname, working directory, or Hugging Face cache paths.

Unparseable outputs count as wrong. The scorer prefers the final `FINAL: <number>` line and transparently marks last-number fallback parsing.

`analyze_budget_sweep.py` refuses mismatched samples/configurations, verifies every `raw.jsonl` hash against its run summary, and emits both a machine-readable per-item trajectory file and a Markdown report.

## Pin revisions first

Use the exact revision SHAs in every run and final write-up.

```bash
python - <<'PY'
from huggingface_hub import HfApi
api = HfApi()
print("MODEL_REVISION=" + api.model_info("XHToken/Spark-X2.5-1.7B").sha)
print("DATASET_REVISION=" + api.dataset_info("openai/gsm8k").sha)
PY
```

Record those two values before downloading or running anything.

## Serve Spark-X2.5

The upstream Spark-X2.5 repository documents vLLM as a supported OpenAI-compatible inference path. Download the pinned checkpoint, then start a local server. Keep the exact `vllm --version`, container/image tag if any, GPU type, precision/quantization, and server command in the final report.

Illustrative local commands:

```bash
hf download XHToken/Spark-X2.5-1.7B \
  --revision "$MODEL_REVISION" \
  --local-dir ./models/Spark-X2.5-1.7B

vllm serve ./models/Spark-X2.5-1.7B \
  --port 30000 \
  --trust-remote-code \
  --served-model-name spark25 \
  --gpu-memory-utilization 0.80 \
  --max-model-len 8192 \
  --enable-prefix-caching \
  --chat-template ./models/Spark-X2.5-1.7B/chat_template.jinja
```

If a different supported runtime, image, precision, or quantization is used, disclose it. Do not compare numbers across runtime changes as though only token budget changed.

## Run the controlled sweep

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

for BUDGET in 64 128 256 512; do
  python eval_gsm8k.py \
    --model-revision "$MODEL_REVISION" \
    --dataset-revision "$DATASET_REVISION" \
    --prompt-mode reason \
    --sample-size 64 \
    --sample-seed 20260908 \
    --generation-seed 20260908 \
    --max-tokens "$BUDGET" \
    --output-root "runs-b${BUDGET}"
done
```

Each invocation refuses to reuse an existing run directory. A partial/crashed run is evidence of a failed attempt, not a completed benchmark; preserve it separately and start a clean output root for a replacement run.

The exact run directory includes prompt mode, sample size, seed, and model revision. Analyze the four completed directories like this:

```bash
python analyze_budget_sweep.py \
  --run 64=runs-b64/reason-n64-s20260908-"${MODEL_REVISION:0:40}" \
  --run 128=runs-b128/reason-n64-s20260908-"${MODEL_REVISION:0:40}" \
  --run 256=runs-b256/reason-n64-s20260908-"${MODEL_REVISION:0:40}" \
  --run 512=runs-b512/reason-n64-s20260908-"${MODEL_REVISION:0:40}" \
  --output-dir budget-analysis
```

If the analyzer recommends the predeclared 1024-token extension, run the same evaluator command with `BUDGET=1024` into `runs-b1024`, then rerun the analyzer with that fifth `--run`.

If a model revision contains characters that the evaluator sanitizes in its directory name, use the actual created directory path rather than reconstructing it from the shell expression above.

## Required return bundle

A GPU runner should return:

- every completed budget run's `manifest.json`
- every completed budget run's `raw.jsonl`
- every completed budget run's `summary.json`
- `budget-analysis/budget_sweep_summary.json`
- `budget-analysis/budget_sweep_report.md`
- exact model and dataset revision SHAs
- exact server command and runtime/container version
- GPU model, precision/quantization, and whether compute was paid or free
- any startup/server log needed to substantiate the run
- SHA-256 hashes for transferred evidence files

Before publication, verify every `summary.json` `raw_jsonl_sha256` against its returned `raw.jsonl`.

## Final report analysis

The final Hugging Face Discussion should answer more than "what was pass@1?":

- Where does accuracy improve as budget rises, and where does it saturate?
- What fraction of failures are literal token-limit stops?
- How many items flip wrong→right with more budget?
- How many flip right→wrong, showing that more reasoning can destabilize a correct answer?
- At what smallest tested budget does each final prediction stabilize?
- Are extra generated tokens buying accuracy or only latency?
- For a deterministic, predeclared set of flip indices from the analyzer, inspect the **complete** reasoning at both adjacent budgets and classify the mechanism: truncation, late correction, arithmetic drift, answer-format failure, or another evidenced category.
- Include at least one right→wrong case if one exists; do not cherry-pick only successes.

## Submission checklist

The challenge requires publication in the Hugging Face Discussion for the model actually tested, followed by a GitHub issue reply linking that Discussion. Include:

- exact model + dataset revisions and acquisition source
- runtime/hardware/precision/quantization
- all decoding parameters and random seeds
- sample size, split, exact scoring rule, parse-failure treatment
- the full controlled budget table and adaptive-extension decision
- representative complete reasoning selected by the analyzer's declared indices
- links to the scoring/analyzer harness and sanitized raw evidence
- license/source attribution for Spark-X2.5 and GSM8K
- explicit AI-assistance disclosure
- no Hugging Face tokens, personal cache paths, private data, intranet addresses, or model-weight uploads

Do not claim the USD 100 prize is earned merely by submitting; it is a judged winner award.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
