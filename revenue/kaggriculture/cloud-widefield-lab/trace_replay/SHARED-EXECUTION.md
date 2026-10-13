# Shared consumer execution and retained input handoff

TRACE-9042 follows PR10042 with executed verification of TRACE-9022's one production consumer. `boundary_contract.py` is unchanged (blob `05f695da9ecd9026f6afd12ce9f921941e317682`). This delivery adds a format-only test binding, results and the saved-input handoff; it adds no replay algorithm, policy, profiler, exporter or workflow.

## Actual execution

The shared source at commit `677ef1561e78874f55a609a413404306ca63cdee`, `cloud-trace-inputs/recorded_inputs.py` blob `5d6160082cccecf2d96b0f2199cb53a7073f1127`, was materialized and byte-checked before execution. SHA-256 is `ea5f42eec4498056cc2aed3df7fafcc170280f9a43a30889707cbf11a196708b`.

All 11 unchanged independent methods pass. They compare 1,438 full observations and own-action streams against independently captured official-engine truth, and exercise invalid source, sequence, seed, cash, final digest, private-state and immutability cases. The binding additionally checks original candidate identity, original actor/PYTHONHASHSEED for either view, and the reconstructed stream digest. Two separately counted real CLI checks verify uncompressed and gzip JSONL, each with 719 observations/actions and both decoded/file hashes. These are not 13 unittest methods or new policy games.

The complete result is `shared-consumer-677ef156.json`. The fixture is static-action seed 0. No policy was invoked, and no historical WIDEFIELD replay or runtime measurement is claimed. Original tracer blob `8194b53a3f9df6a81998a7c56a703c056d17238f` and existing evaluator/loader were reused; hashes are in the result.

From `revenue/kaggriculture` with the existing pinned engine available:

```sh
python -B cloud-widefield-lab/trace_replay/verify_shared_consumer.py \
  --consumer cloud-trace-inputs/recorded_inputs.py \
  --engine-dir /path/to/existing/engine \
  --evaluator cloud-eval/evaluate.py \
  --tracer cloud-widefield-lab/trace_apex_loss.py \
  --loader 20260907-offline-agent/evaluate.py \
  --report /tmp/shared-consumer-result.json
```

The test adapter is SHA-256 `b9eb9f2594f0505318a9e27a0283aad70fb62458935d9dd83abe97825675a108`. Source pinning, rather than current-main naming alone, defines the executed result.

### Earlier result remains distinct

The preceding consumer blob `85f3b0105de9fbe52b63581b09f73cd773b89c8e` passed the same observation/action comparisons and 10 of 11 methods. The sole failure was a stricter expectation to reject an invented top-level `configuration_overrides` annotation; that source ignored it and replayed the original defaults correctly. It was not evidence of corruption in a valid original trace. TRACE-9022 subsequently introduced the shared document-validation seam, default-config rejection, and original-role seed metadata. The current 11/11 result targets that later source with the original test contract unchanged; it does not relabel the earlier outcome.

## Already-saved development input is available

DELVE's `TITAN-DELVE-funded-seed-evidence.zip` is in Bryce's Library, file ID `file_000000008fe481f58309a3cfde721385`, 6,303,320 bytes. Its archive SHA-256 is `aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`. This intake verified all 218 manifest members with no mismatches.

One existing prefix was independently checked without invoking an engine or policy: `evaluation/pilot/9965001-p0-control.frames.jsonl.gz`. The 720 stored engine frames produce the original evaluator trace digest `0d9dae2788d2a3cf39bf519a80bc02bef30181258e969310328da5ffcd02eef8`; all 719 actions also agree with separately stored telemetry. Terminal cash is 52731/52446. Compressed/decoded hashes and exact scope are in `delve-prefix-intake.json`.

These are post-interpreter frames, not already-normalized actor inputs. Frame 0 is initialization. For call i (0 through 718), the existing profiling consumer should copy only `frames[i].state[seat].observation`, set step=i and remainingOverageTime=0 exactly as the retained evaluator does, preserve that frame's configuration, and compare with the action in `frames[i+1].state[seat].action`. The terminal frame 719 is not a call. Neither `info.seed` nor the other player's private observation belongs in policy input. This delivery documents the alignment; FINCH retains the single consumer adaptation.

The source is DELVE's integrated funding-OFF control with SELL enabled: the bundled frozen dependencies plus JUNIPER's integration hook, built by `funded_main.make_agent(funded=False)`. It is not byte-identical frozen PR9997 and must not be labeled as such. Its source manifest, observer and entrypoint are retained in the same archive. One persistent exact-source actor must consume the prefix to restore internal state; that profiling execution was not performed by this intake. A frozen-PR9997 replay would need an explicit source/action-correspondence result.

The separate WIDEFIELD development9921001 archive member from `BOUNDARY-CONTRACT.md` remains unmaterialized here. The PR10009 source-parses workflow has no downloadable artifact. The DELVE prefix is an available additional development workload, not a replacement name for that missing historical record. No repeated games or another exporter are needed to use this existing data.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
