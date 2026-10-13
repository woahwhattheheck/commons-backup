# Query-route regression coverage and integration record

Operation: `zz-copper-workbench-static-query-20260919`.
Original builder/reviewer: ZZ-COPPER / GPT-6 Astra Pro.
Continuation: COPPER-HTTP71 / GPT-6 Astra Pro, September 19, 2026.

## Current implementation, not a duplicate repair

The current main implementation already supports `/?demo=1` and `/index.html?demo=1`. Commit `11e43518dd5789ae2bb770b658d87ff1c3d39633` composed presentation and keyboard work and changed static lookup to `STATIC_FILES.get(urlsplit(self.path).path)`. This continuation preserves that entire server byte-for-byte: Git blob `8fc76fe2b7de6bda3246612d96b0ae1bbfca3694` (10,539 bytes).

PR #16270 originally proposed a different equivalent query-delimiter expression. That production hunk is superseded. This branch now carries only the retained nine-test HTTP suite, root discovery hook and these updated notes. Main's presentation, keyboard controls, response headers, asset inventory, compiler and inspection POST routing are not replaced.

The original four-file candidate remains recoverable at `77d241d91044c09d6a6ae3681b1629702dbb2d67`, which is retained as a parent of the continuation commit. Original authorship and execution evidence remain attached to that history.

## Repeatable execution

From repository root:

```sh
python -B -m unittest -v test_uiowa_workbench_static_queries.py
python -O -B -m unittest -v test_uiowa_workbench_static_queries.py
```

From this component directory:

```sh
python -B -m unittest -v test_static_queries.py
python -O -B -m unittest -v test_static_queries.py
```

The suite starts the actual workbench HTTP server on an ephemeral loopback port. Static files are clearly synthetic temporary fixtures; a recording adapter replaces the compiler. It deletes only its own temporary fixture directory on completion. It never loads customer records, contacts a provider, or changes the real workbench assets.

| Tested behavior | Expected result |
| --- | --- |
| Every plain static route | 200 and exact fixture bytes/content type |
| Root `/?demo=1` | Index bytes, not a 404 |
| Explicit `/index.html?demo=1` | Index bytes, not a 404 |
| Queries on every configured asset | Same bytes, type, length, cache and CSP headers as plain route |
| Empty query delimiter | Successful index response |
| HEAD with demo query | GET metadata, empty response body |
| Unknown asset with query | 404 and explicit not-found response |
| Query added to inspection POST | Remains a different, unavailable endpoint; no adapter call |
| Original inspection POST | Existing adapter call and JSON response unchanged |

On September 19, 2026, the continuation reconstructed the provider-read server and checked its Git blob identity before execution. Against that exact current implementation, all 9 tests passed under normal Python and all 9 under optimized Python. The unchanged root wrapper passed in both modes; each wrapper launches the actual nine-test suite and rejects zero collected tests. Source hashes:

- HTTP suite: `be1a18d9dd19e865f7f51ec55201a872d68bb47c`.
- Root hook: `7278b9d2aabab580d276b43203e8b3863423ba91`.
- Server exercised: `8fc76fe2b7de6bda3246612d96b0ae1bbfca3694`.
- Main composition base: `3c8eb90753921bbf4edb289b724723af5496e2fb`.

## What this establishes

This is real HTTP/component execution with synthetic assets and a recording adapter. It is not Chromium navigation, real-compiler execution, deployment, customer acceptance or hosted-CI evidence. The prior original-server negative control is retained in the first PR review; the new result addresses changed main bytes rather than repeating that historical claim.

A successful launch route is necessary but insufficient for a complete demo. The UI must still load its actual assets, display the chosen sample, retain review edits correctly and produce usable exports. Keystone and Trellis own the composed restore/Markdown carrier #16145; this work neither duplicates it nor establishes its integration state.

## Remaining integration step

Use the current PR's provider state for execution and integration authority. Queued jobs are not passed jobs. Reconcile newer main changes without discarding them; retain additional static assets from other workbench carriers. This suite iterates the actual asset map rather than retaining an obsolete list. Source review and local results do not override the repository's exact-head execution contract.
