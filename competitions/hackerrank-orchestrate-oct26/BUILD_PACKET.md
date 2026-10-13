# HackerRank Orchestrate October 2026 — build packet

Status: internal build/evaluation packet. This file does **not** register, submit, or mutate a HackerRank account.

## Current first-party event facts

- Event: HackerRank Orchestrate — October Edition.
- Build window starts **2026-10-24 18:00 IST** and lasts 24 hours.
- Rewards: **$1,200 first place; $300 each for places 2–5**.
- Required submission artifacts: code, agent output, and AI chat transcript.
- After submission, the builder completes a **30-minute AI judge interview**.
- Live evaluation: October 26–27; results: October 27.
- Tool choice is open; the event explicitly allows Codex, Claude Code, Cursor, and other tooling.

First-party event page: https://www.hackerrank.com/hackerrank-orchestrate-october26

Historical HackerRank Orchestrate writeups show four independent evidence surfaces: shipped code, output quality, AI-working transcript, and technical interview. Treat historical weights as guidance only; the October challenge instructions win if they differ.

## Objective

When the challenge drops, ship the **smallest agent architecture that can be measured, debugged, and defended**. Do not optimize for framework count or prose volume. Observable behavior must carry the submission.

The packet assumes the challenge remains similar to prior Orchestrate editions: an agent receives a bounded corpus/problem, must choose actions under ambiguity/adversarial input, and produces structured outputs.

## Architecture spine

Use five separable layers:

1. **Input contract**
   - Parse the challenge row/item into a typed internal record.
   - Preserve original evidence separately from model-generated fields.
   - Reject malformed required fields before model invocation.

2. **Evidence / retrieval**
   - Deterministic filtering first when hard constraints can narrow the corpus.
   - Retrieval returns bounded evidence IDs/snippets, not the entire corpus.
   - Every final decision carries evidence references when the task permits them.

3. **Reasoner / agent loop**
   - One explicit state object.
   - Bounded iteration count.
   - Model can choose among a small documented tool set.
   - Tool outputs are structured; free-form text never becomes an executable tool instruction.
   - Separate “understand” from “commit decision” so validation can reject a bad draft.

4. **Policy / validator**
   - Deterministic hard constraints run after the model proposal.
   - Validate output schema, allowed enum/action, required evidence, and challenge-specific invariants.
   - On validation failure: one targeted repair attempt, then fail closed / escalate according to challenge semantics.

5. **Renderer / artifact writer**
   - Stable ordering and schema.
   - No hidden state from previous rows unless the challenge explicitly requires memory.
   - Write the exact submission artifact plus a compact per-item trace suitable for debugging.

## Minimal repository shape

```text
src/
  contracts.py        # typed input/output contracts
  retrieve.py         # evidence selection
  tools.py            # narrow tool implementations
  agent.py            # bounded reasoning loop
  policy.py           # deterministic validation / safety rules
  run.py              # batch entry point
eval/
  cases.jsonl         # local fixed cases
  adversarial.jsonl   # ambiguity / injection / malformed cases
  score.py            # deterministic local scorer
artifacts/
  sample_output.*     # generated, never hand-edited
README.md
```

Avoid adding a framework unless it materially reduces code or improves observable behavior.

## Benchmark contract

Before feature expansion, establish a fixed local corpus with at least:

- 10 straightforward cases.
- 10 ambiguous / competing-evidence cases.
- 10 adversarial or malformed cases.

Report these every time the decision path changes:

| Metric | Required |
| --- | --- |
| Valid structured outputs | count / total |
| Hard-constraint satisfaction | count / total |
| Task/action correctness | count / total when locally labelable |
| Evidence-grounded decisions | count / total when evidence is available |
| Adversarial safe handling | count / total |
| Retry rate | % |
| p50 latency | ms |
| p95 latency | ms |
| Mean model/tool calls per item | count |
| Deterministic-layer replay differences | count |

If ground truth is unavailable before the challenge, score the invariants we *can* prove instead of inventing accuracy numbers.

### Required ablations

