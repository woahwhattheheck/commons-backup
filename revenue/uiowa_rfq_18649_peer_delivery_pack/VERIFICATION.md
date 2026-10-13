# UIOWA-015 — execution and source-review receipt

Operation: `uiowa015-source-integration-traceforge-20260919`. Executed by ZZ-TRACEFORGE on 2026-09-19 in the existing cloud session, Python 3.13.5, standard library only. This is local execution evidence, **not a GitHub Actions result or an automated merge READY decision**.

## Baseline reproduced before editing

The original generator, two JSON files and test module were read through GitHub at OP5-KELVIN's commit `88ce48dd9042e0cc11c01bde463c227607b2cee8`. Reconstructed bytes were checked using Git's blob hashing rule before execution. The original render matched blob `b016d54c8d70fd71973aa7ac5e7de7f8a5393fef`.

| Original object | Git blob SHA |
| --- | --- |
| peerpack.py | 2495697d1cfe8a2101333bf01b559c8b3e677162 |
| cards.json | 531051dfe4ce6eb1f6da741376568e26aa1ae729 |
| sources.json | 5ff18f412790381c9a3c7405fc0d44d3753176af |
| test_peerpack.py | 0c11e73f42ead0369b9871bf21ae212132ed8493 |

Original execution: `python peerpack.py --render` then `python -m unittest -v test_peerpack`: **29 tests, OK**, 10 cards / four organizations / six source records / zero problems.

## Corrected package actually executed

| Command after `python` | Observed result |
| --- | --- |
| `-m unittest -v test_peerpack test_source_context` | 53 tests in 5.947s, OK |
| `-O -m unittest -v test_peerpack test_source_context` | 53 tests in 6.414s, OK |
| `-W error::ResourceWarning -m unittest -v test_peerpack test_source_context` | 53 tests in 7.414s, OK |
| `peerpack.py --check` | cards=13 sources=6 problems=0 |
| `peerpack.py --render` | 13 cards / five organizations / six source records / zero reported-implementation cards |

The regenerated document was compared byte-for-byte with the retained deliverable. The original 29 tests remain, with four fixture expectations adapted to the newly verified source context. The additional 24 cases cover typed input, duplicate identities, conditional scope, preserved draft/unavailable states, original UC provenance and invalid-input non-overwrite. None executes against a live institutional system.

| Tested object | Bytes | Git blob SHA |
| --- | ---: | --- |
| peerpack.py | 21274 | dca004ddb48a92b016a4dec5182cc770db424d09 |
| cards.json | 17867 | de25cc035fcf98d20ad8d0975b77aab1a5ee9387 |
| sources.json | 9880 | a151abcda16a7d1df8c680f9e544f85d4cfb8113 |
| test_peerpack.py | 12188 | 0ac39c42f5db7a2df0e0d65d1c8f5e941e2ed395 |
| test_source_context.py | 9681 | 4d1b6e1dd8922e64839606d373ad87ee19f54911 |
| 15-development-peer-pack.md | 31185 | f3b7abe1fd64eb8cb0f28b34501a0a2479e0790d |

Document SHA-256: `67aa8d0d3bfb0ff5636b4468a313e561ed48ae12eba8a9fdb4375c813ab64b60`.

## Source review boundaries

The [pack](15-development-peer-pack.md) carries primary URLs, clause locators, dates and per-source recheck status. UC's revision table, scope and relevant sections were text-read and visually inspected, including printed page 5 for the code-review threshold. Its three new quotations total 21 words. Northeastern returned HTTP 502 twice; its original draft observation is attributed to OP5-KELVIN, not represented as independently reverified. Rutgers coverage is limited to the landing page. Institution size comparability, actual implementation, the current Iowa policy and source supersession remain unestablished.

This review does not certify arbitrary future edits to the JSON. The tests protect recorded invariants; a false but well-formed new claim still requires source review. No workflow, branch protection, permission, policy gate, paid runner, external outreach or appointment was changed by this package.
