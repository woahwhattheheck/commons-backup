# UIOWA-114 source recovery and delivery contract

Recovery and reference/export repair: ZZ-LANTERN-8J2Q / GPT-6 Astra Pro.
Original generator, wording, six templates, fictional registers, examples, README and 35-test suite: OP5-FLINT / Claude Opus 5, source commit `66806042cf6e0fe69418b75e984a6f9bf638365d`.

This is an isolated continuation of that component, not a merge of the shared `claude/multi-agent-slack-demo-4ikzfs` branch. Source publication is not a main-integration or hosted-execution claim.

## What changed and why

The original generator was reconstructed from native GitHub reads and its Git blob verified as `c1c4b7dcea184f5674fcf7264d5efe7b59a22606` before independent fictional executions. Two repeated observation IDs produced two cards and `accounted_for=2/2`, but only one searchable card. Distinct `OBS-A` and `OBS-OBS-A` also collapsed to `QC-A`. A repeated source ID selected the last locator without warning. A known role with an absent session silently retained that phantom session. CSV exported possible answers without their resulting findings. Search discarded the observation diagnostics.

The repair validates identity before rendering or output creation, removes only the leading `OBS-` namespace, rejects remaining derived-card collisions and duplicate search identities, retains unresolved session routing as a warning with the actual role preserved, adds a lossless `outcome_map_json` CSV column, and shows diagnostics/coverage during search. The six wording templates and all original data objects are unchanged. There is no new ranker or workbench.

## Compatibility that callers must know

Register rows require unique, nonblank string IDs. Ambiguous registry structure raises `ValueError` through the Python API; CLI `build`, `check` and `search` return 2 with a named input error before creating output. A duplicated ID is not silently renamed, deduplicated or selected. Ordinary IDs such as `OBS-ESS-DEP-01` retain their established `QC-ESS-DEP-01` card IDs. An embedded `OBS-` is now preserved. Derived collisions such as `A` and `OBS-A` require a curator to choose unambiguous observation IDs.

Known roles whose sessions cannot be resolved produce `NO_SESSION_FOR_ROLE`, keep their role title, and render under `UNSCHEDULED`. This is a proposed grouping, not a calendar booking. No code in this component schedules or contacts anyone.

The final CSV column is `outcome_map_json`, a JSON array retaining every answer and resulting-finding pair. Read it with `json.loads(row['outcome_map_json'])`; do not split the human-readable `possible_answers` string to reconstruct relationships. Existing CSV columns retain their order. JSON remains the canonical structured output. The original checked-in examples initially retained here precede this additive CSV column; regenerate into a fresh output directory with the repaired source rather than treating that historical CSV as a current-schema export.

Search now prints coverage and diagnostics, then matching cards. It returns 1 when the observation register has errors, even if a surviving card matches; valid empty search and warning-only search return 0. Bad queries return 2. `check` retains exit 1 for observation errors. `build` still returns 0 after exporting an inspectable diagnostic packet; build success is not validation success. Use `check` to evaluate readiness.

## Actual execution at this publication

`python -m unittest -v test_delivery_integrity`: 28 tests, OK.
`python -O -m unittest -v test_delivery_integrity`: 28 tests, OK.
`python -m py_compile question_cards.py`: exit 0.

These are independent regression fixtures and real subprocess CLI checks executed in the cloud container, not the owner's computer or GitHub Actions. The original 35-test result remains FLINT's attributed result until separately reproduced against this candidate. No full-repository, hosted-green or reducer-READY result is implied.

The locally executed repaired generator is Git blob `51d8424fa6f4d9096f79cad9c7123f21b23c3377` (24,986 bytes); the new retained test module is `9778b76826378fecaba7a650fe5c3075335a8fad` (15,879 bytes). Native blob creation matched both exactly.

From this directory, run the retained complete suite with `python -m unittest -v test_question_cards test_delivery_integrity`, and again using `python -O`. Regenerate with `python question_cards.py check --out /tmp/uiowa114-fresh`; choose a new output directory because valid builds retain the original overwrite behavior. Never point output at an input directory or at a prior packet that must be preserved.

## Human judgement is not delegated to the generator

Every shipped observation, role, locator and register is FICTION. The card outcome maps are proposed conditional interpretations, not verified University findings. An answer does not by itself prove the supporting record, applicability, period or scope. A reviewer must confirm those and retain the exact new artifact locator before changing a draft finding. Missing supplied evidence must not be relabeled as an absent practice. An unscheduled role is unresolved routing, not evidence of noncooperation.

UIOWA-113 retains prioritization. It may consume card IDs, observation IDs, uncertainty types, concrete requests and open-finding references; this package supplies no competing rank order. The analyst workbench and shared compiler are unchanged.
