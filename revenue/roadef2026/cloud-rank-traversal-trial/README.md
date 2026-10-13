# Cold paired trial: rank traversal versus first polish

This dispatch-only experiment compares two candidate implementations inside the
same three-lane portfolio. A04 runs `base_e801` then `new_d85`; A14 runs
`new_d85` then `base_e801`. Each starts cold with fresh output paths. Both arms
enable `FLEET_POLISH_AFTER_EXHAUSTION=1` with explicit bounds of 16 passes,
32 demands and 24 pair nodes. Only `new_d85` enables
`FLEET_POLISH_RANK_TRAVERSAL=1`. Both retain a separate rank report.

The base is the measured first-polish implementation, not the earlier 758
candidate stored inside the retained supporting context:

| Component | SHA256 |
|---|---|
| Base source, prior/new.cpp | e8014d78f40df5546d80f0ff6f1c6bc3a97944a526d7c347eb0dcdbe77728e46 |
| Base executable, prior/new-candidate | 13694deaa08e933c65a1460c2963208b020cbb17b12db92e6b8bdea27f7279df |
| New source | d85ee6187607b1e04c9d77073d42e3eba699fe42309ee3f3324f25528a8f945e |
| New builder | 264ae946c36954f7a9545dc569af8666ee4c58e161210056d5988349f4181c30 |
| New patch | 9d18568c3cefada7c2f3af964b863a740d5024da34ad4923f92019e1727f47f6 |

The workflow retrieves artifact **10050120696**, from completed run
**34211426650**, source ref `320bfc25002d4836c13fa772d8e82de7d7cb8054`.
It pins the prior manifest to
`140cb4200b29e27840f2e0c21f249742a3d9edf6037bc7ec3a096185f45fb64c`
and verifies all 529 listed files and their exact sizes and hashes before use.
The complete prior artifact is retained in `prior/`. SEDGE, FLORA, checker,
supervisor, comparator, headers and the six official A04/A14 input files are
reused. No previous arm is resumed. No other panel is run.

Only the new d85 executable is compiled, using the retained vendor headers and
`g++ -O3 -std=c++20 -DNDEBUG`. The builder must reproduce the reviewed source
and patch exactly. The base binary is reused without rebuilding. ZIP extraction
loses executable permissions, so the workflow restores them with `chmod +x`.
The [official download-artifact documentation](https://github.com/actions/download-artifact/blob/v4/README.md)
defines cross-run artifact retrieval, its token inputs and permission behavior.
The workflow grants only `contents: read` and `actions: read` to its job token.

Each portfolio receives 585 seconds with the unchanged internal 565-second
search allowance. GNU timeout provides a separate TERM-at-590/KILL-at-600 guard.
The four portfolio invocations and their independent official 6/12 checks run
strictly sequentially. The retained process-tree monitoring, start-token cleanup,
cold environment isolation and checker parsing come from the first experiment's
tested harness. Source/binary records identify the actual candidate used per arm.
Inherited FLEET, SEDGE, CLOUD and PORTFOLIO overrides are removed.

Authoritative comparison uses the complete descending official Decimal vector,
including native scientific submicro tokens. It does not rescale, round again or
use cost as a tiebreak. Both report precisions must be valid and agree on exact
coordinate sets, lengths and cost. The selected solution must match the validated
supervisor receipt. Abnormal exits, missing reports and unresolved descendants
remain explicit rather than being interpreted as successful fallback.

`results/summary.json` identifies `base_e801` and `new_d85`, records the first
differing rank and values, and preserves completion status separately from saved
output quality. Raw lane logs and parsed `FLEET_POLISH` events retain natural
phase entry, attempts, accepts, selected ranks and stopping reason. A missing
phase event does not establish either execution or fallback. Resource receipts
record observed CPU affinity, available quota fields, RAM, sampled process-tree
RSS, wall/CPU time, exits and cleanup; unavailable quota fields remain unknown.
One pair per case is not an equal-CPU-work speed benchmark or a general quality
guarantee. No improvement, fallback selection or full-budget exhaustion is assumed.

## Publication mapping and one explicit dispatch

Map only these files from the preparation directory:

- `run_paired_trial.py` and `README.md` to
  `revenue/roadef2026/cloud-rank-traversal-trial/`.
- `roadef-rank-traversal-paired.yml` to
  `.github/workflows/roadef-rank-traversal-paired.yml`.

The separately reviewed integration files belong in
`revenue/roadef2026/cloud-rank-traversal/`. Keep private validation notes and the
local downloaded artifact outside this publication mapping.

Only `workflow_dispatch` exists; there are no push/PR triggers. The job skips
provider rerun attempts and serializes dispatches. Inspect existing runs before
the single dispatch, and resolve an uncertain provider response before retrying.
Use an actual published immutable commit for `PUBLISHED_COMMIT`:

```sh
gh workflow run roadef-rank-traversal-paired.yml \
  --repo woahwhattheheck/commons --ref main \
  --field operation_id=roadef-rank-traversal-cold-a04-a14-20260908-01 \
  --field integration_ref=PUBLISHED_COMMIT
```

The operation ID appears in the run name, `RUN.json`, summary and retained
artifact name `roadef-rank-traversal-OPERATION_ID-RUN_ID`. Record the provider run
ID after dispatch. This preparation performs no publication, dispatch or
qualification action.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
