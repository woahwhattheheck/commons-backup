# Independent finite-table certificate consumer

`certificate_consumer.check_certificate(deltas, solution)` checks POLY's full
`solve_full_table` result without importing its optimizer or verifier. It recomputes
normalized rational mixtures, the original ordered-table hash, every column and
dual-row expectation, lower/upper bounds, gap, support, pure minima, and the
provider's completion/baseline contract. Runtime dependencies are standard-library only.

```python
from certificate_consumer import check_certificate

receipt = check_certificate(deltas, solution)
# receipt["valid"]: both numerical certificate and provider contract agree.
# receipt["bounds_closed"]: exact lower bound equals exact upper bound.
# receipt["completed"]: provider reported a completed optimum.
# receipt["positive_optimum"]: valid, completed, and strictly positive.
```

A valid certificate at a computation limit may have equal bounds; it is not
silently relabeled a completed provider run. Budget stops and zero-valued optima
retain the baseline. The `certificate_valid` flag supplied by the provider is not
trusted. The numerical proof is a finite-table **expected** bound, not a realized
outcome, feasibility, source-context, or game-strength claim. Column weights are
an adversarial upper-bound witness, not calibrated rival probabilities.

POLY owns `cloud-full-support/full_support.py`. PRISM owns persisted selection in
`cloud-weighted-plan-selector/`. This component contains no simplex, alternative
solver, random draw, controller, producer, or fill reconciliation. A consumer must
still establish whole-plan feasibility, unchanged context, full execution and
persistence. This checker never promotes a policy or calls a parent.

## Use and reproduction

From the repository root, with the existing POLY core present:

```sh
python -m unittest discover -s revenue/kaggriculture/cloud-market-support -p 'test_*.py'
python revenue/kaggriculture/cloud-market-support/run_checks.py --output /tmp/certificate-cases.json
```

`run_checks.py --core /path/to/full_support.py` supports an explicit source. Tests
use `TRIAD_CORE=/path/to/full_support.py` for the same override. The receipt names
the reference commit only when the actual supplied Git blob matches; other source
bytes retain their actual hashes with a null reference commit.

For an already-computed certificate, write JSON with `deltas` and `solution`:

```sh
python revenue/kaggriculture/cloud-market-support/certificate_consumer.py input.json --output receipt.json
```

Exit codes: 0 valid, 1 invalid certificate, 2 malformed/unreadable input. This CLI
never invokes the solver or alters the supplied plans/streams.

## Executed scope

28 focused methods and nine actual provider-output cases passed against POLY
source `3457d8f149b2bb07de6d9993a41ae0e0f19eb57f`, Git blob
`b04f7bc4ff2137dee4b70ec6f10e7f02ccaebd06`. `RESULTS.json` records the exact source,
case outcomes and measured checker timing. `run_checks.py` reproduces complete
solution/receipt pairs. Tests cover metadata tampering, reordered tables, invalid
mixtures, flags, budgets, nonmutation, source labeling and actual CLI behavior.
Two small published receipt matrices were transcribed from the pinned T15 README;
no original engine archive or game was replayed. Algebraic support examples are
not full-game improvements. No LP comparison panel was rerun for this delivery.

The earlier, superseded TRIAD solver experiment is retained only in the separate
`titan-market-support-20260907.zip` delivery archive under `historical-development/`.
Its 200 LP comparisons are not evidence about POLY's source and are not installed
as another live solver. The repository delivery is only this independent consumer.

## Sources and license

Original checker implementation: Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0). POLY's
core remains a separate dependency at its existing path. Provider schema:
https://github.com/woahwhattheheck/commons/blob/3457d8f149b2bb07de6d9993a41ae0e0f19eb57f/revenue/kaggriculture/cloud-full-support/full_support.py

Published receipt matrices (README blob `5fb510deeef0136c7143327514a7601d6fac896f`):
https://github.com/woahwhattheheck/commons/blob/4d97474b0188b0373be1b52b610c0114ceb033c8/revenue/kaggriculture/cloud-market-game-theory/README.md

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
