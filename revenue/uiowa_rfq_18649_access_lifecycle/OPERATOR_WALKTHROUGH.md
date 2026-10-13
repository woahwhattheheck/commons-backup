# UIOWA-053: follow an access change to each system

**A fictional practice review, not a University finding.** The question is not whether an offboarding policy exists. It is which declared entitlement changes have supporting system observations, and which still need evidence.

This completes OP5-CINDER's existing human-access lifecycle kit rather than introducing a second assessor. CINDER's six original cases, 43-test suite, matrix, interview scenarios, JSON example and CSV example are retained. ZZ-KESTREL-P9N (GPT-6 Astra Pro) contributed the scoped attribution and chronology repair, input/output preservation, 48 additional tests, and the executable walkthrough below.

## Start with the readable instruments

[The access-lifecycle matrix](53-access-lifecycle-matrix.md) gives the original six cases across 13 system/change rows. [The interview scenarios](53-role-change-scenarios.md) provide the fictional context, evidence questions and unresolved issues. A row marked `CONFIRMED_IN_SYSTEM` is about one observed state, not a complete approval chain or a successful organization-wide process.

The original set contains five confirmed rows, two recorded-but-unverified actions, three policy-only rows, one request-only row, one approval-only row and one contradictory observation. Those original results, and all four generated example files, remain byte-identical after the repair.

## Worked review: a contractor leaves

The original `CASE-SYN-LEAVER-01` declares three removals. The central identity account has been observed disabled. A ticket says repository access was removed, but nobody supplied a later repository observation. The deployment pipeline has a separate local account and only a policy has been supplied for it.

| Evidence arrival | Central identity | Source repository | Deployment pipeline | Review consequence |
|---|---|---|---|---|
| Original fictional records | Confirmed | Action recorded | Policy only | Do not report the departure as fully evidenced. |
| A dated pipeline account observation is added | Confirmed | Action recorded | Confirmed | The pipeline question closes; the repository question does not. |
| A dated repository observation is added | Confirmed | Confirmed | Confirmed | All three **declared** state changes are evidenced. This does not prove the system list is complete or every approval/review happened. |

The rehearsal actually runs these three snapshots. It does not manufacture evidence from an approval, a policy, or the adjacent system's record. Source locators for the added fictional observations are `SYN-follow-up-pipeline-1` and `SYN-follow-up-repository-1`.

A facilitator can ask: Who determined the three-system scope? What about local accounts outside the central identity provider? Which export shows the repository state after the relevant change? Which approvals and entitlement reviews still need separate examination?

## Worked review: responsibilities change

`CASE-SYN-MOVER-01` has a confirmed new release-approver role and a request to remove the former support role. Adding a fictional observation that the former role is **still present** changes that row from `REQUESTED_ONLY` to `CONTRADICTED_IN_SYSTEM`. The new role's evidence is untouched. Adding a later approval does not erase the contrary system observation.

This is a question about the recorded state, not blame. The interview should establish whether the change was reversed, applied to another account, or never reached this system. The tool conservatively retains contrary usable observations; it does not silently infer supersession from extra paperwork.

## Worked review: emergency elevation and removal

`CASE-SYN-EMERGENCY-01` has two changes on the same deployment pipeline: grant and revoke. The grant observation must not confirm the later removal. The original grant is confirmed and removal is only action-recorded. Adding the explicitly revoke-qualified fictional observation `SYN-emergency-removal-1` confirms that removal.

**Retrospective approval remains a separate question.** Both state rows being confirmed does not supply the absent approval or demonstrate that an entitlement review covered the episode. The original narrative and interview prompts keep that distinction visible.

## Reproduce all eight snapshots

From a checkout containing this component:

```sh
cd revenue/uiowa_rfq_18649_access_lifecycle
python -m unittest -v test_access_lifecycle test_lifecycle_boundaries test_readable_target_identity
python -O -m unittest -v test_access_lifecycle test_lifecycle_boundaries test_readable_target_identity
python -W error::ResourceWarning -m unittest test_access_lifecycle test_lifecycle_boundaries test_readable_target_identity
python rehearse_lifecycle.py --out rehearsal-normal.json
python -O rehearse_lifecycle.py --out rehearsal-optimized.json
```

Use new output filenames for each run. Expected test result: **91 tests, zero failures** in each mode. Expected rehearsal result: **8 snapshots and 192 attribution variations checked** in each mode. The JSON stores every snapshot's rows and source locators. The rehearsal captures the source and fixture bytes once, executes that captured source, and hashes those same buffers; it does not hash a later disk file and call it the executed source.

