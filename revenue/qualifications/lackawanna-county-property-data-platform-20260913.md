# Lackawanna County property-data platform RFP — qualification

**Evidence date:** 2026-09-13  
**Owner lane:** FISCHER-Z / GPT-5.6 Sol  
**Status:** **PARTNER-FIRST / CONDITIONAL GO** — technically aligned, but do not represent direct qualification until the required comparable-government references and delivery/insurance capacity are proven.  
**External contact:** none. No questions, proposal, spend, or representation sent.

## Opportunity

Lackawanna County, Pennsylvania is soliciting a technology provider for a **County-Wide Property Data Management, Land Record Indexing, and Parcel Intelligence Platform**. The public RFP was advertised September 9, 2026. Written questions are due **September 24, 2026** and sealed proposals are due **September 30, 2026 at 3:00 PM Eastern**.

The required submission is physical: **three hard copies plus two digital copies on USB**, delivered to the Lackawanna County Chief of Staff at the County Government Center in Scranton. No late proposals are accepted.

The RFP does not state a contract value. Treat budget and award value as **UNKNOWN**, not zero and not inferred from scope.

## Scope / technical fit

The requested platform is materially aligned with the Commons/Titan-style software and agent/data work:

- ingest and normalize County Tax Assessment data through APIs where available or scheduled imports;
- build a parcel-level view across official County sources;
- ingest/index deeds and, where appropriate, mortgages and liens, including historical records from approximately 1966 forward;
- extract recording metadata such as document number/date, grantor/grantee, property description, parcel identifier and book/page references;
- describe **OCR, AI or other automated indexing**, including confidence scores, quality-control thresholds, exception handling and human/manual review;
- provide search/repository functions, role-based access, audit logs, change tracking, attribution, backups, patching and incident response;
- integrate with County IT, land-record and assessment systems/vendors;
- perform migration, validation, testing, deployment, training and continuing support;
- provide availability/support/security SLAs and clean data-export / exit provisions.

The County already exposes live ArcGIS parcel and land-record services, which is useful evidence that parcel/GIS integration is a real implementation surface rather than speculative scope.

## Evaluation weights

The RFP scores proposals on:

| Criterion | Points |
|---|---:|
| Technical solution / scope satisfaction | 25 |
| Comparable government/property-data experience | 20 |
| Professional services + subscription cost / value | 20 |
| Security, auditability, integration, support + SLAs | 15 |
| Implementation, training + coordination | 10 |
| Proposal quality / responsiveness | 10 |

This makes the qualification bottleneck explicit: technical ingenuity alone cannot compensate for weak references and delivery credibility.

## Qualification

### Strong fit

- custom data ingestion, API integration and normalization;
- AI/OCR-assisted extraction and review workflows;
- audit trails, provenance and human-in-the-loop confidence gating;
- searchable web application / workflow tooling;
- rapid implementation planning and integration proof-of-concepts.

### Gaps that must be closed before a direct bid

1. **Comparable references.** The proposal asks for **3–5 comparable implementations**, preferably county/municipal property data, assessment, recorded land documents, parcel indexing, title/property-history research, or multi-department government data environments. Do not invent or stretch unrelated work into these references.
2. **Prime delivery capacity.** The RFP expects named project, integration, security and implementation personnel plus ongoing support.
3. **Contract/insurance posture.** Final terms include insurance/cybersecurity requirements, indemnification, data ownership, confidentiality, records retention and transition provisions. Exact required limits should be verified from any County addendum/final contract package before committing.
4. **Physical submission logistics.** A bid requires timely production/delivery of hard copies and USB copies in Scranton.
5. **Budget is unknown.** No spend/revenue forecast should be booked without a stated value or a defensible owner-approved pricing model.

## Recommended route

**Conditional GO only as a partner-first pursuit.** Find one established GIS/property-records/public-sector SaaS or implementation prime with the required 3–5 references; position Commons/Titan capabilities as the AI/OCR ingestion, workflow/audit, integration or prototype acceleration component. A direct prime bid is a **HOLD** until the reference and delivery-capacity proof exists.

Before the September 24 question deadline, an owner-approved question package should resolve at minimum:

- expected parcel/document volumes and historical-record digitization/indexing baseline;
- current assessment and Recorder-of-Deeds vendors/interfaces and available API/export formats;
- whether existing scanned historical documents are machine-readable and what OCR/index metadata already exists;
- preferred hosting/security standards and any mandated compliance framework;
- expected user count/departments and SLA targets;
- whether teaming/subcontractors are permitted and what disclosures are required;
- expected initial term/renewals and whether the County can publish an anticipated budget range.

**Do not send these questions without explicit owner authorization.**

## Source custody

- Official County PDF URL surfaced by the public solicitation listing:  
  `https://www.lackawannacounty.org/Document_center/Rfp%20Rfq/090926%20RFP%20Property%20Data%20Platform.pdf?t=202609090826380`
- Public solicitation mirror with the County attachment preview and deadline/scope/evaluation text:  
  `https://www.governmentcontracts.us/government-contracts/opportunity-details/40617818501223008.htm?cts=5766f`
- Independent listing identifying the County document as `090926 RFP Property Data Platform.pdf` and bid `LC-255`:  
  `https://publicbidsearch.com/bids/rfp-for-county-wide-property-data-platform-scranton-pa-f79353`
- Live Lackawanna County parcel FeatureServer (integration-surface evidence):  
  `https://gis.lackawannacounty.org/arcgis/rest/services/GISViewer/Parcels/FeatureServer/0`
- Live Lackawanna County land-record service (integration-surface evidence):  
  `https://gis.lackawannacounty.org/arcgis/rest/services/GISViewer/LandRecords/MapServer/layers`

## Decision

**PARTNER-FIRST / CONDITIONAL GO.** Preserve the September 24 question deadline and September 30 submission deadline in the revenue feed. The next useful action is partner/reference qualification, not unsolicited County contact and not a speculative full proposal.
