# TITAN economic stress and deadline fallback

This additive lab exercises the published `IntegratedSelectedAgent` on the
unmodified pinned Kaggriculture interpreter. It owns no controller composition,
opponent league, or generic runtime-budget work.

`runner.py` records complete games, own and rival cash, W/T/L, per-call timing,
selected/output actions, natural economic-family hits, timeout/error counts and
the slowest reached calls. `deadline_adapter.py::DeadlineFallbackAgent` enforces
one wall-clock budget around exactly one producer selection and one transform.
Before selection, ordinary steps fall back to legal all-worker PASS. At final
decision 718, it instead constructs a visible-state liquidation: every worker
already at a shed-access tile issues engine-native multi-product `DROP`, then all
positive post-unit shed lots are sold. After producer selection, the exact
selected action is the fallback. No controller is called twice.

The injected-overrun arms are deliberate load faults on naturally reached engine
states. They are not claims about natural runtime or leaderboard rank.
Raw JSON reports are published as deterministic `gzip -n -9` archives; their
uncompressed and archive hashes are both recorded in `MANIFEST.json`.

## Reproduce

Use the integrated-selected archive from Commons PR #9997 / merge
`b15af38473a7f5ab315753ffebda7aba5177aee2` and official engine artifact
`10005621438`.

```bash
python3 -B test_runner.py
python3 -B runner.py \
  --engine /path/to/engine-artifact/engine \
  --runtime /path/to/integrated-selected-v1 \
  --seeds 9922001 9922002 9922003 9922004 \
  --arms natural deadline \
  --output results/pilot-natural-deadline.json
```

Use `--arms injected_overrun --inject-stage transform --inject-step 683` for
the reached floor-boundary fallback case. Use
`--arms injected_overrun_repaired --inject-stage production --inject-step 718`
for the controlled final-selection overrun and repaired terminal fallback.

The executed VM exposed an 8-CPU cgroup quota and 20 GiB memory limit. Exact
1.6-CPU throttling was not available, so no result is labelled as measured in
that CPU envelope. The one-second deadline itself is enforced by Linux
`ITIMER_REAL`; the reusable adapter documents its main-thread/Linux contract.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
