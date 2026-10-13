# City of Billings Bid 1421 — AquaTrace LIMS Operations Package

Status: **INTERNAL PROPOSAL-OPERATIONS DRAFT — NOT SUBMITTED, NOT DELIVERED**  
Lane: `billings-bid-1421-operations-package-20260831-01`  
Source of truth: City of Billings official bid page and official RFP packet only.

- Official bid page: https://billingsmt.gov/bids.aspx?bidID=1421
- Official RFP packet: https://billingsmt.gov/DocumentCenter/View/56340/2026-LIMS-RFP
- RFP deadline shown by the City: September 4, 2026, 5:00 PM MST.

## Truth boundary and status vocabulary

This package does not assert that AquaTrace is deployed, certified, secure, compatible with a named instrument, supported to a particular SLA, or compliant with NIST/FedRAMP. It is an operations plan for work that would begin only after award and contract execution.

- `RFP_SOURCE_FACT`: stated by the official RFP.
- `PLANNED_AFTER_AWARD`: proposed activity or artifact; not currently delivered.
- `BUYER_INPUT_REQUIRED`: cannot be finalized without City/laboratory-owned information or approval.
- `CANNOT_CLAIM`: no present evidence supports the claim; exclude it from the proposal unless evidence is obtained and reviewed.

## 1. Implementation discovery checklist

All discovery outputs are `PLANNED_AFTER_AWARD`. Buyer inputs are `BUYER_INPUT_REQUIRED`.

| Workstream | Discovery questions / buyer inputs | Planned output | Acceptance evidence | Owner |
|---|---|---|---|---|
| Governance | Contract liaison; executive sponsor; lab, IT, security, records, and regulatory owners; decision and escalation matrix | Named RACI and decision log | City-approved owner matrix and meeting record | Joint implementation lead + City sponsor |
| Environments | Approved hosting/tenancy; nonproduction and production separation; network paths; IdP; endpoint and browser standards | Environment and connectivity design | City approval plus synthetic connectivity checks | Vendor platform lead + City IT |
| Field/offline | Field locations; devices; offline duration; conflict rules; custody signatures; reconnect behavior | Offline collection and reconciliation design | Synthetic disconnect/reconnect replay with no duplicate custody event | Product lead + lab field owner |
| Sample lifecycle | Sample identifiers; collection, receipt, preservation, hold, disposal, retest, release, and disposition rules | Buyer-approved lifecycle state map | Signed state-transition map and synthetic edge-case replay | LIMS configuration lead + lab QA |
| Scheduling | Work queues, forecasting horizons, calendars, turnaround targets, priority rules | Scheduling/forecasting configuration workbook | Buyer-approved fixtures and expected queue results | Configuration lead + lab operations |
| Analyst qualification | Methods, demonstrations of capability, training/certification records, expiration and hold rules | Analyst-method authorization matrix | Synthetic unauthorized-method denial and renewal fixture | Training lead + lab QA |
| QC/QA | Control samples, blanks, spikes, duplicates, limits, chart rules, retest and release authority | QC rule and charting catalog | Buyer-approved synthetic QC cases including failed QC and retest | QA configuration lead + lab QA |
| Instruments | Exact model, serial, firmware, software, export format/protocol, units, timestamps, identifier keys, and vendor support status for each Attachment F device | Per-instrument interface contract and test plan | Sample files/messages, protocol evidence, synthetic import/retry tests | Integration lead + lab instrument owner |
| Chemical inventory | Certificate-of-analysis source, metadata, version/replacement, retention, and access rules | COA storage/index specification | Synthetic upload, supersession, permission, and retrieval tests | Configuration lead + chemical inventory owner |
| Reporting | City-approved CMDP, netDMR, client/internal templates; Power BI/data-export needs; signoff and correction rules | Report and reconciliation catalog | Gold synthetic reports tied to exact source results | Reporting lead + regulatory owner |
| Records | Retention, legal hold, public-record, export, deletion, and archive rules | Records and audit-export plan | City approval plus synthetic export/retrieval exercise | Records lead + City records/security |
| Migration | Source systems, volumes, schema, attachments, quality problems, cutoff and rollback criteria | Migration mapping and reconciliation plan | Record-count/hash reconciliation and signed exceptions | Data lead + City data owner |
| Support | Hours, channels, severity rules, authorized requesters, maintenance windows, notice periods | Support handbook and escalation matrix | Tabletop incident exercise and contact-tree acknowledgement | Support lead + Contract Liaison |
| DR | Buyer-approved RTO/RPO, backup locations, encryption/key ownership, recovery authority, exercise cadence | Backup/restore and DR test plan | Restore drill with timestamps, hashes, reconciliation, and signed result | Platform/SRE lead + City IT/security |

