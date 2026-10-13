# Revision 2 research component

`main.py::agent(observation, configuration)` retains one frozen SELL controller
and makes one compatible continuation choice at step 360. The parent directory's
`selected.py` remains the default. This revision is an experimental cash proxy;
its conditional projections are not calibrated win probabilities.

`continuation.py::evaluate_continuations(observation, configuration, plans,
scenarios, baseline=..., mechanics=..., kernel=...)` accepts complete action
routes and explicit conditional rival supply/shop streams. It returns a selected
route, scenario cash components, minimum cash, funding failures and projected
exit states. `policy.py::EconomicPolicy` supplies pinned mechanics and prefix
checks. No additional controller or external model call is made. Runtime inputs
are current observations and prior public market transitions only.

Projection sale timing uses frozen route lots with stock clamps and liquidation;
the live agent continues using its original adaptive SELL scheduler. Future
shop draws, weed growth and rival production are uncertain. Scenario output
must not be read as a realized continuation or a probability distribution.

From the parent directory:

```sh
python3 revision2/test_continuation.py
python3 revision2/run_panel.py --seeds UNUSED_DEVELOPMENT_SEED --panel development --output revision2/results/new-development
```

Tests include a retained development observation with its trace identity.
The public-bank source closure is required only for opponent evaluation.
Older held panels and validation seed 9880328 are consumed evidence, never new
validation. Reproduction must respect the seed ledger and freeze identities.

Original revision code is Apache-2.0 under the parent license. T12 flow code is
vendored unchanged with its MIT notice. Frozen parent, engine and public-bank
dependencies retain their original licenses and notices. No upload is performed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
