# Scientific actor launch environment

This opt-in helper applies scientific-library thread settings before a selected
Python actor starts. It composes with an independently loaded cloud evaluator
without changing its source, wire protocol, action/startup/game deadlines,
resource sampling, or cleanup.

## Use

Load `scientific_environment.py` alongside the per-game driver, then install it
on that game's independently loaded evaluator module before creating actors:

```python
from scientific_environment import install

launch_environment = install(evaluator, [str(scientific_opponent_path)])
# Run the existing evaluator normally, with the same deadlines and source pin.
# Retain launch_environment.launches with the game's ordinary result.
```

The selected specification must exactly match the value following `--worker`
in the existing actor command. Selection only chooses an environment variant:
all other actor specifications and non-worker subprocesses pass through the
original implementation unchanged. There is no actor access restriction.

The selected launch must already provide the evaluator's explicit environment.
The helper copies that mapping and sets `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`,
`MKL_NUM_THREADS`, `BLIS_NUM_THREADS`, `NUMEXPR_NUM_THREADS`, and
`VECLIB_MAXIMUM_THREADS` to `1`. It never copies the parent process environment.
An environment already initialized by Python startup can precede an agent's own
imports, so placing these settings inside the agent can be too late.

Install once per independently loaded evaluator module, before any actor is
created. The facade delegates ordinary subprocess attributes and records the
worker specification, process ID and applied settings. It does not modify the
global `subprocess` module. Restore or discard the private evaluator module when
the per-game driver ends; do not install concurrently on one shared module.

## Validation and limits

[test_scientific_environment.py](test_scientific_environment.py) passed all 12 focused checks. Coverage includes
exact selection, unchanged other actors, environment-map isolation, delegated
subprocess behavior, launch exceptions and installation scope.

```sh
python -B -m unittest discover \
  -s revenue/kaggriculture/cloud-bridge-environment \
  -p 'test_scientific_environment.py' -v
```

The helper was also exercised through the existing native actor protocol.
A balanced eight-call cold-process comparison retained identical returned
actions. Both arms returned all four calls; observed thread counts were 14
without the helper and 1 with it. Earlier in-agent settings left 10 threads in
that environment. These observations establish placement and thread-control
behavior for that runtime, not a general latency guarantee.

The subsequent fresh full-game consumer retained three first-action opponent
RPC request timeouts despite the pre-launch settings. Those attempts remain separate
from complete games and are not retried or counted as wins. This repair controls
the launch environment; it does not establish immunity from scheduling delays,
cold imports, filesystem stalls or other deadline causes. Existing evaluator
source, default policy, timer budgets and original artifacts remain unchanged.

Match inputs, detailed traces, diagnostics and manifests remain in the private
TITAN work area. This directory contains only the reusable helper, its focused
tests and usage documentation.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