### Required discovery exit gate

Implementation may advance only when the City has approved the owner matrix, lifecycle states, role matrix, reporting catalog, instrument inventory, nonproduction boundary, migration plan, support model, and DR objectives. Any unresolved item remains a visible `HOLD`; it is not silently assumed.

## 2. Lab-owned configuration intake

Each row is `BUYER_INPUT_REQUIRED`. The City remains authority for laboratory methods, QC rules, regulatory meaning, release decisions, roles, retention, and production access.

| Configuration domain | Required fields | Validation rule |
|---|---|---|
| Organization/site | site, facility, laboratory, collection location, timezone, active dates, owner | Unknown or duplicate canonical identifier is held |
| Method/analyte | analyte, exact method/version, matrix, units, preparation, detection/reporting limits, effective dates | No inferred method, unit, or regulatory status |
| Sample type | container, preservation, volume, hold time, storage, custody requirements | Missing preservation/hold rule blocks configuration release |
| Lifecycle | allowed states, transitions, required evidence, approver role, correction path | Illegal transition fails closed and is logged |
| QC | control type, batch rule, frequency, limits, calculation, chart, failure/retest/release authority | No automatic regulatory release; failed/unknown QC routes to authorized human |
| Analyst authorization | person/role, method, demonstration/training, effective/expiry dates, exception owner | Expired or absent authorization denies method work |
| Instrument | manufacturer, exact model, serial, firmware, software, protocol/file format, clock/timezone, units, identifiers, vendor contact | Attachment F's category name alone is insufficient evidence of compatibility |
| Report | template/version, destination, field mapping, approval, correction/resubmission, reconciliation rule | Generated output remains draft until authorized release |
| Security/role | IdP group, application role, site/data scope, allowed verbs, separation-of-duties conflicts, approver, review date | Deny by default; no self-approval for controlled changes or release |
| Retention | record class, retention, legal hold, archive/export, deletion authority | No deletion rule is activated without City approval |

## 3. Training outline

Training is `PLANNED_AFTER_AWARD`; roster, shifts, role groups, delivery format, and completion criteria are `BUYER_INPUT_REQUIRED`.

1. **Role-based orientation** — navigation, search, help/knowledge base, session safety, and support route.
2. **Field/offline collection** — sample creation, custody evidence, offline state, conflict/reconnect handling, and device-loss escalation.
3. **Sample receipt and laboratory workflow** — accessioning, custody transfer, preservation/hold checks, assignments, disposition, and corrections.
4. **Analyst execution** — method authorization check, result entry/import, calculation review, evidence attachment, and error correction.
5. **QC/QA** — controls, charts, failed-QC hold, retest lineage, exception review, and human release authority.
6. **Instrument operations** — per-approved-adapter import, duplicate/out-of-order handling, timeout/unknown-effect reconciliation, and manual exception queue.
7. **Reporting** — draft generation, source-result reconciliation, CMDP/netDMR/client/internal review, correction, approval, and export receipt.
8. **Administration and security** — role assignment, separation of duties, audit review, retention/export, and controlled configuration change.
9. **Support and continuity** — knowledge base, ticket evidence, severity classification, maintenance notice, backup/DR responsibilities, and incident tabletop.

