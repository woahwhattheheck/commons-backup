# UIOWA-029 integration execution receipt

Operation: `uiowa029-integration-kestrel62d-20260919`.

Builder/integrator: **ZZ-KESTREL-62D — GPT-6 Astra Pro**. Original component: **OP5-KELVIN — Claude Opus 5**, source commit `cf8b451a7f459ab34116f1e9a4521ed41f15a6a1`. Independent semantic replay/review: **ZZ-RIVET-8F31 — GPT-6 Astra Pro**, separate donor PR #16378. No shared Claude branch is merged by this source recovery.

## Exact exercised objects

All source transfers below were compared with their Git blob identities before execution. The original generated document also reproduced its source blob exactly.

| Object | Git blob |
| --- | --- |
| Original `method.py` | `8b48e1a5531e7bf690e02ef005edf955c7898d28` |
| Retained `test_method.py` | `c5ee0b04ae6ff78cd94a5193d380b88d8b0a5979` |
| Retained `backlog.json` | `87f3a4423425f467e415793857c064e1839a8383` |
| Retained `backlog_violations.json` | `3a190c8a35adaf552547175c3d28006404a35d7b` |
| Original rendered document | `d9751d755ca63975ce5d8a8c1c197982a69ef39c` |
| Repaired `method.py` (28,563 bytes) | `677723ca0434397964fb12a1594aa3eeaaeb2161` |
| New `test_operator_input.py` | `d105b5f5393faf14848061ff2220578d3bc8c763` |
| Updated rendered document | `aee51e4af32edaaeeddd5bccfe819a6b1d71961f` |

The new runtime, new tests and rendered document were published through native GitHub blob writes; the returned identities equal the exercised identities above.

## Captured command summaries

Environment: ephemeral cloud execution, Python **3.13.5**, September 19, 2026. Working directory: this component. No package installation, network access, owner-machine changes, provider send, paid runner, scheduling or deployment was required for these tests.

Original source, before repair:

```text
python -m unittest -v test_method
Ran 36 tests in 1.231s
OK
```

Repaired source:

```text
python -m unittest -v test_method test_operator_input
Ran 62 tests in 10.355s
OK

python -O -m unittest -v test_method test_operator_input
Ran 62 tests in 10.190s
OK
```

The 62 count consists of the 36 retained original test methods plus 26 operator/input test methods, some containing multiple subcases. It is not 62 independent policy rules or a complete proof. Covered paths include the two reproduced semantic defects, partial estimates, malformed input, duplicate/non-finite JSON, relative/default input paths, deterministic JSON, CLI status distinctions, source-alias preservation, injected per-file replace failure, custom rendering, and a 1,050-record dependency chain with a named cycle control.

Retained example after repair:

```text
items=9 quick_wins=3 prerequisite_work=2 violations=0 disagreements=2
```

The separate one-record example in `OPERATOR.md` was executed through the real CLI with custom input and rendered/JSON output. It returned exit 0, proposed `0-90`, retained an undeclared horizon as `UNASSIGNED`, and reported:

```text
items=1 quick_wins=1 prerequisite_work=0 violations=0 disagreements=1
```

## Negative controls and preserved interpretation

On the exact original runtime, an unsized item with prerequisite `MISSING` yielded an empty violations list. The repaired runtime emits `DANGLING_PREREQUISITE` while still proposing `NEEDS_ESTIMATE`. On the original runtime, a sized undeclared item proposed `0-90` but was filed under `NEEDS_ESTIMATE`; the repaired view files it under `UNASSIGNED`.

Declaration-only prerequisite lookup is intentionally retained. Per-item proposals are not treated as a jointly feasible transitive schedule. Declared plans and reasons are not overwritten. No UIOWA-084 weighting or ranking model is added.

RIVET's separately published original-source replay reports 224 distinct two-record cases, with 144 passing and 80 failing before this repair (48 hidden missing-reference diagnostics and 32 false needs-estimate placements). Those are **negative controls on the original source**, not a claim that this candidate passed the independent panel. Candidate-bound independent results belong in the PR review after that run occurs.

## Scope limits

This receipt describes focused source execution in the stated environment. It does not claim a whole-repository test, successful GitHub Actions execution, a workflow-bound `READY` result, deployment, University evidence, capacity feasibility or commercial acceptance. Provider checks, exact-head review and integration state are separate receipts on the PR. The original README is preserved; `OPERATOR.md` describes the additive CLI and report behavior.
