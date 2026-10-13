# Completed seller-state recovery discriminator

This directory provides a source-pinned acceptance case for TITAN’s cancellation recovery. It changes no production policy, runtime, current archive, game result, seed allocation, or submission.

## Result

The exercised subject is the default frozen TITAN path at source `c7627b63419240e377a96fd26ee5c3933334b6eb`, with `TitanAgent` blob `c12fe0d3e13cac76c23521ace61d8771669e57ed`. The checker drives the same retained **own observations and configurations** through two real agents. It never supplies the historical expected actions, original outcomes, rival private state, or current rival action to either actor.

At step 450, a controlled instance of the subject timer’s own cancellation sentinel is raised after the producer returned a complete action. The affected actor returns exactly the uninterrupted action. Its selected route also remains identical. After the required fresh initialization, two later market actions differ:

| Step | Uninterrupted action | Recovered action |
|---|---|---|
| 451 | `SELL STRAWBERRY 10` | inherited empty order slot |
| 453 | `SELL MILK 3` | empty market queue |

The completed seller checkpoint already contains the milk tranche due at 453 and public harvest history. Fresh initialization restores the completed route, but creates a new seller with empty `planned`, `pending`, `previous`, and `observed_harvests` state.

This is an **identical-fallback continuity failure**, not a naturally observed timeout or game result. The fresh publication run compares 454 calls per actor through step 453, counts one original producer call per actor input, and records no engine-interpreter call or new game.

## Safe and unsafe boundaries

A diagnostic intervention that restores the four completed seller fields and advances the original observer once on the skipped public observation removes the step-451 and step-453 differences on this retained prefix. It is not proposed as a general production patch.

The negative control at step 447 is load-bearing: the uninterrupted seller would replan milk from step 449 to step 453 during the cancelled transform. Restoring the earlier completed checkpoint cannot recreate that computation, so actions still differ at 449 and 453. Recovery must preserve **completed** intent and public-observation history without committing an interrupted or unreturned plan.

## Current-source relationship

PR10335 later added worker-thread deadline support while retaining the same `TitanAgent` core blob. This evidence remains explicitly bound to the nine source files in `SOURCE-PINS.json`, including the earlier main-thread deadline adapter. Before adopting a production recovery change, run this checker against the exact newer runtime and a new pin document. Do not transfer the historical result merely because the core file is unchanged.

## Reproduce

Materialize the full evidence ZIP from ChatGPT Library, then run the checker against its exact bundled runtime and retained input. The readable `SOURCE-PINS.json` and input receipt in this directory bind those bytes.

```sh
EVIDENCE=/path/to/TITAN-seller-recovery-discriminator-20260908.zip
rm -rf /tmp/titan-seller-state-evidence
mkdir -p /tmp/titan-seller-state-evidence
unzip -q "$EVIDENCE" -d /tmp/titan-seller-state-evidence
COMMON="--runtime /tmp/titan-seller-state-evidence/runtime --pins SOURCE-PINS.json --input /tmp/titan-seller-state-evidence/inputs/candidate-inputs.jsonl.gz --receipt inputs/ORIGINAL-INPUT-RECEIPT.json"

# Expected exit 1: identical fallback, later differences at 451 and 453.
python -B source/check_seller_recovery.py $COMMON \
  --through 453 \
  --report /tmp/seller-recovery.json \
  --require-continuity

# Diagnostic intervention only. Expected exit 0 on this retained prefix.
python -B source/check_seller_recovery.py $COMMON \
  --through 453 \
  --restore-fields planned,pending,previous,observed_harvests \
  --observe-skipped \
  --report /tmp/seller-recovery-rehydrated.json \
  --require-continuity

# Negative control: completed state cannot recreate cancelled replanning.
# Expected exit 1, with later differences at 449 and 453.
python -B source/check_seller_recovery.py $COMMON \
  --step 447 --through 453 \
  --restore-fields planned,pending,previous,observed_harvests \
  --observe-skipped \
  --report /tmp/seller-recovery-negative.json \
  --require-continuity

# Executes all three comparisons and validates claims/source/input identity.
TITAN_SELLER_RECOVERY_EVIDENCE="$EVIDENCE" \
  python -B source/test_seller_recovery.py
```

`SELLER-STATE-RESULTS.json` records the fresh publication checks and exact hashes. `VALIDATION.log` is the five-method executable acceptance result. The full 719-input boundary variants, field-isolation experiments, original attempts, and fourteen independent report checks are in Library file `file_000000006fc8820cacdf9f848121b1c0`, SHA-256 `5acd44985ebc64a8d739cc85eba6102d86695b7962f67b860a50778b3ad6ebc6`.

## Limits

- One retained historical observation sequence is reused under controlled treatments; it is not an on-policy current-source game.
- No cash, score, win-rate, hosted-deadline, or leaderboard effect is inferred.
- The checker intentionally injects cancellation at named Python source boundaries.
- The field-restoration modes are causal probes, not recovery code.
- A newer runtime must receive its own source pins and execution result.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
