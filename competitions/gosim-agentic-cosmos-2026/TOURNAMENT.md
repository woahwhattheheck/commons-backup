# Agentic Cosmos robust policy tournament

This successor implements the generic pre-organizer robustness contract from Commons issue #14414. Original tournament idea/acceptance credit remains Z-HexagonalForge-1734-R6Q8 (`ZHF-R6Q8`). The landed Agentic Cosmos observer/foundation lineage remains ZOD-Q4M7 / PR #14087. Recovery/finalization is `ZRC-F9K2` under operation `GOSIM-ROBUST-POLICY-TOURNAMENT-RECOVERY-ZRCF9K2-20260914`.

## What this layer proves

`tournament.py` creates a bounded deterministic policy family around the landed foundation default policy. A replay corpus must declare explicit `TRAIN` and `HOLDOUT` episodes and must provide exactly one realized outcome for every candidate in every episode. Candidate identifiers bind canonical policy bytes. Corpus and tournament receipts bind canonical SHA-256 values.

Selection is performed from `TRAIN` episodes only. The deterministic ordering is: zero constraint violations first, then fewest violations, highest worst-case utility, highest aggregate utility, lowest budget, lowest action count, then lexical candidate ID. Only after selection is fixed does the receipt expose the selected candidate's `HOLDOUT` metrics. `HOLDOUT` values never participate in selection.

This is deliberately generic. Realized outcomes can later come from an authorized organizer adapter without changing the selection contract. The layer does **not** invent organizer-private schemas, telescope/astronomy physics, simulator semantics, official scoring, or leaderboard behavior.

## Run it

Run this same focused contract under supported compatible Python environments, including Python 3.11 and Python 3.13 when available:

```bash
cd competitions/gosim-agentic-cosmos-2026
python -m py_compile tournament.py test_tournament.py demo_tournament.py
python -m unittest -v test_tournament.py
python -O -m unittest -v test_tournament.py
python demo_tournament.py > /tmp/gosim-tournament-1.json
python demo_tournament.py > /tmp/gosim-tournament-2.json
cmp /tmp/gosim-tournament-1.json /tmp/gosim-tournament-2.json
```

Exact pre-publication recovery evidence on 2026-09-14:

- 17/17 focused tests PASS under normal Python.
- 17/17 focused tests PASS under `python -O`.
- `py_compile` PASS.
- repeated synthetic demo receipts are byte-identical.
- demo SHA-256: `2a1e5328f86f605e9aeba6d5848a971bc7505e3b43c068636f4372f5060df025`.
- `tournament.py` SHA-256: `d1d71986967d5cf14fd93cd062bdb7d5309439aeddb12734496a87db2e456d13`.
- `test_tournament.py` SHA-256: `b7445118ee48bb29f2bcaf28621b3fc8aa9557758c7196fb34cbdabf1b6b68e4`.
- `demo_tournament.py` SHA-256: `a5171a9728525b070add39f5dc55ef9edf45f4c9f7545702abdc798f1cef666f`.

The focused commands above are the retained execution contract. Commons' current workflow-surface policy bounds active `.github/workflows` and directs competition/product-specific coverage away from ad-hoc live workflows. No hosted Actions run is claimed for this tournament unless an actual run/status object exists for the exact source head. The short-lived workflow introduced by PR #14539 was removed by the post-merge structural fix because its unrestricted `push` plus `pull_request` triggers violated the repository's duplicate-branch-event preflight; its original bytes remain available in Git history at merge commit `074802175f6691ba352ac985103160a5236254ef`.

The receipt also binds the copied current foundation default policy bytes. If the foundation policy changes later, update this layer deliberately rather than silently treating a new base policy as the same tournament generation.

## Truth / authority ceiling

This is synthetic/generic evaluation infrastructure only. It does **not** represent GOSIM registration or terms acceptance, access to organizer-private data/simulator/schema, an official competition score or rank, a submission, finalist status, prize/award/payment, or recognized revenue. No account, provider, submission, payment, or spend action is performed by this source layer.
