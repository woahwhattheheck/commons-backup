# T07 portable public opponent bank

Two frozen public source revisions, not three independent opponent families:

- `lonespear/kaggriculture@774b26093ccf4246525517d48420349b841b6e50`, `main_v18.py`, MIT. Source SHA256 `eb5b5f59a8ec2d40b77cc99d4ffe3b932136fdcf9f6b6e168726b7f07ab47cb0`.
- `COK-ZhangZiliang/Kaggriculture@7ef67eac458cd9ecd13786063e2e581fbe7403ec`, `main.py`, Apache-2.0 with its unchanged `THIRD_PARTY_NOTICES.md` and license copies. Source SHA256 `56831f3c43c9727d90016b7a7a8d4eb51d1a4c08c1120d58f061d9176e8bc109`.

The source files are not patched. The COK notice distinguishes its new work from older route-table provenance; retain that notice rather than widening its license claim. Commons adapter additions in this directory are Apache-2.0; the preserved loader retains its own bundled license scopes.

## Obtain and launch offline

Reuse the existing GitHub connector artifact road in `woahwhattheheck/commons`:

1. New source artifact **10032525998**, run **34160817137**. ZIP SHA256 `6601d709ffa3cd17d994228869ba770a7189bb9b69467cca07ff40e8e6023da5`. Extract it to `sources/`. It contains both policies, four license/notice files, and `SOURCES.json`; intake never imports either policy. Retention is 30 days. The immutable public URLs and hashes are also recorded in that manifest and `intake.py`.
2. Existing source-loader artifact **10030763484**, ZIP SHA256 `68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`, contains the published `cloud-pack` closure. Keep its repository-relative paths when extracting `titan-reusable-sources.tar`.
3. Existing engine artifact **10005621438**, ZIP SHA256 `06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`, supplies the unchanged `engine/` cache for tests. No replacement export is needed.

From this directory, with `PACK` pointing to that extracted `cloud-pack` directory:

```sh
python intake.py verify sources
python bank.py --sources sources --pack "$PACK" --output bank
```

This creates `bank/lonespear-v18-greedy.py` and `bank/cok-v10.py`, all source/license/loader dependencies, and a per-file `BANK.json`. Copy the whole bank directory; the generated entrypoints are relative-path portable. Their interface is `agent(observation, configuration=None)`. They use the preserved official last-callable/argument-slicing loader. Cold first-call timing includes policy initialization.

For an existing SciPy environment, add `--include-scipy` to prepare an additional `bank/lonespear-v18-scipy.py`. Preparation records the actual NumPy and SciPy versions. Launch verifies those versions and the policy's actual `_HUNGARIAN` branch; it does not silently fall back to a different opponent. Our smoke used NumPy **2.3.5**, SciPy **1.17.0**, Python **3.13.5**. The explicit greedy entry exercises the source's original optional-import fallback and restores the import function even on an exception. Do not count the two assignment modes as independent source lineages.

Keep one adapter module or `bank.make_agent(bank_root, entry_name)` instance per actor and per match. Never reuse an instance across players or games. The existing `cloud-eval` worker does this automatically.

## Actual compatibility smoke

`SMOKE.json` records all 12 completed games: development seed **9771001**, both player positions against intact Arlene and Apex, 719 decisions each, **zero load/action failures**. The source/launch snapshot was frozen before execution: BANK.json SHA256 `9cdd5d854956faaa86351c759d630018f76632e39cf1d73bbdd0c174d601bb06`.

All 12 games were losses for these public entries on this one development seed. This verifies a usable broad-opponent input, not competitive superiority, a held-out result, an activated COK gate, or a leaderboard rating. Preserve the losses and distinct behavior rather than selecting from this smoke. No Barnyard panels were repeated and no hidden evaluation seeds were consumed.

Maximum measured action, including cold initialization: lonespear greedy **0.019871 s**; lonespear SciPy **0.297177 s**; COK **0.054815 s**. Greedy and SciPy produced different cash, so dependency choice is material. Game limits and evaluator source were unchanged.

Reproduction uses existing `cloud-eval/evaluate.py`, the exact engine cache, and the existing `cloud-pack/pack.py::write_adapter` controls. Apex is compiled beforehand with the existing C++17 command in `next-panel/prepare.py`; do not run that historical preparation main recipe, which expects other exports.

```sh
python "$EVALUATOR" --engine-dir "$ENGINE" \
  --candidate bank/lonespear-v18-greedy.py \
  --opponent "arlene=$ARLENE_ADAPTER" --opponent "apex=$APEX_ADAPTER" \
  --seeds 9771001 --output lonespear-v18-greedy.json
```

Repeat with `cok-v10.py` and the explicitly prepared SciPy entry to reproduce this spent development smoke, not as a new held panel. `SMOKE.json` retains source pins, raw-report SHA256s, terminal scores, failures, timing, and evaluator trace digests. The trace digests are not full transition traces.

Eight focused tests use the actual preserved official loader: fresh-instance state, persistent state, one-argument slicing, last-callable selection, real greedy import fallback, assignment mismatch, import restoration on failure, and source drift, plus byte/hash cases. Run `python -m unittest discover -s . -p 'test_bank.py' -v`; outside the normal repository layout set `T07_PACK` to the real cloud-pack directory. Hosted status is reported separately from local tests.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
