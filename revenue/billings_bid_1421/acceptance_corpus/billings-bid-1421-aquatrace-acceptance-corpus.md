# City of Billings Bid 1421 / AquaTrace LIMS

## Synthetic 100-Case Acceptance Corpus

**Artifact ID:** billings-bid-1421-acceptance-corpus-20260831-01  
**State:** SYNTHETIC_TEST_SPEC_ONLY - not implemented, delivered, submitted, certified, or production-tested.  
**Official source:** https://www.billingsmt.gov/DocumentCenter/View/56340/2026-LIMS-RFP  
**Source SHA-256:** 667d3d260f28877ad41ca6313d03eaddf3e45ae278a995ebf72d78d144339882

This corpus translates the official RFP's Section 3 functional requirements, Section 7 security boundary, and Attachment F methods/instruments/reporting list into deterministic nonproduction checks. All values are synthetic. The system never releases or transmits a regulatory result.

## Global Pass Gate

- PASS requires 100/100 cases.
- Every case must emit exactly one immutable receipt with the required evidence fields.
- Duplicate/replay paths create zero additional business effects.
- Held, denied, conflicting, and ambiguous inputs never become accepted or released.
- Regulatory release count and regulatory transmission count must remain zero.
- Two clean full-corpus runs must produce identical normalized business outcomes and root hashes.

## Distribution

- field_collection: 10
- offline_sync: 10
- chain_of_custody: 10
- sample_receipt_and_disposition: 10
- qc_retest_authorized_release: 10
- instrument_ingest: 10
- audit_export: 10
- report_reconciliation: 10
- role_denial_and_accountability: 10
- retry_replay_and_recovery: 10

## Cases

### AT-001 - Complete online collection

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-001 complete collection for SAMPLE-001 under method EPA 300.0
- **Fault:** none
- **Expected disposition:** ACCEPTED
- **Specific PASS:** One collection event creates one traceable sample start.
- **Specific FAIL:** The sample start is absent, duplicated, or lacks actor/method evidence.
- **Regulatory release/transmission:** prohibited

### AT-002 - Missing required collection time

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-002 omits collection_time
- **Fault:** required field missing
- **Expected disposition:** HOLD
- **Specific PASS:** No lifecycle transition occurs and reason_code is REQUIRED_FIELD_MISSING.
- **Specific FAIL:** A sample proceeds without collection time.
- **Regulatory release/transmission:** prohibited

### AT-003 - Unknown synthetic method code

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-003 uses METHOD-UNKNOWN
- **Fault:** unmapped method
- **Expected disposition:** HOLD
- **Specific PASS:** The event is retained with METHOD_MAPPING_REQUIRED and zero result eligibility.
- **Specific FAIL:** The unknown method is silently mapped or accepted.
- **Regulatory release/transmission:** prohibited

### AT-004 - Exact duplicate field event

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-004 is submitted twice byte-for-byte
- **Fault:** duplicate delivery
- **Expected disposition:** DUPLICATE_SUPPRESSED
- **Specific PASS:** One business collection exists and the second delivery adds zero effects.
- **Specific FAIL:** Two sample starts or custody events exist.
- **Regulatory release/transmission:** prohibited

### AT-005 - Same event ID, different payload

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-005 reuses event_id with a changed sample point
- **Fault:** identity conflict
- **Expected disposition:** CONFLICT_HOLD
- **Specific PASS:** Both hashes are retained and neither payload advances.
- **Specific FAIL:** Either payload overwrites the other or advances.
- **Regulatory release/transmission:** prohibited

### AT-006 - Unauthorized field role

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-006 is submitted by role_fixture VIEWER
- **Fault:** role denial
- **Expected disposition:** DENIED
- **Specific PASS:** No collection state is created and the denial is audited.
- **Specific FAIL:** The viewer creates or changes a sample.
- **Regulatory release/transmission:** prohibited

### AT-007 - Electronic custody initialized

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-007 includes collector, sample_id, container_id, method, and collection_time
- **Fault:** none
- **Expected disposition:** ACCEPTED
- **Specific PASS:** The initial custody node links to the collection receipt.
- **Specific FAIL:** Custody begins without a linked collection receipt.
- **Regulatory release/transmission:** prohibited

### AT-008 - Missing collector identity

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-008 omits actor_fixture
- **Fault:** accountability evidence missing
- **Expected disposition:** HOLD
- **Specific PASS:** No custody node is created and reason_code is ACTOR_REQUIRED.
- **Specific FAIL:** An anonymous collection enters the lifecycle.
- **Regulatory release/transmission:** prohibited

### AT-009 - Future-dated field timestamp

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-009 is 25 hours beyond the fixture clock
- **Fault:** synthetic clock anomaly
- **Expected disposition:** HOLD
- **Specific PASS:** The anomaly is explicit and requires human resolution.
- **Specific FAIL:** The event silently changes the authoritative sample time.
- **Regulatory release/transmission:** prohibited

### AT-010 - Certificate attachment pointer

