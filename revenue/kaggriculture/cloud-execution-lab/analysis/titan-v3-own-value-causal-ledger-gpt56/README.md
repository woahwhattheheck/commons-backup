# TITAN V3 own-value causal transition ledger

This directory supplies the evidence seam missing from the own-value objective experiment. It does **not** modify the objective, canonical runtime, `TITAN-CONFIG.json`, selected archive, release pointers, provider state, or Kaggle state.

The development panel behind PR #11965 reported a large action-active signal, but PR #12040's disjoint confirmation was correctly held: whole-game action hashes cannot establish which actor changed first, whether both arms saw the same world, whether the rival returned the same action, or whether the changed action altered the interpreted next state. Treat the #12040 bank as spent. A successor must use a newly derived bank and record the transition evidence defined here.

## What this closes

The `causal_ledger` package validates a complete paired panel and fails closed unless all of the following hold:

1. **One exact precommit.** The experiment records its hypothesis digest, exact Git head and parent, workflow run ID, `run_attempt == 1`, seed-bank label, and a content address over the ordered opponents, seeds, and seats. A rerun attempt is rejected.
2. **Transitive package custody.** One panel-level closure pins the engine, loader, evaluator, control tree and entry, candidate tree and entry, and a separate transitive opponent-tree digest for every named opponent. Every game must match that closure.
3. **Unforgeable logical placement inside the panel.** Every primary and replay ledger contains its own `{opponent, seed, candidate_seat, arm}` identity. Relabeling or reusing a game under another grid cell fails.
4. **A complete engine-owned transition ledger.** Every game contains exactly `expected_action_steps` sequential records. Each record carries the full preworld, both observations, both returned actions, interpreted postworld, and two-seat bank. Each preworld must byte-match the prior postworld. The final bank must byte-match the reported score.
5. **First-divergence causality.** Before the tested seat changes an action, the two arms must be byte-identical. At the first tested-seat action difference, the preworld and both observations must match, the rival action must match, and the interpreted postworld must differ. A score delta without this chain is malformed evidence, not a negative result.
6. **Deterministic active-cell replay.** Both control and candidate must be replayed for every action-active or score-active cell, and each replay must byte-match its primary ledger. Inactive cells may omit replays.
7. **Seed-clustered admission.** Opponent and seat rows are never counted as independent trials. The gate reports and evaluates seed means, an exact one-sided sign tail, lower-tail floors, opponent × seat strata, own cash, rival cash, margin, W/T/L transitions, lost wins, and new losses.
8. **Strict transport.** Duplicate JSON keys, booleans masquerading as integers, floating or non-finite bank values, unknown fields, incomplete grids, input/output aliases, and detached summaries are rejected.

The validator emits `ADMIT`, `REJECT`, or `INACTIVE`. `INACTIVE` means the candidate changed no tested-seat action anywhere and no score; it is not a promotion result.

## Fresh-successor execution contract

Do not rerun the eight seeds spent by #12040. Before executing a successor:

1. Derive and publish a fresh ordered seed list under a unique label.
2. Commit an immutable seed-bank reservation whose filename includes `seed_bank_sha256(...)`.
3. Use one workflow event only, pin checkout to the exact event head, reject `GITHUB_RUN_ATTEMPT != 1`, and remove manual dispatch and duplicate push/PR triggers.
4. Materialize private, read-only, content-addressed control, candidate, and opponent trees. Hash the complete regular-file closure before and after the panel.
5. Record every primary cell. After primary comparison, rerun both arms of every action- or score-active cell from fresh processes and fresh package roots.
6. Validate the resulting panel with this module. Retain the raw panel and report even when the verdict is `REJECT` or `INACTIVE`.

`run_attempt == 1` prevents a GitHub rerun from passing this validator. Global uniqueness across separate workflow runs must still be enforced by the successor workflow's immutable, content-addressed seed-bank reservation; the validator deliberately does not claim access to repository history.

## Evaluator adapter

Construct one `GameRecorder` per logical cell and arm. The evaluator—not the policy—must supply the values. Snapshot a complete canonical engine state, including every value that can affect the next transition such as RNG state.

