# Retained-state intake

`reached_states.py` makes the existing lossless T05 × SELL archive usable as independent policy-input files. It does not run an agent, engine, or game. Source is additive; the frozen policy, original reports and source hashes stay unchanged.

## Source and execution

Use the existing private `osprey-terminal-sell-raw.json.xz` archive. Its compressed SHA-256 is `a85fdedc100b54d9e853c0db43c6609fece99e93497a49d01df91fdcc12948f4`. The filename-to-original-JSON-text format is documented in RESULTS.md. The actual file is available in the account Library; it is not a missing GitHub path. Keep that payload and generated cases out of public repository documentation.

```sh
python reached_states.py /path/to/osprey-terminal-sell-raw.json.xz /tmp/osprey-dev-cases
python reached_states.py /path/to/osprey-terminal-sell-raw.json.xz /tmp/osprey-terminal-cases --arm composed --step 718
python reached_states.py /path/to/osprey-terminal-sell-raw.json.xz /tmp/osprey-pressure-cases --only-pressure
OSPREY_RAW_ARCHIVE=/path/to/osprey-terminal-sell-raw.json.xz python -m unittest -v test_reached_states.py
```

Run from this directory. Use a fresh output directory. Without the environment variable, 24 synthetic/CLI regression tests run and the retained-archive test is explicitly skipped; with the supplied archive all 25 pass. No optional package is required.

`read_archive(path)` checks the compressed pin, bounds decoded size and retains original member text. `collect(records, phase='dev', arms=None, step=None, only_pressure=False)` returns deduplicated cases and separate evaluation records. `export(records, destination, **selection)` writes the files.

## Consumer contract

Only `inputs/*.json` belongs in an actor process. Each file contains `observation` and `configuration`, with this seat's delivered private inventory preserved. Recorded actions, terminal scores/state, evaluator seed and local source path are excluded. This reader supports the pinned archive's documented observation/configuration fields, not arbitrary future environment schemas.

`index.json` carries source-file hashes, source seed/arm/opponent/seat/step, input hashes and current inventory metrics. `evaluation-only.json` carries final outcomes separately. Neither file belongs in the actor's runtime input. A standalone observed frame does not recreate a stateful controller's prior history: use it for stateless transforms or supply the independently retained controller state.

Default extraction uses only development. `--phase held` is explicit and labels those records **previously consumed held**, not fresh validation. Every requested step must exist in every matching source record. The retained window is 696–718; requesting 360 fails rather than inventing a checkpoint from seed or outcome.

Repeated exact inputs share one input file but keep all original references. These counts are neither new games nor independent sample counts. In the development archive, 736 frame references from 32 old games reduce to 376 exact input payloads; they originate from only two independent development seeds.

## Inventory metrics

`total_inventory_excess` compares shed plus all carried inventory with shed capacity. `ready_excess` includes only workers currently standing on one of the four shed access tiles. It is potential current deposit pressure, not a claim that the selected action deposits those goods. Goods still traveling, future arrivals, production and later sale schedules require their own execution model.

Actual development intake: 28 frame references have total inventory above capacity (maximum excess 6), but none has ready-to-deposit load exceeding current shed room. Accordingly `--only-pressure` returns zero cases for this bank. This limited observation does not imply that other trajectories or future steps lack admission constraints.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
