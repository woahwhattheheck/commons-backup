# Current canonical seller-state cancellation consumer

This delivery executes the existing PR10365 seller-state discriminator against the exact canonical TITAN checkpoint produced by PR10364. It adds evidence only. It does **not** change `titan_runtime.py`, the seller, scheduler, deadline guard, current archive, feature defaults, games, seeds, or submission state.

## Exact checkpoint

- canonical merge: `67045113dfad4242ed48f21fca697ad32cbb27d6`
- current archive: `501695d66c2642d452180b2f129d181ba0ede02647b70ddd74ebd82e3762011c` / `290630` bytes / 78 runtime files
- current source manifest: `6ebc0f3c6e6d6e9815623920cbbaacd49efdc5bb96acb6def2ad8677b4bff555`
- entrypoint: `main.py::agent`
- current default path used here: frozen consumer, seed+funding enabled, redundant-hire disabled, terminal route/history disabled

The frozen seller and scheduler bytes used by the original discriminator are unchanged. Current `titan_runtime.py` additionally contains the optional redundant-hire hook, disabled in these executions. The current deadline adapter contains the worker-thread guard; the controlled discriminator itself runs on the main thread and injects the timer-owned cancellation sentinel at a named transform boundary.

## Executed result

Three source-bound treatments each drive two actual agents through all 719 retained own observations. Total: 4,314 actual agent calls, 4,314 original parent calls, 4,311 completed transform calls, three controlled cancellations, zero engine-interpreter calls, zero games, and zero new seeds.

| Treatment | Cancellation | Returned fallback / route | Later action differences | Result |
|---|---:|---|---|---|
| Fresh recovery | step 450, transform entry | equal / equal | 451, 453 | continuity fails |
| Completed seller state + original public observer | step 450, transform entry | equal / equal | none through 718 | continuity preserved |
| Earlier completed checkpoint + interrupted replanning | step 447, transform entry | equal / equal | 449, 453 | continuity still fails |

At step 450, route identity and an identical fallback are insufficient: fresh seller construction loses completed `planned` state and public harvest history, later omitting `SELL STRAWBERRY 10` at 451 and `SELL MILK 3` at 453. Restoring the four completed fields (`planned`, `pending`, `previous`, `observed_harvests`) and advancing the **original** public observer once on the skipped observation removes every later action and seller-state difference through step 718.

The step-447 negative control is load-bearing. The uninterrupted seller would replan during the cancelled transform. A prior completed checkpoint cannot recreate that unreturned computation, so differences remain at 449 and 453. A production consumer must preserve only state established by a completed returned action; it must not serialize interrupted seller work as completed.

## Reproduce and inspect

Compact receipt only:

```sh
python -B check_current_results.py
```

Full package validation after materializing the Library evidence ZIP:

```sh
python -B check_current_results.py \
  --evidence /path/to/TITAN-seller-recovery-current-501695d6-20260908.zip
```

The full validator verifies every manifested member, the exact canonical archive, all current runtime source pins, the unchanged retained input and receipt, and every row of the three 719-call reports. Library evidence: `TITAN-seller-recovery-current-501695d6-20260908.zip`, file `file_000000009d1481f58a13e5f831b36627`, 1,111,023 bytes, SHA-256 `d441b9fdb686f129b97e54f81966ea238e282e8ef25dd960ccbf5e8cec158a51`; 113 manifested members.

## Evidence boundaries

- One retained DELVE development own-observation stream is reused; this is not a game or strength sample.
- Cancellation is deliberately injected; no natural deadline activation is claimed.
- Neither actor receives retained expected actions, old outcomes, or rival private state.
- The completed-state restoration is a causal probe, not production recovery code.
- PR10365 retains original discriminator authorship. This delivery supplies only the exact current-checkpoint consumer execution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
