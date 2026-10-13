# COK source discriminators and saved-game observer consumer

This package adds stateless source/table diagnostics and a replay consumer of the
shared `../cloud-opponent-observer/observe.py::CokObserver`. It does not maintain
a second runtime observer or change COK, Arlene, the public bank, or selected SELL.

## Interfaces

`diagnose.load_source(path)` loads the exact supplied COK source into an isolated
namespace. `gate_facts(namespace, observation)` returns the source helper's public
predicate and its component inputs. `route_prefixes(namespace)` compares the
actual frozen action tables. Neither function calls the policy or modifies its
routing state. A true predicate on an arbitrary observation is **not activation**.

`read_evidence.read()` decodes the separately delivered measurement bundle and
checks its compressed, decoded, action-stream and historical-source hashes.
`read_evidence.actions(data, case, position)` reconstructs a complete actor trace.

`replay_observer.py` reconstructs original observations by applying both saved
action streams to the unchanged pinned interpreter. Only those saved actions
control the replay. A fresh shared `CokObserver` sees its own original observation
and returns an action to compare, never an action to apply. The command checks
all original retained observations/configurations, the complete original engine
trace digest, terminal scores and every observer action. This is saved-data
consumer verification, not a new scored panel or an opponent-policy rerun.

The shared observer consumed here is source
`2fb938dcd54c98fff1190673ad35593657863ed2`, file blob
`eee78b475e4a9a5e30ac59025e7eeb507d41135b`, SHA256
`5c1c75a70af171563485ac019fe3fdb5611204e5cb6261fd1007965cc9e7b03a`.
Its schema is `cok-activation-v1`.

## Exact inputs

COK upstream `COK-ZhangZiliang/Kaggriculture` commit
`7ef67eac458cd9ecd13786063e2e581fbe7403ec`, `main.py`, SHA256
`56831f3c43c9727d90016b7a7a8d4eb51d1a4c08c1120d58f061d9176e8bc109`.
Git blob `736577e3810f018f1844b8ac9824a4e69b4c37d3` matches the existing T07
artifact manifest. Preserve the upstream license and third-party notices.

Reuse public-source artifact `10032525998`, source/loader artifact `10030763484`
and engine artifact `10005621438`; their original launch instructions are in
`../cloud-opponent-frontier/runtime/public_bank/README.md`. No replacement
transport job or source patch is needed. The official engine pin is
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

The immutable delivery archive is
`TITAN-IRIS-COK9894001-evidence-20260907.zip`, 553379 bytes, SHA256
`27294547deb92ae9ddf7f6ffa8860aa2f5744e09ce2674b139904a2092446c8f`.
It is saved in the project owner's Library and supplied with the delivery.
Its 48 members retain the original raw logs, measurement source, full dependency
sources and licenses, shared-observer telemetry, and compact evidence bundle.
Every member except the manifest itself is covered by its `MANIFEST.json`.
The archive was independently materialized from Library and hash-matched.

The compact bundle is not duplicated in this source directory. From an extracted
archive in a cloud workspace, copy `evidence/evidence.json.gz.b64` beside these
scripts. The checked-in `EVIDENCE-MANIFEST.json` matches the archive's manifest.
The bundle contains both complete actor streams for both games (identical streams
across positions are stored once), 18 original own-observation/configuration
checkpoints, original results and exact historical measurement code. Full raw
per-call diagnostics remain in the archive. The historical instrument is retained
for provenance, not offered as an alternative active observer.

## Execute offline

Run from this directory in an ephemeral cloud workspace with the retained inputs:

```sh
cp "$ARCHIVE/evidence/evidence.json.gz.b64" .
python read_evidence.py --output decoded
python diagnose.py --source "$COK" --output source-tables.json
TITAN_COK_SOURCE="$COK" python -m unittest -v test_stateless
python replay_observer.py \
  --source "$COK" --pack "$PACK" --engine "$ENGINE" \
  --evaluator ../cloud-eval/evaluate.py \
  --observer ../cloud-opponent-observer/observe.py \
  --output consumer-readback
```

`COK` is the retained `cok-v10/main.py`, `PACK` the existing `cloud-pack`
directory, and `ENGINE` the exact engine cache. The archive contains these inputs
under `upstream/` as well. Outputs use new directories; source and original
measurements stay unchanged. The optional `diagnose.py --observations input.jsonl`
expects rows containing `observation` and emits stateless facts only. The shared
observer owns ordinary observation-to-telemetry JSONL processing.

## Recorded measurements and limits

`RESULTS.json`, `TABLES.json` and `CONSUMER.json` separate three kinds of evidence:

* Two **development** full games on searched-unused seed `9894001`: COK versus
  intact Arlene in both positions, 719 decisions each, zero failures. COK loses
  both, 37537 versus 85968. Same-observation official-loader shadows match all
  1438 original COK actions. No V5 activation: at step 72 the first shop is
  PET_CAFE and rival counts are COW3/SHEEP2/WHEAT7/MELON12. Timings include logging
  and duplicate shadow work and are not policy-only performance numbers.
* Exact table comparisons: V5 low/high first differ at 168; V5 versus the ten
  current/legacy route tables first differs at 72 or 73. These are action-table
  prefixes, not proof that arbitrary live controllers can be spliced.
* The shared observer consumer replays those **saved** trajectories. All 1438
  actions, all 18 retained checkpoints, both original terminal scores and both
  complete engine trace digests match, with zero telemetry errors. Each actor
  has one gate evaluation, 72 unknown-prefix calls and 647 closed calls.

Ten focused tests cover source facts in both positions, positive synthetic
public conditions, numeric parsing, tolerance/malformed inputs, state neutrality,
lossless action decoding, changed-byte detection and the stateless CLI. Two CLI
regressions additionally preserve both input types across direct paths, symbolic
links and hard links. Output/input aliases are rejected before policy loading or
report writing; the original eight-test source checkpoint remains PR9958. The
archived initial measurement instrument separately passed 17 focused tests;
those are historical coverage, not additional current-package tests.

Development `9894001` is already consumed. No held evaluation, new Kaggle upload,
new spend, owner-PC execution, policy promotion or general-strength claim follows
from these measurements. The synthetic positive predicate tests are not games.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
