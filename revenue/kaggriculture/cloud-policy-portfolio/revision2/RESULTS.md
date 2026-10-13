# Recorded revision2 panels

| Panel | Games | SELL W/T/L | Economic W/T/L | Economic own/rival cash delta |
|---|---:|---:|---:|---:|
| Development | 96 | 23/0/1 | 23/0/1 | −3,490 / +718 |
| Unconditioned validation | 64 | 16/0/0 | 16/0/0 | 0 / 0 |
| Source-condition validation | 32 | 8/0/0 | 8/0/0 | +12,308 / −4,574 |

Each panel includes four coherent arms. Unconditioned validation had no
compatible alternative; source-condition validation used a separately frozen
early-YARN intake with eleven recorded prefixes and no outcome criterion.
Seven economic decisions completed and one used its budget fallback in that
conditional panel. The largest complete economic action took 0.674 seconds.
All paired action prefixes matched before step360. No policy is promoted:
the parent `selected.py` remains frozen SELL and all research arms are retained.

The new run comprises 192 complete games. Twenty-four initial startup attempts
record an entry-point bug; eight completed controls from that batch were reused
without replay. The first development batch has no after-call decision receipt;
later batches record actual decisions. Missing decisions are not inferred facts.
The old 266 games and adapter suite were not replayed.

`FREEZE.json` and `CONDITIONAL-FREEZE.json` separate source freeze, intake and
terminal labels. `results/*summary.json` provides comparisons; the receipt
archive retains all per-game observations, decisions, searches and attribution.
The trace archive contains lossless semantic observation/action streams.

```sh
python3 revision2/artifacts/decode.py --output /tmp/t14-r2-artifacts
tar -xJf /tmp/t14-r2-artifacts/receipts.tar.xz
python3 evidence.py unpack /tmp/t14-r2-artifacts/full-traces.xz /tmp/t14-r2-traces
```

Runtime projections use explicit scenarios and approximate future SELL timing.
Conditional cash studies are separate from actual game labels. These are offline
scores, with no hosted-rating or revenue claim and no Kaggle/notebook write.

After these panels, the offline harness moved its diagnostic receipt through the
existing JSON worker response. The driver removes metadata before executing or
hashing game actions. `HARNESS-UPDATE.json` records the two harness-file changes
and its focused transport check. Policy code and all panel receipts are unchanged;
the runtime archive and historical freeze retain the exact evaluated harness.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
