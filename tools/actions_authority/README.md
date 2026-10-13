# Policy-bound exact-head Actions classification

`actions_authority` is an offline, fail-closed **classifier** for captured GitHub Actions evidence. It distinguishes terminal results, active execution, missing evidence, and runner-starved zero-step attempts without granting merge or side-effect authority.

## v3 security contract

Earlier experimental schemas were unsafe:

- v1 let a caller choose workflow display names and one preferred run, then exposed merge authority;
- v2 bound complete run/job counts but did not bind each job capture to the exact workflow `run_id` and `run_attempt`, so evidence from an older attempt could be spliced into the latest attempt;
- v2 also accepted a `completed/success` job as green without affirmative runner, chronology, and completed-step evidence.

`commons-actions-evidence/v3` rejects v1/v2 and requires:

1. a digest-bound `commons-actions-policy/v1` descriptor whose required workflows are identified by numeric workflow ID, canonical workflow path, and display name;
2. a complete exact-head run inventory bound to repository and head by the canonical locator `github-actions:runs:<owner/repo>:<head_sha>`;
3. for every run, a complete **attempt-specific** job inventory bound to repository, `run_id`, and `run_attempt` by `github-actions:attempt-jobs:<owner/repo>:<run_id>:<run_attempt>`;
4. every supplied job row to repeat and match the containing `run_id` and `run_attempt`;
5. terminal success to include an assigned runner, run/job start and completion times, and at least one completed successful step. Label-only, runnerless, timestampless, or step-less “success” is `HOLD`, never green.

Workflow ID/path/name alias collisions, stale policy snapshots, duplicate IDs/numbers, wrong heads, incomplete pagination, count mismatches, cross-attempt evidence, temporal contradictions, and malformed exact fields fail closed.

## Classification is never permission

Every valid receipt contains:

```json
{
  "authorization_scope": "CLASSIFICATION_ONLY",
  "merge_authorized": false,
  "side_effects_authorized": false
}
```

`declared_policy_green=true` means only that the latest captured exact-head run for every workflow in the declared policy is terminal success with affirmative executed-job evidence. A separate trusted online boundary must verify the live repository policy, current head/base graph, reviews, permissions, and any merge exception immediately before mutation.

## Decisions

- `TERMINAL_GREEN`: every required workflow's latest run has affirmative execution success.
- `TERMINAL_RED`: at least one latest required run is terminal failure, with no contradictory `HOLD` evidence.
- `WAIT_RUNNER_BACKLOG`: every non-green latest required attempt is complete-inventory, unassigned, and zero-step. This only sets `runner_exception_candidate=true`.
- `WAIT_EXECUTION`: a required latest run is active or lacks backlog proof.
- `WAIT_MISSING`: no exact-head run exists for a required workflow in the complete inventory.
- `HOLD`: contradictory or unsafe evidence. `HOLD` dominates `TERMINAL_RED` so contradictions cannot be hidden by a separate failure.

GitHub may encode an unassigned job as null runner values or `runner_id=0` plus `runner_name=""`; both normalize to unassigned. A queue-time `started_at` alone is not execution proof. Cancelled backlog requires every job in the exact attempt-specific inventory to remain unassigned and step-less.

## CLI

```sh
python -m tools.actions_authority.cli evidence.json --out classification.json
```

The CLI reads one retained ordinary non-symlink file generation, publishes create-exclusively through a retained output-parent descriptor, and never calls GitHub. Exit `3` means a valid classification receipt was emitted; exit `2` means evidence or publication failed. `--now` exists only for deterministic offline replay and does not add live authority.

## Verification

```sh
python -m py_compile tools/actions_authority/*.py
python -B -m unittest -v tools.actions_authority.test_authority
python -O -B -m unittest -v tools.actions_authority.test_authority
```

Hostiles cover old-green/new-red selection, workflow aliases, omitted run/jobs, exact attempt provenance, generic/latest jobs-source rejection, cross-attempt splice, runnerless/timestampless/step-less success, mixed RED+HOLD precedence, provider-native zero-step queue shapes, stale policy/capture chronology, deterministic receipts, strict JSON, symlink input, and create-exclusive publication.