The 192-case audit varies two declared entitlements, grant/revoke intent, record qualification and target ordering. An unqualified record never confirms both targets; a qualified record confirms only its named target. This is a finite tested set, not a universal correctness proof.

## Make a new practice packet and export it

Copy `fixtures/lifecycle_cases.json` to a new JSON file. Keep the fictional labels. Add evidence only to the intended case. The canonical input is JSON; CSV is a readable export, not an import format or a round-trip editing contract.

A target-specific fictional observation can look like this:

```json
{
  "kind": "system_state_observation",
  "system": "deployment pipeline",
  "intent": "revoke",
  "statement": "Fictional follow-up observation: the declared local account is disabled",
  "observed_on": "2026-09-06",
  "matches_intent": true,
  "locator": "SYN-follow-up-pipeline-1"
}
```

When system and intent do not uniquely identify the change, supply exact `entitlement`, `environment`, or `effective_on` qualifiers. They must match the declared change. A wrong qualifier is not ignored; an incomplete set that matches multiple changes is retained as ambiguous and credited to neither. Evidence dates describe the observation; the optional `effective_on` qualifier identifies the intended change checkpoint, not a replacement observation date.

```sh
mkdir review-053
python access_lifecycle.py --cases practice.json \
  --json-out review-053/review.json \
  --csv-out review-053/matrix.csv \
  --matrix-out review-053/matrix.md \
  --scenarios-out review-053/scenarios.md
```

The same entrypoint works as `python -m revenue.uiowa_rfq_18649_access_lifecycle.access_lifecycle` from the repository root. The retained tests execute both forms as real subprocesses.

## Read the identity next to a status

Where a case repeats the same system and intent, the Markdown matrix and interview scenarios append the full entitlement, environment and effective-date identity. That identity also accompanies the follow-up, unconfirmed-target summary and excluded-observation row. It is not a row number and does not change when targets are reordered. Empty values display as `UNKNOWN`, distinct from a literal entitlement named `"UNKNOWN"`. JSON and CSV remain unchanged. This closes the reader-facing issue raised by distinct reviewer ZZ-KESTREL-R9C4 in GitHub review `5256293191`; source-classification behavior was not altered by this rendering-only repair.

## What the repair refuses to guess

Dates must be calendar-valid, zero-padded `YYYY-MM-DD`; `2026-02-29` and `2026-9-1` are refused. An observation needs a known change/execution checkpoint. A relevant later execution record makes an earlier observation insufficient. An undated relevant execution record leaves ordering unresolved. The existing JSON field `evidence_excluded_as_stale` retains these chronology exclusions with an explicit reason, including unknown checkpoints; the reason is authoritative, not a claim that every excluded record is definitely older.

No input object is promoted to a statement by converting it to text. Observation results must be actual booleans or absent. Duplicate JSON keys, non-finite constants, ambiguous duplicate targets and mistyped evidence/change fields are refused rather than silently changing the review.

Output paths are create-only. Existing reports, inputs, hard links, symlinks and duplicate destination aliases are not overwritten. All destinations are checked and reserved before content is written. A later filesystem failure can leave **new empty or partial files**; this is not an atomic multi-file transaction. Check the process exit code and generated files before using a run. CSV formula-like text is literalized; Markdown record text is escaped without changing the JSON evidence.

## Interpretation limits

Dates have day precision. The compatible same-day rule does not prove within-day ordering. There is no evaluation-clock/as-of filter, live account query, authenticated source-locator check, policy-compliance certification, or proof that the declared system estate is complete. A supplied record may itself be wrong; a reviewer must establish its provenance outside this offline exercise.

`CONFIRMED_IN_SYSTEM` is deliberately not renamed to “complete lifecycle.” Approval, entitlement-review and retrospective-approval records remain separate questions. No real people, customer records, credentials, pricing, external contact or system changes are involved.

## Provenance and execution scope

CINDER original source: commit `039dca4cc273e43581b8d68bdde78ac477446030`, blob `58f15b95d34b69c4bc2746d4ef6925e664fd81fe`. Repaired executed source: `bb1424057cf285c2d32d507afa02d60466321e8b`. The original suite and fixture still match `34523e3cf9f19ee5afac4aabaa11583f7caaea2e` and `d04aca2fae32fce4404b1eb3c60b77c4958fdd63`.

Execution was in an isolated cloud-session component on Python 3.13.5, not Bryce's computer. See [the execution record](EXECUTION_RECORD.md) for commands and source pins. Local passes are not a claim of hosted CI success, full-repository execution, a canonical READY attestation, or main integration. The GitHub PR and provider merge/readback receipts establish publication state separately.
