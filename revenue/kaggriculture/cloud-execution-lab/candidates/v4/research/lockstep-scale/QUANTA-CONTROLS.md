# QUANTA: quote, cash and capacity controls

Companion evidence for **AXLE-SCALE's existing `lockstep-scale` package**. This
adds no second runner, agent, feature key, default change, archive, or deployment.
The preliminary parallel QUANTA runner was discarded after the live-thread
ownership check. The earlier AXLE-SCALE implementation remains the authority.

## Executed evidence

- Exact runner blob: `9eebd953931635e23e000cfeb27772421abe4688`.
- Exact engine blob: `3c202c7ee921da239356789e266b694635103fc4`, recovered from
  existing GitHub Actions artifact `10285621024`; no new workflow dispatched.
- Added companion test blob: `c6879abcf48e065db88d73933a528277890b5b29`.
- **17/17 tests normal; 17/17 under `python -O`.**
- Owner report independently reproduced: **414 microcases + 18 repeated-arrival
  cases**, byte-exact SHA256
  `3859b1cd4485bc5813277392516a1991eb8c1e221e6fea9c01baa77d9748328d`.
  This does not claim the owner's original 22-test suite was rerun by QUANTA.

The owner's hash-pinned loader executes unchanged AST-selected constants and
functions. `_process_market`, `_parse_order`, `_commit_unit` and prices are real;
there are no market mocks. The added fixture uses the owner's state constructor.
No full interpreter, actor transitions, production schedule, or game outcome is
claimed. Funds are explicitly synthetic and all new starting sheds fit 100 units.

## What the extra controls distinguish

An isolated buy/sell roundtrip is cash-neutral in the tested regimes. That must
not be generalized to every opponent action: two players executing aligned
100-unit FERTILIZER cycles at inventory 10000 finish **+20 each**; five cycles
use all ten raw market rows and finish **+100 each**. Both gain equally, so this
is **not a head-to-head margin improvement** and requires the stated opponent
participation. Six cycles produce no additional result because rows 11/12 are
not executed. Requesting 1000 does not overcome the shed's actual 100-unit cap.

A one-raw-row shift instead yields **+990/-990** in this explicit synthetic
cycle scenario; swapping the physical seats swaps the payouts. This reinforces
the earlier scale/seat findings, not a claim of physical p0 priority.

At the $1 floor, a cycle can be cash-neutral while public inventory changes:
the paired test at inventory 11000 ends at 10800 because floor SELLs do not
restore supply. Cash neutrality is not state neutrality.

Additional checks cover other cargo occupying 99 shed slots, affordability at
the post-buy quote, a failed buy followed by a still-executable sale, different
products, ignored tuple rows retaining their queue position, and input
nonmutation. See `QUANTA-CONTROLS.json` for exact results and provenance.

## Reproduce

From this directory, with the pinned engine file available:

```sh
TITAN_ENGINE=/path/to/kaggriculture.py python -m unittest -v test_lockstep_quote_controls
TITAN_ENGINE=/path/to/kaggriculture.py python -O -m unittest -v test_lockstep_quote_controls
python lockstep_scale.py --engine /path/to/kaggriculture.py --output results.json
```

The companion deliberately checks the runner blob. A future legitimate runner
change requires re-execution and an explicit custody rebind, not deleting the
check or silently labeling the old receipt current. No policy promotion follows
from these mechanism controls; opponent behavior and full-game economics remain
separate evidence requirements.
