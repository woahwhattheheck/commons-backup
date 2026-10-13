# Joined terminal action execution

This consumer runs LARCH's actual `transform_terminal` through PORT's receipt
projection, POLY's unchanged certified solver, PRISM's exact sampler, T15's
original selector class, and the pinned official interpreter. It supplies a
current-own-state feasibility callback, submits the returned complete action,
and checks realized cash, DONE rewards, inventories, original plan identity,
input nonmutation, and solve/draw counts.

It adds no production selector, solver, worker planner, forecast, or game runner.
LARCH owns the absolute-score implementation (PR10019); PRISM owns the retry
repair (PR10022). This is the missing joined-engine consumer, not a rerun of
LARCH's 761 LP comparisons or PRISM's 13 extracted-method cases. The original
PORT runtime, tests, and 66-transition receipt archive remain unchanged.

## Run with existing sources

From the repository root, with the dependency revisions below and the existing
engine artifact already available locally:

```sh
D=revenue/kaggriculture/cloud-terminal-utility
python -B "$D/check_absolute_execution.py" \
  --engine-dir /path/to/engine \
  --engine-loader /path/to/peer/evaluate.py \
  --output /tmp/absolute-execution.json
```

The engine and evaluator come from existing artifact10005621438. The command
checks all source bytes before invoking the evaluator; absent inputs produce an
error rather than a source download. A flat existing cloud cache can be supplied
with `--source-dir /path/to/cache`. The six filenames are listed in the script's
DEPENDENCIES mapping. `--receipts` selects the unchanged PORT archive when it is
not beside the script. No workflow, export job, provider request, or credential
is needed to execute the consumer.

Exact source inputs (all Commons paths are under revenue/kaggriculture):

| Component | Source revision | File / blob |
| --- | --- | --- |
| PORT | a7682040f54ef4ce5845f8caabada0408018fa1c | cloud-terminal-utility/terminal_utility.py / 6734e0b3 |
| LARCH + PRISM retry | 1f15b08e9e58d33a39770a831c6dfc84f49968a0 | cloud-score-endgame/score_endgame.py / 543ab5b4 |
| POLY | 3457d8f149b2bb07de6d9993a41ae0e0f19eb57f | cloud-full-support/full_support.py / b04f7bc4 |
| PRISM | 696ba1dc4ffff55ab047a91361508843ad0e08af | cloud-weighted-plan-selector/weighted_selector.py / 2c21f897 |
| T15 | 46332a6b2ed2e3b329cca62faf85d2482c23000f | cloud-market-game-theory/selector.py / 546b7118; solver.py / 3a6446d9 |

Later source changes do not silently receive this result. Supply these recorded
revisions from an existing checkout/cache to reproduce this source-specific
receipt; do not replace a newer live policy with them.

## Executed results

The successful run passes 12 methods with no failures, errors, or skips. It
contains 36 selected-queue interpreter transitions and 12 separately counted
transitions constructing the new retry-input tables. There are 51 fixture
initializations and 48 selector calls, including retries. No full game is run.

The original receipt regimes now exercise actual returned actions: the lead33
varying-baseline case selects WHEAT-first in both possible rival worlds and both
positions; the two recovery draws select the two intended support actions;
protected leads and the extra rival-supply world retain baseline. Nonterminal
inputs do not invoke a solver. Budget exhaustion, current stock reservations,
order limits, and unknown continuing feasibility preserve the supplied action.
A supplied fallback is not made valid by the wrapper: the deliberately invalid
reservation/order-limit fallback cases are not sent to the interpreter.

### Same-step parent change has an executed consequence

The new retry input adds one carried EGG, then changes the same-step supplied
parent to DROP plus a final EGG sale. Every current alternative has that same
parent phase. Twelve official transitions build these new complete receipt
cells; no values are guessed from cash deltas. The former PASS/WHEAT/MILK action
remains physically executable, so current feasibility alone cannot catch it.

| Actual consumer | Own final cash | Rival final cash | EGG disposition |
| --- | ---: | ---: | --- |
| Original d03fc481 | 100400 | 100396 | One still carried and unsold |
| PRISM-fixed 543ab5b4 | 100447 | 100398 | Dropped and sold |

The fixed implementation retires the obsolete commitment and preserves the
entire current fallback without another solve or draw. The measured difference
is +47 own, +2 rival, +45 relative cash in each mirrored constructed position.
Identical retries retain the original draw. This is a contract/engine witness,
not two independent gameplay improvements or a rating claim.

To execute the original-source negative control, supply LARCH's original
score_endgame.py from 385ea7ec7d07d9e1250e063b75c6dd75b7a055ab:

```sh
python -B "$D/check_absolute_execution.py" \
  --engine-dir /path/to/engine --engine-loader /path/to/peer/evaluate.py \
  --score-file /path/to/original/score_endgame.py --only-retry \
  --output /tmp/original-retry.json
```

It exits 1 with two failing position subtests and zero execution errors. That
run retains two selected-action transitions and twelve table-input transitions
separately from the successful suite. There is no second retry repair here.

## Read the complete retained evidence without execution

`absolute-execution.json.xz` and `retry-original-execution.json.xz` contain the
lossless successful and original-source reports: dependency hashes, test logs,
every submitted own/rival queue, before/after own private state, cash, statuses,
rewards, decision records, exact solver certificates, and new retry documents.
The archive and expanded hashes are in ABSOLUTE-EXECUTION.json.

```python
import json, lzma
from pathlib import Path
report = json.loads(lzma.decompress(Path("absolute-execution.json.xz").read_bytes()))
print(report["tests"]["log"])
print(report["execution_counts"])
```

The feasibility callback intentionally supports only these sale-only fixtures
and PASS/DROP/PLACE/PICKUP worker operations through the original engine
primitives; purchases and other worker commands return unknown. It is not a
replacement for ATLAS/QUEUE/COORD's general contracts. All possible rival
receipts are supplied before choice. The actual hypothetical rival action is
used only by the evaluator after selection; it never selects our distribution.

Checks run in this cloud container with the existing engine and connector-read
public sources. Preliminary executions are not pooled into the successful
receipt. No new scored panel, held seed, selected default, Kaggle upload,
owner-PC execution, or spending is part of this work. Source and ordinary CI
publication are distinct from hosted execution of this consumer.

New checker code is Apache-2.0. Consumed components retain their existing
Apache-2.0 notices; the official engine remains pinned to
Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
