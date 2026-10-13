# Value of released budget: two fixed-round public comparisons

This follow-through consumes the **already-saved** neutral encodings from
PR10214. It tests whether they give the existing search useful starting states,
not merely a lower-cost equivalent representation. No solver source is changed.

## Predeclared comparison

B07 and B11 were chosen before the primary-search comparison because the neutral
preparation released eight and six transition-budget units respectively. Each
has two starting solutions: QUARTZ's exact original SEDGE incumbent and the
exact-flow-equivalent neutral encoding. Both arms execute the **same unchanged
fleet2885d176 binary** for eight primary search rounds with a 30-second ceiling.
There is no ongoing neutral operator inside these continuation searches.

Execution order is original then released for B07, reversed for B11. The calls
finish in 1.96–4.87 native seconds, well before the ceiling. This is fixed-round
work, not equal attempted-move counts or a controlled timing benchmark.

## Results

| Public input | Original → released first differing 6-decimal saturation | Rank | Peak in both arms | Primary accepts |
|---|---|---:|---:|---:|
| setB-07 | 0.085349 → 0.085342 | 4,022 | 0.664909 | 18 → 21 |
| setB-11 | 0.220739 → 0.220694 | 2,618 | 0.363609 | 54 → 60 |

Both released-input arms improve the complete six-decimal lexicographic vector
relative to their corresponding original-input arms. **Neither peak improves.**
These are two predeclared cases, not a claim of general superiority or a
qualification rank. Selection for observed headroom makes this a mechanism
probe, not a random or held evaluation set.

All four original solver calls and eight official checks at six/twelve decimal
places complete successfully. Every link/time saturation coordinate and total
transition cost reconciles with native diagnostics within 1.01e-12. Complete
solutions, budgets, objective vectors, timings, source/input hashes and all
process output remain in the raw package. The freed budget may be spent during
later search; final total transition costs are not assumed to remain lower.

The portable command was then executed on the same two cases as a separate
reproducibility check: four additional solver calls and eight checker calls.
All solution bytes, non-timing solver statistics and complete official checker
outputs are exactly equal to the original runs. These are **repeats**, not four
new independent results. Their timings and commands remain separately recorded.

Changing the initial encoding can alter the candidate neighborhoods as well as
budget feasibility. The experiment does not attribute each later improvement to
one isolated budget unit. A broader quality decision remains with the portfolio
owner; S139's draft, attachment, selected source and submission state are not
changed by this follow-through.

## Source and inputs

Both primary arms use original fleet commit
`2885d176373c33410148829fef93c310c3752c0b`, `main.cpp` Git blob
`9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df`, SHA-256
`322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1`.
Recorded GCC14.2 `-O2 -std=c++20 -DNDEBUG` solver binary SHA-256:
`f842485f38acdcfff24ba919bb38bab3765b6ed4e319b20d2efb56627a4e36a5`.
The official checker comes unchanged from QUARTZ's existing pinned context; its
local binary SHA-256 is
`e2a2297b5a43aaf4d95d6cbc65b16e62d4fc5fb1381e59a2323a8bad3015a472`.

The 22-output neutral occurrence confirmation was handed to OSPREY, who owns the
single canonical occurrence consumer. This continuation does not duplicate that
runner or add its repeated cases to an independent benchmark count. The two
reused released solutions are retained by exact hash in the new result package.

Dependency/data roads already exist:

- QUARTZ screen: `ROADEF-QUARTZ-screen30-2885d176.zip`, Library file
  `file_0000000004f881f5bb67303fe7f403b4`, SHA-256
  `0fed26e0260aad3c3c840c3e2c38b035f21ce6d3cac5544428f4f8a5f2959d9d`.
- QUARTZ source/checker context: Library file
  `file_000000008c8481f783a95eb409c035fb`, SHA-256
  `62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`.
- DATE neutral confirmation: Library file
  `file_000000007dc881f5837c374f3183fbcf`, SHA-256
  `b155eef21726e657053d4170912d48931187fbf8591782563d2bb8ef749d8ef6`.

## Reproduce or inspect without rerunning

The driver is a small consumer of the **existing** `benchmark.execute` function,
not another benchmark scheduler. Default mode only reads saved outputs. It uses
Decimal for the checker vectors, preserving the official writer's scientific
notation rather than rounding the reports into a different comparison.

```sh
python3 -B check_released_search.py --results /path/original-results
```

To repeat exactly these two predeclared pairs, use a new output directory:

```sh
python3 -B check_released_search.py --execute \
  --screen /path/extracted-quartz-screen \
  --released /path/extracted-date-confirmation \
  --benchmark /path/extracted-quartz-context/pinned-fleet/benchmark.py \
  --solver /path/original-fleet-binary \
  --checker /path/unchanged-official-checker \
  --results /tmp/new-released-budget-search
```

The smaller result package also includes the two released starts under
`released/`, which can be used instead of extracting the whole DATE confirmation.
The driver checks original/released solution identities and original public input
hashes. It records supplied executable and benchmark hashes; callers remain
responsible for compiling the documented source. Another compiler may produce
different binary bytes, and floating-point differences must not be silently
relabeled as the recorded result.

`RELEASED-SEARCH.json` retains source identities, each original paired result and
reproduction counts. The raw package preserves the execution-used initial driver
and the final portable consumer separately, all original and repeat outputs,
complete official reports and checksums. There is no new runtime source,
portfolio configuration, public-screen result, Docker workflow or submission.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
