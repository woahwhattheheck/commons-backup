# NIH temporal KG ontology interoperability profile

This subtree is a deliberately **restricted, deterministic interoperability profile** layered on the existing `research/nih_temporal_kg_2026/temporal_evidence.py` bitemporal evidence model. It does not claim to be a general RDF, OWL, SPARQL, Biolink, or biomedical reasoner.

## What it does

`profile.py` converts the existing strict temporal JSONL contract to canonical RDF 1.1 N-Triples and back without silently dropping semantics. The emitted graph uses:

- **OWL-Time** `time:Interval`, `time:Instant`, `time:hasBeginning`, `time:hasEnd`, and `time:inXSDDateTimeStamp` for validity intervals. Finite validity preserves `[begin,end)` through the source model; open-ended validity omits `time:hasEnd` entirely.
- **PROV-O** `prov:Entity`, `prov:wasDerivedFrom`, and `prov:generatedAtTime` to bind each assertion/event to its source identifier, exact SHA-256, and observation/correction clock.
- **Biolink** canonical IRIs for syntactically valid `biolink:<LocalName>` predicate lexemes while preserving the original compact lexeme. Other predicates are represented by a deterministic content-addressed `urn:` and retain their exact source lexeme.
- Project-owned profile vocabulary uses the neutral, stable `urn:temporal-kg-interop:profile:v1:` namespace; it does not backlink the Commons build surface.
- Explicit append-only `retract` / `supersede` event resources whose target and replacement fact IRIs must resolve to canonical facts and still pass the existing temporal graph invariants.

The importer accepts **only** the graph shape this profile emits. Blank nodes, language-tagged literals, arbitrary RDF predicates, unknown profile terms, unsupported datatypes, duplicate triples, conflicting functional properties, noncanonical timestamps/decimals, malformed escapes, alias/transplant attempts, orphan profile resources, and digest-inconsistent facts/events fail closed.

## Determinism and evidence

Export is independent of input JSONL record order and sorts exact N-Triples bytes. Import reconstructs the parent model's canonical JSONL. `build_conformance_receipt()` binds:

- raw input JSONL SHA-256;
- canonical input JSONL SHA-256;
- N-Triples SHA-256;
- reconstructed JSONL SHA-256;
- profile descriptor SHA-256;
- interoperability implementation SHA-256;
- exact parent `temporal_evidence.py` implementation SHA-256;
- fact/event/triple counts; and
- exact semantic round-trip result.

`verify_conformance_receipt()` recomputes the whole receipt against exact supplied bytes rather than trusting caller-authored digest fields.

## Run

From the repository root:

```bash
python research/nih_temporal_kg_2026/ontology/profile.py export \
  research/nih_temporal_kg_2026/ontology/example.jsonl /tmp/example.nt \
  --receipt /tmp/receipt.json

python research/nih_temporal_kg_2026/ontology/profile.py import \
  /tmp/example.nt /tmp/roundtrip.jsonl

python research/nih_temporal_kg_2026/ontology/profile.py verify \
  /tmp/receipt.json \
  research/nih_temporal_kg_2026/ontology/example.jsonl \
  /tmp/example.nt
```

Tests:

```bash
python -m unittest -v research.nih_temporal_kg_2026.ontology.test_profile
python -O -m unittest -v research.nih_temporal_kg_2026.ontology.test_profile
python -m py_compile \
  research/nih_temporal_kg_2026/ontology/profile.py \
  research/nih_temporal_kg_2026/ontology/test_profile.py
```

## NIH challenge criterion mapping

This successor addresses the interoperability/ontology-rigor gap already identified by the parent challenge map: machine-verifiable temporal representation, reuse of established OWL-Time and PROV-O terms, explicit Biolink predicate mapping, provenance/version evidence, and deterministic conformance fixtures. The source contract remains bitemporal: **valid time** is represented by the OWL-Time interval while **knowledge/observation time** remains the PROV generated-at clock.

What remains intentionally outside this carrier: real biomedical ontology alignment/evaluation, domain-correctness claims, a general OWL reasoner, SPARQL service, PHI or clinical use, NIH registration/eligibility/submission, official challenge scoring, award, payment, or revenue evidence. Those require separate authorized and source-backed work.

## Hostile coverage

`test_profile.py` exercises finite/open intervals, supersession and retraction, deterministic record-order independence, canonical Biolink/non-Biolink predicate mapping, malformed escapes and surrogate escapes, blank nodes, duplicate triples, conflicting functional properties, unknown terms, noncanonical date/decimal lexemes, fact digest drift, source alias/transplant, interval endpoint loss, replacement omission, orphan resources, and exact receipt tampering.
