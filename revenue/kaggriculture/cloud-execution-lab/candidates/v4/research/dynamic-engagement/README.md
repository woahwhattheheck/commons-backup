# TITAN V4 dynamic engagement census

This is a read-only evidence reducer for one failure class: a component can be
landed, source-bound, and even syntactically composed while its live callsite is
unreachable or semantically inert.

The reducer does **not** discover profitability, set defaults, compose runtime
code, or replace a mechanism owner. It accepts execution evidence produced by
mechanism-specific harnesses and makes the shared claims comparable.

## Evidence contract

Input schema: `titan-v4-dynamic-engagement-evidence/v1`.

Every record binds the exact files used by Git blob id and a panel identity by
SHA-256, then reports five monotone counters:

`callbacks >= entry_calls >= eligible_calls >= engaged_calls >= output_changed_calls`

The `--root` worktree is mandatory. Bound files are re-hashed using Git's blob
identity rule; path escape, symlinks, missing files, duplicate paths, and blob
drift fail closed.

Each component should provide at least one `positive_control` designed to make
the component change an output, plus zero or more `natural` panels. A positive
control is the distinction between "we saw no opportunity" and "the seam is
broken".

States:

- `CONTROL_UNWIRED`, `CONTROL_NOT_ELIGIBLE`, `CONTROL_NOT_ENGAGED`,
  `CONTROL_NO_OUTPUT_CHANGE`: the constructed witness did not traverse the
  expected boundary. This is a wiring/witness blocker, not an economics result.
- `CONTROL_PROVEN_NATURAL_ZERO`: the positive control changed output, but the
  supplied natural panel did not. **This is not a kill.** It is explicit zero
  opportunity/engagement evidence for that search space.
- `ENGAGED`: at least one natural panel changed the component's output. This
  proves engagement only, not positive EV or activation authority.
- `NATURAL_EXECUTION_FAILED` / `INSUFFICIENT_POSITIVE_CONTROL`: evidence is not
  strong enough to make an engagement conclusion.

The stricter natural sub-state is retained separately (`NATURAL_ZERO_ENTRY`,
`NATURAL_WIRED_ZERO_ELIGIBILITY`, `NATURAL_ELIGIBLE_NO_ENGAGEMENT`,
`NATURAL_ENGAGED_NO_OUTPUT_CHANGE`, or `NATURAL_OUTPUT_CHANGED`).

## Use in the current V4

Mechanism owners keep their source and economics. Their current-native or
full-engine harnesses can emit these rows alongside existing receipts. Intake
can then catch dead source/composition seams before spending opponent-diverse
field gates. The immediate motivating example is EXEC-PACE-2: a composed-source
positive control should fail if baseline and candidate plan arguments alias and
therefore no temporal advance can ever be observed.

No sibling V4, controller, feature key, runtime/default/archive/Kaggle mutation,
or merge authority is introduced here.
