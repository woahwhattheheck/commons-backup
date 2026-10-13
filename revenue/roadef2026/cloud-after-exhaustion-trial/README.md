# Cold paired trial: polish after natural exhaustion

This manual-only workflow prepares exactly four cold portfolio invocations:

1. A04 frozen baseline, then integrated candidate.
2. A14 integrated candidate, then frozen baseline.

Every invocation uses the same frozen three-lane supervisor, SEDGE, FLORA and
official checker. Only the candidate executable changes, and only the new arm
sets `FLEET_POLISH_AFTER_EXHAUSTION=1`. No saved incumbent is supplied. Inherited
FLEET, SEDGE, CLOUD and PORTFOLIO diagnostic overrides are removed. Both arms
receive portfolio585/internal565 seconds; GNU timeout sends TERM after590 and
KILL ten seconds later. Each arm and its independent6/12 checker calls finishes
before the next starts. Fresh output roots are mandatory. Observed surviving
descendants are stopped by recorded process-start identity; unresolved survivors
prevent a later arm. No solver retry or repeat of a completed cell occurs.

## Exact source contract

- Runtime freeze: `6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055`.
- Candidate recipe: original `2885d176373c33410148829fef93c310c3752c0b`, source
  SHA256 `322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1`,
  plus combined.patch Git blob `0ff8d2ee7c4df1022c50484a89e7424329cce0ec`.
- Baseline composed source:
  `758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f`.
- Integrated source:
  `e8014d78f40df5546d80f0ff6f1c6bc3a97944a526d7c347eb0dcdbe77728e46`.
- Integration builder:
  `57a97b7384bce27caa96ca0048c4adf1c83fcbddac9c8a59df6c32ea974e915a`.
- PRISM method builder at `73a805e290cee36981917ac09e7ce2133f35afd7`:
  SHA256 `e5a77185d7126c8e87ab5e54557d7a7ff40a918e2a14646923cc95b0f25b08d6`,
  Git blob `96d457207f1e3a63e8932a20dce8be63e4f87a1d`.
- Supervisor:
  `182371658e82f9037716e90ea8cd115622d089d02512916c7a7bf3b39fca1c63`.
- Comparator:
  `a402a0166b1e52c95dd181e15b8a124504ac78ddea7e815944c754569b323cb8`.
- Official inputs/checker v1.2.2: challenge commit
  `d84d319a7fdb8de3b1866830d2eaa2937871e5ae`; the frozen bootstrap retains its
  four archive hashes and unchanged Networktools pin.

The workflow invokes the integration builder rather than the standalone PRISM
experimental runner. It verifies reproduced source bytes before serial C++20
compilation. Internal conservative integer-bin move acceptance is unchanged;
authoritative ranking comes from the frozen official-output Decimal reader.
Scientific submicro values remain exact, with no local re-rounding and no cost
tiebreak. Validity, complete coordinate sets and vector lengths are checked.

## Publication mapping and explicit dispatch inputs

Map only these files from this preparation directory:

- `run_paired_trial.py` and `README.md` to
  `revenue/roadef2026/cloud-after-exhaustion-trial/`.
- `roadef-after-exhaustion-paired.yml` to
  `.github/workflows/roadef-after-exhaustion-paired.yml`.

The separately reviewed five integration files belong in
`revenue/roadef2026/cloud-after-exhaustion/`. All other private working files stay
outside that mapping. There is no push or pull_request trigger. Workflow reruns
are skipped, concurrent dispatches are serialized, and a duplicate operation is
not made safe merely by using the same name. Inspect existing provider runs and
resolve uncertain dispatch results before another dispatch.

Required dispatch inputs:

- `operation_id`: `roadef-prism-cold-a04-a14-20260908-01` for this reviewed trial.
- `integration_ref`: the actual immutable40-character published commit containing
  the reviewed integration, harness and workflow. This commit is not yet known
  during local preparation and must not be guessed.

After publication and explicit execution authorization, one operational command
is sufficient (replace PUBLISHED_COMMIT with the actual returned commit):

```sh
gh workflow run roadef-after-exhaustion-paired.yml \
  --repo woahwhattheheck/commons --ref main \
  --field operation_id=roadef-prism-cold-a04-a14-20260908-01 \
  --field integration_ref=PUBLISHED_COMMIT
```

Record the provider run ID after dispatch. Its run name contains the operation ID;
artifact name is `roadef-after-exhaustion-OPERATION_ID-RUN_ID`. `RUN.json` and
`results/summary.json` retain both identifiers and immutable source selection.

## Readout

`results/summary.json` records fixed arm order, per-arm completion, exact new-vs-old
first differing rank/value, peak and vector length, without assuming a win.
Every arm retains raw6/12 checker JSON, full supervisor receipt, raw lane logs,
parsed `FLEET_POLISH` begin/skipped/end events, stdout/stderr, process returns,
elapsed times, waited-child CPU, cgroup CPU/RAM and before/after usage counters,
and sampled process-tree RSS. Sampling is not a hard memory bound. Raw logs remain
authoritative if event parsing fails or a phase never starts. Missing events do
not establish fallback. A valid saved output after an abnormal process exit may
still have a diagnostic comparison, while the arm remains incomplete.

The artifact retains the exact baseline context, integrated source/binary,
builders, patch, official six input files, full source/binary hashes and an
artifact manifest. Failures retain whatever output exists; an incomplete pair
is not reported as completed. Compilation and these four cold invocations are
cloud execution only. No original20-case calibration or final-B panel is run,
and no qualification package, draft, attachment or submission is changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
