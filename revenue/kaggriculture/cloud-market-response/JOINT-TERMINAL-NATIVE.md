# Joint terminal history: native consumer tests

`test_joint_terminal_native.py` executes the existing T12 history, joint scenario adapter, POLY terminal receipts, and official interpreter. It adds no runtime implementation, policy, solver, workflow, or game panel. The test imports `flow.py` directly; it does not depend on the contents of another test module.

## Run

Reuse engine artifact `10005621438`, ZIP SHA256 `06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`. Set `ENGINE_DIR` to the directory containing its `kaggriculture.py` and `utils.py`.

```sh
TITAN_ENGINE_DIR="$ENGINE_DIR" \
TITAN_TERMINAL_INPUTS_PATH=revenue/kaggriculture/cloud-score-endgame/terminal_inputs.py \
TITAN_JOINT_REPORT=/tmp/joint-terminal-native.json \
python -B revenue/kaggriculture/cloud-market-response/test_joint_terminal_native.py
```

Use a separate Python process. This offline harness installs a minimal engine utility module in `sys.modules`; it extracts the original `resolve_episode_seed` definition but its post-initialization fixtures do not call it. No game seeds are drawn. The adjacent runtime and flow files are used; `TITAN_FLOW_PATH` can supply a source-equivalent flow file when testing an extracted package.

## Executed source

These Git blob identities were matched to current repository readbacks before this recovery execution on September 8, 2026:

| Input | Git blob SHA1 |
| --- | --- |
| `joint_terminal_history.py` | `3d03475fb422fa0aab998b3f537a1b9532ff6e90` |
| `flow.py` | `7b3c1c383e98ce1eb5bf539caddf0ab4351f8633` |
| `terminal_inputs.py` | `2eae54ea4c62a83048ba8c5d69b9bbd48af2caa7` |
| Native test | `4b74df6473b4b4da6c0efc8287ca253676f36e94` |

The runtime identity is resolved: the saved runtime bytes compute to the same blob as the repository. No runtime replacement was needed. The test explicitly checks the terminal producer pin. Engine and source SHA256 values plus measured counts are in `JOINT-TERMINAL-NATIVE-VALIDATION.json`.

## Result and limits

Seven methods pass. Twelve constructed historical transitions yield 84 exact non-operating-product intervals. The adapter retains each same-lag product vector and explicit operating-stock/slot hypotheses.

The complete-table checks cover both seats at market inventory levels **0, 95, and 500**, with a retained `BUY_SEED` order. All **288** own/rival terminal cash pairs match full native interpreter transitions; own shed, seeds, terminal status, unchanged inputs, and the inherited purchase slot also match. The suite executes 303 terminal-producer cells in total, including boundary cases. Four separate full transitions form the empty-slot control.

For that control, two own EGG sales precede a rival EGG sale in slot 2. Preserving the two empty rival slots gives cash **1474/1897**; compacting them gives **1458/1915**, a relative-margin difference of **34**. Both seats repeat one constructed mechanism, not independent wins.

Exhausted cell budgets retain missing receipts and the complete fallback action. An expired deadline performs zero market calls. The supplied post-unit path performs no second unit-action call. These seven methods do **not** establish HIRE coverage, insufficient-history consumer dispatch, LARCH/PRISM selection, live actor state, full-game strength, or hosted timing. Existing dedicated suites cover other boundaries separately.

## Consumer use

Pass a ready joint family's complete `scenarios` to the existing terminal producer. An unavailable family must preserve the caller's already-selected action; do not replace missing or censored history with zero or silently trim scenarios. Runtime integration remains with the existing CEDAR/POLY/canonical consumers.

This delivery recovers previously saved tests. It does not add their repeated execution to old game or sample counts, and no hosted CI or merge status is inferred from a local result.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
