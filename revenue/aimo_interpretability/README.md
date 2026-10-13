# AIMO Interpretability — answer-stability public-data carrier

Operation: `AIMO-INTERP-PUBLIC-BASELINE-PLUS-ED913-20260913`.

This directory is a source-faithful, offline submission candidate for the AIMO Interpretability Challenge. It targets the organizer's current `are_robust(model_id, problems) -> list[bool]` contract and uses only the model that the evaluator already mounts locally. It does **not** look up public model IDs or public labels at inference time.

Official starter pin used for this carrier: `aimo-interp/getting-started@995f9923a680a157c9239e08e4ef0fa0fa53bb58` (observed 2026-09-13). The competition phase currently lists Qwen/Qwen3.5-4B, Skywork/Skywork-OR1-Math-7B, allenai/Olmo-3-7B-Think, deepseek-ai/DeepSeek-R1-0528-Qwen3-8B, and openai/gpt-oss-120b. The evaluator is offline and provides torch/Transformers itself.

## Method

For each original problem, the candidate asks the evaluated model for a final answer under three benign wrappers:

1. direct answer-only instruction;
2. independent verification instruction;
3. an irrelevant-note distractor plus answer-only instruction.

The exact mathematical problem text is preserved in all three prompts. Outputs are normalized conservatively (`\\boxed{...}`, explicit final-answer lines, or the final non-empty line). A problem is predicted robust only when at least two non-empty final-answer signatures agree. Failures and ambiguous/truncated outputs fail closed to `False`, so the interface still returns one native Python boolean per problem.

The model/tokenizer are loaded lazily and one checkpoint is cached at a time. Generation is greedy, offline, and capped at 192 new tokens per probe. No network call, external API, private label, case identifier, or extra model is used.

## Why not memorize the public sample?

The 28-row official public validation sample has 9 robust and 19 non-robust rows. A majority-label lookup by public `model_id`, fitted and scored on those same rows, gets 26/28 = 92.857%. That apparent uplift disappears when model identity is held out: unseen-model fallback gets 19/28 = 67.857%, exactly the all-False baseline. The current competition model IDs also differ from several public aliases/checkpoints.

`public_val_prior_audit.py` records this leakage test. It is deliberately disconnected from `solution.py` and `stability_probe.py`.

## Local proof

The focused standard-library tests cover nested `\\boxed` extraction, explicit/fallback answer normalization, majority voting, empty/truncated outputs, generator failure, native bool output, model-id independence, and the public model-prior leakage arithmetic. They do not claim real-GPU accuracy for the dynamic method.

Run from the repository root:

```bash
python -m unittest -v test_aimo_interpretability_stability_probe.py
python -O -m unittest -v test_aimo_interpretability_stability_probe.py
python -m py_compile \
  revenue/aimo_interpretability/solution.py \
  revenue/aimo_interpretability/stability_probe.py \
  revenue/aimo_interpretability/public_val_prior_audit.py \
  test_aimo_interpretability_stability_probe.py
python revenue/aimo_interpretability/public_val_prior_audit.py
```

Build a main-track archive by making `solution.py` the ZIP root next to `stability_probe.py`:

```bash
cd revenue/aimo_interpretability
zip -j ../../aimo-answer-stability.zip solution.py stability_probe.py
```

Do not include the audit file in the competition archive. The next empirical gate is an authorized GPU run against the organizers' public validation tooling, followed by threshold-free error analysis and only then an entrant submission decision.

No Codabench registration, terms acceptance, private/test-set access, sponsor contact, submission, prize claim, or paid compute is performed by this carrier.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
