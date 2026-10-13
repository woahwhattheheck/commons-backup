# Frozen-seller recovery after an exact deadline fallback

This directory is an additive, source-bound discriminator for the canonical TITAN builder. It changes no production runtime, default, archive, timer, policy or game result.

## Result

At canonical source checkpoint `4cf8f678507574afb0d8a1a0f24056e55bb168ab`, the nine exercised default-path blobs match their recorded Git and SHA-256 identities in `CURRENT-SOURCE-PINS.json`. The retained input is the complete 719-observation own-state sequence from DELVE development `9965001`, seat 0. It is a recorded workload, **not a new game** and not on-policy evidence for this newer source.

A controlled expiry at `TitanAgent.transform_selected` entry on step 450 returns exactly the uninterrupted selected action. Both actors retain the same route for all 719 calls, and each makes one original producer call per input. Recovery nevertheless reconstructs a fresh frozen seller without the completed seller plan/history:

- step 451: uninterrupted `SELL STRAWBERRY 10`; recovered action has no sale;
- step 453: uninterrupted `SELL MILK 3`; recovered action has no sale.

The full baseline report records 268 later seller-state differences. No engine transition or opponent response is executed by this checker.

## Causal controls

A bounded intervention restores only `planned`, `pending`, `previous`, and `observed_harvests` from the completed checkpoint, then calls the **original public observer once** on the skipped step-450 own observation. On the same exact source, all actions and compared seller-state digests match through step 460.

That is not a generic runtime patch. A separate step-447 control retains the older completed checkpoint while the cancelled call would have replanned MILK from step 449 to 453. Restoring the older checkpoint cannot recreate that unreturned computation; differences remain at 449 and 453. Production must distinguish completed output-associated state from interrupted mutations.

## Reproduce

Materialize the Library package identified in `LIBRARY-EVIDENCE.json`, extract it, and run from the extracted `evidence/` directory:

```bash
python -B check_seller_recovery.py --report /tmp/seller-recovery.json --require-continuity
# Expected nonzero: the source-bound discontinuity is the test result.

python -B check_seller_recovery.py --through 460 \
  --restore-fields planned,pending,previous,observed_harvests --observe-skipped \
  --report /tmp/seller-rehydrated.json --require-continuity
# Expected zero for this bounded intervention.
```

To run the checked-in checker against a later source, pass `--runtime`, `--pins`, `--input`, and `--receipt` explicitly. It verifies every source and input digest before actor construction, refuses bytecode caches in the tested source tree, invokes the actual timer sentinel at the selected boundary, and compares complete actions and seller-state digests. The report path must not already exist.

The compact repository contract can be checked without actor execution:

```bash
python -B revenue/kaggriculture/cloud-execution-lab/seller-recovery/test_seller_recovery_evidence.py -v
```

## Evidence classification

The Library package contains `baseline-entry450.json.gz`, `rehydrated-entry450-through460.json.gz`, and `negative-replan447-through460.json.gz` with the complete source-bound records. `CURRENT-RESULTS.json` is the checked-in compact index; `LIBRARY-EVIDENCE.json` pins the durable full package. The input contains only the acting seat's recorded observation/configuration; expected actions and original outcomes are never passed to either actor.

This result does not establish economic loss, a naturally occurring timeout, a general state-serialization interface, or a safe blind restore. The single canonical builder owns any production implementation and archive advance.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