- **Category:** field_collection
- **RFP basis:** S3_FIELD, S3_LIFECYCLE, S3_RBAC
- **Synthetic input:** FC-010 includes a synthetic COA hash and filename only
- **Fault:** none
- **Expected disposition:** ACCEPTED
- **Specific PASS:** The COA pointer is linked without treating its contents as a test result.
- **Specific FAIL:** The attachment is orphaned or used to release a result.
- **Regulatory release/transmission:** prohibited

### AT-011 - Ordered offline batch

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-001 sequence 1..5 for SAMPLE-011
- **Fault:** offline then reconnect
- **Expected disposition:** ACCEPTED
- **Specific PASS:** All five events apply once in sequence and cite one batch receipt.
- **Specific FAIL:** Any event is lost, duplicated, or applied out of sequence.
- **Regulatory release/transmission:** prohibited

### AT-012 - Offline duplicate replay

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-002 replays a previously committed 4-event batch
- **Fault:** full-batch duplicate
- **Expected disposition:** DUPLICATE_SUPPRESSED
- **Specific PASS:** Replay adds zero lifecycle effects and produces a replay receipt.
- **Specific FAIL:** Any second custody or result effect appears.
- **Regulatory release/transmission:** prohibited

### AT-013 - Out-of-order offline delivery

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-003 arrives sequence 3,1,2
- **Fault:** reordered delivery
- **Expected disposition:** ACCEPTED_AFTER_REORDER
- **Specific PASS:** Events apply as 1,2,3 using sequence evidence.
- **Specific FAIL:** Arrival order becomes authoritative lifecycle order.
- **Regulatory release/transmission:** prohibited

### AT-014 - Missing offline predecessor

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-004 contains sequence 1 and 3 but not 2
- **Fault:** sequence gap
- **Expected disposition:** HOLD
- **Specific PASS:** Sequence 3 does not apply and the missing predecessor is named.
- **Specific FAIL:** Sequence 3 advances before sequence 2.
- **Regulatory release/transmission:** prohibited

### AT-015 - Timeout before commit

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-005 loses acknowledgment before any commit marker
- **Fault:** timeout-before-commit
- **Expected disposition:** RETRY_SAFE
- **Specific PASS:** One bounded retry commits one effect.
- **Specific FAIL:** No retry occurs or more than one effect is committed.
- **Regulatory release/transmission:** prohibited

### AT-016 - Timeout after commit

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-006 loses acknowledgment after commit marker
- **Fault:** timeout-after-commit
- **Expected disposition:** RECONCILED_COMMITTED
- **Specific PASS:** Readback resolves the effect without a second write.
- **Specific FAIL:** A blind retry creates a duplicate effect.
- **Regulatory release/transmission:** prohibited

### AT-017 - Conflicting offline replay

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-007 reuses an event ID with changed result bytes
- **Fault:** payload conflict
- **Expected disposition:** CONFLICT_HOLD
- **Specific PASS:** Both hashes and the device sequence are retained; zero result effect applies.
- **Specific FAIL:** One payload silently wins.
- **Regulatory release/transmission:** prohibited

### AT-018 - Interrupted resume cursor

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-008 stops after 6 of 10 events then restarts
- **Fault:** client crash
- **Expected disposition:** ACCEPTED_AFTER_RESUME
- **Specific PASS:** Resume begins at event 7 and final count is exactly 10.
- **Specific FAIL:** Events 1..6 replay as new effects or 7..10 are lost.
- **Regulatory release/transmission:** prohibited

### AT-019 - Synthetic device clock skew

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-009 device time is 3 hours behind server fixture
- **Fault:** clock skew
- **Expected disposition:** ACCEPTED_WITH_CLOCK_EVIDENCE
- **Specific PASS:** Device and receipt times are both preserved; sequence remains authoritative.
- **Specific FAIL:** Device time overwrites receipt time or reorders custody.
- **Regulatory release/transmission:** prohibited

### AT-020 - Offline clean-room replay

- **Category:** offline_sync
- **RFP basis:** S3_FIELD, S3_STORAGE, S3_AUDIT
- **Synthetic input:** OS-010 runs the same 12-event batch in two fresh stores
- **Fault:** determinism check
- **Expected disposition:** ACCEPTED
- **Specific PASS:** Normalized final state and receipt hashes are byte-identical.
- **Specific FAIL:** The two clean runs differ in business state or normalized hashes.
- **Regulatory release/transmission:** prohibited

### AT-021 - Valid collect-transfer-receive chain

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-001 has three signed synthetic custody nodes
- **Fault:** none
- **Expected disposition:** ACCEPTED
- **Specific PASS:** The chain has one root, two valid predecessor links, and one current custodian.
- **Specific FAIL:** Any node is unlinked or two current custodians exist.
- **Regulatory release/transmission:** prohibited

### AT-022 - Missing transfer actor

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-002 transfer omits actor_fixture
- **Fault:** accountability gap
- **Expected disposition:** HOLD
- **Specific PASS:** The transfer does not change custody and ACTOR_REQUIRED is recorded.
- **Specific FAIL:** Custody changes anonymously.
- **Regulatory release/transmission:** prohibited

