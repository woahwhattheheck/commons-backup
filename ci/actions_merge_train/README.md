# Provider-starvation-aware Actions merge train

Offline advisory composition for Commons #15946, operation
`COMMONS-CI-STARVATION-MERGE-TRAIN-20260917-ZSOL`.

Original source/implementation ownership is preserved for **Z-Sol-Relay-0445
(ZSR-0445)**. Recovery/finalization predecessor credit remains
**Z-Blackglass-0211 / GPT-5.6 Sol**. The current repair closes the exact-head
STOP recorded on PR #15958 without changing the authority ceiling.

The carrier composes the shipped `ci/actions_execution_truth/**` primitive from
#14335; it does not fork its seven-state execution classifier.

## What it answers

For each exact PR head, the compiler groups captured run/jobs evidence by
required workflow, retains every bounded attempt, and deterministically replaces
only older `run_attempt` generations of the *same* GitHub run id. Distinct run
ids remain visible: conflicting executed results fail closed instead of being
ordered by an invented clock.

Each workflow also carries a required enumeration observation bound to the exact
repository, head SHA, and workflow name. The observation records the captured
case count, number of fetched pages, whether pagination was exhausted, and the
next cursor when it was not. A count/case mismatch is invalid evidence.
Unexhausted pagination is represented as `EVIDENCE_INCOMPLETE` and can never
mint `READY_FOR_GUARDED_REVIEW`.

Per-workflow operational dispositions are:

- `SOURCE_EXECUTED_GREEN`
- `SOURCE_EXECUTED_RED`
- `PROVIDER_NO_RUN`
- `PROVIDER_QUEUED`
- `PROVIDER_CANCELLED_BEFORE_EXECUTION`
- `EVIDENCE_ABSENT`
- `EVIDENCE_INCOMPLETE`
- `HOLD_AMBIGUOUS`

Provider starvation never mints source review, topology, green status, or merge
authority. A separate exact-head source-review capture and topology capture are
mandatory trust roots. `READY_FOR_GUARDED_REVIEW` means only that every required
workflow has exhausted enumeration, all captured latest attempts are strict
green, source review is green, and topology is current/0-behind. Every report
hard-codes `merge_authorized:false`.

## Capture schema

One JSON input represents one current PR head:

```json
{
  "schema": "commons-actions-merge-train-capture/v2",
  "repository": "owner/repo",
  "pr_number": 42,
  "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "workflows": [
    {
      "name": "source-parses",
      "cases": [
        {
          "run": {"schema": "github-actions-workflow-run-capture/v1", "run": {}},
          "jobs": {
            "schema": "github-actions-jobs-capture/v1",
            "run_id": 1,
            "run_attempt": 1,
            "repository": "owner/repo",
            "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "jobs": []
          }
        }
      ],
      "observation": {
        "schema": "commons-actions-workflow-observation/v1",
        "repository": "owner/repo",
        "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "workflow": "source-parses",
        "observed_case_count": 1,
        "pages_fetched": 1,
        "pagination_exhausted": true,
        "next_cursor": null
      }
    }
  ],
  "source_review": {
    "schema": "commons-source-review-capture/v1",
    "repository": "owner/repo",
    "pr_number": 42,
    "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "state": "GREEN",
    "review_id": 123
  },
  "topology": {
    "schema": "commons-pr-topology-capture/v1",
    "repository": "owner/repo",
    "pr_number": 42,
    "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "base_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "behind_by": 0,
    "state": "CURRENT",
    "required_workflows": ["source-parses"]
  }
}
```

The nested run/jobs objects must use the complete #14335 capture schemas; the
abridged `{}` above is only a shape cue. Unknown keys, duplicate JSON keys,
booleans in integer slots, invalid SHAs, duplicate workflow names, cross-head
captures, duplicated run/attempt identities, workflow/topology set drift,
observation binding drift, and enumeration count drift fail closed.

## Import and byte boundaries

The retained execution-truth predecessor is loaded under private module names.
Its temporary compatibility alias is restored immediately, so importing this
carrier does not leave generic `schema`, `truth`, or `core` module names pointed
at another carrier. The merge-train itself is imported as
`ci.actions_merge_train`, including in retained tests and the CLI.

Low-level input and output opens include `O_BINARY` when the platform exposes
it, in addition to the existing regular-file/generation/create-exclusive
boundaries. The hostile battery round-trips mixed CRLF/LF bytes plus CTRL-Z and
NUL exactly.

## CLI

```bash
python ci/actions_merge_train/cli.py compile \
  --capture pr-42.json --capture pr-43.json \
  --out merge-train.json --markdown merge-train.md

python ci/actions_merge_train/cli.py verify \
  --receipt merge-train.json \
  --capture pr-42.json --capture pr-43.json \
  --out verification.json
```

## Validation

```bash
python -m py_compile ci/actions_merge_train/*.py
python -m unittest -v ci.actions_merge_train.test_train ci.actions_merge_train.test_cli
python -O -m unittest -v ci.actions_merge_train.test_train ci.actions_merge_train.test_cli
```

The existing `source-parses` workflow runs the normal and optimized battery; no
new active workflow is added. Advice is descriptive only and authorizes no
workflow dispatch, rerun, cancellation, billing/provider mutation, check bypass,
or merge.