Planned training evidence: versioned materials, attendance, role/module completion, knowledge check, supervised role exercise, unresolved-question log, and City signoff. Completion does not equal analyst certification unless the City explicitly defines and approves that rule.

## 4. Support and escalation runbook

This runbook is `PLANNED_AFTER_AWARD`. Hours, response/resolution targets, communication channels, maintenance windows, and named contacts are `BUYER_INPUT_REQUIRED`; no SLA is presently claimed.

| Step | Required action | Durable evidence |
|---|---|---|
| Intake | Authenticate authorized requester; capture environment, impact, time, correlation/sample ID, screenshots/log references without unnecessary sensitive data | Ticket ID and intake receipt |
| Triage | Classify severity using City-approved definitions; separate configuration, data, integration, security, availability, and user guidance | Classification, owner, timestamp, rationale |
| Contain | Preserve evidence; pause unsafe integration/release path; avoid unauthorized scanning or access | Containment action and approver |
| Investigate | Reproduce in approved nonproduction with synthetic/redacted fixtures; link exact build/config/log versions | Reproduction record and evidence hashes |
| Reconcile | For timeout-after-commit or unknown external effect, query authoritative state before retry; never duplicate sample/result/report effects | Expected/observed state and reconciliation disposition |
| Escalate | Route security/privacy events to City security; regulatory/reporting issues to City regulatory owner; instrument issues to approved instrument owner/vendor | Escalation acknowledgement |
| Restore | Apply buyer-approved fix/workaround; verify affected workflow and adjacent controls | Test results, approver, release receipt |
| Close | Buyer confirms service/result; capture root cause, prevention, follow-up owner, and due date | Closure and post-incident receipt |

Maintenance updates require a change record, test evidence, rollback plan, City-approved window, notice, post-change checks, and closure receipt. Emergency change authority must be defined by the City before use.

## 5. Backup and disaster-recovery test-evidence outline

All controls and exercises below are `PLANNED_AFTER_AWARD`. No current backup topology, RTO, RPO, encryption, restore success, redundancy, or disaster-recovery capability is claimed.

1. **Buyer objectives** (`BUYER_INPUT_REQUIRED`): service tiers, RTO/RPO, critical records, geographic/tenancy constraints, key ownership, retention, restore authority, and communications.
2. **Backup inventory**: database, attachments/COAs, audit logs, configuration, report templates, integration state, identity/role mapping, and runbooks; record schedule, location, encryption, immutability, and retention.
3. **Routine evidence**: job ID, start/end, byte/record counts, encrypted artifact identifier, checksum, failure/exception, retry, and review owner.
4. **Restore exercise**: restore to isolated nonproduction; verify sample/custody/result/QC/audit/config/integration counts and hashes; confirm role denial; run a synthetic end-to-end workflow; document gaps.
5. **Disaster scenario exercise**: declare scenario, invoke owners, restore approved point, reconcile events after that point, hold unknown effects, validate reports, measure actual RTO/RPO, and obtain City signoff.
6. **Fail criteria**: missing artifact, checksum mismatch, unapproved access, unreconciled sample/result/report state, lost audit history, duplicate external effect, exceeded objective, or absent owner. A failure remains open until retested.

Planned evidence pack: approved plan version, participant/role list, environment boundary, backup and restore receipts, checksums, timing, reconciliation report, defects/corrective actions, retest results, and City acceptance. This is operational evidence, not a certification.

## 6. Nonproduction security and RBAC boundary

The RFP requires adequate security, alignment to the City's NIST Cybersecurity Framework practices, evaluation using the latest NIST SP 800-53 after FIPS PUB 199 categorization, reasonable independent proof, and annual NIST or FedRAMP Security Assessment Reports. Present status for every such assurance is `CANNOT_CLAIM` until verified evidence exists.

### Permitted internal proof boundary (`PLANNED_AFTER_AWARD`)

