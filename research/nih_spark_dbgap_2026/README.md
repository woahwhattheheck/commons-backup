# NIH/NLM SPARK dbGaP — pre-launch transparent baseline

This directory is a **pre-launch engineering substrate**, not an NIH submission and not a claim of official score. It targets the public requirements posted for the 2026–2027 **Semantic Precision for AI Retrieval of Knowledge (SPARK) dbGaP Challenge**.

## Official contract captured 2026-09-13

- Registration opens **2026-09-15**; submissions open **2027-01-18** and close **2027-01-31**.
- Total prize pool: **$250,000**. Each of two tracks receives $125,000 ($100,000 first, $25,000 second).
- Track 1 maps phenotypic study variables to standardized concepts, including `ONT_NONE`; published primary metric is average F1 across target concepts/classes.
- Track 2 ranks dbGaP studies for natural-language cohort-feasibility/discovery queries; published primary metric is NDCG.
- Required deliverables include JSON outputs, a reproducible Docker image, source code, and technical/reproduction documentation.
- Runtime evaluation may be zero-egress except for explicitly allowed NLM services. Public/legal reusable open resources and open-weight models only; external resources must be disclosed.
- Organizers reserve unseen/private adversarial probes and anti-gaming audits.

Source of controlling public facts: NIH challenge page, `https://www.nih.gov/challenges/semantic-precision-ai-retrieval-knowledge-spark-dbgap-challenge`.

## What is here

The runtime is dependency-free and deterministic:

- `core.py`: strict duplicate-key-rejecting JSON ingress, bounded double-read generation checks, descriptor-bound no-follow lexical ancestry, canonical serialization/hashing, exact scalar/schema primitives;
- `contracts.py`: canonical public study/variable/concept corpus with exact text digests and an explicit external-resource manifest carrying versions/licenses/provenance/digests;
- `track1.py`: transparent lexical concept ranking with stable tie-breaking, policy-bound `ONT_NONE` abstention, and per-class precision/recall/F1 plus macro-F1;
- `track2.py`: study-level lexical ranking with transparent term-frequency/rarity contributions, intersection-coverage bonus, and CG/DCG/IDCG/NDCG evaluation;
- `baseline.py`: content-addressed run receipts binding corpus, resources, input, output, policy and source version, with all authority facts false, plus an anti-hardcoding scanner;
- `publication.py`: retained-parent, create-exclusive two-file publisher that stages both selected outputs before commit, verifies exact bytes/generations, rolls back only exact owned inodes, and reports ambiguity instead of deleting foreign replacements;
- `cli.py`: offline `python -m research.nih_spark_dbgap_2026.cli` runner using the pair publisher for output + receipt.

`fixtures/` and `test_baseline.py` use **synthetic dbGaP-like metadata and synthetic concepts only**. They are not NIH/dbGaP data, UMLS/OBO content, a hidden validation set, or evidence of challenge performance. CI executes both track CLIs against those fixtures on Python 3.11–3.13 in addition to the hostile unit suite.

### Filesystem truth boundary

The local runner is intentionally Linux/POSIX-oriented: safe ingress and publication require descriptor-relative directory operations and no-follow opens. It refuses a platform that cannot provide those primitives rather than silently weakening the custody contract.

Two independent filesystem names cannot become visible in one portable namespace operation. The pair publisher therefore does **not** claim crash-atomic visibility. It guarantees that both payloads are staged before either selected destination is committed; in-process failures roll back only when retained inode identity proves cleanup is safe. If another actor replaces a selected path or cleanup cannot be proven, the run fails with an explicit ambiguous-inspect status and preserves foreign bytes.

## Intentional limitations

This baseline is designed as a transparent floor and reproducibility harness. It does **not** pretend a lexical mapper will be competitive with a strong ontology model or that a lexical study ranker will win Track 2. Its job is to make later improvements measurable and hard to accidentally game.

The following must remain unresolved until NIH releases the relevant launch artifacts/details:

- exact official input/output JSON schemas and filenames;
- challenge-provided dbGaP snapshot identity/digests;
- validation-set structure;
- designated AWS base image and resource limits;
- exact list/contract of approved NLM network services, if any;
- exact permitted UMLS/OBO releases and any participant-side licensing/access obligations;
- final Docker interface and mandatory validation script.

Do not hardcode guessed versions or treat synthetic fixtures as official truth.

## Privacy / authority ceiling

This package consumes study-level public metadata only. It does not access controlled dbGaP participant data, create DARs, infer individual records, register for the challenge, accept participation terms, submit to NIH, publish a Docker image, contact sponsors, or claim a biomedical conclusion, award, payment, or revenue.

## Run tests

```bash
python -m unittest research.nih_spark_dbgap_2026.test_baseline -v
python -O -m unittest research.nih_spark_dbgap_2026.test_baseline -v
python -m py_compile research/nih_spark_dbgap_2026/*.py
```

The package has no runtime dependency outside the Python standard library and performs no network calls.
