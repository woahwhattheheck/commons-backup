# Synthetic rehearsal — expected interpretation

Running:

```bash
python3 test_data_assessor.py fixtures/catalog.synthetic.json
```

should produce these high-level results:

| Dataset | Expected interpretation |
| --- | --- |
| ESS-REGISTRATION-BOUNDARIES | Seven checks evidenced; no observed gaps or unknowns in the synthetic catalog entry |
| RIS-AWARD-SYNC | Observed gaps for refresh freshness, interface alignment, and documented boundary-case coverage |
| IAM-ROLE-TRANSITION | Unknown ownership, refresh, cleanup-verification, and retention evidence; observed gap only for missing documented boundary cases; interface alignment and synthetic origin remain evidenced |

The point of the rehearsal is not the counts themselves. It is to show that one dataset can have strong evidence in one dimension and unknown evidence in another without collapsing everything into a single maturity label.

No row represents University of Iowa data or a University finding.
