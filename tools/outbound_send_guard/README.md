# Outbound send guard

This package is a read-only preflight against duplicate outbound contact. It does not search providers or send messages; callers supply intent/evidence snapshots.

## CURRENT authority boundary

Positive CURRENT authority begins **outside an imported Python library**, at direct isolated/no-site startup:

```bash
python -I -S tools/outbound_send_guard/cli.py compile --intent intent.json --evidence evidence.json --out receipt.json
python -I -S tools/outbound_send_guard/cli.py verify --intent intent.json --evidence evidence.json --receipt receipt.json --out verification.json
```

The CLI checks that it is the direct script (`__name__ == "__main__"`), not package-imported, and that both `-I` and `-S` are active before it imports the internal current runtime. Only that clean process binds the deterministic historical engine into the verifier-clock implementation and samples process UTC.

Imported/library surfaces are deliberately non-authorizing. `tools.outbound_send_guard.evaluate`, `current.compile_current`, and compatibility `guard.evaluate` can reconstruct historical decisions but never emit positive CURRENT clearance; historical `ALLOW_NEW`/`REPLY_ONLY` becomes outward `HOLD`. Terminal `DO_NOT_RESEND` remains terminal. `verify_current` on the embedded surface never returns current validity.

This narrowing is intentional. Arbitrary Python can execute before package import and can rewrite module globals, defaults, closures, clocks, cores, or launch primitives. Hiding those objects behind another imported wrapper would only move the trust defect. `current_worker.py` is an internal runtime/testing primitive, not a supported authority API.

## Historical engine and compatibility

`_guard_core.py` retains the deterministic v1 engine. `guard.py` preserves parsing/canonicalization helpers and the legacy receipt shape used by composed guards, including exact source-digest kwargs, but embedded positive decisions are forced to HOLD. Explicit `compile_historical_at()` is integrity/reconstruction only and is always outward HOLD.

The reviewed verifier-clock implementation remains in `current_impl.py`. By default it imports the fail-closed public facade; a bare/imported/module execution therefore cannot recover positive CURRENT. The direct isolated worker explicitly binds `_guard_core` only after the CLI boundary is proven.

## Authority ceiling

Every surface keeps `side_effects_authorized=false`. CURRENT clearance is only a precondition: Muse election/custody, route and relationship policy, fresh provider evidence, one-shot send consumption, and the provider mutation remain separate controls.

## Canonical Muse publication election

For **new** Muse publication elections, the canonical repository protocol is v2: `muse_election_v2.py` plus [MUSE_ELECTION_V2_MIGRATION.md](MUSE_ELECTION_V2_MIGRATION.md).

The two predecessor request protocols—`muse_election.py` / `MUSE_ELECTION.md` and `muse_selection_gate.py` / `MUSE_SELECTION_GATE.md`—are superseded for new election requests. Their historical receipts retain their original schemas and verifiers; do not relabel or reinterpret old receipts as v2.

Raw caller-authored Muse snapshots remain non-authorizing analysis evidence. Live Muse arbitration, provider-authenticated adapter work, relationship/DNR/route/content gates, current-worker lease possession, and fresh provider preflight remain separate requirements.

Canonical v2 retained CI does not consume another active workflow slot. Root `test_muse_election_v2_retained.py` is discovered by the existing `tests.yml` battery, executes both canonical nested suites in normal Python, reruns the complete suites under `python -O`, and syntax-checks the canonical source/test surfaces. This topology preserves the repository workflow-surface budget rather than bypassing it.

## Regression gate

The dedicated workflow runs Python 3.11 and 3.13, normal and optimized (`-O`), and covers:

- the full deterministic v1 engine suite against `_guard_core`;
- embedded package/compatibility HOLD behavior and legacy-shape preservation;
- inert `_utc_now`/`_core` predecessor assignments on the embedded wrapper;
- direct CLI rejection without `-I -S` or when imported;
- real direct `python -I -S .../cli.py` compile→verify round trips, normal and optimized;
- the exact stale matched-pair predecessor: historical `ALLOW_NEW` must be CURRENT `HOLD`.

Queued or absent hosted jobs are never represented as green.
