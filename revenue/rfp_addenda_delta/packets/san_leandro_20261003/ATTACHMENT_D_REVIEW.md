# San Leandro Attachment D: original and corrected workbook review

Reviewed on **October 4, 2026**, using the two complete files retained by [#30918](https://github.com/woahwhattheheck/commons/pull/30918) in the October 3 packet for [original issue #14844](https://github.com/woahwhattheheck/commons/issues/14844).

**The corrected workbook changes answer-cell formatting and layout; it does not change any of the 159 question prompts. Both workbooks remain blank response templates.** The existing Addendum 2 requirement to use the corrected workbook still applies. This comparison supplies no vendor answers, qualification finding, accepted exception or owner review decision.

**Z-VesperFoundry-0829-P6R3 retains pursuit and partner ownership**, including operation `SAN-LEANDRO-CADRMS-MARK43-ZVFP6R3-20260916`. The recorded September 16 outbound and **Mark43 HARD DNR** remain unchanged. The historical offer remains `PROPOSED_NOT_ACCEPTED`; this review establishes no commercial acceptance or revenue. No mailbox refresh, contact, registration, signature or submission was performed.

## 1. Exact retained sources and review boundary

Both files were read through the native GitHub file API at commit `1360360a97ca563afcad0a71e68bc7d252af1eb7`. Their identities and regular-file modes were unchanged at the fresh claim fence on `0cd6c4c61fad499787690110ede7c8d5ff9fa543`.

| Retained workbook | Bytes | Git blob, mode 100644 | SHA-256 recorded by the existing capture manifest |
| --- | ---: | --- | --- |
| [Original](https://github.com/woahwhattheheck/commons/blob/1360360a97ca563afcad0a71e68bc7d252af1eb7/revenue/rfp_addenda_delta/packets/san_leandro_20261003/retained/attachment-d-original.xlsx) | 58,482 | `2e04123e7b6588c1204a2a5cde4b4f8768b7fcab` | `ace7effd19c03c1d94ed6b9d9b7a1db7e56322c57883b08a551a1ecfc6ae4716` |
| [Corrected](https://github.com/woahwhattheheck/commons/blob/1360360a97ca563afcad0a71e68bc7d252af1eb7/revenue/rfp_addenda_delta/packets/san_leandro_20261003/retained/attachment-d-updated.xlsx) | 58,844 | `18cdda1b86c304fdbc420c2b7d4cc94434e03a7e` | `e6563f254cac2efbd8eb99609275c81586df03762d2072c5ace26a9134013081` |

The [source manifest](source_manifest.json) preserves the official requested/final URLs and the original capture times, **2026-10-03T18:43:40Z** and **2026-10-03T18:44:04Z**. This review does not replace those capture events or claim a newer official-document retrieval. The native Git identities above bind the reviewed bytes; the SHA-256 values are the existing manifest's capture records.

The unchanged [JSZip 3.10.2 bundle](https://github.com/Stuk/jszip/blob/609d95f4098a11507160cd101e0b181cfad6a582/dist/jszip.js) and [fast-xml-parser bundle](https://github.com/NaturalIntelligence/fast-xml-parser/blob/80e88a848b073fd630bc181291a24922c6d1e839/lib/fxp.cjs) read the actual retained files in V8. ZIP CRC checks completed for both packages. All **25 parts per workbook**, including all **23 XML/relationship parts**, were retained for comparison; the complete XML sources passed the standing source exclusions. No DTD/entity declaration was present. All XML was parsed without executing Office content. The single embedded PNG was inspected and is the City of San Leandro Information Technology logo. The printer-settings binary was compared exactly, not interpreted as a printer configuration.

This is complete retained XML/text/cell/style/relationship review and exact package-part comparison. It is **not an Excel rendering, interactive editing, print-layout or recalculation observation**. No external workbook resource or saved SharePoint location was opened.

## 2. Workbook and response surface

Every cell coordinate in this report refers to the single sheet named **`Security Questionnaire `**, including its trailing space, backed by **`xl/worksheets/sheet1.xml`**. Both packages use sheet ID **3** and workbook relationship **rId1**. There are no hidden sheets, hidden rows or hidden columns.

| Property | Both retained workbooks |
| --- | --- |
| Declared sheet dimension / stored rows | `A1:H772` / 772 rows |
| Populated cell values | **341**, identical at every address, including exact shared-string content |
| Questions | **159**: 126 in `C5:C130`; 33 in `C132:C165`, excluding blank `C136` |
| Control labels | 84 labeled groups / 83 distinct IDs; duplicate `AI-04` is preserved |
| Shared strings | 312 entries, all referenced; the complete shared-string XML is byte-identical |
| Merged ranges | 74, identical |
| Worksheet formulas / cached formula values | **0 / 0**; there is no score or calculated compliance result |
| Response and notes fields | Every retained value in `D5:H165` is blank |
| Later rows | Rows 166–772 contain formatting but no populated cell values |
| Sheet protection / data validation | Neither is present in the worksheet XML |
| Comments, external-link parts, macros, embedded Office objects | None appears in the complete package inventory |

Columns **A/B/C** carry the domain, control ID and question. **D/E/F/G/H** are labeled **Yes / No / Not Applicable / Explain / Notes** in rows 2–4. Cell **C4** explicitly calls for an explanation when the response is No or Not Applicable. A later authorized response therefore needs the explanation in G; evidence references in H are a proposed internal review practice, not a new buyer instruction.

The title in **A1** contains the source typo “No Applicable”; C4 supplies the clearer existing instruction. Blank response cells are unprovided answers, not No, Not Applicable, failed controls or accepted exemptions.

## 3. Complete original-to-corrected comparison

There are **no added or removed package parts**. **21 of 25 uncompressed part payloads are exactly equal**. The only changed parts are:

| Changed part | Observed change | Consequence for this review |
| --- | --- | --- |
| `xl/worksheets/sheet1.xml` | 563 existing cells change only their style index; two empty styled cells, `D38` and `E38`, are added. View origin, column geometry and row-height/descent metadata change. | All existing cell child content, populated values, question coordinates, response blanks and formulas remain identical. |
| `xl/styles.xml` | Adds two font records, one fill record and eight cell-format records; later format indexes shift. | The meaningful cell-format change is confined to the entire Yes/No range `D5:E165`, including the two added empty cells. |
| `xl/workbook.xml` | Save/build and revision metadata, saved location, window position and one calculation option change. | Sheet identity/order/visibility and the two pre-existing broken named references are unchanged. |
| `docProps/core.xml` | Creator/last-modifier metadata changes; stored modified time changes from `2026-09-04T19:15:12Z` to `2026-10-02T18:09:14Z`. Stored creation time remains `2021-09-07T16:44:33Z`. | Document metadata is not a capture timestamp, authorship verification, buyer approval or qualification record. |

The 21 equal payloads comprise `[Content_Types].xml`; all seven `.rels` files; `xl/sharedStrings.xml`; `xl/theme/theme1.xml`; `xl/drawings/drawing1.xml`; `xl/media/image1.png`; `xl/printerSettings/printerSettings1.bin`; six `customXml/item*.xml` / `itemProps*.xml` files; and `docProps/app.xml` / `docProps/custom.xml`.

### Answer-cell formatting

The updated file applies the new **solid theme-0 fill, fill index 31**, throughout **D5:E165**. The relevant font records omit their former explicit color element. The existing borders, alignment, wrapping and numeric formats of the previously stored Yes/No cells are retained. These are stored formatting facts; no rendered color/contrast result is asserted.

| Exact cells / original format | Corrected format | Count |
| --- | --- | ---: |
| `D5:E10`, style 39 | 75: font 14 → 19; fill 0 → 31 | 12 |
| `D11:E11`, style 42 | 76: font 12 → 20; fill 0 → 31 | 2 |
| Existing Yes/No cells with style 11 | 77: font 12 → 20; fill 0 → 31 | 64 |
| `D13:E13`, style 23 | 78: font 12 → 20; fill 0 → 31 | 2 |
| `D38:E38`, previously absent | 79: two explicit empty cells with font 13, fill 31, border 6 and centered/top wrapped alignment | 2 |
| `D44:E45` and `D64:E64`, style 10 | 80: font 3 → 13; fill 0 → 31 | 6 |
| Existing Yes/No cells with style 5 | 81: font 3 → 13; fill 0 → 31 | 230 |
| `D130:E130`, style 60 | 82: font 3 → 13; fill 0 → 31 | 2 |
| `D131:E131`, style 70 | 82: font 3 → 13; fill 30 → 31 | 2 |

These groups cover exactly **322 positions, D5:E165**. In addition, **243 other cells** receive different numeric style indexes whose referenced format records are exactly equal to their original records. The corrected style table is the original indexes **0–74**, followed by eight inserted records **75–82**, followed by the original indexes **75–203** shifted by eight. Fonts increase **19 → 21**, fills **31 → 32**, and cell formats **204 → 212**. The existing font/fill entries, borders, base styles, named styles, differential styles, color definitions and style extensions remain unchanged.

### Geometry, view and named references

The sheet remains frozen after **two columns and four rows**. Its lower-right view origin moves **C10 → C5**, and the selected cell moves **C15 → E7**. Zoom remains 110%. Default column width changes **19.81640625 → 19.88671875**, while default row height remains 15; default `x14ac:dyDescent` changes **0.35 → 0.3**.

| Columns | Original width | Corrected width |
| --- | ---: | ---: |
| A | 39 | 39 |
| B | 14.7265625 | 14.6640625 |
| C | 171.7265625 | 171.6640625 |
| D | 6.54296875 | 6.5546875 |
| E | 6.7265625 | 6.6640625 |
| F | 16.1796875 | 16.109375 |
| G | 83.7265625 | 83.6640625 |
| H | 35.453125 | 35.44140625 |
| I–XFD | 19.81640625 | 19.88671875 |

Only height (`ht`) and descent (`x14ac:dyDescent`) differ in the **756 changed row-attribute records**. Height changes affect **723 rows**; descent changes affect **728 rows**, namely **38, 44–62, 64–99 and 101–772**, each **0.35 → 0.3**. Rows **1, 3–4, 7–8, 12, 16–19, 22, 28–30, 41 and 43** have identical row attributes. The complete changed-height groups are recorded in Appendix A. Rows **33–35 and 39–40** grow **29 → 43.2**; the other height changes fall between −0.3 and +0.05 in the stored values.

The 74 merge ranges, phonetic properties, duplicate-value conditional-format rule, page margins, portrait page setup, drawing relationship and worksheet root attributes are unchanged. The conditional rule still covers `C166:C1048576 C1:C3 C5:C131`; it does not cover the AI questions in C132:C165. This is template formatting, not an approval or scoring rule.

In `xl/workbook.xml`, both the workbook-scoped and sheet-scoped **Instructions** defined names remain **`#REF!`**. Preserve this source defect; no valid instructions destination was recovered. The stored `calcId` remains 191028, while `concurrentCalc="0"` is removed. There are no worksheet formulas to evaluate. Save/build changes include `rupBuild` **30228 → 30430**, revision-last-save **98 → 0**, changed document/revision identifiers, and window position **(13140, −16320) → (−28920, −4845)**. The saved `absPath` changes from the consultant's project location to a City Addendum 2 location. Those locations are metadata only.

### Relationships and non-cell content

All **17 relationship records across seven relationship files** are exactly equal. They connect the package to its workbook/properties, the workbook to one worksheet/styles/theme/shared strings/three custom XML items, the worksheet to its drawing/printer settings, the drawing to the single logo, and each custom XML item to its properties. None has `TargetMode="External"`.

The three custom XML items contain document-library form names, document-management properties and the associated content-type schema; they add no questionnaire responses. The logo, drawing anchor and printer-settings binary are unchanged. There are no formula caches, external workbook relationships, data connections, macros or embedded Office objects to evaluate. The saved SharePoint path is not an external-data relationship and was not followed.

## 4. Full questionnaire evidence map

This map covers **all 159 prompts**. It summarizes the existing questions and identifies useful **internal owner evidence work**; it neither answers them nor turns the questions into newly adjudicated eligibility gates. Use the exact domain plus cell coordinate because IDs can repeat and a merged ID can cover several questions.

### General, application and operational security — 126 prompts

| Exact question cells / IDs | Existing scope | Internal evidence needed for a later authorized response |
| --- | --- | --- |
| C5:C10 — GES-01…06 (6) | Security staffing; directory/SSO integration; privileged MFA/access control; role design; encryption/masking; certificate maintenance. | Actual proposed-system architecture and responsible roles; identity/control configuration descriptions; data-protection and certificate procedures. |
| C11:C20 — AIS-01…05 (10) | Secure development standards, automated/manual code review, supplier SDLC, pre-production remediation; integrity routines; vulnerability triage; removal of debug/test code; security architecture. | Applicable lifecycle policies and evidence, code-analysis/release practices, supplier assurance, interface/data integrity controls and architecture basis. |
| C21:C27 — AAC-01…02 (7) | Audit planning/effectiveness, tenant access to assurance reports, infrastructure/application penetration assessment, annual internal and independent audits. | Scope/date of available audit reports and assessments, distribution conditions, audit schedule and documented control coverage. |
| C28:C32 — BCR-01…03 and literal BCR-4 (5) | Continuity/disaster recovery, RPO/RTO, testing intervals, impact analysis and annual backup/redundancy testing. | Product-specific recovery objectives, continuity plans, dependency/impact analysis and relevant exercise records. No numeric RPO/RTO is supplied by the questions. |
| C33:C37 — CCC-01…04 (5) | Authorized acquisition/development, external partner change practices, unauthorized software controls, production separation of duties and risk management. | Approved change/release procedures, role separation and installation controls, with actual supplier responsibilities. |
| C38:C42 — DSI-01…05 (5) | Data classification/handling, production-data restrictions, stewardship, secure deletion of archives/backups and tenant exit sanitization. | Data lifecycle and environment-use policies; accountable steward; deletion/exit scope and evidence, including backup limitations. |
| C43:C46 — DCS-01…02 (4) | Critical-asset classification/inventory, data-centre physical access/visitor logging and asset management. | Applicable hosting/asset inventories, assurance responsibility and physical-access evidence for the proposed deployment. |
| C47:C51 — EKM-01…03 (5) | Key-management policy, per-tenant keys, secret storage, transport encryption and encryption formats/algorithms. | Documented key lifecycle, tenancy boundaries, secret custody and actual encryption configuration. |
| C52:C58 — GRM-01…07 (7) | Infrastructure security baselines, annual/triggered risk assessment, management oversight, annual program review, risk register and control effectiveness. | Approved baselines, current review/risk records, ownership and evidence of the stated review cadence. |
| C59:C63 — HRS-01…04 (5) | Asset return, timely access revocation, role-specific security training and workspace protection. | Staff/contractor offboarding, training and sensitive-workspace practices within the responding party's scope. |
| C64:C76 — IAM-01…06 (13) | Security-tool/privileged logging, least privilege, identity inventories, source-code access, access changes, federation/MFA and password/lockout controls. | Identity architecture and policy/configuration evidence, access reviews, provisioning/revocation and privileged/source-code controls. |
| C77:C96 — IVS-01…11 (20) | Integrity/IDS/IPS, firewall policy, VM change detection, secure transport, virtualization-aware assessments, diagrams/hardening, environment and tenant separation, VPN/MFA, rogue devices and network attacks. | Current network/data-flow and tenant-boundary diagrams; operating baseline, monitoring and firewall practices; applicable infrastructure assurance. |
| C97:C99 — IPY-01…03 (3) | Standard/custom API inventory, governing API agreements and secure data import/export/management protocols. | The proposed product's actual interfaces, supported standards and service terms; keep standard and customized work distinct. |
| C100:C107 — MOS-01…06 (8) | BYOD software, device inventory, encryption, rooting/jailbreaking, wipe consequences, password/MDM enforcement and authentication-setting restrictions. | Applicable mobile-device policy and enforcement details, supported deployment model and user-data implications. |
| C108:C115 — SEF-01…04 (8) | Incident plan, customer breach-notification SLA, annual exercise, standards, tenant separation for legal production, response team, metrics and retained forensic logs. | Documented notification commitment and response responsibilities, exercised plan, log scope/retention and tenant-isolated evidence handling. C109 asks for an SLA but supplies no numeric deadline. |
| C116:C123 — STA-01…02 (8) | Prompt incident reporting, outsourced-provider standards/contracts, per-customer recovery, geography restrictions/disclosure and breach notification. | Actual provider/sub-processor roster and contractual controls; customer recovery and data-location capabilities with evidenced limits. |
| C124:C130 — TVM-01…02 (7) | Anti-malware, detection updates, network/application/OS vulnerability assessment, patching and disclosure of shared control responsibilities. | Assessment/patch scope and cadence, detection coverage, remediation ownership and customer responsibility documentation. |

### AI — 33 prompts

| Exact question cells / source group | Existing scope | Internal evidence needed for a later authorized response |
| --- | --- | --- |
| C132:C135 — AI System Overview, AI-01 (4) | AI functionality, external models/APIs, hosting/integration and connectivity. | Actual AI feature/provider inventory, deployment/data-flow description and connectivity requirements; distinguish proposed/optional features. |
| C137:C141 — AI Data Usage, Privacy and Retention, AI-02 (5) | Prompts/files/logs, training/fine-tuning and opt-out, geography, retention and tenant separation. | Data categories/flows, provider terms/settings, training controls, processing/storage location and deletion/isolation evidence. Keep training and inference facts distinct. |
| C142:C146 — AI Model Security and Access Control, AI-03 (5) | Administrative access, endpoint authentication, credential rotation, adversarial/vulnerability assessment and output filtering. | Actual roles, endpoint/key controls, applicable assessment scope/results, output controls and limitations. |
| C147:C150 — AI Governance, Transparency and Compliance, AI-04 (4) | Governance framework, review against named laws/frameworks, internal oversight and model/dataset documentation. | Approved policies, scoped review records, accountable roles and model cards/equivalent. Named laws/frameworks in a question do not establish applicability or compliance. |
| C151:C153 — AI Third-Party Dependencies and Sub-Processors, AI-04 (3) | Provider inventory/assurance and sub-processor changes. | Reconcile providers to the architecture; retain assurance reviews and change/notification procedures. This is a separate group despite the duplicate ID. |
| C154:C158 — AI Incident Response and Monitoring, AI-05 (5) | AI event logging, drift/hallucination/misuse, harmful outputs, leakage controls and customer incident evidence. | Applicable monitoring/response procedures, exercised evidence where available, output-error handling and log availability/retention/access terms. |
| C159:C162 — AI Customer Controls and Configuration, AI-06 (4) | Disabling/limiting AI, role restrictions, explainability/confidence and content review/deletion. | Product configuration/permission documentation, feature limits and actual customer content-management workflows. |
| C163:C165 — AI Future Roadmap and Accountability, AI-07 (3) | Future data-handling changes, risk/compliance ownership and governance/data-protection contact details. | Internally approved roadmap statements, responsible role and approved response information. C165 requests information; it authorizes no contact. |

## 5. Source anomalies and remaining owner work

- **Duplicate ID:** `AI-04` occurs at **B147:B150** and **B151:B153**, covering governance and provider dependencies respectively. Keep all seven prompts with their domain and coordinate; do not collapse or renumber the source.
- **Blank question:** **C136** is empty within the merged **A132:A136 / B132:B136** overview group. The other 33 AI cells contain prompts. Do not invent a missing question or count C136 as answered.
- **Broken named references:** both **Instructions** names remain `#REF!`; the retained readable instructions are A1/C4 and the existing RFP/addenda record.
- **Literal source labels:** **B32** is `BCR-4`, and A1 has the wording noted above. These survive in both versions and were not corrected by this review.
- **Evidence gap:** every answer/explanation/notes field remains blank. Owner work is to map the actual proposed product and responding parties to these exact coordinates, retain evidence and explain No/Not Applicable responses. No generic marketing claim or this review substitutes for that evidence.
- **Broader source gap:** Attachments **A, B, C1, C2 and E** remain unretained, and the base RFP review remains limited to the previously cited anchors. Both generations' `complete=false`, plus manifest `source_set_complete=false` and `requirements_complete=false`, remain unchanged.
- **Existing authority boundary:** the six required owner-review rows and the dated **2026-10-03T18:49:10Z** application result are untouched. No new normalized requirement row, review decision or current-time receipt is minted. The existing October 9 registration / October 27 proposal dates, question-date conflict and conditional CJIS execution timing remain as documented in the [packet README](README.md). These observations create no question reopening or contact/submission permission.

Only this report, the README's review-status explanation, and the two D-file `review_scope` strings in the manifest change. The manifest is supporting provenance: the existing [CLI](https://github.com/woahwhattheheck/commons/blob/1360360a97ca563afcad0a71e68bc7d252af1eb7/revenue/rfp_addenda_delta/cli.py), [engine](https://github.com/woahwhattheheck/commons/blob/1360360a97ca563afcad0a71e68bc7d252af1eb7/revenue/rfp_addenda_delta/engine.py) and [schema](https://github.com/woahwhattheheck/commons/blob/1360360a97ca563afcad0a71e68bc7d252af1eb7/revenue/rfp_addenda_delta/schema.py) consume the separate old/new generation, optional decision and report inputs. Those input/report bytes, retained documents and all action-authority flags are preserved. The accepted #30918 CLI proof was not rerun.

## Appendix A. Complete changed row-height groups

These are literal `ht` attribute values from `xl/worksheets/sheet1.xml`; long decimal strings are preserved as stored. Groups account for all 723 changed-height rows. The independent descent-only changes and unchanged rows are specified in section 3.

| Rows | Original ht | Corrected ht |
| --- | ---: | ---: |
| 2 | 13.15 | 13.2 |
| 5 | 34.75 | 34.65 |
| 6 | 37.4 | 37.35 |
| 9 | 34 | 33.9 |
| 10 | 40.4 | 40.35 |
| 11 | 44.15 | 44.1 |
| 13, 15, 21 | 28.15 | 28.2 |
| 14, 37 | 14.5 | 14.4 |
| 20 | 101.65 | 101.7 |
| 23 | 16.149999999999999 | 16.2 |
| 24 | 31.15 | 31.2 |
| 25 | 20.65 | 20.7 |
| 26 | 19.899999999999999 | 19.95 |
| 27 | 25 | 24.9 |
| 31 | 106.15 | 106.2 |
| 32 | 43.5 | 43.2 |
| 33–35, 39–40 | 29 | 43.2 |
| 36 | 92.15 | 92.1 |
| 38 | 85.15 | 85.2 |
| 42 | 43.4 | 43.35 |
| 45 | 64.75 | 64.650000000000006 |
| 46 | 44.15 | 44.1 |
| 47 | 59.15 | 59.1 |
| 48 | 19.149999999999999 | 19.2 |
| 49 | 22 | 21.9 |
| 50 | 36.4 | 36.450000000000003 |
| 51, 70, 95 | 38.15 | 38.1 |
| 52, 58, 91, 99, 104, 118 | 29 | 28.8 |
| 54 | 49 | 48.9 |
| 55–57, 88–89, 111 | 32.15 | 32.1 |
| 60, 74, 76, 90, 92–93, 127–129, 133–136, 138–141, 145–146, 148–150, 152–153, 155–158, 160–162, 164–304 | 14.5 | 14.4 |
| 63 | 35.65 | 35.700000000000003 |
| 65 | 83.15 | 83.1 |
| 66 | 31 | 30.9 |
| 67 | 46.4 | 46.35 |
| 68 | 50.15 | 50.1 |
| 69 | 37 | 36.9 |
| 71 | 22.9 | 22.95 |
| 72 | 38.65 | 38.700000000000003 |
| 75, 123 | 23.15 | 23.1 |
| 77, 80 | 82.75 | 82.65 |
| 79 | 50.65 | 50.7 |
| 82–83 | 35.15 | 35.1 |
| 84 | 62.15 | 62.1 |
| 85 | 45.4 | 45.45 |
| 87 | 33.4 | 33.450000000000003 |
| 94 | 43.75 | 43.65 |
| 96 | 49.75 | 49.65 |
| 97 | 76.150000000000006 | 76.2 |
| 100 | 44.65 | 44.7 |
| 101 | 57.4 | 57.45 |
| 102 | 64 | 63.9 |
| 103 | 51.4 | 51.45 |
| 105 | 28.4 | 28.35 |
| 106 | 32.65 | 32.700000000000003 |
| 115 | 55.9 | 55.95 |
| 116 | 48.4 | 48.45 |
| 119 | 18.399999999999999 | 18.45 |
| 121 | 17.149999999999999 | 17.100000000000001 |
| 122 | 19.75 | 19.649999999999999 |
| 130–131 | 76.75 | 76.650000000000006 |
| 305–772 | 14.5 | 14.4 |
