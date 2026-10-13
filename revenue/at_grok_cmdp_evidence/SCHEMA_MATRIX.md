# AT-GROK-CMDP-EVIDENCE-01 schema matrix

Draft/export preparation only. EPA/state primary sources. Never invent fields.
Unknowns are written exactly as `UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED`.

## Sources

- **epa-cmdp-xml-schema-1.13** — CMDP Web Services Sampling XML Schema Definitions — https://www.oregon.gov/oha/PH/HEALTHYENVIRONMENTS/DRINKINGWATER/MONITORING/Documents/CMDP-XML-Schema.pdf — version SDWIS CMDP 1.17 – CY19R5 Version 1.13 — effective 2019-12-09 — Introduction; Table 1; A.1.1 Sample Result Data XML Structure and data elements; Appendix A
- **epa-cmdp-user-manual-1.4.1** — Compliance Monitoring Data Portal User Manual — https://health.hawaii.gov/sdwb/files/2019/06/CMDP-User-Manual-v-1.4.1.pdf — version v1.4.1 — effective 2019-06 — 6.7 Certify and Submit; 6.8 Reject a Job; 6.10 Migrate Job; 6.12 Add Microbial/Chem/Crypto samples; 6.12.3.2 / 6.12.4.2 / 6.12.5 data elements
- **hi-eha-sample-validation-submission-guide** — Sample Validation & Submission Guide (Using CMDP Templates) — https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf — version 2019-06 Hawaii EHA guide (references EPA CMDP templates and Help Center) — effective 2019-06 — Parts 1–5; Federal Reporting Validation; XML Submittal Validation; Part 5 State rejection
- **hi-eha-cmdp-training-201909** — Compliance Monitoring Data Portal (CMDP) HIEHA Training — https://health.hawaii.gov/sdwb/files/2019/09/CMDP-HIEHA-Training.pdf — version 2019-09 — effective 2019-09 — Prepare / upload / review validations / state reject; Sample IDs for rejected samples cannot be reused
- **sc-des-cmdp-electronic-reporting** — Electronic Reporting for Water Quality: Compliance Monitoring Data Portal (CMDP) — https://des.sc.gov/programs/bureau-water/water-quality-standards/electronic-reporting-water-quality-compliance-monitoring-data-portal-cmdp — version SCDES public page as retrieved 2026-08-31 — effective UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — Sample Results Guidelines; correction of submitted results; XML / Web Services point to EPA Sample Data Dictionary
- **epa-cmdp-landing** — Compliance Monitoring Data Portal | US EPA — https://www.epa.gov/ground-water-and-drinking-water/compliance-monitoring-data-portal — version EPA web page — effective 2025-10-28 — page body; Last updated on October 28, 2025
- **epa-cmdp-help-center** — CMDP Help Center / SDWIS Program portal — https://usepa.servicenowservices.com/sdwisprogram?id=cmdp_homepage&sysparm_domain_restore=false&sysparm_stack=no — version UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — effective UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — named by SC DES and CT DPH as the host of the Sample Data Dictionary and CMDP-LIMS ICD

## Child nodes (Table 1)

- MICROBIAL: sampleResultMicro, sampleResultField
- CHEMS_RADS: sampleResultChem, sampleResultField
- CRYPTOSPORIDIUM: sampleResultCrypto, sampleResultMeasure, sampleResultField

## Fields