### AT-023 - Unauthorized recipient role

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-003 transfers to role_fixture VIEWER
- **Fault:** role denial
- **Expected disposition:** DENIED
- **Specific PASS:** The prior custodian remains authoritative and denial is logged.
- **Specific FAIL:** The unauthorized recipient becomes custodian.
- **Regulatory release/transmission:** prohibited

### AT-024 - Broken predecessor hash

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-004 references an unknown prior custody hash
- **Fault:** lineage break
- **Expected disposition:** HOLD
- **Specific PASS:** No custody transition applies and the missing hash is named.
- **Specific FAIL:** The chain is accepted with a broken link.
- **Regulatory release/transmission:** prohibited

### AT-025 - Duplicate custody handoff

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-005 submits the same transfer twice
- **Fault:** duplicate delivery
- **Expected disposition:** DUPLICATE_SUPPRESSED
- **Specific PASS:** Exactly one transfer exists and replay is receipted.
- **Specific FAIL:** Two transfers or two current custodians appear.
- **Regulatory release/transmission:** prohibited

### AT-026 - Out-of-order custody node

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-006 receive arrives before transfer
- **Fault:** reordered delivery
- **Expected disposition:** HOLD_PENDING_PREDECESSOR
- **Specific PASS:** Receive remains unapplied until the transfer arrives.
- **Specific FAIL:** Receive applies before the transfer.
- **Regulatory release/transmission:** prohibited

### AT-027 - Append-only custody correction

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-007 corrects a container label with reason and approver fixtures
- **Fault:** correction
- **Expected disposition:** ACCEPTED_AS_CORRECTION
- **Specific PASS:** Original and correction remain visible with linked hashes.
- **Specific FAIL:** Original evidence is overwritten or deleted.
- **Regulatory release/transmission:** prohibited

### AT-028 - Disposition before receipt

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-008 requests DISPOSED while sample is still IN_TRANSIT
- **Fault:** invalid lifecycle transition
- **Expected disposition:** DENIED
- **Specific PASS:** State remains IN_TRANSIT and transition rule is named.
- **Specific FAIL:** Disposition bypasses laboratory receipt.
- **Regulatory release/transmission:** prohibited

### AT-029 - Custody export completeness

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-009 exports a 7-node synthetic chain
- **Fault:** none
- **Expected disposition:** ACCEPTED
- **Specific PASS:** Export contains all seven ordered nodes and matches the ledger root hash.
- **Specific FAIL:** A node is missing, duplicated, or reordered.
- **Regulatory release/transmission:** prohibited

### AT-030 - Authorized void with reason

- **Category:** chain_of_custody
- **RFP basis:** S3_LIFECYCLE, S3_RBAC, S3_AUDIT
- **Synthetic input:** CC-010 requests VOID by role_fixture QA_MANAGER with reason
- **Fault:** none
- **Expected disposition:** VOIDED
- **Specific PASS:** Void is terminal, reasoned, role-checked, and append-only.
- **Specific FAIL:** Void erases prior custody or lacks reason/authority.
- **Regulatory release/transmission:** prohibited

### AT-031 - Valid laboratory receipt

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-001 receives SAMPLE-031 with container and method fixtures
- **Fault:** none
- **Expected disposition:** RECEIVED
- **Specific PASS:** One accession receipt links to the final field custody node.
- **Specific FAIL:** Receipt is missing or creates a second sample identity.
- **Regulatory release/transmission:** prohibited

### AT-032 - Duplicate laboratory receipt

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-002 submits the same accession twice
- **Fault:** duplicate delivery
- **Expected disposition:** DUPLICATE_SUPPRESSED
- **Specific PASS:** One RECEIVED state exists and the replay adds zero effects.
- **Specific FAIL:** Two accession records exist.
- **Regulatory release/transmission:** prohibited

### AT-033 - Sample ID metadata conflict

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-003 reuses sample_id with a different container_id
- **Fault:** identity conflict
- **Expected disposition:** CONFLICT_HOLD
- **Specific PASS:** Both hashes are preserved and neither becomes authoritative.
- **Specific FAIL:** Existing metadata is silently replaced.
- **Regulatory release/transmission:** prohibited

### AT-034 - Missing requested analysis

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-004 has no method/analyte request
- **Fault:** required mapping missing
- **Expected disposition:** HOLD
- **Specific PASS:** Sample is traceable but ineligible for analysis until mapped.
- **Specific FAIL:** Analysis begins without a requested method.
- **Regulatory release/transmission:** prohibited

### AT-035 - Damaged container

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-005 has synthetic condition DAMAGED
- **Fault:** receipt exception
- **Expected disposition:** HOLD
- **Specific PASS:** Condition, reason, actor, and owner are recorded.
- **Specific FAIL:** Damaged sample silently enters analysis.
- **Regulatory release/transmission:** prohibited

### AT-036 - Unscheduled sample

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-006 has no schedule fixture
- **Fault:** schedule exception
- **Expected disposition:** MANUAL_REVIEW
- **Specific PASS:** The sample is retained without invented schedule approval.
- **Specific FAIL:** The system invents a schedule or rejects without trace.
- **Regulatory release/transmission:** prohibited

