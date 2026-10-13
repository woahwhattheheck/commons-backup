# Evaluate an edited recommendation backlog

UIOWA-029 operator supplement, ZZ-KESTREL-62D (GPT-6 Astra Pro), September 19, 2026. Original horizon method and nine-record examples: OP5-KELVIN (Claude Opus 5). The original README is retained; this supplement describes the integration additions.

**Fictional rehearsal only.** These examples are not University of Iowa observations, delivery commitments, capacity approvals or certification conclusions. Quality/security/delivery scoring remains in UIOWA-084. This tool organizes and compares horizons; it does not implement a second ranker.

## Start with the retained example

From this directory:

```sh
python method.py --check
python method.py --json
python -m unittest -v test_method test_operator_input
python -O -m unittest -v test_method test_operator_input
```

The original nine-record example still produces three quick wins, two prerequisite-work items, zero violations and two disagreements. The declarations and their stated reasons remain unchanged. A disagreement is a review decision, not permission for the tool to rewrite the plan.

## Review a separate editable input

Create a new synthetic input without replacing the committed example:

```python
import json

example = {
    "backlog_id": "UIOWA-029-OPERATOR-EXAMPLE",
    "synthetic": True,
    "recommendations": [{
        "recommendation_id": "REC-SYN-EDIT-001",
        "title": "Fictional review-template improvement",
        "group": "ESS", "area": "SD",
        "effects": {"quality": 1, "security": None, "delivery": 0},
        "complexity": 2,
        "effort_days_low": 2, "effort_days_high": 4,
        "prerequisites": [], "declared_horizon": None
    }]
}
with open("edited-rehearsal.json", "x", encoding="utf-8") as handle:
    json.dump(example, handle, indent=2)
```

Then run:

```sh
python method.py --input edited-rehearsal.json --render --outdir rehearsal-review
```

The input path is relative to the current working directory. Without `--input`, the retained `backlog.json` beside the module is used, even from another working directory. The command above produces a readable `29-prioritization-method.md` and machine-readable `horizons.json` in the selected output directory. Its exercised result is:

```text
items=1 quick_wins=1 prerequisite_work=0 violations=0 disagreements=1
```

The item is proposed for `0-90`, but its declared-horizon view places it in **UNASSIGNED**. Its missing security assessment remains unknown; its assessed delivery effect of zero remains zero. The tool does not turn the proposal into a declaration.

For machine-readable stdout without writing reports, use:

```sh
python method.py --input edited-rehearsal.json --json
```

`--json` cannot be mixed with `--render`, `--print` or `--outdir`, so success messages cannot corrupt its JSON stream. Diagnostics remain on stderr. `--check --json` is supported.

## Distinguish the operator actions

| State | Meaning | Next operator action |
| --- | --- | --- |
| `UNASSIGNED` | Complete effort range, no declared horizon | Review the proposal and record a deliberate declaration in the input copy |
| `NEEDS_ESTIMATE` | No complete effort range | Obtain the missing bound(s); a supplied partial bound is retained, not erased |
| `INVALID_HORIZON` | A declaration such as `soon` is outside the supported vocabulary | Correct the declaration; do not treat this as an estimation problem |
| `DANGLING_PREREQUISITE` violation | A named prerequisite is missing from the backlog | Resolve the reference, even when the dependent has unknown effort |
| Disagreement | Proposal and declaration differ | Review both readings and the declared reason; neither is silently substituted for the other |

A partial estimate such as low=2/high=null stays visible as `2–UNKNOWN` and cannot produce a scheduled proposal. Malformed numeric values, booleans, negative estimates, non-finite numbers and duplicate JSON keys receive input errors rather than a misleading quick-win result.

## Exit status and report preservation

`0` means no detected rule violations, not a complete assessment. `1` means one or more rule violations; requested JSON/Markdown still exposes the findings. `2` means invalid input, invalid option combinations, read/encoding errors or report-write errors. Check the exit status before using an output as a successful result.

Edited-input `--render` requires an output directory, avoiding an accidental replacement of the committed example. A report path that aliases the input, including hard links and symbolic links, is rejected without changing the source. Each report is staged and atomically replaced, so an individual replacement failure preserves that file's previous contents. This is **per-file atomicity, not a multi-file transaction**: an earlier file in a multi-output command may already have been replaced when a later output fails. Use a separate directory for each saved review and inspect the command result.

## What the horizons do not establish

Prerequisite proposals inspect **declared** prerequisite horizons, not the proposals of other rows. Therefore an undeclared chain A → B → C can produce A=`180+` and B/C=`90-180`; this is a preserved policy boundary, not a coherent schedule. The rendered document calls this out explicitly. Review declarations and sequencing before treating the collection as a plan. Same-horizon ordering and actual available capacity are not calculated here. Deep graph traversal is iterative, but that does not add capacity planning or a transitive scheduling policy.

Independent semantic replay and its original-source negative controls are developed separately by RIVET-8F31 under `independent_review/`. They are not a runtime dependency. See `EXECUTION.md` for the exact source identities and execution scope of this integration.
