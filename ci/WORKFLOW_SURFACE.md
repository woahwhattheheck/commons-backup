# Commons workflow surface

`.github/workflows` contains the durable operational workflows, reusable
workflow dependencies, workflows referenced by existing source/tests, and the
structural preflight. Candidate and product-specific recipes without those
dependencies live in `ci/workflow-recipes` with their original bytes. The
inventory in `ci/workflow-surface.json` binds every moved recipe to its original
path, source commit, byte length and SHA-256.

This change does not enable GitHub Actions or modify notification preferences.
The board, device, Pages, backup, mirror, inbox and Slack operational definitions
remain available. Existing `path-manifest` concurrency is preserved. For retained
workflows that tested a feature branch on both push and PR, push is restricted
to main; the PR still tests the candidate and main push tests its integration.
The branch-only land-admission candidate keeps its PR and manual triggers without
adding a new main push. The TITAN V4 integration branch retains both its existing
branch push and its PR-base trigger, which represent distinct tree transitions.
Job definitions, runner settings, matrices and test commands are preserved.

## Offline structural preflight

Install `PyYAML==6.0.3` in the worker environment, then run:

```sh
python3 -B -m unittest -v test_workflow_surface.py
python3 -B host/workflow_surface.py check
```

The preflight rejects NUL bytes, malformed UTF-8/YAML, duplicate YAML keys,
missing workflow events/jobs, missing local reusable workflows, excess active
workflow files, overlapping feature-branch push/PR triggers, and missing,
changed or accidentally reactivated archived recipes. Main-only push plus PR
is permitted because it checks a different integration ref, as is a fixed push
branch explicitly named as the PR base. This is structural
validation, not a claim that GitHub ran any job or that every Actions-specific
expression/action is valid.

## Run the original tests on alternative compute

The existing core battery is already independent of Actions and runs one test
process at a time, preserving failures and exact-checkout evidence:

```sh
python3 host/ci_battery.py --output-dir /tmp/commons-ci-results
```

Its scope remains root Python tests, nested `infra` Python tests, and root
JavaScript tests. It does not pretend to cover every candidate/product suite.
For a changed candidate/product, retrieve all applicable original recipes:

```sh
python3 host/workflow_surface.py plan --path revenue/agentic_genai_evaluation_gate/gate.py
python3 host/workflow_surface.py show --recipe agentic-genai-evaluation-gate.yml
```

Repeat `--path` for every changed path. Ordered exclusions and directory globs
are applied to the original push/PR path filters. Branch constraints are not
used to suppress a candidate's test plan. Unsupported bracket, plus or escape
glob syntax fails explicitly for manual inspection. Each selected recipe contains the
complete original job definitions: commands, setup actions, required runner,
environment and matrix. Recipe changes select that recipe directly. Manual-only
recipes are retrievable with `show`.

Execute the relevant commands on compatible ephemeral cloud compute, with the
original setup/environment and matrix coverage, before reporting that suite as
passed. `show` and `plan` return `PLANNED_NOT_EXECUTED`; retrieval is not test
execution. Recipes are not automatically re-registered as GitHub workflows.
Do not substitute the core battery or a structural PASS for a selected domain
suite's execution evidence. Preserve the existing owner-device compute limits.

## Adding or changing coverage

Add candidate/product recipes under `ci/workflow-recipes` and update their
inventory hashes together. Keep the active workflow surface within the budget;
creating a workflow for every individual experiment is unnecessary. Preserve
existing operational/ref dependencies when moving definitions. The original
source commit remains available for comparing the migration's complete bytes.
The archive is source-controlled test coverage, not a collection of passing
test receipts.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

Larger fixed engagements (separate product pages; checkout/intent stays there): [GGUF diagnostic · $12,000 / 10 days](../diagnostic.html) · [White Box pilot · $30,000 / 30 days](../commercial.html). Not remints of tip SKUs. Cite grok-bass-md-larger-fixed-20260916-01.
