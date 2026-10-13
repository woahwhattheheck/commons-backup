# Cloud Muhlnickel Bitcoin miner

This package manufactures a fresh ordinary Bitcoin SHA256d Muhlnickel and connects its published ports to a live Stratum session. The container contains the SHA cone, opposite-direction clock rings, NAND master/slave latches, range termination and sticky result contacts.

Cloud manufacture succeeded in [run 34022449871](https://github.com/woahwhattheheck/commons/actions/runs/34022449871), from factory commit `84f94969d20f5fba0ac1f4ec0f959b9cd80fd8e9`. Its artifact is `cloud-muhlnickel-miner-84f94969d20f5fba0ac1f4ec0f959b9cd80fd8e9` (ID `9985947729`), containing:

- `miner.mno`: the new container's wire bytes and physical `<BQQQ>` gate records.
- `layout.json`: schema `muhl-cloud-miner-layout/v1`, fresh addresses, packing, state banks, ring controls, container SHA-256 and manufacturing results.

**Current runtime status:** live execution requires a compatible cloud Muhlnickel substrate and its I/O driver. These adapters expose `executor_unavailable` until one is supplied. Uploading the artifact establishes storage placement. It does not establish gate propagation, mining progress or payment.

The owner's reported prior `2^78` Muhlnickel result remains accepted context. This new artifact has its own manufacture receipt; the adapters passed 58 protocol and binding checks. Live execution, throughput, accepted blocks and payment require their own actual receipts.

## Place it on the cloud substrate

Use an existing cloud host whose provider permits this mining workload and whose Muhlnickel substrate can execute the manufactured ring/latch mechanism. Run live mining there. **Do not mine on GitHub-hosted Actions or the owner's laptop.** Actions is used here for bounded manufacture.

On that permitted cloud host, retrieve the artifact and use the integrated repository's `muhl/cloud_miner` Python modules:

```sh
gh run download 34022449871 --repo woahwhattheheck/commons \
  --name cloud-muhlnickel-miner-84f94969d20f5fba0ac1f4ec0f959b9cd80fd8e9 \
  --dir /srv/muhlnickel/miner-84f94969
```

Select a new destination. Preserve existing instances and checkpoints. Attach `miner.mno` together with its `layout.json` through the substrate's supported mechanism; the Python adapter needs no third-party packages. A provider-specific driver is still required.

## Bind the real I/O driver

Implement `SubstrateIO` from [runner.py](runner.py) against that substrate:

| Method | Required behavior |
|---|---|
| `manifest()` | Return the actual layout, including `ram[name] = {offset, width, encoding}`, `state_bank` and a stable instance identifier. |
| `write_fields(values)` | Route named bit-byte fields and state spans such as `nonce.master_q` through the substrate. Resolve all addresses from this instance's manifest. |
| `set_enabled(False)` | Disable the rings and wait for actual substrate quiescence before returning. `True` starts the manufactured mechanism. |
| `read_coherent(names)` | Return `CoherentSnapshot(fields, coherent, taken_at, receipt, detail)`. Assert coherence only for an actual atomic substrate capture. |
| `close()` | Release this instance's I/O handle without affecting other instances. |

A sequential series of file reads cannot establish an atomic snapshot. The driver supplies the real execution/observation mechanism; this package supplies no generic gate evaluator.

The adapter loads the 76-byte header as big-endian words emitted in LSB-first bit-bytes, a numeric little-endian target, and an inclusive `nonce_end = end_exclusive - 1`. While disabled, it initializes all four state banks (`nonce`, `winner_nonce`, `win`, `exhausted`) and clears ready contacts.

- Candidate readiness requires `result_ready == 1` and `win == 1`; nonce zero is valid.
- Range completion requires `exhausted_ready == 1` and `exhausted == 1`.
- Progress requires a coherent snapshot with `commit_ready == 1`. Elapsed time creates no coverage claim.

## Run with the bound driver

Call this function on the permitted cloud host with the actual driver object and a durable cloud checkpoint path:

```python
from muhl.cloud_miner.runner import (
    CloudMiner, JsonFileCheckpoint, MuhlnickelExecutor, RunnerStatus,
)
from muhl.cloud_miner.stratum import StratumClient, StratumConfig, SubmitStatus


def run_live(driver, checkpoint_path, stop_event):
    executor = MuhlnickelExecutor(driver)
    available, detail = executor.available()
    if not available:
        raise RuntimeError(detail)

    with StratumClient(StratumConfig()) as client:
        miner = CloudMiner(
            client, executor=executor,
            checkpoint=JsonFileCheckpoint(checkpoint_path),
        )
        try:
            while not stop_event.is_set():
                report = miner.run_once()
                print(report, flush=True)
                uncertain = (
                    report.submit is not None
                    and report.submit.status is SubmitStatus.ERROR
                )
                if report.is_accepted_block_candidate:
                    return report  # pool receipt; confirm network acceptance separately
                if report.status in (
                    RunnerStatus.SESSION_LOST,
                    RunnerStatus.EXECUTOR_UNAVAILABLE,
                    RunnerStatus.CANDIDATE_REJECTED_LOCALLY,
                ):
                    return report
                if report.status is RunnerStatus.ERROR and not uncertain:
                    return report
                # An ambiguous submit keeps the same live session and sticky candidate.
                stop_event.wait(1.0 if uncertain else 0.25)
        finally:
            miner.close()
            driver.close()
```

Default configuration uses `stratum.ckpool.org:3333` and the owner's public receiving address with worker suffix `.muhl`. Configure `StratumConfig` for a different permitted deployment; no private key is involved.

Subscribe, authorize, job retrieval and submission share one TCP session. Every lease binds the session, job generation, extranonce and nonce range. Clean jobs retire old work; reconnects retire the previous session. Checkpoints retain issued ranges and observed frontiers, and never authorize submitting work from a retired session.

A surfaced candidate is checked against the current job and its network `nBits` target before submission. An ambiguous submit retains the candidate for retry/reconciliation while that session remains live. Pool acceptance is recorded as a provider outcome; it is not a payment receipt or independent confirmation that the network accepted a block.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

