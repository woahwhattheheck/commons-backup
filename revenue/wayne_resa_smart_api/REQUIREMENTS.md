# Wayne SMART API requirements crosswalk

This crosswalk describes the recovered buyer requirements, not bidder compliance. Source **RFP** is the 32-page [WRESA-50-2026-2027-07 API Services RFP](https://www.resa.net/downloads/purchasing/rfp_wresa-50-2026-2027-07_api_services.pdf); dates and source hashes are in [SOURCE_REGISTER.md](SOURCE_REGISTER.md). References below use printed pages and the original section hierarchy. Each A–H identifier is within §1.3.1.

**No row is marked accepted or satisfied.** “Lab relevance / remaining evidence” is original analysis: it explains where a proposed offline simulation can help and which real implementation evidence is still unavailable. The frozen 150-case predecessor, credited in the [original response history](https://github.com/woahwhattheheck/commons/pull/16455), is synthetic. Its case totals are not buyer requirements, code-coverage measurements, throughput measurements, or production acceptance evidence.

**Current source supplement, October 3:** apply the [October 3 Addendum 2 review](ADDENDUM_2_REVIEW_20261003.md) to the base crosswalk below. Rows retain their original RFP citations for traceability. A2 narrows several scope and evidence interpretations; it does not make any lab row compliant or accepted.

## Existing system and business interfaces

| ID | Page | Buyer fact or requirement | Lab relevance / remaining evidence |
|---|---|---|---|
| A.1.a | 7 | Demonstrate competence with SQL Server relational structures, procedures, views, and transaction indexes. | Actual database definitions and query plans are unavailable. An in-memory ledger is not SQL Server compatibility evidence. |
| A.1.b | 7 | Existing application uses .NET MVC. | A local Python fixture does not demonstrate a .NET adapter. |
| A.1.c | 7 | Rules live in application controllers/services and database procedures. | Preserve existing rule boundaries in proposed architecture; exact callable methods are unknown. |
| A.1.d | 7 | Existing database is 3.6 TB. | No capacity inference from small fixtures. |
| A.1.e | 7 | Environment includes on-premises, client/server, and web hosting. | Production topology, network boundaries, and deployment access remain unknown. |
| A.1.f | 7 | Estimated current population is 35,000 users. | Not a concurrency figure; no synthetic-to-production load equivalence. |
| B.1.a | 7 | Current overnight file transfers use GoAnywhere/SFTP. | Real batch schedules and file contracts need discovery. |
| B.1.b | 7 | Manual CSV/Excel transfers are another current interface. | Actual layouts, owners, and reconciliation rules are missing. |
| B.1.c | 7 | Some reporting reads directly from the database and bypass application rules. | Describes the present state; it is not permission to reproduce that bypass. |
| B.2 | 7 | New integration layer must preserve existing .NET rules and prevent external direct database access. | Proposed adapter boundary only; no database connector or external exposure authorized. |
| C.1.a | 8 | HR/finance integration covers employee lifecycle, accounts, roles, organization hierarchy, payroll/benefits, and orders such as Amazon Business. | Proposed domain labels can demonstrate routing; entity schemas and partner API contracts are not supplied. |
| C.1.b | 8 | AWS integration covers processing pipelines, cloud monitoring, backup, and analytics. | No AWS account, services, credentials, or live endpoint is established. |
| C.1.c | 8 | Document integration covers routing, metadata, employee-file indexing, and external record/contract systems. | Document fixtures are synthetic; no real files or target platform selected. |

C.1 requires both data exchange and transactional/synchronization actions across all three integration areas. A ledger-only demonstration addresses a narrow part of that scope.

## Functional behavior

| ID | Page | Buyer requirement | Lab relevance / remaining evidence |
|---|---|---|---|
| D.1 | 8 | Bidder selects and justifies an API style appropriate to SMART and its integrations; REST, GraphQL, gRPC, and hybrid are examples. | Any chosen fixture protocol is a design proposal. Reconcile with G.2.a's OpenAPI requirement before a final design commitment. |
| D.1.a | 8 | Specify and justify serialization for the target integrations. | JSON fixture format is not the issued SMART payload schema. |
| D.1.b | 8 | API architecture must be stateless. | A durable business journal need not imply client-session dependence; explain the distinction in the proposed design. |
| D.1.c | 8 | Return consistent structured errors with useful failure context. | An offline error dictionary can demonstrate shape and safe redaction, not actual upstream error mapping. |
| D.2 | 8 | Deploy a complete data-access catalog mapped to SMART, with pagination, field filtering, and index-based sorting protections. | Synthetic catalog only until actual schema, access policy, and query budgets are known. |
| D.3 | 9 | Provide asynchronous change notifications so consumers need not repeatedly poll the database. | An offline delivery simulator demonstrates a subset; it is not a registered webhook service. |
| D.3.a | 9 | Queue notifications on employee, organizational, and document-reference changes. | Proposed event fixtures; no change capture, database trigger, or production queue is installed. |
| D.3.b | 9 | Securely deliver event metadata to registered listeners promptly after the source change. | No numeric timing target is given. Listener trust, signatures, and real latency need agreement. |
| D.3.c | 9 | Automatically retry failed webhook transmission using exponential backoff; timeout and 5xx are examples. | Delay values, cap, jitter, attempt budget, and replay policy are unspecified. Delivery retry does not establish that repeating an uncertain financial mutation is safe. |

## Security and operating requirements

| ID | Page | Buyer requirement | Lab relevance / remaining evidence |
|---|---|---|---|
| E.1 | 9 | Unauthenticated endpoints or exposed direct database access disqualify a proposal. | Offline permit/refuse fixtures are not a caller-auth system or an exposed service. |
| E.1.a | 9 | Standard identity protocols with cryptographically protected tokens; OAuth flows and JWTs are examples. | Actual issuer, audience, keys, claims, and token validation are unimplemented unless separately evidenced. |
| E.1.b | 9 | Enforce granular roles and the precise data scope of each request. | Synthetic scope decisions can be tested; real role-to-data mapping is missing. |
| E.1.c | 9 | Store integration secrets in environment configuration or a vault, never source code. | No live secrets belong in this lab. Production secret lifecycle remains a deployment deliverable. |
| E.1.d | 9 | HTTPS is compulsory for traffic; TLS 1.2 is the minimum and TLS 1.3 preferred; reject insecure HTTP. | No transport encryption assurance follows from an offline simulator. See the stronger G.7.b documentation language. |
| E.1.e | 9 | Protect sensitive stored data, logs, and settings with strong encryption; AES-256 is an example. | Synthetic fixtures avoid real PII; production storage encryption is not demonstrated. |
| E.1.f | 9 | Meet relevant student/organizational privacy mandates and demonstrate alignment with SOC 2 Type II or ISO 27001 style controls. | A2 answers 25 and 73 clarify certificate eligibility; the packet supplies no audit, certification, or compliance evidence. |
| E.1.g | 10 | Apply request limits and reject excess load gracefully. | A simulated throttle cannot establish safe production thresholds. HTTP 429 is an example in the RFP. |
| E.1.h | 10 | Log caller, method, source location/IP, and outcome while removing sensitive values. | Journal records must distinguish fixture identifiers from real identities; full production audit/redaction evidence is outstanding. |
| E.2.a | 10 | Base availability target is at least 99.99%. Apply A2 answers 44, 51, 61, 85 and 108 for scope and measurement. | Requires an agreed measurement boundary and deployed evidence; use the addendum review before assigning an SLA. |
| E.2.b | 10 | Ordinary non-bulk reads must be responsive under normal load. | No numeric latency limit or normal-load profile appears in the recovered clause. |

## Delivery and developer experience

| ID | Page | Buyer requirement | Lab relevance / remaining evidence |
|---|---|---|---|
| F.1 | 10 | Base text seeks end-2026 operation using a September award assumption. A2 answers 6, 21, 39, 49, 59 and 109 clarify the schedule. | Base calendar labels below are historical; no approved replacement implementation plan is supplied. |
| F.1.a | 10 | Base September phase: discovery, API-style validation, endpoint mapping, and architecture approval. | Apply A2 calendar guidance; discovery inventory remains proposed and unapproved. |
| F.1.b | 10 | Base October–November phase: isolated environments, SQL-backed logic, and token authentication. | Apply A2 calendar guidance; no real SMART sandbox or SQL connection supplied. |
| F.1.c | 10 | Base December phase: notifications, throttling, logs, and initial HR/AWS/document integration tests. | Apply A2 calendar guidance; all three real integrations remain outstanding. |
| F.1.d | 10 | Base Phase 4 is labeled January 2027 and also refers to year-end deployment; load, integrity, and security validation are included. | Read with A2's calendar clarification; neither old label establishes a committed launch date. |
| F.2.a | 11 | Maintain interactive developer documentation for schemas, parameters, and example responses. | Markdown explains a proposal; it is not the requested live catalog. |
| F.2.b | 11 | Supply partner instructions for authentication, webhook subscription, and batch processing. | Actual partner onboarding contracts are missing. |
| F.2.c | 11 | Provide documented integration examples or libraries in common languages; C#, Python, and JavaScript are examples. | Any runnable examples must be labeled for the offline fixture, not SMART. |
| F.2.d | 11 | Use an API versioning approach that preserves existing clients. | Fixture/profile versioning can demonstrate the concept; backward compatibility with actual clients is unverified. |

## Sign-off artifacts and handover

The G umbrella clause (p.11) makes the artifacts conditions of milestone and final acceptance. Documentation must be in English, editable, and also provided as PDF. These Markdown lab documents alone do not complete that delivery package.

| ID | Page | Buyer requirement | Lab relevance / remaining evidence |
|---|---|---|---|
| G.1.a | 11 | Complete entity/relationship model showing referential integrity, immutable records, and double-entry balance. | A2 answers 70 and 120 define the affected scope; proposed ledger diagrams do not supply the actual model. |
| G.1.b | 11 | Transaction-state/data-flow diagrams from initiation through reconciliation, including mutations. | Useful lab target: distinguish transport state from ledger business state. |
| G.1.c | 11 | Explain concurrency control and lock handling under high throughput. | A local journal model does not demonstrate distributed or SQL locking behavior. |
| G.2.a | 12 | Interactive API catalog conforming to OpenAPI 3.0 or newer. | A fixture contract may inform it; an interactive deployed catalog remains outstanding. |
| G.2.b | 12 | Complete request/response definitions, including idempotency headers, payloads, queries, and success/error codes. | Lab idempotency rules are proposed. Buyer scope, key lifetime, and duplicate/conflict responses are unknown. |
| G.3.a | 12 | Keep all custom source in a private Git repository owned by the client. | Internal development publication is not delivery into that future client repository. |
| G.3.b | 12 | Follow language conventions, document code, use structured logs, and separate responsibilities. | Can be reviewed locally within the lab's limited scope. |
| G.3.c | 12 | Provide an executed IP transfer assigning all custom artifacts upon milestone payment. | Read A2 answers 41 and 57 for the IP boundary; no agreement or signature is supplied. |
| G.4.a | 12 | Provide unit, integration, and end-to-end tests with at least 80% overall code coverage and 100% ledger-calculation coverage. | Apply A2 answers 43, 52, 70, 123 and 140 to coverage scope. Case counts are not measured coverage; full implementation evidence remains outstanding. |
| G.4.b | 12 | Produce simulation logs for high-volume anomalies, including mid-transaction disconnects, with no ledger imbalance. | Apply A2 answers 43, 52 and 140 to ledger scope. Offline traces evidence only the model; unknown commit cannot authorize another write. |
| G.5.a | 12 | Automate equivalent local, staging, and production environments using infrastructure definitions. | A reproducible local run is narrower than environment equivalence. |
| G.5.b | 12 | Automate build/test/deploy, PR checks, and uninterrupted blue/green production rollout. | No production deployment, rollback, or zero-downtime result is established. |
| G.6.a | 12 | Developer guide covers checkout, environment setup, dummy database, and local tests. | The lab can provide fixture onboarding; actual application/database setup remains unknown. |
| G.6.b | 13 | Administration guide covers daily/weekly backups, secret rotation, logs, and troubleshooting. | Production runbook requires environment and operator discovery. |
| G.7.a | 13 | Supply static/dynamic assessment reports without critical findings. | No production security assessment is performed or claimed in this task. |
| G.7.b | 13 | Explain encryption at rest and TLS 1.3/mTLS in transit. | Resolve deployment-specific interpretation with E.1.d before a compliance commitment. |
| G.8.a | 13 | Document restore procedures, recovery-point objective, and recovery-time objective. | Apply A2 answers 85 and 124 before setting recovery commitments; no approved objectives or production restore evidence supplied. |
| G.8.b | 13 | Explain recovery on another region or infrastructure node. | Apply A2 answer 124 to deployment scope; no target infrastructure or failover evidence supplied. |
| G.9.a | 13 | Lead architect/developer supplies at least 40 hours of technical walkthroughs to the SMART team. | No attendance, staffing commitment, or completed training is claimed. |
| G.9.b | 13 | Provide a structured one-week technical Q&A handover after delivery. | Future delivery obligation, not satisfied by repository discussion. |
| G.10.a | 13 | Supply a 90-day post-launch warranty covering defects, calculation errors, and regressions without extra charge. | Apply A2 answers 87 and 125 to the warranty boundary and start; no authorized delivery/support commitment supplied. |
| G.10.b | 13 | Propose support tiers and response targets. | Read A2 answers 118 and 137 together before assigning post-warranty responsibilities or optional support prices. |
| H | 14 | Subcontracting requires Wayne RESA's express written consent. | Workshare planning and teammate contributions do not establish buyer consent. |

## Other response and acceptance obligations

These rows complete the scope outside A–H. Actual company evidence, commercial response, and signatures remain unavailable; see [SUBMISSION_READINESS.md](SUBMISSION_READINESS.md).

| Source section | Pages | Required subject / readiness implication |
|---|---|---|
| Bid summary; 1.1 | 2–3, 5–6 | Statewide cooperative opportunity; base three-year term with up to two mutually agreed annual extensions. Minimum five years of API experience, three comparable customer references, and a completed Attachment A. Funding approval is a condition of award; selected respondents may have to attend interviews/presentations. |
| 1.2 | 6 | Replace manual/flat-file exchanges, improve cross-system consistency and near-real-time synchronization, support queries and postings to authorized SMART modules, connect the three target ecosystems, and enable secure cooperative access. Institutional context is 33 public districts, approximately 97 academies, and more than 260,000 students; these are not API load-test specifications. |
| Proposal I–III; 1.3; 3.4 | 5–6, 28 | Plain-language executive response, full solution/methodology, relationship management, and one consolidated assumptions list tied to source sections. Every relevant section/subsection needs an explicit response or exception. |
| 1.4 | 14–15 | Cooperative participation, maintenance of accepted commercial schedules, and remittance/reporting obligations require an authorized commercial response. This lab creates no prices. |
| 1.5; 1.6.3 | 15 | Reserved; no additional scope inferred. |
| 1.6.1 | 15 | Describe performance communications, issue resolution, and continuity through corporate/leadership changes. |
| 1.6.2 | 15 | Identify actual people and contact details for delivery performance, contract negotiation/signature, and reporting. |
| 1.7 | 16 | Describe customer service locations/hours and ordinary/emergency response; dedicated contact is preferred, same-business-day ordinary and immediate emergency responses are stated expectations. |
| 1.8 | 16 | Participating agencies issue future requests and purchase orders under their own detailed requirements. A cooperative award is not a guaranteed order. Apply A2 answers 67, 96 and 138 before interpreting award or funding. |
| 1.9 | 16–17 | Deliver on the agreed schedule; transfer digital materials securely; final acceptance requires conformance, training, implementation, and functioning integrations. Defects must be corrected within five business days without extra charge. |
| 1.9.1 | 17 | Authorized commercial response must address the stated net-30 terms. No financial recommendation is made here. |
| 1.10 | 17–18 | If campus checks are conducted, complete them before on-site work and obtain written assignment clearance; proposer has related processing obligations. No individual's clearance is asserted. |
| 1.11; 1.11.1–4 | 18 | Attachment A is required; 1.11.1 is reserved; volume terms are optional; required quantities and applicable tax treatment must be addressed by the commercial owner. No pricing is created. |
| 1.12 | 18–19 | Source requires ongoing price-assurance/cooperative-listing obligations and an explicit agreement/exception response. Commercial review is outstanding. |
| 2.0 | 20 | Authorized declarations, prime-contractor responsibility, all-addenda acknowledgment, company standing/permissions, contractual commitments, and pre-award insurance evidence. |
| 2.1 | 21 | Actual entity and representative details, corporate background, relevant status disclosures, and authorized signature. |
| 2.2 | 22 | Three similar-service customer references from the last five years with service details and contact/date/volume fields. |
| 2.3 | 23–27 | Employment eligibility, debarment, nondiscrimination, records access, sanctions, independent-price determination, and lobbying declarations, with required signatures/notarization. Applicability and truth require authorized review. |
| 3.1–3.4 | 28 | Only incorporated commitments bind; response truth/completeness, official addenda, and a minimum 120-day proposal-validity period matter. |
| 3.5–3.7 | 29 | Electronic BidNet submission only; minimum requirements/references are a pass/fail gate before scored evaluation. Buyer may request supporting information. |
| 3.8–3.10 | 30 | Technical response 40 points, references 20, pricing 25, contractual adherence 15. Buyer may use further evaluation methods and reject proposals. |
| 3.11–3.14 | 30–31 | Disclosure/confidentiality instructions, exclusive procurement contact route, discretionary award structure, and cancellation terms require response-owner review. |
| Appendix A | 32 | Identify actual service coverage among ten named Michigan regions; no statewide delivery capability is presumed. |

## Explicit design boundaries

An offline lab may propose synthetic event envelopes, replayable clocks, retry schedules, an append-only journal, bounded idempotency rules, profile/source binding, and a hold when commit state is uncertain. Those choices are motivated by D.3, G.1, G.2, and G.4; the RFP does not prescribe their particular implementation.

The lab must not relabel proposed routes as buyer endpoints, infer business authorization from transport success, count a retry as another ledger posting, or promote source availability into qualification/acceptance. Neither this crosswalk nor a passing local test changes the Dewpoint/Wayne do-not-route constraint.

## Recovered attachment supplement

Subsequent read-only recovery of the issued pricing workbook adds a concrete scope detail: Table A rows 17–19 specify one production integration each for HR/finance, AWS, and document storage. They do not define the actual endpoints or schemas. The workbook also contains five-year recurring fields, optional units, labor categories, and required assumptions; all bidder inputs remain blank. General CoPro+ terms are recovered, with applicability and their differing acceptance/insurance wording still requiring qualified review. See [ATTACHMENTS.md](ATTACHMENTS.md) for exact source ranges and sections. This supplement does not change any A–H row to compliant or accepted. A2's later pricing, staffing, insurance, award, and support references are indexed in the [October 3 Addendum 2 review](ADDENDUM_2_REVIEW_20261003.md); Attachment A bidder values remain blank.
