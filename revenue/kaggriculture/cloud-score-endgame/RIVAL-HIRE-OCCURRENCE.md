# Retained rival-HIRE occurrence at the terminal boundary

`terminal_inputs.py` can model an explicit rival queue containing `SELL` then
`HIRE`, but that interface is deliberately opt-in and does not predict when a
rival will hire. This additive scanner asks the missing empirical question on
already-retained evidence: **does the rival actually submit HIRE at decision
718, where the terminal score selector can affect the same market?**

## Result

The scanner consumed two existing, source-bound development banks without
running an actor, engine transition, or new game:

* POLY terminal-input package: 32 retained records from seeds 9860001 and
  9860019, archive SHA-256
  `af693707f97eea60e068a094af075255c107407c067eb82977a84a2ad74c1cd4`.
* ORBIT exact-current/frozen-control lonespear package: 16 complete records from
  seeds 9926001 and 9926002, archive SHA-256
  `f5dd230a88a447e8630a864735a047abca473282e23bb3b77b2abfea7910c759`.
  Its current arm is the canonical `a8af2b83...` checkpoint.

Across all 48 records (17 source-bound exact rival action streams):

| Measurement | Count |
|---|---:|
| records with rival HIRE at terminal decision 718 | **0 / 48** |
| terminal SELL orders | 150 |
| terminal BUY_PRODUCT orders | 16 |
| records with rival HIRE earlier on day 29 | 48 / 48 |
| preterminal day-29 HIRE orders | 496 |

Every retained day-29 HIRE occurs at hour 0 or 1 (decisions 696 or 697). None
occurs at hour 22 / decision 718. The ORBIT current and matched control arms
also have identical rival HIRE event sequences in every paired record: six
orders at day 29 hour 0 and five at hour 1.

## Consumer decision

Keep `allow_rival_hire=False` in the canonical terminal-history feature on this
evidence. The constructed native reversal in `RIVAL-HIRE.md` remains a valid
conditional mechanic and its explicit API remains useful, but these banks do
not supply a reached terminal-HIRE scenario. An earlier final-day HIRE cannot
be caused or blocked by changing the later decision-718 sale queue.

This is not a claim that no opponent can ever hire at the terminal decision.
A future activation requires a separately identified public-history or reached
trace source containing terminal HIRE, or a deliberately declared stress
family whose uncertainty is kept explicit. Do not convert the earlier-day
counts into terminal recurrence probability.

## Reproduction

Materialize and extract the two exact archives, then run:

```sh
python hire_occurrence.py \
  --poly-bank /path/to/poly/inputs/development-records.json.xz \
  --orbit-root /path/to/orbit-extraction \
  --poly-archive-sha256 af693707f97eea60e068a094af075255c107407c067eb82977a84a2ad74c1cd4 \
  --orbit-archive-sha256 f5dd230a88a447e8630a864735a047abca473282e23bb3b77b2abfea7910c759 \
  --expected-current-archive-sha256 a8af2b834bb5e1d6486245b9538c2de5a041085be38c7707d08e6d49e6149e89 \
  --output /tmp/RIVAL-HIRE-OCCURRENCE.json
python -m unittest -v test_hire_occurrence.py
```

The JSON output retains each source record, candidate seat, terminal queue
hash, source-bound action-stream hash, operation counts, and HIRE timestamps.
Recorded rival actions are evaluation-only evidence and never actor inputs.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