### AT-037 - COA upload linkage

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-007 includes a synthetic chemical-inventory COA hash
- **Fault:** none
- **Expected disposition:** RECEIVED
- **Specific PASS:** COA is stored as evidence and linked to its inventory fixture.
- **Specific FAIL:** COA is orphaned or treated as regulatory result evidence.
- **Regulatory release/transmission:** prohibited

### AT-038 - Corrupt COA bytes

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-008 attachment hash does not match bytes
- **Fault:** integrity failure
- **Expected disposition:** HOLD
- **Specific PASS:** Attachment is quarantined and the sample state is unchanged.
- **Specific FAIL:** Corrupt bytes are stored as valid evidence.
- **Regulatory release/transmission:** prohibited

### AT-039 - Authorized rejection

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-009 role_fixture RECEIVING_LEAD rejects with reason BROKEN_SEAL
- **Fault:** none
- **Expected disposition:** REJECTED
- **Specific PASS:** One terminal rejection cites actor, role, reason, and source receipt.
- **Specific FAIL:** Rejection lacks authority/reason or deletes prior custody.
- **Regulatory release/transmission:** prohibited

### AT-040 - Orphan result before sample

- **Category:** sample_receipt_and_disposition
- **RFP basis:** S3_LIFECYCLE, S3_QC, S3_COA
- **Synthetic input:** SR-010 result references unknown SAMPLE-040
- **Fault:** orphan event
- **Expected disposition:** HOLD
- **Specific PASS:** No sample is invented; event waits with SAMPLE_NOT_FOUND.
- **Specific FAIL:** A phantom sample/result enters reports.
- **Regulatory release/transmission:** prohibited

### AT-041 - QC pass awaiting human release

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-001 result and synthetic QC controls meet fixture limits
- **Fault:** none
- **Expected disposition:** ELIGIBLE_FOR_HUMAN_RELEASE
- **Specific PASS:** Eligibility is recorded but result remains unreleased.
- **Specific FAIL:** The system changes regulatory release state.
- **Regulatory release/transmission:** prohibited

### AT-042 - QC control out of range

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-002 positive control exceeds synthetic upper limit
- **Fault:** bad QC
- **Expected disposition:** QC_HOLD
- **Specific PASS:** Release eligibility is false and the exact failed control is named.
- **Specific FAIL:** The result becomes eligible or released.
- **Regulatory release/transmission:** prohibited

### AT-043 - Blank contamination

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-003 blank fixture exceeds its limit
- **Fault:** bad QC
- **Expected disposition:** QC_HOLD
- **Specific PASS:** Affected batch and results are held with one reasoned linkage.
- **Specific FAIL:** Only the blank is held while affected results pass.
- **Regulatory release/transmission:** prohibited

### AT-044 - Expired analyst capability

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-004 analyst fixture capability expired before run
- **Fault:** capability lapse
- **Expected disposition:** DENIED
- **Specific PASS:** Result entry/review is blocked and capability evidence is cited.
- **Specific FAIL:** Expired capability is ignored.
- **Regulatory release/transmission:** prohibited

### AT-045 - Missing analyst method capability

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-005 analyst fixture lacks the requested method
- **Fault:** capability missing
- **Expected disposition:** DENIED
- **Specific PASS:** No result effect applies and method capability is named.
- **Specific FAIL:** A generic role substitutes for method capability.
- **Regulatory release/transmission:** prohibited

### AT-046 - Retest linked to original

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-006 retest references failed QC-002
- **Fault:** none
- **Expected disposition:** RETEST_RECORDED
- **Specific PASS:** Original remains held; retest has its own receipt and predecessor link.
- **Specific FAIL:** Retest overwrites or hides the original.
- **Regulatory release/transmission:** prohibited

### AT-047 - Duplicate retest event

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-007 replays the same retest
- **Fault:** duplicate delivery
- **Expected disposition:** DUPLICATE_SUPPRESSED
- **Specific PASS:** Exactly one retest exists.
- **Specific FAIL:** A second retest/result is created.
- **Regulatory release/transmission:** prohibited

### AT-048 - QC rule version drift

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-008 result evaluated under v1 then fixture changes to v2
- **Fault:** rule drift
- **Expected disposition:** REVIEW_REQUIRED
- **Specific PASS:** Cached v1 eligibility is invalidated and both versions remain visible.
- **Specific FAIL:** Stale v1 eligibility remains authoritative.
- **Regulatory release/transmission:** prohibited

### AT-049 - Unauthorized release request

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-009 role_fixture ANALYST requests regulatory release
- **Fault:** role denial
- **Expected disposition:** DENIED
- **Specific PASS:** Release count remains zero and denial is audited.
- **Specific FAIL:** The analyst releases or transmits the result.
- **Regulatory release/transmission:** prohibited

### AT-050 - Authorized human approval boundary

