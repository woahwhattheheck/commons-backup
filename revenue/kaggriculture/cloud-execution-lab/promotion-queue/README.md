# Promotion queue service

Turns the manual Titan V3 promotion ritual — submit a candidate, pin the
inputs, run the paired gate against the frozen control and LAND, get an
independent review sign-off (see #11913) — into a CLI-driven service.

The queue is **orchestration and receipt only**. The gate itself is always
the existing `../titan-v3-paired-game-gate/` scripts (`gate.py`,
`dual_predecessor_gate.py`); this service pins inputs, builds
per-predecessor gate bundles, shells out to those scripts, and seals the
outcome in a tamper-evident receipt. It never reimplements gate logic.

## Pipeline

```
submit  ->  blob pinning (SHA-256 pin of artifact + games + policy)
run     ->  paired gate vs frozen control AND vs LAND (FIFO)
receipt ->  tamper-evident JSON: input hashes, results, policy version
```

## CLI

```bash
# hash-pin a candidate and enqueue it (dedupe on identical input bytes)
python3 promote.py --state-dir <dir> submit \
  --name v3-p07-joint-actors \
  --artifact joint_actors.py \
  --games matched_p07.GAMES.jsonl \
  --policy policy.json

# run the next pending promotion (or --all for the whole FIFO)
python3 promote.py --state-dir <dir> run --all --predecessors predecessors.json

# queue introspection
python3 promote.py --state-dir <dir> list [--status pending|running|passed|failed]
python3 promote.py --state-dir <dir> status <submission-id>

# requeue a failed promotion (attempt history is kept)
python3 promote.py --state-dir <dir> rerun <submission-id>

# inspect / verify the sealed receipt
python3 promote.py --state-dir <dir> receipt <submission-id> [--verify]

# hash a file without submitting
python3 promote.py pin <file>
```

## Predecessor config

`predecessors.json` declares the two comparison slots and the engine/runner
identities. See `predecessors.example.json`. Each slot needs a pinned games
panel and an artifact file; the engine and runner are pinned identity
manifests. The queue pins every referenced file and writes their SHA-256
digests into the gate contracts' provenance, so the gate binds the exact
bytes it evaluated.

Runner/engine provenance convention: `engine_sha256` / `runner_sha256` are
the digests of the pinned identity manifests, and the `commit` fields carry
the declared upstream commits. For content-addressed runner identities the
queue accepts the manifest's own SHA-1 as the commit value; the convention
is recorded verbatim in the config and the receipt — it is a queue-pinned
identity claim, not a claim about an external repository.

## Gate strategy

* `paired` (default when predecessors collapse): one `gate.py` run per
  slot against the same pinned candidate snapshot. Verdict is PROMOTE only
  when every slot promotes.
* `dual`: the atomic `dual_predecessor_gate.py` comparison, used when the
  two predecessor slots carry genuinely distinct artifact identities. The
  queue generates the strict run-custody receipts the dual gate demands.
* `auto` (default): picks `dual` for two slots with distinct artifact
  bytes, otherwise `paired`. When frozen control and LAND are byte-identical
  the queue does **not** fabricate a distinction; it runs the paired
  comparisons and records both roles against the same bytes.

## Receipts

See [RECEIPT-CONTRACT.md](RECEIPT-CONTRACT.md). Tamper-evident via
SHA-256 over the canonical JSON encoding; repeated attempts on one
submission form a hash chain. Key-based signing is future work.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 python3 -m unittest discover -s tests
```

* `test_pinning` — pin determinism, dedupe, tamper detection.
* `test_store` — FIFO order, dedupe, status tracking, rerun.
* `test_receipts` — receipt format, digest coverage, chain, verify.
* `test_e2e_mocked` — full CLI flow against mocked gate scripts that
  honor the real gate CLI contract (exit 0/2/3).
* `test_dual_wiring` — the queue's dual strategy against the **real**
  `dual_predecessor_gate.py`, including the auto-collapse path.

## State layout

`<state-dir>/queue/queue.json` — entries and attempt history
`<state-dir>/pin-store/blobs/` — content-addressed input bytes
`<state-dir>/pin-store/pins/` — pin manifests
`<state-dir>/receipts/` — sealed receipts
`<state-dir>/attempts/<submission>/` — per-attempt gate bundles and reports

State is runtime data, not source; keep it out of git.
