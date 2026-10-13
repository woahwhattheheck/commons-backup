# UIOWA-073 — measured synthetic before/after rehearsal

These are deterministic lexical-retrieval and source-support results, not LLM answers, real team readiness, or evidence of AI benefit.

| Query | Before current-supported facts | After current-supported facts | Before source support | After source support |
|---|---|---|---|---|
| Q-ESS-CONFLICT | 0/1 | 1/1 | contradictory_sources_require_resolution | complete_source_support_not_answer_validation |
| Q-RIS-METADATA | 0/2 | 2/2 | incomplete_source_support | complete_source_support_not_answer_validation |
| Q-RIS-VOCABULARY | 0/1 | 1/1 | incomplete_source_support | complete_source_support_not_answer_validation |
| Q-IAM-MISSING | 1/2 | 2/2 | incomplete_source_support | complete_source_support_not_answer_validation |
| Q-IAM-UNKNOWN-JUDGMENT | 1/1 | 1/1 | complete_source_support_not_answer_validation | complete_source_support_not_answer_validation |

## Controlled changes and interpretation

The combined repair changes several inputs, so it does not isolate a general causal effect. Each change has a targeted regression test.

The vocabulary case is a direct retrieval rehearsal: zero matching terms before repair, then the same query retrieves the relevant revised source after a vocabulary bridge. No embedding or model was used.

Conflicts disappear only because the synthetic steward explicitly supersedes one source. Metadata completeness improves only because a fictional review supplies it. The new IAM procedure is written support, not demonstrated restoration.

Relevance sets are intentionally versioned when the active corpus changes. Precision/recall across these snapshots is not a controlled model benchmark. Unknown relevance judgments stay unknown.


## Execution receipt

Executed on 2026-09-19 in an ephemeral Linux cloud container, CPython 3.13.5.
All commands below completed successfully on the authored files:

```text
python -m unittest -v test_readiness.py       30 tests, OK
python -O -m unittest -v test_readiness.py    30 tests, OK
python -m py_compile readiness.py demo.py test_readiness.py    PASS
python demo.py /mnt/data/uiowa073-rehearsal-final               PASS
python readiness.py /mnt/data/uiowa073-rehearsal-final/before/collection.json --out /mnt/data/uiowa073-rerun    PASS
cmp /mnt/data/uiowa073-rerun/report.json /mnt/data/uiowa073-rehearsal-final/before/report.json    identical
```

Paths in this receipt identify this execution environment, not required operator
paths. Use the portable commands in README.md. No network, model call, real
University record or live-system operation was used. This receipt establishes
these tests and this five-question synthetic rehearsal, not repository-wide
correctness or a production performance claim.
