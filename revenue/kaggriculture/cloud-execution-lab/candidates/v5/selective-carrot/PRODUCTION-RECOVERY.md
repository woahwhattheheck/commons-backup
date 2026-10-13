# Production recovery experiment

This experimental package combines the exact V3.1 R04 production policy with
the frozen V4 economics and completed-route recovery, plus delivery-timed
cap12 carrot selection. It retains the V4 seller and active helper files. The
13 R04 dependencies are copied byte-for-byte from the submitted V3.1 archive;
the adapter makes one donor policy call per action and exposes its selected
route to the retained economics. No current-main production defaults, release
pointers or Kaggle submissions are changed.

## Exact package and reproduction

The default builder now emits import-safe production **v3**. A fresh Linux
run through the prescribed raw-file loader found that v2 crashes on its first
callback: it imports the shipped `full_production_context` after the loader
has removed the payload directory from `sys.path`, before the baseline callback
can restore that directory. V3 loads that context during entry-file execution.
Only `main.py` changes; the other 91 members, including configuration, remain
byte-identical. `--version v2` still reproduces the original archive.

All input assets and the historical v2 outputs are on the existing public
[gauntlet release](https://github.com/woahwhattheheck/commons/releases/tag/titan-kaggriculture-gauntlet-20260912).
V3 is reproduced by the builder below; no new release asset is required.

| Archive | SHA256 |
|---|---|
| Production v3 builder output | `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239` |
| `titan-v5-production-recovery-v2.tar.gz` | `0aded66a2c393cc60f4f45d10f11c384a7e788182bf5430863829a02b66daf02` |
| `titan-v4-route-recovery-delivery-carrot-v2.tar.gz` | `0d42ee5fabb089745fa0064207654bfdf5df9466ba6499d91b6e685d4880cab1` |
| Exact V3.1 `titan-v3.1-56172377-5db3921f.tar.gz` | `5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361` |

From this directory, using downloaded authenticated archives:

```bash
python -B test_production_recovery.py --v31 /path/to/titan-v3.1-56172377-5db3921f.tar.gz --delivery /path/to/titan-v4-route-recovery-delivery-carrot-v2.tar.gz
python -O -B test_production_recovery.py --v31 /path/to/titan-v3.1-56172377-5db3921f.tar.gz --delivery /path/to/titan-v4-route-recovery-delivery-carrot-v2.tar.gz
python -B build_production_recovery.py --v31 /path/to/titan-v3.1-56172377-5db3921f.tar.gz \
  --delivery /path/to/titan-v4-route-recovery-delivery-carrot-v2.tar.gz \
  --out /new/path/production --tar /new/path/production.tar.gz
```

The builder reproduces the exact 92-member archive. It checks both inputs,
the full 13-file dependency closure, unchanged retained payload members and
the final archive hash. `PRODUCTION-PACKAGE-MANIFEST.json` records every output
member hash for historical v2; `PRODUCTION-V3-PACKAGE-MANIFEST.json` records v3.
The existing `build_delivery.py` reproduces its delivery v2 input
from exact cap12 and route-recovery archives; see `DELIVERY.md`.

The source configuration is grounded in exact V3.1 `TITAN-CONFIG.json`:
`r04_sale_window` is true, and `TitanAgent.act` delegates to `_v3_r03_act` at
that branch. The adapter installs the same R04 policy options. Tests compare
every installed option against that actual configuration and cover route
identity, one donor call, configuration forwarding, immutable input
observations, and present/null/absent step for both seats.

Both v2 entry points normalize `step` before policy and delivery receipt
callbacks. When step is absent or null, they derive it from day/hour and
configured `turnsPerDay`, then pass the same copied observation to both.

## Observed development screen

`PRODUCTION-SCREEN.json` contains 13 distinct paired cells with exact tested
archive identities: nine use production v1 (`35a4528c...`) and four directly
use v2 (`0aded66a...`). Across Arlene, Kaito and Igor, all 13 margins improve
over exact V3.1; 12 improve over exact V4. Mean paired deltas are +4275.15
versus V3.1 and +7801 versus V4. The weakest V3.1 delta is +123; Kaito seed9601
seat1 is -406 versus V4. Keep this negative cell in the comparison.

These are local development games with timing guards disabled. Arlene's
five-seed portion covers seat0 only; paired seeds and seats are correlated.
This is neither a native deadline result nor a hosted rating estimate.

`PRODUCTION-CALLBACK-BRIDGE.json` separately records four full 719-action
checks. Three production v2 streams (absent step seat0; null step seat1 with
controlled cancellation227; null step seat0 with controlled cancellation510)
match the clean production v1 reference action hash exactly. Delivery v2 with
absent step seat1 matches its clean v1 stream. That is 2876 matching decisions
under the specified observation/cancellation treatments. It supplies a
specific callback bridge between versions, without relabeling the nine v1
screen cells as direct v2 measurements or attributing hosted losses to timeouts.

## Native fleet demand

The earlier SPARK assignment used production v2, 12 games: seeds
2051966578,1209125501,1209125502 against Apex_v7 and Arlene_v14, both seats.
Reuse all exact-matching V4/V3.1 controls from the delivery panel, including
engine, opponent, seed, seat, RNG and timing limits. Preserve running delivery
games and all eight top30 shards. If no delivery process has started, the
leading production arm takes the next slot. Kaito/Igor9601/9602 local cells
are already recorded and are not part of this native demand.

Use the existing generic evaluator and `pack.write_adapter` setup in
`DELIVERY.md`, substituting a `production` payload/adapter and report path.
Do not create an evaluator. The generic evaluator runs both seats automatically:

```bash
python "$KG/cloud-execution-lab/reference/evaluator/evaluate.py" \
  --engine-dir "$ENGINE" --loader "$KG/20260907-offline-agent/evaluate.py" \
  --candidate "$RUN/production-adapter.py::agent" \
  --opponent "apex_v7=$RUN/opponents/apex_v7/adapter.py::agent" \
  --opponent "arlene_v14=$RUN/opponents/arlene_v14/adapter.py::agent" \
  --seeds 2051966578,1209125501,1209125502 --rng-seed 20260912 \
  --action-timeout 1.25 --startup-timeout 10 --game-timeout 900 \
  --output "$RUN/production-report.json"
```

Preserve any existing process and its actual archive identity. New unstarted
production runs should use v3; do not relabel an existing v2 result or restart
completed controls. Post PID/workspace and exact identity before results.

## Fresh native result: seed 1209129901

The separate bounded sample in [native-9901/README.md](native-9901/README.md)
completed 20 games with native timers enabled: exact V3.1, exact V4, production
v3, town-off and aggregate postprocessor bypass, against Apex and Arlene in both
seats. All eight control games were reused across the candidate treatments.
The original v2's four step-zero import failures are retained alongside them.

| Opponent | V3.1 margin | V4 margin | V5 production v3 margin |
|---|---:|---:|---:|
| Apex v7 | 9810 | 8062 | 10068 |
| Arlene v14 | 5600 | 1446 | 5820 |

Each row has identical mirrored terminal scores in both seats. Production v3
gains +258 and +220 margin over V3.1, but Apex own-score is 237 lower. Arlene
own-score is 332 higher. Town-off loses another 2/1 score; aggregate bypass
returns exactly to V3.1 terminal scores. Retain the full production composition
for wider development. These results do not select either treatment.

V3's maximum callback time is 0.252 seconds, below the configured inner
deadline; all four games complete 719 decisions without external failures.
This one-seed sample is correlated development evidence, not champion
clearance or a hosted rating estimate. The Apex own-score gap remains a
concrete blocker to the strict V3.1 own-score condition. The Kaggle submission
hold remains in force.
