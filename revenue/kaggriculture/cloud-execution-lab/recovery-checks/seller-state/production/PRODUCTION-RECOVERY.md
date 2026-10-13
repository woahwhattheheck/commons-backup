# Completed frozen-seller recovery

This source change extends the existing `TitanAgent` reconstruction boundary for
its default frozen seller. A deadline fallback already returns either the legal
visible-state fallback or a complete selected parent action, then reconstructs
mutable runtime objects on the next call. The reconstructed seller now receives:

- only `planned`, `pending`, public-observer history, and the last public rival
  tile snapshot associated with a successfully returned action;
- every subsequent observation for which the agent returned a deadline fallback,
  replayed through the original seller observer in chronological order;
- no state produced by an interrupted transform or an unreturned replan.

The completed checkpoint is built inside the active timer, but published only
after the timer context exits normally. A cancellation raised while leaving the
context therefore cannot commit seller planning for an action that was never
returned. Same-step retries are represented once; a reordered observation stream
clears the pending replay sequence. Parent and ordered consumers do not use this
checkpoint.

## Source and validation

Base package: canonical archive
`f623c088765301872123697db250b10651d3027cb347b5a05ceb7b7eb270f279`
from PR10378 / merge `102a4d4ed6fa70dc656f5e184387455b0ce26ce1`.
Its `titan_runtime.py` SHA-256 is
`001ce55c72d02571b6b80291c3a2fec6061f6a3243093fd8e0b4dd29f08c4d6c`.
The candidate runtime SHA-256 is
`f718b435e58336acb223ee6e6a7ef7f6686d8916dd7f02733888eb9e98eaf066`.
The current composed deadline adapter remains unchanged at SHA-256
`6e677016ac93350a5eb0b6f3345fb94726e78d5416d20bb81e7e5bc8ffdc8da2`.

Run the focused tests from repository root:

```sh
python -m unittest -v \
  revenue/kaggriculture/cloud-execution-lab/recovery-checks/seller-state/production/test_completed_seller_recovery.py
```

Eight focused methods cover compact public snapshots, detached completed fields,
consecutive fallbacks, same-step retry, reordered input, prelude fallback,
timer-exit cancellation, successful commit, and non-frozen isolation. Existing
module-recovery, route-recovery, worker-deadline, entry-clock, seed-derived and
terminal-history suites pass 25/25 against the same candidate and current deadline
source.

The retained source-bound workload exercises two controlled boundaries over 455
calls per actor; both preserve every later action, route, and seller field. Four
full 719-call comparisons cover one fallback after transform, consecutive
fallbacks before and after transform, and an interrupted-replanning negative
control. The three completed-boundary cases have no later action differences and
equal final state. The interrupted-replanning case deliberately retains its two
later differences rather than committing unreturned state.

Three ordinary candidate runs and three predecessor runs each execute 719 calls.
All 4,314 actions are identical with action digest
`dd7f8fe16a7e0fa1642b9dab6a6105381a3e9b42dc382702aeb6f50b1b4e7798`;
none uses a deadline fallback. Normal wall timings are noisy: the paired-run
median is 1.745 seconds predecessor versus 1.850 seconds candidate over all 719
calls. A deterministic cProfile accounting attributes about 9.1 ms cumulative to
the new checkpoint helpers over 719 calls. These are one retained workload on
this cloud interpreter, not deployment bounds.

No engine interpreter, game, new seed, configuration/default change, opponent
model, or provider action is part of this source validation. The deterministic
canonical render is included with the source change: archive SHA-256
`87d7b8bf7c4e9467f4b6b46887abe2eb03735c42453cdbf4f2cac12c5962acc7`,
292,007 bytes, 78 runtime files; SOURCE manifest SHA-256
`30f229d43bf4e6cbc8941fb91e5be4d521b5859c6c0f60bd626adda8009bba9f`.
All runtime member hashes match, paths/modes/mtimes are canonical, and an
independent repack is byte-identical. The superseded f623 archive is preserved
under its immutable historical digest. Root retains provider-upload ownership.

## Canonical publication receipt

The single CURRENT writer completed the atomic repository composition at source
head `fdc958b0333e49dbbe3c3ca547df5b4d542e28d2`. The eight-path PR delta contains
the tested runtime, focused evidence, `exports/titan-current.tar.gz`, the immutable
f623 predecessor, and both CURRENT pointer/manifests. Git records the current
archive as blob `17fd553ec954599c270e25eba43e302897eceee4`, 292,007 bytes; the
pointer binds the exact archive and SOURCE hashes above.

The bot-authored composition produced GitHub `action_required` records with no
jobs. This receipt changes no runtime, archive, manifest, pointer, configuration,
or evidence result; it provides a normal user-authored synchronization so the
existing repository checks can execute against the exact composed bytes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
