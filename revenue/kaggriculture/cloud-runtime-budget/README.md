# Saved-observation runtime budget

`profile_saved.py` measures the actual selected entrypoint in fresh Python processes without advancing an engine. It consumes TANDEM's existing `cloud-combination-analysis/execution_timing.py`; no replacement timing observer, game runner, policy, optimizer or timeout mechanism is introduced.

The ordinary pass measures every action. The second process rebuilds the actor from the same uninterrupted observation prefix and profiles only the first, final and five slowest ordinary-pass steps. Every output action is hashed in both passes. Successful correspondence requires identical action sequences, input identities, runtime source hashes and successful process exits. Policy-body exceptions are never retried. Factory errors, action failures and process timeouts remain explicit; existing result files are not overwritten or accepted as a new result.

## Use

Extract the already-published PR9997 archive from existing artifact **10036877991**; its SHA-256 is `95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153`. The source manifest in that archive remains authoritative. The reference public workload is episode106540665 from existing artifact **10031480684**; its original decoder recovers the exact raw response, SHA-256 `410e9dc42ffabd02118a5782bc077156f952a094ad2669f64ce85941fd5bd94a`. Neither artifact is rebuilt or fetched from Kaggle by this utility.

```sh
D=revenue/kaggriculture/cloud-runtime-budget
T=revenue/kaggriculture/cloud-combination-analysis/execution_timing.py
python -B "$D/profile_saved.py" \
  --entrypoint /existing/extracted/integrated_main.py \
  --timing-source "$T" --replay /existing/106540665.raw --seat 0 \
  --max-decisions 719 --process-timeout 180 \
  --classification retained-public-off-policy --output /new/profile-result.json
python -B -m unittest discover -s "$D" -p 'test_profile_saved.py' -v
```

The default factory is `make_agent()` and method is `act`. `--factory Agent` supports the unchanged Arlene source; `--method __call__` accepts a callable factory result. The selected signature is bound before execution. Tests normally use the repository's existing timing utility; `TITAN_TIMING_SOURCE` selects an already-materialized copy in an isolated source cache.

A normalized workload is a JSON object with schema `titan.profile.observations.v1`, `configuration`, `provenance`, and `records`. Each record contains a complete `observation` and optionally an `expected_action`. The actor is rebuilt from the uninterrupted step0 prefix for the selected player; summaries alone do not contain those inputs. Configuration seed is omitted from agent delivery. Shared public fields may come from the companion replay row, while private inventory comes only from the selected player. Expected-action mismatch is reported independently from instrumentation parity.

Native TRACE JSONL and its execution receipt can be consumed directly with `--input-receipt`; see [TRACE-INPUTS.md](TRACE-INPUTS.md) for actor seeds, per-row configuration, factory keyword arguments and sibling-source coverage. The original measurements below remain bound to PR10052, not this later input adaptation.

## Executed result

`RESULTS.json` records the exact source, inputs, environment, raw report hashes and measurements. Sixteen new contract methods passed. The intact Arlene source also completed both 719-call passes with action correspondence. The actual archived PR9997 integrated candidate completed 719 ordinary plus719 sampled-profile calls in independent processes, with identical sequence hash `bcc596cb183ca8c363f1b45c9bdc0c9aad351cd4a02f7ea716d1001e48bcc2ae`. All17 Python source files were unchanged. This is an **off-policy workload on a retained public observation stream**, not a replayed game, rating result or recovered on-policy development checkpoint.

On this container, target loading through the first attempted action took **39.36ms**; ordinary p99 was **18.83ms**, and the outer action maximum was **25.17ms**. No ordinary call exceeded one second. The container reported a4-CPU cgroup allowance and4GiB memory limit, not Kaggle-equivalent hardware. Peak process RSS includes the entire loaded replay and harness. Fresh-process module loading is measured, not a flushed filesystem cache. Process start-to-exit includes input parsing, hashing, all calls, serialization and shutdown, and must not be mislabeled cold first-action latency.

The seven sampled steps are0,467,468,470,471,697,718. Cumulative instrumented producer time is120.8ms and integrated transform215.9ms; the latter includes projection77.3ms and seller89.8ms. These nested cumulative costs overlap and are not independent maxima to add. The profile uses original archive source; later WREN, SPRUCE, BROOK and funded-seed variants were not silently substituted. No performance patch follows from this single workload.

Two initial full-stream instrumentation attempts were interrupted by the surrounding execution harness. Their completed ordinary receipts are retained separately; no successful full profile is claimed for them. The bounded-sampling method subsequently completed with719-action correspondence. Raw reports, the original interrupted-attempt receipts, test log and source are retained in the companion Library delivery **TITAN_FINCH_runtime_profile_20260907.zip**; each report hash is in `RESULTS.json`.

## Next consumer and limits

T08 can run this exact command over TRACE's eventual verified development prefix, optionally carrying recorded candidate actions. Observation reconstruction and actor-state rebuilding are separate: the profiler executes the entire prefix to rebuild the supplied actor and checks expected actions where provided. It does not invent a missing checkpoint. ECON-STRESS's accepted game/deadline evidence remains its own result and was not rerun.

The one-second threshold is descriptive, not a hosted timeout verdict: official overage and execution-environment rules remain separate. No T14 continuation-scorer composition, new game, held seed, Kaggle request, provider write, owner-PC work, new workflow or source export is part of this delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
