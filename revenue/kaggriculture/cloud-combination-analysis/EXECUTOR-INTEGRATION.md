# Existing executor timing integration

`cloud-model-lab/execute_arm.py` now consumes the unchanged `TimedFactory` from PR9999 directly. Every returned game row has `executor_timing`: a measurement of the existing per-match factory and that actor's action attempts, or null when execution failed before that factory was attempted. Initialization, first action, initialization plus that same first action, maximum action and maximum later action remain distinct. Constructor and action errors reach the existing failure recorder. This is in-process timing with existing caches, not fresh-process cold start or a hosted deadline measurement. Existing worst_action_s, game loop, source selection and completed results retain their meanings; the small observer overhead is included in the outer action timer.

The shared opponent resolver also receives the single-invocation repair delivered separately to main by PR10013. Its Claude-specific public-bank registry stays intact. CALLABLE's PR9998 candidate-side binding is unchanged. No policy or opponent implementation is rewritten and no ongoing process is restarted.

## Validation

Python 3.13.5, connected cloud container. The complete patched branch resolver passes16 new tests. Nine additional tests execute the actual modified executor, loader, observer and failure recorder with a deliberately tiny test-double environment. They cover initialization/first/later distinctions, constructor and action failures, pre-factory failure, opponent failure before the candidate turn, no-action episodes, fresh per-game timing and preserved candidate single invocation. These are integration fixtures, not scored games. All nine pass.

The actual pinned intact Arlene source was then called on12 explicit synthetic observations through both the repaired opponent resolver and the timed candidate loader. All12 opponent comparisons and12 candidate comparisons have identical actions and post-call inputs to the direct Agent.act calls, with zero differences. No new engine games or seeds were used. The existing source artifact10030763484 was reused; no exporter was created.

Source identities (Git blob):
- Original executor6469ead662bd9f3a0b818d195d61f5881c1041d8; integrated224d3995f56dadc6762ebc2f35de6ea06ddee782.
- Original branch resolver1132023eab7af9f2ea2325437880c6b2e6d7526e; repaired4885d62f7fba568a483e63ed57ca1b136b7c35ee.
- Observerda9ebd2cd4777f1abbb90c4f8718ef61a3257540, reused unchanged.
- Resolver tests5c81b96d46b7a63437f655051025bfa669b57d43; executor testsc41b85e3caa51312dcf125bba7a3fbf4d4302ba2; smoke27bab2a48d071cadcae1f304465bc8148e5e757d.

From repository root:

```sh
python -B revenue/kaggriculture/cloud-combination-analysis/test_opponent_invocation.py
python -B revenue/kaggriculture/cloud-combination-analysis/test_executor_timing_integration.py
python -B revenue/kaggriculture/cloud-combination-analysis/opponent_policy_smoke.py \
 --arlene /path/to/existing/pinned/arlene.py \
 --resolver revenue/kaggriculture/cloud-model-lab/arlene_arm.py \
 --executor revenue/kaggriculture/cloud-model-lab/execute_arm.py \
 --out /tmp/opponent-executor-smoke.json
```

Run `execute_arm.py` with its existing arguments for subsequent assigned jobs; no new flag or wrapper is required. The observer must be retained at its existing sibling path. Branch source integration does not establish consumption by an already-running VM process, whole-repository CI success, policy strength or any new game result. The model-lab owner's ordinary main delivery can carry these exact changes without touching its saved experiment data.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