- **Category:** qc_retest_authorized_release
- **RFP basis:** S3_ANALYST, S3_QC, S3_RBAC, WORK_ORDER_BOUNDARY
- **Synthetic input:** QC-010 role_fixture QA_MANAGER records approval intent
- **Fault:** none
- **Expected disposition:** HUMAN_RELEASE_APPROVAL_RECORDED
- **Specific PASS:** Approval intent is receipted while system release/transmission counts stay zero.
- **Specific FAIL:** The system equates approval intent with regulatory release.
- **Regulatory release/transmission:** prohibited

### AT-051 - pH meter normal mock import

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-001 mock source PH-METER-01 reports synthetic pH under SM 4500-H+ B
- **Fault:** none
- **Expected disposition:** INGESTED
- **Specific PASS:** One normalized result links source bytes, mapping version, sample, and method.
- **Specific FAIL:** Import loses source evidence or creates multiple results.
- **Regulatory release/transmission:** prohibited

### AT-052 - Balance duplicate delivery

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-002 BALANCE-01 sends the same synthetic weight twice
- **Fault:** duplicate delivery
- **Expected disposition:** DUPLICATE_SUPPRESSED
- **Specific PASS:** One result exists and the replay adds zero effects.
- **Specific FAIL:** Two weight results exist.
- **Regulatory release/transmission:** prohibited

### AT-053 - Furnace AA out-of-order batch

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-003 AA-FURNACE mock results arrive 3,1,2
- **Fault:** reordered delivery
- **Expected disposition:** INGESTED_AFTER_REORDER
- **Specific PASS:** Results apply in source sequence with all raw hashes retained.
- **Specific FAIL:** Arrival order silently changes sample/result ordering.
- **Regulatory release/transmission:** prohibited

### AT-054 - Ion chromatograph bad QC

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-004 METROHM-IC mock batch includes failed QC
- **Fault:** bad QC
- **Expected disposition:** QC_HOLD
- **Specific PASS:** All affected synthetic analyte results are held.
- **Specific FAIL:** Failed-QC results become report eligible.
- **Regulatory release/transmission:** prohibited

### AT-055 - TOC timeout after commit

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-005 SIEVERS-TOC mock loses acknowledgment after commit
- **Fault:** timeout-after-commit
- **Expected disposition:** RECONCILED_COMMITTED
- **Specific PASS:** Commit readback prevents a second result write.
- **Specific FAIL:** Retry creates a duplicate result.
- **Regulatory release/transmission:** prohibited

### AT-056 - Discrete analyzer malformed payload

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-006 SEAL-DISCRETE mock omits sample_id
- **Fault:** schema failure
- **Expected disposition:** HOLD
- **Specific PASS:** Raw bytes are quarantined with MISSING_SAMPLE_ID.
- **Specific FAIL:** Malformed payload enters the result ledger.
- **Regulatory release/transmission:** prohibited

### AT-057 - Unknown instrument source

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-007 source INSTRUMENT-UNKNOWN sends a result
- **Fault:** unmapped source
- **Expected disposition:** HOLD
- **Specific PASS:** No compatibility is inferred and INSTRUMENT_MAPPING_REQUIRED is recorded.
- **Specific FAIL:** The system guesses a parser or method.
- **Regulatory release/transmission:** prohibited

### AT-058 - Instrument mapping drift

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-008 parser mapping changes from fixture v1 to v2 mid-batch
- **Fault:** mapping drift
- **Expected disposition:** REVIEW_REQUIRED
- **Specific PASS:** Mixed-version results are named and held pending review.
- **Specific FAIL:** Mixed versions appear as one homogeneous batch.
- **Regulatory release/transmission:** prohibited

### AT-059 - Blank method in Attachment F fixture

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-009 synthetic Paint Filter Test has no official method string
- **Fault:** official mapping absent
- **Expected disposition:** HOLD
- **Specific PASS:** The missing buyer-approved method is explicit; no method is invented.
- **Specific FAIL:** A method is guessed or compatibility claimed.
- **Regulatory release/transmission:** prohibited

### AT-060 - Multi-instrument reconciliation

- **Category:** instrument_ingest
- **RFP basis:** S3_INSTRUMENT, S3_QC, AF_INSTRUMENTS, AF_METHODS
- **Synthetic input:** II-010 imports 12 synthetic events across all named mock instrument families
- **Fault:** none
- **Expected disposition:** INGESTED
- **Specific PASS:** Input count equals ingested plus held plus duplicate-suppressed; no orphan event remains.
- **Specific FAIL:** Counts do not reconcile or any event disappears.
- **Regulatory release/transmission:** prohibited

### AT-061 - Complete lifecycle audit export

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-001 exports SAMPLE-061 from collection through QC hold
- **Fault:** none
- **Expected disposition:** EXPORTED
- **Specific PASS:** Every transition includes actor, role, time, rule version, and predecessor hash.
- **Specific FAIL:** Any lifecycle change lacks attribution or ordering.
- **Regulatory release/transmission:** prohibited

### AT-062 - Append-only correction audit

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-002 exports an original value plus reasoned correction
- **Fault:** none
- **Expected disposition:** EXPORTED
- **Specific PASS:** Both values and the correction link are present.
- **Specific FAIL:** Original evidence is overwritten.
- **Regulatory release/transmission:** prohibited