```python
from causal_ledger import GameRecorder

recorder = GameRecorder(
    identity={
        "opponent": opponent_name,
        "seed": seed,
        "candidate_seat": tested_seat,
        "arm": arm_name,  # "control" or "candidate"
    },
    provenance={
        "engine_sha256": engine_digest,
        "loader_sha256": loader_digest,
        "evaluator_sha256": evaluator_digest,
        "runtime_tree_sha256": runtime_tree_digest,
        "entry_sha256": entry_digest,
        "opponent_tree_sha256": opponent_tree_digest,
    },
    expected_actions=719,
)

for step in range(719):
    preworld = canonical_full_engine_state(environment)
    observations = [observation_for(0), observation_for(1)]
    actions = [actor0(observations[0]), actor1(observations[1])]
    environment.step(actions)  # the pinned official interpreter
    postworld = canonical_full_engine_state(environment)
    bank = [int(environment.bank[0]), int(environment.bank[1])]
    recorder.append(
        step=step,
        preworld=preworld,
        observations=observations,
        actions=actions,
        postworld=postworld,
        bank=bank,
    )

game_ledger = recorder.finalize(scores=bank)
```

The recorder copies only JSON values and infers nothing. Do not substitute an observation snapshot for full world state, a policy-produced bank for the interpreter bank, or a hash for any raw transition field. Hashes in the final report are derived by the validator from retained raw evidence.

## Panel shape

The top-level object is strict and has exactly these fields:

```text
schema
experiment
expected_action_steps
opponents
seeds
candidate_seats
provenance
gate
cells
```

`candidate_seats` must be exactly `[0, 1]`. `cells` must be the full Cartesian product of every opponent, seed, and seat, with no missing, duplicate, or unexpected cell.

The experiment object is:

```json
{
  "id": "unique experiment identifier",
  "hypothesis_sha256": "64 lowercase hex",
  "seed_bank_label": "fresh immutable label",
  "seed_bank_sha256": "digest returned by seed_bank_sha256",
  "git_head": "40 lowercase hex",
  "parent_head": "40 lowercase hex",
  "run_id": 123,
  "run_attempt": 1
}
```

The panel provenance object is:

```json
{
  "engine_sha256": "...",
  "loader_sha256": "...",
  "evaluator_sha256": "...",
  "control_runtime_tree_sha256": "...",
  "control_entry_sha256": "...",
  "candidate_runtime_tree_sha256": "...",
  "candidate_entry_sha256": "...",
  "opponent_tree_sha256": {
    "arlene": "...",
    "v1": "..."
  }
}
```

The default gate is intentionally strict:

```json
{
  "min_seed_own_mean": 0,
  "min_seed_margin_mean": 0,
  "max_seed_own_positive_tail_p": 0.05,
  "max_seed_margin_positive_tail_p": 0.05
}
```

At least five nonzero all-positive seed clusters are required for an exact one-sided sign tail below 5%; four positive clusters produce `1/16 = 0.0625` and fail. A single large positive seed cannot turn seven zero seed clusters into evidence. Any negative seed mean fails the default lower-tail floor even when the global mean is positive.

## Run

From this directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v
python -m causal_ledger --input PANEL.json --output REPORT.json
```

CLI exit codes:

- `0`: `ADMIT` or `INACTIVE`; inspect the printed verdict and report rather than treating zero as promotion.
- `1`: well-formed evidence with verdict `REJECT`.
- `2`: malformed, incomplete, detached, non-causal, or aliased evidence.

`report_sha256` is the SHA-256 of the canonical report before the `report_sha256` field is inserted. The raw panel is addressed separately by `input_sha256`.

## Current local verification

The focused suite contains 34 contracts. It includes predecessor killers for score changes without tested-action changes, unequal preworlds, unequal observations, unequal rival actions, engine-no-op action changes, hidden prefix drift, missing and nondeterministic replays, identity relabeling, per-cell provenance drift, incomplete and duplicate grids, same-tree arm aliasing, float/bool scores, duplicate/non-finite JSON, stratum masking, lost wins, seed-tail masking, one-seed domination, report determinism, recorder continuity, and input/output aliasing.

This is evidence infrastructure only. A fresh, exact-engine successor panel remains necessary before the own-value factor can enter the one-tree integration tournament.
