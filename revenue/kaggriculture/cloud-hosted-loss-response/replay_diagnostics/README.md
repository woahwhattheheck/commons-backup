# T13 public-replay diagnostics

KESTREL's additive diagnostic component. ALDER owns the parent policy/runtime,
its integration and every development/held full-game seed. This directory runs
no opponent program and consumes no full-game panel. See `RESULTS.md` and
`results/HOSTED-RESULTS.json` for the two actual hosted analyses and counterexamples.

## Inputs and execution

Reuse ROWAN's four lossless public replay files from
`cloud-frontier-trace/results/t13-public-inputs/` at Commons commit
`16a2d4a7675c7e27b97bedc00f8073690bf7a763` (PR9912). ATLAS transported these exact
files in Actions artifact10031480684, `titan-t13-public-replays-16a2d4a7`, from
run34157565094. The original parent source pack was not rebuilt. Extract once and
run the unchanged `decode.py`; it verifies compressed/raw hashes, EpisodeId and
terminal rewards before writing `106541578.raw` and `106540665.raw`.

The provider receipt binds submission56081391 to seat1 in106541578 and seat0 in
106540665. Matching cash alone does not establish submission identity.

```sh
D=revenue/kaggriculture/cloud-hosted-loss-response/replay_diagnostics
ENGINE=/path/to/existing/engine
INPUT=/path/to/decoded/replays
python "$D/diagnostics.py" "$INPUT/106541578.raw" \
  --engine-dir "$ENGINE" --episode-id 106541578 --own-seat 1 \
  --our-submission-id 56081391 --expected-cash 95995,96979 \
  --output "$D/results/106541578"
python "$D/diagnostics.py" "$INPUT/106540665.raw" \
  --engine-dir "$ENGINE" --episode-id 106540665 --own-seat 0 \
  --our-submission-id 56081391 --expected-cash 75560,76091 \
  --output "$D/results/106540665"
python "$D/market_witnesses.py" "$INPUT/106541578.raw" \
  --engine-dir "$ENGINE" --own-seat 1 \
  --output "$D/results/106541578/market-witnesses.json"
python "$D/market_witnesses.py" "$INPUT/106540665.raw" \
  --engine-dir "$ENGINE" --own-seat 0 \
  --output "$D/results/106540665/market-witnesses.json"
KAG_ENGINE_DIR="$ENGINE" python -m unittest discover -s "$D" -p 'test_*.py' -v
```

The first CLI emits `diagnostics.json` and deterministic `witnesses.json.gz`.
Witnesses retain exact public before/after frames and full replacement actions.
The first16 chronological harvest alternatives are retained by default, not the
16 most profitable. All candidates are counted. Raw replay bodies need not be
copied into this component: they already have their own pinned source/transport.
The committed compact result binds generated files by actual SHA-256; source
path metadata can change the report bytes when rerunning in a different location.

## Interfaces and evidence boundaries

`load_trace_module()` reuses ROWAN's existing analyzer unchanged.
`summarize_trace(trace, own_seat, material_cash=100, top_n=8)` separates first
observed differences, material cash deficits and largest adverse cash changes.
Cash causes are attributed only on reconciled official transitions; mismatches
never become inferred proceeds or zero residuals. A missing held-yield product
and an explicitly recorded zero are treated as equal quantities.

`scan_noop_harvests(observation, base_action, engine, configuration=None)` tests
same-position HARVEST replacements for genuinely inert worker requests. It
executes the complete ordered unit phase, preserves atomic seed cancellation,
positions, other worker requests and market slots, and does not double-count
another worker's subsequent harvest. It reads only own farm/private state, not
rival actions or future prices. It is a candidate generator, not a deployed agent.

`counterfactual_transition(...)` first reconciles the baseline and then replaces
one player's full action while retaining the recorded rival co-action. It
reports actual one-step cash, inventory and held-yield changes. That co-action is
offline evidence, not an agent input or a forecast of a responsive opponent.

`market_witnesses.impact_order(...)` ranks only the initial SELL prefix by exact
receipt loss under an explicitly hypothetical equal-sized competing lot. It
reads own available goods/public market curves and preserves quantities and all
non-prefix slots. A negative terminal-turn example is retained in the results;
this scenario score is not sufficient for policy promotion.

`market_witnesses.carry_path(...)` propagates both players' cash deltas and one
seed-inventory delta along recorded future actions. It reruns every baseline
transition and stops on any other compared-state change. When a public replay
contains its RNG seed, all boundary fields are compared too; this metadata is
used only inside the offline interpreter. Without it, weed/shop boundary draws
follow the recorded exogenous path and exclusions are explicit. Its CLI selects
the two diagnosed purchase edits and six exploratory market turns; these fixed
indices are research witnesses, never a generic runtime policy.

## Validation and provenance

28 focused real-interpreter tests pass. They are manufactured state/transition
fixtures and CLI tests, not hosted matches. Coverage includes sequential workers,
atomic seed scarcity, missing/corrupt observations, exact DROP-before-SELL cash,
no deposit/no immediate sale, day boundaries, zero-only yield keys, binding,
invalid indices, immutable inputs, market-slot preservation and rejection of
seed cuts that break later planting. `TEST-RESULT.txt` is the actual test output;
`VALIDATION.json` binds the exact source and result bytes.

The official engine is Kaggle/kaggle-environments at
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, verified by the existing evaluator.
ROWAN analyzer blob: `9c7cd95005ce9c84b862f218049fd71e16ccd604`.
Existing source artifact10030763484 and engine artifact10005621438 were reused.
Raw SHA-256 values:

-106541578: `664393c37fc132c75d9d20d0be53ef76a0188ae333852a35430b1ff7fe648375`
-106540665: `410e9dc42ffabd02118a5782bc077156f952a094ad2669f64ce85941fd5bd94a`

Source follows the repository Apache-2.0 license. Preserve upstream notices with
the existing engine cache. No competitor source or engine distribution is added.
No Kaggle write, owner-PC compute, credential transfer, new spend or automatic
agent-default change occurs here. ALDER's independent paired/held evaluations
are separate evidence and remain in ALDER's own scope.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