### AT-063 - Unauthorized attempt audit

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-003 includes a denied release attempt
- **Fault:** role denial
- **Expected disposition:** EXPORTED
- **Specific PASS:** Denial, actor fixture, role fixture, reason, and zero effect are present.
- **Specific FAIL:** Denied attempt is missing or appears successful.
- **Regulatory release/transmission:** prohibited

### AT-064 - Duplicate delivery audit

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-004 includes one accepted event and two replays
- **Fault:** duplicate delivery
- **Expected disposition:** EXPORTED
- **Specific PASS:** One business effect and two replay receipts are distinguishable.
- **Specific FAIL:** Replays are invisible or become effects.
- **Regulatory release/transmission:** prohibited

### AT-065 - Tampered receipt hash

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-005 alters one stored receipt byte before export
- **Fault:** integrity failure
- **Expected disposition:** EXPORT_BLOCKED
- **Specific PASS:** Hash mismatch names the exact receipt and no clean export is claimed.
- **Specific FAIL:** Tampered export is reported valid.
- **Regulatory release/transmission:** prohibited

### AT-066 - Configuration change audit

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-006 changes synthetic QC rule v1 to v2
- **Fault:** none
- **Expected disposition:** EXPORTED
- **Specific PASS:** Old/new hashes, actor, approval fixture, and effective time are present.
- **Specific FAIL:** Configuration change is unattributed.
- **Regulatory release/transmission:** prohibited

### AT-067 - Role change audit

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-007 changes ANALYST to QA_REVIEWER
- **Fault:** none
- **Expected disposition:** EXPORTED
- **Specific PASS:** Role grant/revoke evidence and effective boundary are present.
- **Specific FAIL:** Prior actions are relabeled under the new role.
- **Regulatory release/transmission:** prohibited

### AT-068 - Instrument mapping change audit

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-008 changes mock IC parser mapping
- **Fault:** none
- **Expected disposition:** EXPORTED
- **Specific PASS:** Both mapping versions and affected result IDs are listed.
- **Specific FAIL:** Mapping drift is hidden.
- **Regulatory release/transmission:** prohibited

### AT-069 - Redundancy restore audit

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-009 restores the synthetic store from backup fixture
- **Fault:** restore drill
- **Expected disposition:** EXPORTED
- **Specific PASS:** Restore point, source hash, resulting root hash, and gaps are explicit.
- **Specific FAIL:** Restore is called successful without reconciliation.
- **Regulatory release/transmission:** prohibited

### AT-070 - Deterministic export replay

- **Category:** audit_export
- **RFP basis:** S3_AUDIT, S3_RBAC, S7_SECURITY
- **Synthetic input:** AE-010 exports the same frozen ledger twice
- **Fault:** determinism check
- **Expected disposition:** EXPORTED
- **Specific PASS:** Normalized exports are byte-identical.
- **Specific FAIL:** Equivalent ledgers produce differing normalized exports.
- **Regulatory release/transmission:** prohibited

### AT-071 - CMDP draft count reconciliation

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-001 builds a synthetic CMDP draft from 10 eligible results
- **Fault:** none
- **Expected disposition:** DRAFT_READY_FOR_HUMAN_REVIEW
- **Specific PASS:** Draft count and values match the eligible-result manifest; release count is zero.
- **Specific FAIL:** Draft omits/adds results or is transmitted.
- **Regulatory release/transmission:** prohibited

### AT-072 - netDMR draft count reconciliation

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-002 builds a synthetic netDMR draft from 8 eligible results
- **Fault:** none
- **Expected disposition:** DRAFT_READY_FOR_HUMAN_REVIEW
- **Specific PASS:** Draft exactly matches the manifest and remains untransmitted.
- **Specific FAIL:** Totals differ or transmission occurs.
- **Regulatory release/transmission:** prohibited

### AT-073 - Operations dashboard reconciliation

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-003 renders synthetic dashboard aggregates
- **Fault:** none
- **Expected disposition:** DASHBOARD_RECONCILED
- **Specific PASS:** Dashboard totals equal ledger totals by state.
- **Specific FAIL:** Dashboard totals differ or hide held/unknown states.
- **Regulatory release/transmission:** prohibited

### AT-074 - Orphan sample blocks report

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-004 includes a result for unknown sample_id
- **Fault:** orphan event
- **Expected disposition:** REPORT_HOLD
- **Specific PASS:** Orphan is named and draft sign-off is blocked.
- **Specific FAIL:** Orphan appears in a report or disappears.
- **Regulatory release/transmission:** prohibited

### AT-075 - Duplicate result suppression in report

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-005 includes an exact duplicate instrument result
- **Fault:** duplicate delivery
- **Expected disposition:** DRAFT_READY_FOR_HUMAN_REVIEW
- **Specific PASS:** Duplicate contributes zero second count/value.
- **Specific FAIL:** Duplicate inflates the report.
- **Regulatory release/transmission:** prohibited

### AT-076 - QC-held result accounting

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-006 includes three eligible and two QC-held results
- **Fault:** none
- **Expected disposition:** DRAFT_READY_FOR_HUMAN_REVIEW
- **Specific PASS:** Eligible=3, held=2, total=5 with held results excluded from report values.
- **Specific FAIL:** Held results are released, omitted from accounting, or included in values.
- **Regulatory release/transmission:** prohibited

