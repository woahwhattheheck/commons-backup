# T12: causal public-history market response

**Experimental callable and reusable predictor. Not promoted over frozen SELL.**
See RESULTS.md and games.csv: all20 held response/control pairs are identical,
and two intact development pairs lose four margin units each.

## Interfaces and boundaries

```python
from policy import ResponsePolicy
actor = ResponsePolicy()  # one instance per match
response_action = actor.act(observation, configuration)
control = ResponsePolicy(enabled=False)  # unchanged frozen SELL optimizer
```

`FlowHistory.add(FlowInterval(...))` accepts completed public-observation
intervals. `window_prediction(product, now, end)` returns complete prior
same-phase windows with training timestamps and empirical ranges. `scenarios`
retains sale batches, finite hypothetical stock and relative order uncertainty.
These are conditional hypotheses, not calibrated probabilities.

Live identification and selected-plan confirmation use SORREL's unchanged
adapter. No rival private stock, environment seed, future shop draw or future
action enters the policy. WHEAT/FERTILIZER buy/sell ambiguity is excluded;
floor-censored sale counts are not learned as exact zeros. The policy augments
the completed frozen SELL incumbent, retains its rival stress cases, and calls
the authoritative parent once. Routes, ordered non-SELL slots and the seller's
cash/input/shed constraints remain unchanged. Only this directory is owned.

## Packaging

The official raw-file entrypoint is **main.py**, not policy.py. Raw execution
does not define `__file__`; the lazy entrypoint waits for the loader's first
call and resolves its `__raw_path__`, or normal module `__file__` when imported.

```sh
python -B build.py --output /absolute/cloud/path/t12-response-agent.tar.gz
mkdir /absolute/cloud/path/relocated-agent
tar -xzf /absolute/cloud/path/t12-response-agent.tar.gz -C /absolute/cloud/path/relocated-agent
```

The relocatable archive contains root main.py, runtime dependencies, source
hash manifest and retained licenses. No engine, evaluator, opponent variant,
seed, replay or truth data ships in it. A full isolated719-decision game from
a different directory matched the original final scores.

The sibling `../cloud-titan-composition/vendor/sell/` is required. Its scheduler
SHA256 is32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9.
Other exact sibling hashes are in the source manifests; do not silently update.

## Reproduce

Use Python3.10+ and a C++17 compiler in a Linux cloud runtime. Existing shared
cloud-eval, cloud-pack and offline-loader siblings and their source dependencies
must be available. The official engine is Kaggle/kaggle-environments commit
28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c. Existing source artifact10030763484
and engine artifact10005621438 were reused; no new transport job was launched.

```sh
(cd ../cloud-frontier-policy/next-panel/vendor/apex && \
 g++ -O3 -std=c++17 -Wall -Wextra -pedantic -shared -fPIC -Isource/include \
 -o agent.so source/policy.cpp submission_bridge.cpp)
python -B -m unittest -v test_response.py test_cli.py
python -B engine_cases.py --engine-dir /absolute/cloud/path/engine --output /absolute/cloud/path/market-cases.json
python -B panel.py --seeds 9840001,9840019,9840037 --opponents arlene,apex \
 --engine-dir /absolute/cloud/path/engine --output /absolute/cloud/path/dev-intact
python -B panel.py --seeds 9840001,9840019,9840037 \
 --opponents arlene:sale_cadence,apex:crop_demand,arlene:labor_cadence \
 --engine-dir /absolute/cloud/path/engine --output /absolute/cloud/path/dev-stress
python -B panel.py --freeze RELEASE.json --seeds 9840101,9840119 \
 --opponents arlene,apex,arlene:sale_cadence,apex:crop_demand,arlene:labor_cadence \
 --engine-dir /absolute/cloud/path/engine --output /absolute/cloud/path/held-replication
python -B protocol.py --engine-dir /absolute/cloud/path/engine \
 --expected-dir /absolute/cloud/path/dev-intact --output /absolute/cloud/path/protocol.json
```

Held9840101/9840119 are already consumed; later use is replication, not fresh
holdout. panel.py verifies the listed source hashes before/after execution and
rejects existing result filenames. It does not inventory all unrelated files.

FREEZE.json is the immutable pre-evaluation snapshot from19:59:11UTC on
September7,2026. Its held_started:false describes that moment, not current
status. RELEASE.json records the later harness-only correction: omitted
`--seat` defaults to zero, with valid explicit seats0/1 still checked. Existing
panels pass explicit seats. The frozen model/policy did not change. The full
omitted-seat development replication matches [52754,52429]; three CLI tests
bring release regression coverage to19 passing tests. The open-door guard was
not modified or disabled. No game results were recomputed as fresh holdout.

## Provenance and evidence

SORREL adapter is byte-exact Commons0a1f0ec35e903c4b6052681ecf976705a29ab902,
Apache-2.0. FLOW variants are byte-exact Commons41ea491dd130b206b3402f33e1aff356c837aa99,
evaluation-only; reuse does not establish completion of FLOW's separate panels.
See NOTICE and the preserved dependency licenses. No GPL source was copied.

The repository contains the callable, tests, evaluator, manifests and compact
162-game ledger. Complete original results, v1 source, negative cases and all
719-turn traces are delivered separately as t12-full-evidence.tar.gz, not
misrepresented as committed files. VALIDATION.json records historical check
counts; the three later CLI tests and reproduction are documented above.
Only two held environment seeds were tested; seats/opponents are correlated.
No hosted Kaggle submission, rating, bounty acceptance or payment is claimed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
