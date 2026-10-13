# UIOWA-049 — joint assumptions can overturn endpoint agreement

**SYNTHETIC demonstration.** Actual runs of the existing calculator on fictional assumptions; no University findings, measured savings, investment approval or staffing commitment.

Continuation of [issue #16302](https://github.com/woahwhattheheck/commons/issues/16302) and the [existing decision readout](README.md).

## The retained counterexample

At 32 implementation hours and 12 weeks, the original lower- and upper-endpoint objectives both select BASE + RETRY + SYNC, with net support-hour endpoints 42.00–120.00. Agreement at those two objectives does not establish that the same portfolio wins for every simultaneous realization inside the stated intervals.

Narrow AUTOMATE to 10 weekly support hours and 80% reduction, RETRY to 8 hours and 50%, and SYNC to 6 hours and 50%. REPLACE shares RETRY's workload, so its weekly rate also becomes 8. Every change stays inside the original interval; effort, delays, dependencies, exclusions, evidence labels and capacity remain unchanged.

Under this refinement both objectives select **AUTOMATE**, using **20 upper-effort hours**, with net support-hour endpoints **60.00–68.00**. The former BASE + RETRY + SYNC portfolio becomes **42.00–50.00**. Its feasible status did not change; its benefit assumptions did.

## The simultaneous-assumption experiment

Each bit selects the original low (0) or high (1) endpoint and narrows that interval to the selected value. Bit order is AUTOMATE weekly rate, AUTOMATE reduction, RETRY weekly rate, RETRY reduction, SYNC weekly rate, SYNC reduction. REPLACE's weekly rate follows RETRY's in every corner. Other intervals remain unchanged.

All 64 corners were run at capacities 32, 40, 50 and 52, each at 12 weeks: **256 new calculator runs**. Four original-register baseline runs provide comparison. The full feasible portfolio membership at each capacity is identical in all 64 refinements; membership, counts and digests are published in the JSON.

### Selected portfolios across the 64 corners

| Capacity | Objective | Selected portfolio | Corners |
|---:|---|---|---:|
| 32 | conservative | AUTOMATE | 4 |
| 32 | conservative | BASE + RETRY + SYNC | 60 |
| 32 | optimistic | AUTOMATE | 4 |
| 32 | optimistic | BASE + RETRY + SYNC | 60 |
| 40 | conservative | AUTOMATE + BASE + RETRY | 16 |
| 40 | conservative | BASE + RETRY + SYNC | 48 |
| 40 | optimistic | AUTOMATE + BASE + RETRY | 16 |
| 40 | optimistic | BASE + RETRY + SYNC | 48 |
| 50 | conservative | AUTOMATE + BASE + RETRY | 15 |
| 50 | conservative | AUTOMATE + BASE + SYNC | 1 |
| 50 | conservative | BASE + RETRY + SYNC | 48 |
| 50 | optimistic | AUTOMATE + BASE + RETRY | 14 |
| 50 | optimistic | AUTOMATE + BASE + SYNC | 2 |
| 50 | optimistic | BASE + RETRY + SYNC | 48 |
| 52 | conservative | AUTOMATE + BASE + RETRY + SYNC | 32 |
| 52 | conservative | BASE + RETRY + SYNC | 32 |
| 52 | optimistic | AUTOMATE + BASE + RETRY + SYNC | 32 |
| 52 | optimistic | BASE + RETRY + SYNC | 32 |

Counts describe this chosen finite experiment. They are **not probabilities**, likelihoods, confidence levels or estimates of how frequently a portfolio will be best. The experiment does not cover every point in continuous intervals, every effort realization, or every other register assumption.

### Read every corner

The table gives conservative / optimistic selections. A single selection means both objectives agree. The JSON retains each selected portfolio's effort and support-hour bounds plus register and full-report digests.

| Corner | Capacity 32 | Capacity 40 | Capacity 50 | Capacity 52 |
|---|---|---|---|---|
| 000000 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 000001 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 000010 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 000011 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 000100 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 000101 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 000110 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 000111 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 001000 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 001001 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 001010 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 001011 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 001100 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 001101 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 001110 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 001111 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 010000 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 010001 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 010010 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 010011 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 010100 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 010101 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 010110 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 010111 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 011000 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 011001 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 011010 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 011011 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 011100 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 011101 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 011110 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 011111 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC |
| 100000 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 100001 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 100010 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 100011 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 100100 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 100101 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 100110 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 100111 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 101000 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 101001 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 101010 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 101011 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 101100 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 101101 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 101110 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 101111 | BASE + RETRY + SYNC | BASE + RETRY + SYNC | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 110000 | AUTOMATE | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 110001 | AUTOMATE | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 110010 | AUTOMATE | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 110011 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 110100 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 110101 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 110110 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 110111 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 111000 | AUTOMATE | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 111001 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 111010 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 111011 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY / AUTOMATE + BASE + SYNC | AUTOMATE + BASE + RETRY + SYNC |
| 111100 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 111101 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 111110 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |
| 111111 | BASE + RETRY + SYNC | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY | AUTOMATE + BASE + RETRY + SYNC |

## Replay and retained outputs

Run from a checkout containing the unchanged calculator and register:

```bash
python -m revenue.uiowa_rfq_18649_debt_decision_readout.joint_assumptions
python -m revenue.uiowa_rfq_18649_debt_decision_readout.joint_assumptions --json
```

The default command emits this readout. `--json` emits the published result structure; `--output-dir NEW_DIRECTORY` writes both files in a new directory. Failures exit nonzero with a diagnosis. This is the analysis itself, not a test suite or a replacement solver.

The replay validates the exact input blobs, bounds of every narrowing, unchanged non-assumption fields, shared workload consistency, identical feasible-set membership, and the actual calculator's feasible count. It then retains all 256 raw reports in deterministic corner/capacity order for their complete digest. The checked-in JSON projects the named output fields to avoid duplicating the unchanged item prose 256 times.

| Source | Git blob |
|---|---|
| `model.py` | `a36e01416f7f6eebad420e5b7d9705fb22fdd368` |
| `examples/synthetic-register.json` | `856618996c6f5b51a6ee8dc37e518d22074b4439` |

Original 32-hour report: `272a6fa6f3dea674f54bbd3f2dcf5e5ea52da00da79a76c812a0092d7dd506d4`.

Mixed-refinement report: `dd702a283dd442a3da5f8c652c209f95ded13df8ac17e44ea2948c15e878c676`.

Complete ordered 256-report JSON plus LF SHA-256: `22883c27f17da19fc217526e3f03a78e7f817d49e541dad7be9ea2bb5be79d45`.

Projected artifact payload plus LF SHA-256, excluding its own `artifact_sha256` field: `7bc69ed00f9af34dee824495b99e21ad71bfef58ab342716e09408e6038a6cf8`.

[Published machine-readable outputs](joint_assumptions.json). Hashes use sorted-key compact ASCII JSON plus one final LF, except the calculator's original `report_sha256` fields, which retain its own serialization contract.

The original calculator and original decision sweep remain the source of their earlier results. This continuation supplies the previously requested joint-assumption counterexample and finite experiment. It does not establish live institutional validation, universal stability, actual savings or payment.
