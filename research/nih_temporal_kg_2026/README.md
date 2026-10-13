# Temporal Evidence Graph — NIH “It’s About Time” prototype seed

This directory is a **domain-neutral temporal knowledge-graph reasoning core** built against the failure modes named by NIH ODSS in the 2026–2028 “It’s About Time: Temporal Reasoning in Biomedical Knowledge Graphs Challenge.” It is source/test groundwork, **not a competition submission and not evidence of biomedical or clinical performance**.

Official challenge: https://www.nih.gov/challenges/its-about-time-temporal-reasoning-biomedical-knowledge-graphs-challenge

## What exists now

`temporal_evidence.py` implements a dependency-free bitemporal evidence graph with two separate clocks:

- **valid time** — the half-open interval `[valid_from, valid_to)` during which an assertion says a relationship holds in the modeled world;
- **knowledge time** — `observed_at`, when that assertion or later correction became available to the graph.

That split is the central anti-leakage invariant. Asking “what did we know on March 1 about a relationship valid on January 15?” will not pull in evidence first observed in June.

The core also provides:

- canonical immutable fact IDs bound to subject, predicate, object, validity interval, observation time, source identity + SHA-256, and confidence;
- append-only `retract` and `supersede` evidence events instead of destructive history edits;
- point-in-time snapshot queries filtered by both valid time and knowledge time;
- time-respecting directed path search: each hop time is non-decreasing, lies inside that edge’s validity interval, was known by the knowledge cutoff, and survives any correction known by that cutoff;
- deterministic snapshot and path receipts whose canonical JSON is SHA-256 bound and can be verified offline;
- strict JSONL import/export that rejects duplicate keys, NaN/Infinity, unknown fields, malformed timestamps, invalid source digests, and temporally impossible correction events;
- a small CLI for snapshots, paths, and offline receipt verification.

## Semantics

### Facts

Facts are immutable. Example JSONL record:

```json
{"kind":"fact","subject":"therapy_A","predicate":"precedes","object":"therapy_B","valid_from":"2026-01-01T00:00:00.000000Z","valid_to":null,"observed_at":"2026-01-02T00:00:00.000000Z","source_id":"guideline-v1","source_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","confidence":1.0,"fact_id":"<canonical sha256>"}
```

`valid_to=null` means open-ended. A finite `valid_to` is exclusive.

### Corrections

Corrections are independent evidence events. A retraction makes the target inactive only for knowledge queries at or after the retraction’s own `observed_at`; earlier historical knowledge views remain reproducible. Supersession behaves the same way but points to a replacement fact already observed by the time of the supersession event.

### Time-respecting paths

A static graph can infer `A → B → C` even when `A → B` is only true after `B → C` has ceased to be true. `time_respecting_path()` rejects that chain. It advances a path clock monotonically and requires every chosen edge to be valid at its hop time.

This is intentionally simpler and more inspectable than an embedding model. It provides an executable correctness substrate and receipt layer on top of which temporal embeddings, learned ranking, ontology adapters, or benchmark-specific reasoning can later be added.

## Run the tests

From this directory:

```bash
python -m unittest -v test_temporal_evidence.py
python -O -m unittest -v test_temporal_evidence.py
```

The optimized run matters: validation/security boundaries live in explicit checks and exceptions, not Python `assert` statements.

## CLI

```bash
python temporal_evidence.py snapshot graph.jsonl \
  --valid-at 2026-06-01T00:00:00Z \
  --known-at 2026-09-01T00:00:00Z > snapshot.json

python temporal_evidence.py path graph.jsonl therapy_A therapy_C \
  --earliest 2026-01-01T00:00:00Z \
  --latest 2026-12-31T00:00:00Z \
  --known-at 2026-09-01T00:00:00Z > path.json

python temporal_evidence.py verify snapshot.json
```

Exit status is `0` for a valid receipt and `2` for an invalid one.

## Test adversaries covered

The test suite attacks the high-value boundaries rather than merely exercising happy paths:

1. timezone-normalized canonical identity;
2. half-open validity boundaries and open-ended facts;
3. invalid intervals, naive timestamps, invalid SHA-256, non-finite confidence;
4. future-observed evidence leakage;
5. late retraction preserving old knowledge views while changing later views;
6. correction events that predate their targets;
7. supersession referencing a replacement not yet observed;
8. confidence thresholds;
9. valid monotone paths vs temporally impossible reverse chains;
10. future-observed and retracted edges in path search;
11. predicate and hop limits;
12. deterministic receipts independent of insertion order;
13. receipt content tampering;
14. receipt with a rehashed but temporally non-monotone path;
15. explicit negative/no-path receipts;
16. duplicate JSON keys, NaN/Infinity, unknown fields;
17. JSONL round-trip and event-before-fact ingestion.

## Deliberate non-claims

This seed does **not** yet establish any of the following:

- superiority over a static KG baseline;
- performance on the NIH shared benchmark or test data;
- biomedical ontology interoperability;
- learned temporal embeddings;
- clinically meaningful or safe recommendations;
- use of protected health information;
- eligibility, registration, submission, acceptance, prize, payment, or revenue.

Those require separate evidence. See `CHALLENGE_MAP.md` for the exact next proof gates.