| xml_element | req | type | families | values | source section | version / date |
|---|---|---|---|---|---|---|
| `samples` | R | XML Root Element | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / samples | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sample` | R | XML Element | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sample | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `wsId` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / wsId | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `facilityName` | N/A | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / facilityName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `stateAssignedFacId` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / stateAssignedFacId | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `samplingPointId` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / samplingPointId | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `samplingLocation` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / samplingLocation | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleCd` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleCd | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleReceivedDt` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleReceivedDt | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `collectionDate` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / collectionDate | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `collectionTime` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / collectionTime | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `legalEntityName` | N/A | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / legalEntityName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `laboratoryId` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / laboratoryId | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleTypeName` | N/A | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleTypeName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleTypeCd` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | RT, RP, TG, CO, SP, SB, ST, MR, MS, BB, FB, PE | A.1.1 Sample Result Data XML Structure and data elements / sampleTypeCd | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleVolume` | O | decimal | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleVolume | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `comments` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / comments | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `collectorName` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / collectorName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `repeatLocationName` | C | string | MICROBIAL,CHEMS_RADS | Original Site, Downstream, Upstream, Source, Alternative (RTCR), Other (TCR) | A.1.1 Sample Result Data XML Structure and data elements / repeatLocationName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `originalLabSampleCd` | C | string | MICROBIAL,CHEMS_RADS | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / originalLabSampleCd | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `originalLegalEntityName` | N/A | string | MICROBIAL,CHEMS_RADS | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / originalLegalEntityName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `originalLaboratoryId` | C | string | MICROBIAL,CHEMS_RADS | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / originalLaboratoryId | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `originalCollectionDate` | O | string | MICROBIAL,CHEMS_RADS | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / originalCollectionDate | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleCategoryName` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | Microbial, Chem/Radionuclides, Cryptosporidium | A.1.1 Sample Result Data XML Structure and data elements / sampleCategoryName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleResult` | R | extension point | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleResult | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `analyteName` | N/A | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / analyteName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `analyteCd` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED | A.1.1 Sample Result Data XML Structure and data elements / analyteCd | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `methodCd` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED | A.1.1 Sample Result Data XML Structure and data elements / methodCd | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `methodName` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED | A.1.1 Sample Result Data XML Structure and data elements / methodName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `analysisStartDt` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / analysisStartDt | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `analysisStartTime` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / analysisStartTime | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `analysisComplDt` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / analysisComplDt | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `analysisComplTime` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / analysisComplTime | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `analyzingLabId` | O | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / analyzingLabId | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `volumeAssayed` | O | decimal | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / volumeAssayed | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleResultChem` | family-child | XML Element | CHEMS_RADS | DOCUMENTED_FORMAT_ONLY | Table 1 – Sample Data: Valid childNodes based on Sample Type + sampleResultChem | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `notDetected` | R | boolean | CHEMS_RADS | true, false | A.1.1 Sample Result Data XML Structure and data elements / sampleResultChem.notDetected | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `result` | C | decimal | CHEMS_RADS | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleResultChem.result | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `resultUomName` | C | string | CHEMS_RADS | C, LANG, NTU, pH, umho/cm, TON, CU, mg/L, ug/L, ng/L, pCi/L, MFL | A.1.1 Sample Result Data XML Structure and data elements / sampleResultChem.resultUomName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `standardDeviation` | O | decimal | CHEMS_RADS | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleResultChem.standardDeviation | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `reportingLevel` | C | decimal | CHEMS_RADS | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleResultChem.reportingLevel | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `reportingLevelUomName` | C | string | CHEMS_RADS | C, LANG, NTU, pH, umho/cm, TON, CU, mg/L, ug/L, ng/L, pCi/L, MFL | A.1.1 Sample Result Data XML Structure and data elements / sampleResultChem.reportingLevelUomName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleResultMicro` | family-child | XML Element | MICROBIAL | DOCUMENTED_FORMAT_ONLY | Table 1 – Sample Data: Valid childNodes based on Sample Type + sampleResultMicro | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `apName` | R | string | MICROBIAL,CRYPTOSPORIDIUM | A, P | A.1.1 Sample Result Data XML Structure and data elements / sampleResultMicro.apName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `count` | O | decimal | MICROBIAL,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleResultMicro.count | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `typeName` | N/A | string | MICROBIAL,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / typeName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `typeCd` | O | string | MICROBIAL,CRYPTOSPORIDIUM | Colonies, Tubes, Most probable Number, Oocysts | A.1.1 Sample Result Data XML Structure and data elements / typeCd | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `resultVolume` | O | decimal | MICROBIAL,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / resultVolume | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `interferenceName` | N/A | string | MICROBIAL | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / interferenceName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `interferenceCd` | O | string | MICROBIAL | CNFG, TNTC, TCNG | A.1.1 Sample Result Data XML Structure and data elements / interferenceCd | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `filteredVolExaminedName` | O | string | CRYPTOSPORIDIUM | Y, N | A.1.1 Sample Result Data XML Structure and data elements / filteredVolExaminedName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sourceTypeName` | O | string | MICROBIAL,CRYPTOSPORIDIUM | Flowing stream, Lake, Reservoir, GWUDI | A.1.1 Sample Result Data XML Structure and data elements / sourceTypeName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleResultCrypto` | family-child | XML Element | CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | Table 1 – Sample Data: Valid childNodes based on Sample Type + sampleResultCrypto | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleResultField` | family-child | XML Element | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | Table 1 – Sample Data: Valid childNodes based on Sample Type + sampleResultField | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `fieldAnalyteCd` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | 1013, 1012, 1996, 0100, 1925, 1006, 0999, 1905 | A.1.1 Sample Result Data XML Structure and data elements / sampleResult analyteCd (Sample Field only) | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `fieldResult` | R | decimal | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleResultField.result | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `uomName` | R | string | MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleResultField.uomName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `sampleResultMeasure` | family-child | XML Element | CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleResultMeasure | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `measureName` | N/A | string | CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / measureName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `measureCd` | R | string | CRYPTOSPORIDIUM | SAMPLE VOL FILTER, SAMPLE VOL SPIKE, #OOCYSTS SPIKE, #FILTER USE, PACK PELLET VOL, #OOCYSTS, #OOCYSTS CLC, VOL RESSP C, VOL RESSP CP | A.1.1 Sample Result Data XML Structure and data elements / measureCd | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `measureResult` | R | decimal | CRYPTOSPORIDIUM | DOCUMENTED_FORMAT_ONLY | A.1.1 Sample Result Data XML Structure and data elements / sampleResultMeasure.result | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |
| `measureUomName` | R | string | CRYPTOSPORIDIUM | N, SAMP VOL, SLIDE, Org/100mL, Org/l, G, L, mL | A.1.1 Sample Result Data XML Structure and data elements / sampleResultMeasure.uomName | SDWIS CMDP 1.17 – CY19R5 Version 1.13 / 2019-12-09 |

## Validations

- **CASE_SENSITIVE_REFERENCE** (MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM): Reference data are case-sensitive. Example: oh0000001 is not valid; OH0000001 is. — https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf
- **INVALID_CELL_REJECTS_ROW** (MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM): If any cell contains invalid data or formats, the record (row) is rejected. Valid sample-result rows in the same workbook are still added. — https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf
- **REPEAT_ORIGINAL_MUST_EXIST** (MICROBIAL,CHEMS_RADS): Original Sample ID must exist in CMDP before associated repeat samples are reported, otherwise repeats are rejected. Enter the routine row first, then repeats below it. — https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf
- **ORIGINAL_ID_REQUIRED_RP_TG_CO** (MICROBIAL,CHEMS_RADS): Original Sample Id is required when Sample Type is Repeat, Triggered, or Confirmation. — https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf
- **RECEIVED_AFTER_COLLECTED** (MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM): Sample Received Date must be after Collected Date (XML validation). Hawaii form also states Collection Date ≤ Sample Received Date ≤ Analysis Start Date. — https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf
- **TC_PLUS_REQUIRES_ECOLI** (MICROBIAL): Missing Sample Result for E.coli Given Reported TC+ Sample Result. Hawaii MIC-14: cannot have 3014 Present when 3100 is Absent. — https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf
- **AP_COUNT_CONSISTENCY** (MICROBIAL,CRYPTOSPORIDIUM): When apName is A, count must be null or 0. When P, count must be null or > 0. Hawaii state REJECT: Presence Indicator A and Count Value is not 0. — https://www.oregon.gov/oha/PH/HEALTHYENVIRONMENTS/DRINKINGWATER/MONITORING/Documents/CMDP-XML-Schema.pdf
- **METHOD_PAIR** (MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM): If methodCd or methodName has a value, both are required (Release 1.11 required change). — https://www.oregon.gov/oha/PH/HEALTHYENVIRONMENTS/DRINKINGWATER/MONITORING/Documents/CMDP-XML-Schema.pdf
- **CHEM_RESULT_WHEN_DETECTED** (CHEMS_RADS): result, resultUomName, reportingLevel, and reportingLevelUomName are Federally conditionally required when notDetected is false. — https://www.oregon.gov/oha/PH/HEALTHYENVIRONMENTS/DRINKINGWATER/MONITORING/Documents/CMDP-XML-Schema.pdf
- **SAMPLE_EXISTS** (MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM): Sample already exists — re-upload with a different Sample ID (Hawaii example suffix -01). — https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf
- **UNIQUE_MICRO_VS_CHEM_IDS** (MICROBIAL,CHEMS_RADS): Sample IDs must be unique (Chemical and microbial Sample IDs must be different). — https://des.sc.gov/programs/bureau-water/water-quality-standards/electronic-reporting-water-quality-compliance-monitoring-data-portal-cmdp
- **INVALID_FACILITY_OR_POINT** (MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM): Invalid Facility Id / Invalid Facility Sampling Point Id when IDs are not stored reference data for that water system. — https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf
- **CHILD_NODES_BY_FAMILY** (MICROBIAL,CHEMS_RADS,CRYPTOSPORIDIUM): Microbial: sampleResultMicro + sampleResultField. Chem/Radionuclides: sampleResultChem + sampleResultField. Cryptosporidium: sampleResultCrypto + sampleResultMeasure + sampleResultField. — https://www.oregon.gov/oha/PH/HEALTHYENVIRONMENTS/DRINKINGWATER/MONITORING/Documents/CMDP-XML-Schema.pdf

## Correction / rejection

- **DRAFT_JOB_REJECT** [DRAFT]: Only Draft with Reviewer and Draft with Certifier can be rejected. Status returns to Draft with Preparer. Optional reason recorded in Job History. — runner: DOCUMENTED_ONLY — runner does not reject live jobs
- **DRAFT_JOB_REMOVE** [DRAFT]: Draft with Preparer / Reviewer / Certifier may be removed. Used after validation errors to delete the draft job, fix the template, and re-upload. — runner: DOCUMENTED_ONLY
- **PRE_STATE_FIX_REUPLOAD** [DRAFT]: Validation-tab errors: note errors, Remove the Sample Job, edit the Excel template, regenerate XML, re-upload. — runner: DRAFT_PREP_ONLY
- **POST_STATE_NEW_SAMPLE_ID** [AFTER_STATE]: After state rejection or accepted-then-error: edit the original template and change Sample ID. Hawaii training: rejected Sample IDs cannot be reused; recommend X prefix. SC DES: no delete/correct of submitted results; resubmit with a suffix and notify SCDES. — runner: DOCUMENTED_ONLY — runner never submits and never notifies a primacy agency
- **SUBMITTED_IMMUTABLE** [SUBMITTED]: A Job in Submitted status cannot be modified or edited. Accepted by State cannot be modified. Migration uses DSE to the state compliance system. — runner: OUT_OF_SCOPE
- **CERTIFY_CEREMONY_NOT_PERFORMED** [SUBMIT]: Certify and Submit to State uses SCS username/password plus challenge question. This runner does not perform that ceremony. — runner: REFUSED

## Source-to-draft reconciliation

- **TEMPLATE_TO_XML_TO_DRAFT**: CMDP_Sample_Result_Template.xlsm sheets Microbiological / Chems-Rads / Cryptosporidium. Generate XML (Excel cannot be uploaded). Successful upload creates a draft Sample Job whose contents appear as web forms.
- **ONE_ROW_ONE_RESULT**: Each template row is one sample result. Additional analytes on the same sample leave Sample Information columns blank after the first row.
- **DRAFT_JOB_FEATURES**: Uploaded draft jobs support Add/Remove Attachments, View Job History (from Draft with Reviewer forward), View Validations, Add/Remove Samples.
- **MISSING_SIGNIFICANT_FIELDS_NO_ROWS**: Blank Sample ID, WS ID, or Analyte [Code-Name] yields no Sample Result rows ('No items to show'). Remove the job and fix the template.
- **THIS_RUNNER_STOPS_AT_DRAFT**: This evidence runner prepares citation-backed draft payloads only. It does not upload, send to reviewer, certify, or submit.

## Version / effective date

- XML schema SDWIS CMDP 1.17 – CY19R5 document 1.13 effective 2019-12-09 (https://www.oregon.gov/oha/PH/HEALTHYENVIRONMENTS/DRINKINGWATER/MONITORING/Documents/CMDP-XML-Schema.pdf).
- Later than 1.13: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED

## Unknowns

- **Current EPA Sample Data Dictionary bytes**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — SC DES and CT DPH name the dictionary inside the CMDP Help Center; the ServiceNow portal did not yield a public unauthenticated copy in this run.
- **CMDP-LIMS Interface Control Document full text**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — Named at usepa.servicenowservices.com; viewer required a password in this run.
- **Complete primacy-agency analyteCd and methodCd catalogs**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — Oregon/EPA schema A.1.1 says valid values cannot be listed and depend on user primacyAgency.
- **Cryptosporidium numeric analyteCd**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — Hawaii 6.12.5 lists analyte values as Cryptosporidium by name. No public numeric code in the cited schema table.
- **Schema versions after 1.13 / CY19R5**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — EPA landing last updated 2025-10-28 does not publish a newer XML version number.
- **Complete state rejection-code catalog**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — Hawaii validation guide states its error tables are not all-inclusive.
- **Exact current Excel column letters / header row bytes**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — Cited guides name sheet families and field labels, not a pinned current .xlsm blob.
- **Buyer or vendor live CMDP XML samples**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — No buyer sample was supplied. Synthetic fixtures use documented field names only.
- **Mapping of 40 CFR 141 Subpart W / Y onto unpublished CMDP columns**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — CFR is regulatory context, not an XML tag list. Extra column mappings are not invented.
- **Seivers M5310C as a CMDP XML element**: UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED — Seivers is a buyer instrument label (keep spelling). It is not a documented CMDP XML tag.

State: `NOT_READY / HOLD / BUILD-AND-VERIFY`. cash_usd=0. Seivers spelling preserved if referenced.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