### AT-077 - Rule-version-specific report

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-007 spans synthetic method/rule v1 and v2
- **Fault:** version boundary
- **Expected disposition:** DRAFT_READY_FOR_HUMAN_REVIEW
- **Specific PASS:** Every value cites the applied version; no silent cross-version merge occurs.
- **Specific FAIL:** Version provenance is missing.
- **Regulatory release/transmission:** prohibited

### AT-078 - Corrupt report export

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-008 alters one output byte after rendering
- **Fault:** integrity failure
- **Expected disposition:** REPORT_HOLD
- **Specific PASS:** Output hash mismatch blocks sign-off.
- **Specific FAIL:** Corrupt export is treated as final.
- **Regulatory release/transmission:** prohibited

### AT-079 - Sample-result-report tri-ledger

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-009 reconciles 20 samples, 24 results, and 2 draft reports
- **Fault:** none
- **Expected disposition:** RECONCILED
- **Specific PASS:** Every sample/result is accounted for once and report membership is explicit.
- **Specific FAIL:** Any orphan, duplicate membership, or unexplained count exists.
- **Regulatory release/transmission:** prohibited

### AT-080 - No autonomous regulatory release

- **Category:** report_reconciliation
- **RFP basis:** S3_REPORTS, AF_REPORTS, S3_QC, WORK_ORDER_BOUNDARY
- **Synthetic input:** RR-010 requests SEND on a complete synthetic CMDP draft
- **Fault:** prohibited action test
- **Expected disposition:** DENIED
- **Specific PASS:** Transmission and release counts remain zero; human-owned next step is explicit.
- **Specific FAIL:** Any external send, release, or claim of submission occurs.
- **Regulatory release/transmission:** prohibited

### AT-081 - Field collector cannot release

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-001 role_fixture FIELD_COLLECTOR requests release
- **Fault:** role denial
- **Expected disposition:** DENIED
- **Specific PASS:** Collection permission remains separate from release permission.
- **Specific FAIL:** Collector changes release state.
- **Regulatory release/transmission:** prohibited

### AT-082 - Analyst cannot administer roles

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-002 role_fixture ANALYST changes another role
- **Fault:** role denial
- **Expected disposition:** DENIED
- **Specific PASS:** Role registry is unchanged and denial is audited.
- **Specific FAIL:** Analyst grants or revokes access.
- **Regulatory release/transmission:** prohibited

### AT-083 - QA reviewer can place hold

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-003 role_fixture QA_REVIEWER holds failed QC
- **Fault:** none
- **Expected disposition:** QC_HOLD
- **Specific PASS:** Hold succeeds with actor, reason, and rule evidence.
- **Specific FAIL:** Authorized hold fails silently or releases result.
- **Regulatory release/transmission:** prohibited

### AT-084 - Viewer cannot edit result

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-004 role_fixture VIEWER edits result bytes
- **Fault:** role denial
- **Expected disposition:** DENIED
- **Specific PASS:** Result hash is unchanged.
- **Specific FAIL:** Viewer changes the result.
- **Regulatory release/transmission:** prohibited

### AT-085 - Inactive user denied

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-005 actor_fixture status is INACTIVE
- **Fault:** account disabled
- **Expected disposition:** DENIED
- **Specific PASS:** All mutating actions are denied and logged.
- **Specific FAIL:** Inactive user changes state.
- **Regulatory release/transmission:** prohibited

### AT-086 - Role change effective boundary

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-006 grant becomes effective after event 3
- **Fault:** role transition
- **Expected disposition:** DENIED_THEN_ALLOWED
- **Specific PASS:** Events 1..3 use old role; event 4 uses new role with grant receipt.
- **Specific FAIL:** Role is applied retroactively or before effective time.
- **Regulatory release/transmission:** prohibited

### AT-087 - Method-specific capability denial

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-007 analyst role exists but method capability does not
- **Fault:** capability missing
- **Expected disposition:** DENIED
- **Specific PASS:** Method-level capability gate blocks the action.
- **Specific FAIL:** Generic analyst role bypasses method capability.
- **Regulatory release/transmission:** prohibited

### AT-088 - Session actor mismatch

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-008 token fixture actor differs from payload actor
- **Fault:** identity mismatch
- **Expected disposition:** DENIED
- **Specific PASS:** No effect applies and both fixture identities are logged.
- **Specific FAIL:** Payload actor overrides session actor.
- **Regulatory release/transmission:** prohibited

### AT-089 - Restricted audit export

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-009 role_fixture FIELD_COLLECTOR requests full audit export
- **Fault:** role denial
- **Expected disposition:** DENIED
- **Specific PASS:** No export bytes are produced and denial is receipted.
- **Specific FAIL:** Restricted data is exported.
- **Regulatory release/transmission:** prohibited

### AT-090 - Denial replay

