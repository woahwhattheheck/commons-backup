# TITAN V5 P05 — weed-queue PASS catch-up

P05 is a narrow, held gameplay hypothesis inside the single production-v3/V5 lineage. It is **not** a claim that weed repair caused the V3.1→V4 regression: the canonical convergence map already shows that the main regression was removal of the standalone R04 route topology, and production-v3 has restored that causal center. P05 is a separate opportunity left explicitly owned for measurement.

## Source behavior

Baseline R04 `repair_weeds()` preserves a weed-blocked `PLANT`, `BUILD_COOP`, or `BUILD_PASTURE` by inserting `DIG` and leaving the blocked command at the front of that worker's same-day queue. Every later taped worker command is appended before the queued command is consumed. One blocked command therefore creates one turn of queue debt that persists until dawn; any unconsumed tail is discarded when the day changes.

This component changes only how an **authored PASS** is handled while queue debt already exists. Instead of appending that PASS and preserving the one-turn lag, the worker spends the already-authored idle slot on the oldest deferred command. If the worker is still standing on a weed and the deferred command is still weed-blocked, the worker continues to `DIG` and the debt remains. Non-PASS authored commands keep the existing FIFO behavior. Dawn expiry is unchanged. Market actions are untouched.

The materializer does not guess or reconstruct production bytes. It requires the exact production-v3 archive SHA256 `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`, requires exact `r04_full_router.py` preimage SHA256 `41ea55c5f20c43cd58c5099fbadb212de62ec95a95dfc2e6e1e19c3d4d55b39a`, and requires the source anchor to occur exactly once. It then emits a `titan-v5-staging-component/v1` replacement manifest with `kaggle_submission_hold=true`. Publication uses the shared create-exclusive `publication_custody.publish_exclusive()` primitive.

## Materialize, do not activate

```bash
python -B p05_weed_queue_completion.py \
  --baseline /path/to/titan-v5-production-recovery-v3.tar.gz \
  --out-dir /fresh/p05-weed-queue-pass-catchup
```

The output directory contains only `r04_full_router.py` and `COMPONENT.json`, ready for the canonical staging composer. If another winning component has already replaced `r04_full_router.py`, the P05 baseline preimage intentionally fails composition. The integration owner must produce one reviewed combined postimage and an explicit `overlap_after` relation rather than relying on an implicit textual merge.

## Gate before composition

Source/unit coverage is necessary but not promotion authority. Before P05 is composed into any V5 candidate, a repo-mounted/native seat should materialize it from the exact public production-v3 archive, record the generated router and manifest SHA256 values, and run candidate-only matched cells against the already-canonical C00 production-v3 controls—no baseline rerun. Instrumentation should record P05 trigger count, worker/action recovered into a PASS slot, terminal own/rival/margin, callback count, and failures. A zero-trigger screen is non-engagement, not evidence of benefit. Any default/CURRENT/release/Kaggle action remains forbidden unless a separately reviewed promotion gate authorizes it.

## Focused source gate

```bash
python -B -m py_compile p05_weed_queue_completion.py test_p05_weed_queue_completion.py
python -B -m unittest -v test_p05_weed_queue_completion.py
python -O -B -m unittest -v test_p05_weed_queue_completion.py
```

The focused suite covers exact-once source anchoring, normal PASS behavior with no debt, blocked-work DIG preservation, PASS-slot catch-up, repeated weed blocking, non-PASS FIFO preservation, dawn expiry, exact archive/router binding, duplicate/non-regular tar-member rejection, manifest hashes/hold, and shared create-exclusive publication.
