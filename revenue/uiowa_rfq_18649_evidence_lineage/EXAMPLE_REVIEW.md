# Evidence lineage review

**DRAFT_NON_AUTHORITATIVE**

Synthetic collections: true

## Collection changes

| Record | Classification | Prior records |
| --- | --- | --- |
| ESS-C2 | CONTENT_CHANGED_REVIEW | ESS-C1 |
| ESS-NEW | ADDED | None |
| ESS-P2 | CONTENT_CHANGED_REVIEW | ESS-P1 |
| IAM-A1 | VERSION_LABEL_CONFLICT | IAM-A1 |
| RIS-R1 | RENAMED_EXACT_CONTENT | RIS-R1 |
| RIS-RCOPY | EXACT_CONTENT_COPY | RIS-R1 |
| RIS-S1 | TITLE_MATCH_DIFFERENT_CONTENT | ESS-P1 |

## Records absent from after collection

- ESS-C1
- ESS-P1
- RIS-X1

## Finding follow-up queue

| Finding | Cited record / locator | Status | Declared successors |
| --- | --- | --- | --- |
| F-ESS-C1 | ESS-C1 / lines 1-3 (fictional locator, not automatically revalidated) | CONTENT_CHANGED_REVIEW | None |
| F-ESS-P1 | ESS-P1 / lines 1-3 (fictional locator, not automatically revalidated) | DECLARED_SUPERSEDED_REVIEW | ESS-P2 |
| F-IAM-A1 | IAM-A1 / lines 1-3 (fictional locator, not automatically revalidated) | CONTENT_CHANGED_REVIEW | None |
| F-NO-EVIDENCE | None / None | NO_CITATIONS_SUPPLIED | None |
| F-RIS-R1 | RIS-R1 / lines 1-3 (fictional locator, not automatically revalidated) | EXACT_CONTENT_RETAINED | None |
| F-RIS-X1 | RIS-X1 / lines 1-3 (fictional locator, not automatically revalidated) | MISSING_FROM_AFTER | None |

## Duplicate byte groups

- `056fd23f7aa7ceca9846ee67eb1d56451ee24df130f799e70f6809fe9f5b7c24`: RIS-R1, RIS-RCOPY

## Record anomalies

- {   &quot;document_id&quot;: &quot;IAM-REVIEW&quot;,   &quot;kind&quot;: &quot;VERSION_LABEL_CONFLICT&quot;,   &quot;references&quot;: [     [       &quot;IAM-A1&quot;,       &quot;946e9b0eb953bc6f69e77f51ce4b29e2c2910e17ef58ba9544c061eccdb272a9&quot;     ],     [       &quot;IAM-A1&quot;,       &quot;d7407bb12b0446af1fd355153178bc73770fdfb4194d2b0bfb63a1a96307e58b&quot;     ]   ],   &quot;version&quot;: &quot;v1&quot; }

## Interpretation limits

- Hashes are supplied manifest assertions unless separately checked against source bytes.
- Version strings and titles never establish ordering or semantic equivalence.
- Supersession is a supplied declaration, not an authenticated approval.
- No maturity, compliance, approval, submission or payment conclusion is produced.

The JSON report retains both complete manifests and the original citation records.
Locators are retained verbatim, not revalidated against changed documents.