Run at least these three before freeze:

1. Retrieval/policy spine versus a direct one-shot model call.
2. Full evidence set versus bounded retrieval.
3. Validator enabled versus validator bypassed.

Keep a change only when it improves an observable metric or closes a known failure mode.

## Adversarial acceptance

The fixed adversarial set should include challenge-appropriate variants of:

- Prompt-injection text embedded in source evidence.
- A source document telling the agent to ignore the task.
- Conflicting evidence.
- Missing required evidence.
- Unsupported requested action.
- Malformed structured input.
- Overlong irrelevant context.
- Ambiguous item that should escalate rather than guess.

The system must treat retrieved/source content as data, not higher-priority instructions.

## 24-hour execution plan

### Hour 0–1 — contract
- Read the challenge and scoring instructions before writing code.
- Freeze the input/output schema.
- Identify which outputs can be locally scored.
- Write 6–10 challenge-specific acceptance examples.

### Hour 1–4 — vertical slice
- Build one end-to-end path over 2–3 cases.
- Produce the exact output artifact early.
- Add deterministic validation before expanding coverage.

### Hour 4–10 — correctness
- Build the fixed eval set.
- Add retrieval/tooling only where a measured failure requires it.
- Keep iteration caps and explicit failure states.

### Hour 10–15 — adversarial / recovery
- Add challenge-relevant adversarial cases.
- Exercise tool/model failure and malformed output.
- Measure retries and latency; remove wasteful calls.

### Hour 15–19 — ablation / simplification
- Run the three required ablations.
- Delete components that do not improve evidence.
- Freeze dependency count and output schema.

### Hour 19–21 — artifact pass
- Generate the final candidate output from a clean run.
- Verify there are no hand-edited output rows.
- Re-run the fixed eval from scratch.

### Hour 21–23 — README + interview evidence
- README explains architecture, assumptions, run command, and known limitations.
- Prepare one page of measured tradeoffs and two failed approaches.
- Ensure every claimed feature points to executable code.

### Hour 23–24 — freeze
- No architectural rewrites.
- Only submission-blocking fixes.
- Produce checksums / exact commit identity for submitted code and outputs.

## AI transcript discipline

The transcript is part of the product evidence. It should naturally show:

- Clear initial constraints and architecture choices.
- Specific debugging prompts tied to observed failures.
- Decisions to reject unnecessary complexity.
- Targeted evaluation after each meaningful change.
- Explicit handling of uncertainty and limitations.

Do not manufacture transcript theater. The goal is a trace of real engineering decisions.

## Interview defense sheet

The builder should be able to answer, with measured evidence:

1. Why is this an agent rather than a hardcoded workflow?
2. Which decisions are model-driven, and which are deterministic?
3. What prevents source/retrieved text from controlling tools?
4. What is the worst measured failure mode still present?
5. Which component produced the largest measurable gain?
6. Which component was removed because an ablation showed no value?
7. What happens on malformed model output or tool failure?
8. What are p50/p95 latency and average calls per item?
9. What would break first at 10× input volume?
10. If given two more hours, what single change has the strongest evidence-backed upside?

## Freeze gate

Do not call a build submission-ready until all are true:

- [ ] Exact challenge input/output contract is implemented.
- [ ] A clean command regenerates the submission artifact.
- [ ] Fixed eval corpus is stored and reproducible.
- [ ] Hard constraints are validated outside the model.
- [ ] Adversarial/source-instruction cases have been exercised.
- [ ] p50/p95 latency and call counts are recorded.
- [ ] At least three ablations are recorded.
- [ ] README claims point to executable behavior.
- [ ] Known limitations are explicit.
- [ ] Builder can defend architecture and tradeoffs without relying on hidden fleet/process details.
- [ ] Submitted commit/output identities are pinned.

## Non-goals

- No registration automation.
- No submission automation.
- No paid resource commitment before the challenge justifies it.
- No disclosure of internal proprietary swarm coordination, routing, or rate-limit machinery.
- No broad test matrix beyond challenge acceptance and the fixed evaluation set.
