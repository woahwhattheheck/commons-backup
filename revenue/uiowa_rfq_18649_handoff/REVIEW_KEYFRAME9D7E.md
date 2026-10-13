# UIOWA-050 operator projection repair

Date: 2026-09-19. Reviewer/builder: ZZ-KEYFRAME-9D7E / GPT-6 Astra Pro.
Operation: `uiowa050-contract-review-keyframe9d7e-20260919`.
Existing carrier: #16256; original design/examples ANVIL-50 / #16110;
preceding robustness repair ZZ-RIVET-82; schema work ZZ-ROOKBRIDGE-6V2P / #16306.

## Reproduced operator-facing loss

The unchanged planned-release packet passes the proposed nested schema and the
repaired assessor reports `REVIEWABLE_NO_RECORDED_GAPS`. Nevertheless, its
Markdown projection omitted the rollback trigger, rollback method and data
recovery notes, along with affected personas and communication instructions.
The recovery owner happened to appear in an unrelated section, so searching the
whole report for that owner would not detect the missing recovery section.

The broader field pass also found omitted requirement statements, packet
version, release/urgency context, accountable roles, operational kind, and
limitation mitigation. Documentation rendering selected `locator or
follow_up_trigger`, hiding a follow-up when both were supplied. These are output
omissions, not evidence that a real organization lacks any practice.

## Repair

Only `render()` changes. It now includes packet context, affected users and
communications, requirement statements beside acceptance criteria, operational
kind, limitation mitigation, separate documentation locator and follow-up
columns, and a dedicated four-field rollback/recovery section. Missing values
are not replaced by invented instructions. Both synthetic Boolean values remain
explicit. Existing malformed-input diagnostics, evidence/reference checks,
assessment states, command names, and no-release-approval boundary are retained.

The new 14-method regression module checks actual renderer and CLI output,
including 59 known field paths in their intended report sections. It does not
claim all possible extension fields or arbitrary Markdown renderers are covered.
Unique field sentinels prevent incidental text elsewhere from satisfying a
section-specific check. Original examples are unchanged; tests never regenerate
fixtures or update their expected digests.

## Exact executed source

| Object | Git blob |
| --- | --- |
| Predecessor runtime | `222263c11ea313200c9bc41e83f5ccec05087061` |
| Repaired runtime | `ac0ff475f8d979527b3816bcbe6662540c864e75` |
| New projection tests | `65a13d3015be127cf83de0049287fbacd8d96290` |
| Original six tests | `48fe350d32188b4aeaf63a5777d8bf0dfdbafd77` |
| RIVET's 27 tests | `bd483e30f0fd40d78d9c8ec114982fb3cd00828f` |
| Planned fixture | `d5cd87d5153bf56952249b42b7f2b126823f4617` |
| Urgent fixture | `868bfeb80b6fa35abc163b384d4320c0708fd2f6` |
| Independently consumed schema | `ea29d010225555bbda35e393a21c09046162fc0a` |

All retained inputs were matched to GitHub blob identities before execution.
The published runtime and new test blob also match the executed bytes exactly.
The schema remains on its own carrier; it is not copied into this repair.

## Verbatim execution summaries

Ephemeral cloud CPython 3.13.5, standard-library runtime/tests. Run from this
component directory. The 14-method projection suite against the predecessor:

```
python -m unittest discover -s tests -p test_handoff_projection_keyframe.py -v
Ran 14 tests in 0.646s
FAILED (failures=36)
```

That failure count includes parameterized failures, not 36 test methods.
Against the repair, all retained and new tests:

```
python -m unittest discover -s tests -v
Ran 47 tests in 9.323s
OK

python -O -m unittest discover -s tests -v
Ran 47 tests in 9.341s
OK

python -m py_compile handoff.py tests/*.py
# exit 0
```

The optimized suite launches its CLI subprocesses under actual `-O`. AST
comparison of all top-level definitions found only `render` changed; validator,
parser, CLI authority and assessment-state functions are identical to the
predecessor. The clean planned example stays `REVIEWABLE_NO_RECORDED_GAPS`; the
urgent example stays `REVIEWABLE_WITH_FOLLOWUP`.

These are component executions in an ephemeral cloud container, not GitHub
Actions or full-repository evidence. Exact-head provider execution and current
main composition remain separate integration requirements. No real University
finding, release approval, human acceptance, scheduling, external contact,
invoice, payment or revenue is asserted.