- City-approved isolated nonproduction tenant/environment.
- Synthetic or explicitly approved redacted fixtures only.
- City-approved identities/groups; least privilege and deny-by-default.
- Separate administrator, configurator, analyst, QA reviewer, reporting approver, auditor, integration service, and support roles where the City requires them.
- Logged role/configuration changes; periodic City-owned access review.
- No production credentials, City impersonation, domain spoofing, unauthorized probing/scanning, or access outside written authorization.
- No autonomous regulatory-result release or security/compliance determination.

### Planned RBAC tests

1. Unknown/disabled identity is denied.
2. Field collector can create/transfer only in approved site scope and cannot release results.
3. Analyst can act only on currently authorized methods.
4. QA reviewer can hold/review but cannot erase audit history.
5. Reporting approver can release only reconciled, approved reports.
6. Integration identity is limited to its named adapter/data scope and cannot administer users.
7. Support identity is time-bounded, approved, logged, and cannot silently elevate.
8. Same user cannot approve a controlled change or result where separation of duties forbids it.
9. Every denial and privileged action emits an attributable audit event.
10. Duplicate/replayed privileged request produces at most one effect.

### Security evidence blockers (`CANNOT_CLAIM`)

- No verified independent audit report, operating-system/code/environment scan, NIST Security Assessment Report, or FedRAMP Security Assessment Report is present in this lane.
- No City-approved FIPS PUB 199 categorization or NIST SP 800-53 control selection is present.
- No verified penetration-test, vulnerability-remediation, incident-response, key-management, logging-retention, or annual-assurance evidence is present.
- No authority exists in this lane to test or scan City systems.

## Proposal-operations blockers and owner handoff

The following must remain explicit gaps; none may be converted into a claim by wording alone.

1. **Company authority and legal forms — `CANNOT_CLAIM`:** authorized signer, legal name/address/title/phone, Conditions and Non-Collusion form, willingness statements, insurance, City business license, and vendor forms require owner/legal/account evidence.
2. **Experience and references — `CANNOT_CLAIM`:** the RFP asks for three specific reference categories (new, retained 3+ years, former terminated within 2 years). No qualifying references are evidenced in this lane.
3. **Quality/employment/legal answers — `CANNOT_CLAIM`:** QA-program attachment, mandatory drug testing, SBA status, facilities, headcount, years in business, payment terms, and pending-lawsuit answer require verified company records.
4. **Security assurance — `CANNOT_CLAIM`:** independent audit/scan proof and annual NIST/FedRAMP assessment report require verified artifacts and security review.
5. **Instrument compatibility — `CANNOT_CLAIM`:** Attachment F names categories/manufacturers but omits exact models, firmware, interface software, protocols, file formats, and sample payloads. Compatibility requires buyer inventory and adapter evidence.
6. **Implementation timeline — `BUYER_INPUT_REQUIRED`:** dependencies, migration volume, environment approval, integration access, roster, blackout windows, and acceptance owners are not specified.
7. **Support commitments — `BUYER_INPUT_REQUIRED`:** hours, severity definitions, response/resolution targets, update policy, maintenance windows, and escalation contacts are not specified.
8. **DR commitments — `BUYER_INPUT_REQUIRED`:** RTO/RPO, retention, geography, key ownership, restore authority, and exercise cadence are not specified.
9. **Reporting — `BUYER_INPUT_REQUIRED`:** City CMDP/netDMR schemas/templates, client/internal reports, dashboard measures, approval/correction rules, and Power BI boundary are not provided.
10. **Addenda — `BUYER_INPUT_REQUIRED`:** the official bid page was open when inspected; proposal operations must re-check the City page and reconcile every posted addendum before finalization.

## Internal verification checklist

- [x] Six required operations artifacts are present.
- [x] Every unbuilt, buyer-dependent, or unsupported item is status-labeled.
- [x] Attachment F compatibility is not claimed.
- [x] No reference, certification, deployment, security assurance, SLA, RTO/RPO, insurance, or legal authority is invented.
- [x] No City/prospect contact, proposal submission, pricing action, payment, or secret handling is authorized by this package.
- [x] Regulatory release remains a City-authorized human decision.

