# Independent neutral-budget consumer checks

These tests consume DATE's single `budget_release::find_release` operator and
SEDGE/FLORA's unchanged fleet ECMP kernel. They add no solver, search
neighborhood, acceptance rule, portfolio default, or submission action.

## Inputs and execution

Use the existing fleet source at `2885d176373c33410148829fef93c310c3752c0b`
(`fleet-candidate/main.cpp`, Git blob `9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df`)
and DATE's header at `20a08d3c2e2005d6a6add88331983f5453beb19f`
(Git blob `5ce70d722c6d4e2f7c053990697387d9f46514fc`). The default header path
is the parent directory. Existing RapidJSON headers are required; no download
or dependency installation is performed by these tests.

```sh
D=revenue/roadef2026/cloud-budget-release/atlas
python3 "$D/test_native_invariants.py" \
  --fleet-source /path/fleet-candidate/main.cpp \
  --header /path/cloud-budget-release/budget_release.hpp \
  --vendor /path/fleet-candidate/vendor \
  --report /tmp/atlas-native.json --evidence-dir /tmp/atlas-native-cases

python3 "$D/check_negative_controls.py" \
  --fleet-source /path/fleet-candidate/main.cpp \
  --header /path/cloud-budget-release/budget_release.hpp \
  --vendor /path/fleet-candidate/vendor --output /tmp/atlas-negative

python3 "$D/check_saved_outputs.py" --checker /path/bin/checker \
  --evidence-dir /tmp/atlas-native-cases --output /tmp/atlas-official
```

Evidence/output directories must be fresh. The native CLI checks source
identities before compilation. `--expected-header-blob` explicitly selects a
separately labeled operator revision, including the deliberate negative
controls; it is not a claim that changed source inherits the original result.
Ordinary unittest discovery without native input arguments explicitly skips
the native class. Configured missing/wrong inputs fail rather than skip.

The official checker used here is Orange's unchanged source at
`d84d319a7fdb8de3b1866830d2eaa2937871e5ae`, with networktools
`aebafc9ee91891e5d721bb86725e8cf1533877d1`. QUARTZ's already-verified build
context provides the complete staged source and licenses. The checker was
compiled locally with its existing C++20 command. The saved-output reader
invokes this supplied binary only; it does not run an optimization algorithm.

## What is checked

The test translation unit changes only class-member visibility and the original
main symbol in a temporary copy of the pinned fleet source. All original
method bodies remain unchanged. Each proposal is applied by the independent
test consumer, not by DATE's later `build_candidate.py` injection.

After every accepted proposal, complete cached flows and loads remain
byte-identical; the real fleet routing functions rebuild the entire schedule,
and independent rational per-forwarder ECMP and directed-segment set differences
recompute its physical loads and every transition cost. The fixtures cover
multiple demands sharing forwarding links, maintenance within a constant run,
ECMP splitting, zero traffic, boundary dominance, repeated descent, unreachable
callbacks, exact coefficient equality, callback exceptions, and cancellation
after a real flow callback.

The current native run passes 12 methods, covering 76 constructed cases
(64 deterministically generated cases plus 12 targeted invocations). It accepts
386 neutral proposals across 64 cases, releasing 1,257 aggregate transition
units without increasing any boundary. The official checker validates both
saved solutions for all 76 cases: 152 invocations, identical full saturation
maps and objective arrays at its default 12-decimal output, with matching
transition totals. These numbers describe manufactured correctness fixtures,
not contest-instance gains or an estimate of solver strength.

Five deliberately altered headers are detected for their intended reasons:
checking only one slot, accepting a budget increase at another boundary,
ignoring flow equality, accepting no strict budget improvement, and returning
a proposal after cancellation. Each mutated run has failing assertions with
zero execution errors. These tests do not modify the published operator.

The initial checker pass rejected a generated fixture with duplicate demand
endpoints. Final fixtures use distinct sources over the same forwarding core;
operator and kernel bytes were not changed. The rejected fixture and earlier
negative-harness directory collision are retained in the delivery archive as
setup history, never counted as passing final execution.

`VALIDATION.json` binds the final source files and measured results. The separate
`ROADEF-ATLAS-DATE-invariants-20260908.zip` delivery retains native fixtures,
checker outputs, negative controls, logs, and provenance. DATE retains the one
runtime/injection, OSPREY the improving-move discriminator, and QUARTZ/RENEW the
native/container benchmarks. No public benchmark panel, image execution,
qualification email, held attachment, or submission is part of this component.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