- **Category:** role_denial_and_accountability
- **RFP basis:** S3_RBAC, S3_AUDIT, S3_ANALYST
- **Synthetic input:** RD-010 replays the same unauthorized action
- **Fault:** duplicate denial
- **Expected disposition:** DENIED
- **Specific PASS:** No business effect occurs; attempts remain countable without duplicate state.
- **Specific FAIL:** Replay changes state or erases first denial.
- **Regulatory release/transmission:** prohibited

### AT-091 - Exact input retry

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-001 retries an accepted collection event
- **Fault:** duplicate delivery
- **Expected disposition:** DUPLICATE_SUPPRESSED
- **Specific PASS:** Retry adds zero business effects.
- **Specific FAIL:** A second sample/custody effect exists.
- **Regulatory release/transmission:** prohibited

### AT-092 - Timeout before write

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-002 times out before commit marker
- **Fault:** timeout-before-commit
- **Expected disposition:** RETRY_SAFE
- **Specific PASS:** One bounded retry produces one effect.
- **Specific FAIL:** Effect is lost or duplicated.
- **Regulatory release/transmission:** prohibited

### AT-093 - Timeout after write

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-003 times out after commit marker
- **Fault:** timeout-after-commit
- **Expected disposition:** RECONCILED_COMMITTED
- **Specific PASS:** Readback confirms commit and no second write occurs.
- **Specific FAIL:** Blind retry duplicates the effect.
- **Regulatory release/transmission:** prohibited

### AT-094 - Crash after custody append

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-004 process crashes after append but before acknowledgment
- **Fault:** process crash
- **Expected disposition:** RECONCILED_COMMITTED
- **Specific PASS:** Restart finds the receipt and advances once.
- **Specific FAIL:** Restart appends a second custody node.
- **Regulatory release/transmission:** prohibited

### AT-095 - Report renderer retry

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-005 renderer crashes after draft bytes are stored
- **Fault:** process crash
- **Expected disposition:** RECONCILED_COMMITTED
- **Specific PASS:** Stored hash is reused or verified; one canonical draft remains.
- **Specific FAIL:** Two divergent canonical drafts appear.
- **Regulatory release/transmission:** prohibited

### AT-096 - Offline partition recovery

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-006 two devices reconnect with overlapping event sets
- **Fault:** network partition
- **Expected disposition:** RECONCILED
- **Specific PASS:** Union is exact; duplicates add zero effects; conflicts hold.
- **Specific FAIL:** Events disappear or conflicts silently resolve.
- **Regulatory release/transmission:** prohibited

### AT-097 - Instrument adapter restart

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-007 mock adapter restarts at event 6 of 10
- **Fault:** adapter crash
- **Expected disposition:** INGESTED_AFTER_RESUME
- **Specific PASS:** Resume cursor begins at 6/7 boundary and final count is 10.
- **Specific FAIL:** Events are skipped or duplicated.
- **Regulatory release/transmission:** prohibited

### AT-098 - Stale recovery cursor

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-008 resume cursor points behind committed root
- **Fault:** stale cursor
- **Expected disposition:** RECONCILED
- **Specific PASS:** Committed IDs are checked before replay and add zero effects.
- **Specific FAIL:** Stale cursor duplicates prior work.
- **Regulatory release/transmission:** prohibited

### AT-099 - Full-corpus clean replay

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-009 runs all 100 cases twice against fresh stores
- **Fault:** determinism check
- **Expected disposition:** RECONCILED
- **Specific PASS:** Normalized dispositions and root hashes are identical.
- **Specific FAIL:** Any business outcome or normalized root differs.
- **Regulatory release/transmission:** prohibited

### AT-100 - Configuration rollback

- **Category:** retry_replay_and_recovery
- **RFP basis:** S3_STORAGE, S3_AUDIT, S3_INSTRUMENT, S7_SECURITY
- **Synthetic input:** RRR-010 rolls synthetic rule v2 back to v1
- **Fault:** rollback
- **Expected disposition:** REVIEW_REQUIRED
- **Specific PASS:** Both versions remain auditable; caches invalidate; affected samples are re-evaluated without automatic release.
- **Specific FAIL:** Rollback erases v2 evidence or auto-releases results.
- **Regulatory release/transmission:** prohibited

## Blockers / Buyer-Owned Inputs

- The RFP names instruments but does not provide wire protocols, export formats, firmware/software versions, or vendor interface specifications; mock adapters cannot prove compatibility.
- The RFP does not define the City-approved role matrix, QC thresholds, method-version authority, report schemas, retention schedule, RTO/RPO, or support SLAs; fixtures must be replaced with buyer-owned values.
- Section 7 requires independent security evidence and annual NIST or FedRAMP assessment reports; this corpus supplies no audit, certification, scan, or assurance statement.
- Attachment F contains blank method cells for Paint Filter Test and Volatile Acids; the corpus must hold those mappings rather than invent methods.
- This artifact validates a future nonproduction test harness only; it is not proposal eligibility, product delivery, regulatory compliance, or a City submission.

## Non-Claims

No City or prospect contact, bid submission, instrument compatibility, customer reference, security certification, independent audit, production deployment, regulatory release, or external transmission is claimed. No secrets or live data are present.
