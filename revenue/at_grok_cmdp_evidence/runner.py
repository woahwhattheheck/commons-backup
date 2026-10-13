#!/usr/bin/env python3
"""AT-GROK-CMDP-EVIDENCE-01 — official CMDP schema evidence runner.

Draft/export preparation only. No submission, certification, City contact,
or production write. EPA/state primary sources only. Never invent fields.

Official door: python3 at_grok_cmdp_evidence.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RECEIPT_DIR = HERE / "receipts"
FIXTURE_DIR = HERE / "fixtures"

DEMAND_ID = "AT-GROK-CMDP-EVIDENCE-01"
SCHEMA = "commons-at-grok-cmdp-evidence/v1"
STATE = "NOT_READY / HOLD / BUILD-AND-VERIFY"
HUMAN = "SYN-CMDP-EVIDENCE-OFFICER"
HUMAN_ROLE = "DISPOSITION_OFFICER"
SEIVERS = "Seivers"

# Pinned after first fail-closed run. Do not weaken.
GOLDEN_AUDIT_SHA256 = "1988e9677633be5c253f28155a8139eaf710845006086c944d5f236297914f94"

OFF_LIMITS = (
    "AT-GROK-ADAPTER-EVIDENCE-01",
    "AT-GROK-OPS-ACCEPTANCE-01",
    "corrigan-specialty-fuel-blend-dossier-lims-01",
    "torrent-workorder-commissioning-lims-01",
    "bsk-multilab-accession-parity-lims-01",
    "chemtechford-short-hold-intake-lims-01",
    "aquatrace-work-order-b-production-foundation-20260831-01",
    "aquatrace-work-order-c-reporting-offline-20260831-01",
)

CITE_ONLY = {
    "private_repo": "woahwhattheheck/aquatrace-lims",
    "private_sha": "e380a58",
    "note": "cite only; do not remint; do not push",
    "adapter_leftover": "AT-GROK-ADAPTER-EVIDENCE-01",
    "ops_leftover": "AT-GROK-OPS-ACCEPTANCE-01",
    "corrigan_pr": "6879",
    "corrigan_merge": "1128406c",
    "corrigan_blob": "a45f0e2a",
}

UNKNOWN = "UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED"

# EPA-prepared schema republished by Oregon OHA.
OR_SCHEMA = {
    "id": "epa-cmdp-xml-schema-1.13",
    "title": "CMDP Web Services Sampling XML Schema Definitions",
    "url": "https://www.oregon.gov/oha/PH/HEALTHYENVIRONMENTS/DRINKINGWATER/MONITORING/Documents/CMDP-XML-Schema.pdf",
    "page_or_section": "Introduction; Table 1; A.1.1 Sample Result Data XML Structure and data elements; Appendix A",
    "version": "SDWIS CMDP 1.17 – CY19R5 Version 1.13",
    "effective_date": "2019-12-09",
    "prepared_for": "Deric Teasley, Product Owner, U.S. EPA Office of Water",
    "kind": "EPA_PRIMARY_REPUBLISHED_BY_STATE",
}

HI_MANUAL = {
    "id": "epa-cmdp-user-manual-1.4.1",
    "title": "Compliance Monitoring Data Portal User Manual",
    "url": "https://health.hawaii.gov/sdwb/files/2019/06/CMDP-User-Manual-v-1.4.1.pdf",
    "page_or_section": "6.7 Certify and Submit; 6.8 Reject a Job; 6.10 Migrate Job; 6.12 Add Microbial/Chem/Crypto samples; 6.12.3.2 / 6.12.4.2 / 6.12.5 data elements",
    "version": "v1.4.1",
    "effective_date": "2019-06",
    "kind": "EPA_CMDP_USER_MANUAL_REPUBLISHED_BY_STATE",
}

HI_VAL = {
    "id": "hi-eha-sample-validation-submission-guide",
    "title": "Sample Validation & Submission Guide (Using CMDP Templates)",
    "url": "https://health.hawaii.gov/sdwb/files/2019/06/Sample-Validation-Submission-Guide.pdf",
    "page_or_section": "Parts 1–5; Federal Reporting Validation; XML Submittal Validation; Part 5 State rejection",
    "version": "2019-06 Hawaii EHA guide (references EPA CMDP templates and Help Center)",
    "effective_date": "2019-06",
    "kind": "STATE_PRIMARY",
}

HI_TRAIN = {
    "id": "hi-eha-cmdp-training-201909",
    "title": "Compliance Monitoring Data Portal (CMDP) HIEHA Training",
    "url": "https://health.hawaii.gov/sdwb/files/2019/09/CMDP-HIEHA-Training.pdf",
    "page_or_section": "Prepare / upload / review validations / state reject; Sample IDs for rejected samples cannot be reused",
    "version": "2019-09",
    "effective_date": "2019-09",
    "kind": "STATE_PRIMARY",
}

SC_DES = {
    "id": "sc-des-cmdp-electronic-reporting",
    "title": "Electronic Reporting for Water Quality: Compliance Monitoring Data Portal (CMDP)",
    "url": "https://des.sc.gov/programs/bureau-water/water-quality-standards/electronic-reporting-water-quality-compliance-monitoring-data-portal-cmdp",
    "page_or_section": "Sample Results Guidelines; correction of submitted results; XML / Web Services point to EPA Sample Data Dictionary",
    "version": "SCDES public page as retrieved 2026-08-31",
    "effective_date": "UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED",
    "kind": "STATE_PRIMARY",
}

EPA_PAGE = {
    "id": "epa-cmdp-landing",
    "title": "Compliance Monitoring Data Portal | US EPA",
    "url": "https://www.epa.gov/ground-water-and-drinking-water/compliance-monitoring-data-portal",
    "page_or_section": "page body; Last updated on October 28, 2025",
    "version": "EPA web page",
    "effective_date": "2025-10-28",
    "kind": "EPA_PRIMARY",
}

HELP_CENTER = {
    "id": "epa-cmdp-help-center",
    "title": "CMDP Help Center / SDWIS Program portal",
    "url": "https://usepa.servicenowservices.com/sdwisprogram?id=cmdp_homepage&sysparm_domain_restore=false&sysparm_stack=no",
    "page_or_section": "named by SC DES and CT DPH as the host of the Sample Data Dictionary and CMDP-LIMS ICD",
    "version": UNKNOWN,
    "effective_date": UNKNOWN,
    "kind": "EPA_NAMED_LOGIN_GATED",
    "access": UNKNOWN,
}

AUTONOMOUS = frozenset(
    {"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE", "robot", "GROK", "AGENT"}
)
SUBMIT_VERBS = (
    "submit",
    "certify",
    "certify_and_submit",
    "Certify and Submit to State",
    "live_submission",
    "production_write",
    "city_contact",
)

SAMPLE_TYPE_MICRO_CHEM = ("RT", "RP", "TG", "CO", "SP", "SB", "ST", "MR", "MS", "BB", "FB", "PE")
SAMPLE_TYPE_CRYPTO = ("RT", "MS", "SP", "PE", "BB", "FB", "SB", "ST")
AP_VALUES = ("A", "P")
INTERFERENCE = ("CNFG", "TNTC", "TCNG")
SOURCE_TYPE = ("Flowing stream", "Lake", "Reservoir", "GWUDI")
CHEM_UOM = ("C", "LANG", "NTU", "pH", "umho/cm", "TON", "CU", "mg/L", "ug/L", "ng/L", "pCi/L", "MFL")
FIELD_ANALYTES = ("1013", "1012", "1996", "0100", "1925", "1006", "0999", "1905")
MICRO_ANALYTES_NAMED = ("3100", "3014")
MEASURE_CD = (
    "SAMPLE VOL FILTER",
    "SAMPLE VOL SPIKE",
    "#OOCYSTS SPIKE",
    "#FILTER USE",
    "PACK PELLET VOL",
    "#OOCYSTS",
    "#OOCYSTS CLC",
    "VOL RESSP C",
    "VOL RESSP CP",
)
FAMILIES = ("MICROBIAL", "CHEMS_RADS", "CRYPTOSPORIDIUM")
CHILD_NODES = {
    "MICROBIAL": ("sampleResultMicro", "sampleResultField"),
    "CHEMS_RADS": ("sampleResultChem", "sampleResultField"),
    "CRYPTOSPORIDIUM": ("sampleResultCrypto", "sampleResultMeasure", "sampleResultField"),
}


def _cite(source: dict[str, str], section: str) -> dict[str, str]:
    return {
        "source_id": source["id"],
        "url": source["url"],
        "page_or_section": section,
        "version": source["version"],
        "effective_date": source["effective_date"],
    }


def _field(
    xml_element: str,
    requirement: str,
    data_type: str,
    fmt: str,
    families: tuple[str, ...],
    citation: dict[str, str],
    *,
    valid_values: list[str] | None = None,
    valid_values_status: str = "DOCUMENTED",
    notes: str = "",
    form_labels: list[str] | None = None,
) -> dict[str, Any]:
    if valid_values is None and valid_values_status == "DOCUMENTED":
        valid_values_status = "DOCUMENTED_FORMAT_ONLY"
    return {
        "xml_element": xml_element,
        "requirement": requirement,
        "data_type": data_type,
        "format": fmt,
        "families": list(families),
        "valid_values": valid_values,
        "valid_values_status": valid_values_status,
        "notes": notes,
        "form_labels": form_labels or [],
        "citation": citation,
    }


def schema_fields() -> list[dict[str, Any]]:
    all_f = FAMILIES
    micro = ("MICROBIAL",)
    chem = ("CHEMS_RADS",)
    crypto = ("CRYPTOSPORIDIUM",)
    micro_crypto = ("MICROBIAL", "CRYPTOSPORIDIUM")
    a11 = "A.1.1 Sample Result Data XML Structure and data elements"
    t1 = "Table 1 – Sample Data: Valid childNodes based on Sample Type"
    return [
        _field("samples", "R", "XML Root Element", "root", all_f, _cite(OR_SCHEMA, a11 + " / samples")),
        _field("sample", "R", "XML Element", "sample node", all_f, _cite(OR_SCHEMA, a11 + " / sample")),
        _field(
            "wsId",
            "R",
            "string",
            "9 chars – first 2 state code + next 7 water system ID; Federal ID",
            all_f,
            _cite(OR_SCHEMA, a11 + " / wsId"),
            form_labels=["MIC-1", "CHR 1"],
        ),
        _field(
            "facilityName",
            "N/A",
            "string",
            "GET contains Facility Name; POST accepted but will eventually be no longer supported; use stateAssignedFacId",
            all_f,
            _cite(OR_SCHEMA, a11 + " / facilityName"),
        ),
        _field(
            "stateAssignedFacId",
            "R",
            "string",
            "Alphanumeric 40 chars; State Assigned Facility Identifier / Code",
            all_f,
            _cite(OR_SCHEMA, a11 + " / stateAssignedFacId"),
            form_labels=["MIC-2", "CHR 2"],
        ),
        _field(
            "samplingPointId",
            "R",
            "string",
            "Alphanumeric 40 chars; State Assigned Sampling Point Identification Code",
            all_f,
            _cite(OR_SCHEMA, a11 + " / samplingPointId"),
            form_labels=["MIC-3", "CHR 3"],
        ),
        _field(
            "samplingLocation",
            "O",
            "string",
            "Alphanumeric 250 chars",
            all_f,
            _cite(OR_SCHEMA, a11 + " / samplingLocation"),
            form_labels=["MIC-4", "CHR 4"],
        ),
        _field(
            "sampleCd",
            "R",
            "string",
            "Alphanumeric 80 chars; Laboratory assigned Sample ID",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleCd"),
            notes="Hawaii EHA later lists a 20-character state rejection for lab sample ID. That is a state rule, not the XML 80-char definition.",
            form_labels=["MIC-5", "CHR 5"],
        ),
        _field(
            "sampleReceivedDt",
            "O",
            "string",
            "YYYY-MM-DD or MM/DD/YYYY; GET YYYY-MM-DD 00:00; Federally required",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleReceivedDt"),
            form_labels=["MIC 7.1", "CHR 9.1"],
        ),
        _field(
            "collectionDate",
            "R",
            "string",
            "YYYY-MM-DD or MM/DD/YYYY; Federally required; Hawaii form: cannot be a future date",
            all_f,
            _cite(OR_SCHEMA, a11 + " / collectionDate"),
            form_labels=["MIC-6", "CHR 8"],
        ),
        _field(
            "collectionTime",
            "O",
            "string",
            "Time format 00:00; Federally required",
            all_f,
            _cite(OR_SCHEMA, a11 + " / collectionTime"),
            form_labels=["MIC-7", "CHR 9"],
        ),
        _field(
            "legalEntityName",
            "N/A",
            "string",
            "GET Reporting Laboratory Name; POST accepted but will eventually be no longer supported; use laboratoryId",
            all_f,
            _cite(OR_SCHEMA, a11 + " / legalEntityName"),
        ),
        _field(
            "laboratoryId",
            "R",
            "string",
            "Reporting Laboratory ID lookup",
            all_f,
            _cite(OR_SCHEMA, a11 + " / laboratoryId"),
            form_labels=["MIC-8", "CHR 10"],
        ),
        _field(
            "sampleTypeName",
            "N/A",
            "string",
            "GET Sample Type; POST accepted but will eventually be no longer supported; use sampleTypeCd",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleTypeName"),
        ),
        _field(
            "sampleTypeCd",
            "R",
            "string",
            "Sample Type code; Federally required; Micro/ChemsRads vs Cryptosporidium lists differ",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleTypeCd"),
            valid_values=list(SAMPLE_TYPE_MICRO_CHEM),
            notes="Cryptosporidium documented codes are RT, MS, SP, PE, BB, FB, SB, ST only. RP/TG/CO/MR are documented for Microbial/ChemsRads, not Crypto.",
            form_labels=["MIC-9", "CHR 11"],
        ),
        _field(
            "sampleVolume",
            "O",
            "decimal",
            "Precision 9, Scale 2 [0000000.00]; Federally required (Microbial, Crypto)",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleVolume"),
            form_labels=["MIC-10", "CHR 13"],
        ),
        _field(
            "comments",
            "O",
            "string",
            "Alphanumeric 250 chars; appears on sample and on sampleResult",
            all_f,
            _cite(OR_SCHEMA, a11 + " / comments"),
            form_labels=["MIC 28"],
        ),
        _field(
            "collectorName",
            "O",
            "string",
            "Alphanumeric 250 chars",
            all_f,
            _cite(OR_SCHEMA, a11 + " / collectorName"),
        ),
        _field(
            "repeatLocationName",
            "C",
            "string",
            "Required if Sample Type is Repeat; Original Site / Downstream / Upstream / Source / Alternative (RTCR) / Other (TCR)",
            ("MICROBIAL", "CHEMS_RADS"),
            _cite(OR_SCHEMA, a11 + " / repeatLocationName"),
            valid_values=["Original Site", "Downstream", "Upstream", "Source", "Alternative (RTCR)", "Other (TCR)"],
            form_labels=["MIC-11", "CHR 13.1"],
        ),
        _field(
            "originalLabSampleCd",
            "C",
            "string",
            "Alphanumeric 80 chars; required if Sample Type is Repeat/Triggered/Confirmation",
            ("MICROBIAL", "CHEMS_RADS"),
            _cite(OR_SCHEMA, a11 + " / originalLabSampleCd"),
            form_labels=["MIC-12", "CHR 13.2"],
        ),
        _field(
            "originalLegalEntityName",
            "N/A",
            "string",
            "GET Original Reporting Laboratory Name; 40 chars",
            ("MICROBIAL", "CHEMS_RADS"),
            _cite(OR_SCHEMA, a11 + " / originalLegalEntityName"),
        ),
        _field(
            "originalLaboratoryId",
            "C",
            "string",
            "Alphanumeric 40 chars; when Repeat/Triggered/Confirmation: optional if same lab, required if different lab",
            ("MICROBIAL", "CHEMS_RADS"),
            _cite(OR_SCHEMA, a11 + " / originalLaboratoryId"),
        ),
        _field(
            "originalCollectionDate",
            "O",
            "string",
            "YYYY-MM-DD or MM/DD/YYYY",
            ("MICROBIAL", "CHEMS_RADS"),
            _cite(OR_SCHEMA, a11 + " / originalCollectionDate"),
        ),
        _field(
            "sampleCategoryName",
            "R",
            "string",
            "Microbial / Chem/Radionuclides / Cryptosporidium",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleCategoryName"),
            valid_values=["Microbial", "Chem/Radionuclides", "Cryptosporidium"],
        ),
        _field(
            "sampleResult",
            "R",
            "extension point",
            "Element extended by sampleResultMicro / sampleResultChem / sampleResultCrypto / sampleResultField",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleResult"),
        ),
        _field(
            "analyteName",
            "N/A",
            "string",
            "GET Analyte Name; POST accepted but will eventually be no longer supported; use analyteCd",
            all_f,
            _cite(OR_SCHEMA, a11 + " / analyteName"),
        ),
        _field(
            "analyteCd",
            "R",
            "string",
            "Analyte Code; Federally required; schema: valid values cannot be listed (primacy-agency dependent)",
            all_f,
            _cite(OR_SCHEMA, a11 + " / analyteCd"),
            valid_values_status=UNKNOWN,
            notes="Documented named microbial pairs in Hawaii manual: 3100-Coliform, 3014-E.Coli. Field-only codes are listed separately. Full chem/rad and crypto numeric catalogs are UNKNOWN.",
            form_labels=["MIC 14", "CHR 14"],
        ),
        _field(
            "methodCd",
            "O",
            "string",
            "If submitted, methodName is also required; Federally required; values cannot be listed",
            all_f,
            _cite(OR_SCHEMA, a11 + " / methodCd"),
            valid_values_status=UNKNOWN,
            form_labels=["MIC 21"],
        ),
        _field(
            "methodName",
            "O",
            "string",
            "If submitted, methodCd is also required; Federally required; values cannot be listed",
            all_f,
            _cite(OR_SCHEMA, a11 + " / methodName"),
            valid_values_status=UNKNOWN,
        ),
        _field(
            "analysisStartDt",
            "O",
            "string",
            "YYYY-MM-DD or MM/DD/YYYY; Federally required",
            all_f,
            _cite(OR_SCHEMA, a11 + " / analysisStartDt"),
            form_labels=["MIC 22"],
        ),
        _field(
            "analysisStartTime",
            "O",
            "string",
            "00:00; Federally required",
            all_f,
            _cite(OR_SCHEMA, a11 + " / analysisStartTime"),
            form_labels=["MIC 23"],
        ),
        _field(
            "analysisComplDt",
            "O",
            "string",
            "YYYY-MM-DD or MM/DD/YYYY",
            all_f,
            _cite(OR_SCHEMA, a11 + " / analysisComplDt"),
            form_labels=["MIC 24"],
        ),
        _field(
            "analysisComplTime",
            "O",
            "string",
            "00:00",
            all_f,
            _cite(OR_SCHEMA, a11 + " / analysisComplTime"),
            form_labels=["MIC 25"],
        ),
        _field(
            "analyzingLabId",
            "O",
            "string",
            "Alphanumeric 80 chars; name is N/A legacy tag",
            all_f,
            _cite(OR_SCHEMA, a11 + " / analyzingLabId"),
            form_labels=["MIC 26"],
        ),
        _field(
            "volumeAssayed",
            "O",
            "decimal",
            "Precision 9, Scale 2; Federally required (Microbial); Per (Cryptosporidium)",
            all_f,
            _cite(OR_SCHEMA, a11 + " / volumeAssayed"),
            form_labels=["MIC 20"],
        ),
        _field(
            "sampleResultChem",
            "family-child",
            "XML Element",
            "Extends sampleResult; Chem/Radionuclides child",
            chem,
            _cite(OR_SCHEMA, t1 + " + sampleResultChem"),
        ),
        _field(
            "notDetected",
            "R",
            "boolean",
            "true / false; Federally required on sampleResultChem",
            chem,
            _cite(OR_SCHEMA, a11 + " / sampleResultChem.notDetected"),
            valid_values=["true", "false"],
        ),
        _field(
            "result",
            "C",
            "decimal",
            "Precision 15, Scale 9; Federally conditionally required when notDetected is false; retain trailing decimal zeros (v1.13)",
            chem,
            _cite(OR_SCHEMA, a11 + " / sampleResultChem.result"),
        ),
        _field(
            "resultUomName",
            "C",
            "string",
            "Federally conditionally required when notDetected is false",
            chem,
            _cite(OR_SCHEMA, a11 + " / sampleResultChem.resultUomName"),
            valid_values=list(CHEM_UOM),
        ),
        _field(
            "standardDeviation",
            "O",
            "decimal",
            "Precision 9, Scale 2; optional; used only for Radiological results",
            chem,
            _cite(OR_SCHEMA, a11 + " / sampleResultChem.standardDeviation"),
        ),
        _field(
            "reportingLevel",
            "C",
            "decimal",
            "Precision 15, Scale 9; Federally conditionally required when notDetected is false",
            chem,
            _cite(OR_SCHEMA, a11 + " / sampleResultChem.reportingLevel"),
        ),
        _field(
            "reportingLevelUomName",
            "C",
            "string",
            "Federally conditionally required when notDetected is false",
            chem,
            _cite(OR_SCHEMA, a11 + " / sampleResultChem.reportingLevelUomName"),
            valid_values=list(CHEM_UOM),
        ),
        _field(
            "sampleResultMicro",
            "family-child",
            "XML Element",
            "Extends sampleResult; Microbial child",
            micro,
            _cite(OR_SCHEMA, t1 + " + sampleResultMicro"),
        ),
        _field(
            "apName",
            "R",
            "string",
            "A Absent / P Present; Federally required",
            micro_crypto,
            _cite(OR_SCHEMA, a11 + " / sampleResultMicro.apName"),
            valid_values=list(AP_VALUES),
            form_labels=["MIC 15"],
        ),
        _field(
            "count",
            "O",
            "decimal",
            "Precision 15, Scale 5; when apName A must be null or 0; when P must be null or > 0; retain trailing zeros",
            micro_crypto,
            _cite(OR_SCHEMA, a11 + " / sampleResultMicro.count"),
            notes="Hawaii form MIC 16 disables count when Absent. Schema still allows null or 0 when A.",
            form_labels=["MIC 16"],
        ),
        _field(
            "typeName",
            "N/A",
            "string",
            "GET Type Name; POST accepted but will eventually be no longer supported; use typeCd",
            micro_crypto,
            _cite(OR_SCHEMA, a11 + " / typeName"),
        ),
        _field(
            "typeCd",
            "O",
            "string",
            "Microbial: Colonies / Tubes / Most probable Number. Cryptosporidium: Oocysts. Federally conditionally required (Crypto)",
            micro_crypto,
            _cite(OR_SCHEMA, a11 + " / typeCd"),
            valid_values=["Colonies", "Tubes", "Most probable Number", "Oocysts"],
            form_labels=["MIC 17"],
        ),
        _field(
            "resultVolume",
            "O",
            "decimal",
            "Precision 9, Scale 2; Federally conditionally required (Crypto)",
            micro_crypto,
            _cite(OR_SCHEMA, a11 + " / resultVolume"),
            form_labels=["MIC 18"],
        ),
        _field(
            "interferenceName",
            "N/A",
            "string",
            "GET; POST accepted but will eventually be no longer supported; use interferenceCd",
            micro,
            _cite(OR_SCHEMA, a11 + " / interferenceName"),
        ),
        _field(
            "interferenceCd",
            "O",
            "string",
            "CNFG Confluent Growth; TNTC Too Numerous to Count; TCNG Turbid Culture - no gas",
            micro,
            _cite(OR_SCHEMA, a11 + " / interferenceCd"),
            valid_values=list(INTERFERENCE),
            form_labels=["MIC 19"],
        ),
        _field(
            "filteredVolExaminedName",
            "O",
            "string",
            "Y / N; whether 100% of filtered volume was examined; Federally conditionally required (Crypto)",
            crypto,
            _cite(OR_SCHEMA, a11 + " / filteredVolExaminedName"),
            valid_values=["Y", "N"],
        ),
        _field(
            "sourceTypeName",
            "O",
            "string",
            "Flowing stream / Lake / Reservoir / GWUDI",
            micro_crypto,
            _cite(OR_SCHEMA, a11 + " / sourceTypeName"),
            valid_values=list(SOURCE_TYPE),
            form_labels=["MIC 27"],
        ),
        _field(
            "sampleResultCrypto",
            "family-child",
            "XML Element",
            "Extends sampleResultMicro; Cryptosporidium child",
            crypto,
            _cite(OR_SCHEMA, t1 + " + sampleResultCrypto"),
        ),
        _field(
            "sampleResultField",
            "family-child",
            "XML Element",
            "Extends sampleResult; Field Results and Measurements",
            all_f,
            _cite(OR_SCHEMA, t1 + " + sampleResultField"),
        ),
        _field(
            "fieldAnalyteCd",
            "R",
            "string",
            "Analyte Codes for Sample Field only",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleResult analyteCd (Sample Field only)"),
            valid_values=list(FIELD_ANALYTES),
            notes="1013 Free Chlorine Residual; 1012 Total Chlorine Residual; 1996 Temperature; 0100 Turbidity; 1925 pH; 1006 Chloramine; 0999 Chlorine; 1905 Color. XML element remains analyteCd inside sampleResultField.",
            form_labels=["MIC 29"],
        ),
        _field(
            "fieldResult",
            "R",
            "decimal",
            "Precision 15, Scale 9; sampleResultField.result",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleResultField.result"),
        ),
        _field(
            "uomName",
            "R",
            "string",
            "Result UOM; valid value depends on sampleResult.analyteCd. Documented pairs: 1013/1012/0999/1006 mg/l|mL|L; 1996 F|C; 0100 NTU; 1925 ph; 1905 CU",
            all_f,
            _cite(OR_SCHEMA, a11 + " / sampleResultField.uomName"),
        ),
        _field(
            "sampleResultMeasure",
            "family-child",
            "XML Element",
            "Child embedded inside SampleResultMicro (Cryptosporidium)",
            crypto,
            _cite(OR_SCHEMA, a11 + " / sampleResultMeasure"),
        ),
        _field(
            "measureName",
            "N/A",
            "string",
            "POST accepted but will eventually be no longer supported; use measureCd",
            crypto,
            _cite(OR_SCHEMA, a11 + " / measureName"),
        ),
        _field(
            "measureCd",
            "R",
            "string",
            "Crypto measure codes listed in A.1.1",
            crypto,
            _cite(OR_SCHEMA, a11 + " / measureCd"),
            valid_values=list(MEASURE_CD),
        ),
        _field(
            "measureResult",
            "R",
            "decimal",
            "Precision 9, Scale 2; sampleResultMeasure.result",
            crypto,
            _cite(OR_SCHEMA, a11 + " / sampleResultMeasure.result"),
        ),
        _field(
            "measureUomName",
            "R",
            "string",
            "Documented tokens in A.1.1 include N, SAMP VOL, SLIDE, Org/100mL, Org/l, G, L, mL",
            crypto,
            _cite(OR_SCHEMA, a11 + " / sampleResultMeasure.uomName"),
            valid_values=["N", "SAMP VOL", "SLIDE", "Org/100mL", "Org/l", "G", "L", "mL"],
        ),
    ]


def validations() -> list[dict[str, Any]]:
    return [
        {
            "id": "CASE_SENSITIVE_REFERENCE",
            "applies": list(FAMILIES),
            "rule": "Reference data are case-sensitive. Example: oh0000001 is not valid; OH0000001 is.",
            "citation": _cite(HI_VAL, "Part 1 Step 2 template notes"),
        },
        {
            "id": "INVALID_CELL_REJECTS_ROW",
            "applies": list(FAMILIES),
            "rule": "If any cell contains invalid data or formats, the record (row) is rejected. Valid sample-result rows in the same workbook are still added.",
            "citation": _cite(HI_VAL, "Part 1 Workbook 1 notes"),
        },
        {
            "id": "REPEAT_ORIGINAL_MUST_EXIST",
            "applies": ["MICROBIAL", "CHEMS_RADS"],
            "rule": "Original Sample ID must exist in CMDP before associated repeat samples are reported, otherwise repeats are rejected. Enter the routine row first, then repeats below it.",
            "citation": _cite(HI_VAL, "Part 1 Step 2 repeat-sample note"),
        },
        {
            "id": "ORIGINAL_ID_REQUIRED_RP_TG_CO",
            "applies": ["MICROBIAL", "CHEMS_RADS"],
            "rule": "Original Sample Id is required when Sample Type is Repeat, Triggered, or Confirmation.",
            "citation": _cite(HI_VAL, "Part 3 Step 4 XML error {originalSampleId}"),
        },
        {
            "id": "RECEIVED_AFTER_COLLECTED",
            "applies": list(FAMILIES),
            "rule": "Sample Received Date must be after Collected Date (XML validation). Hawaii form also states Collection Date ≤ Sample Received Date ≤ Analysis Start Date.",
            "citation": _cite(HI_VAL, "Part 3 Step 4 {sampleRecievedDt}"),
        },
        {
            "id": "TC_PLUS_REQUIRES_ECOLI",
            "applies": ["MICROBIAL"],
            "rule": "Missing Sample Result for E.coli Given Reported TC+ Sample Result. Hawaii MIC-14: cannot have 3014 Present when 3100 is Absent.",
            "citation": _cite(HI_VAL, "Part 3 Step 2 Federal Reporting Validation table"),
        },
        {
            "id": "AP_COUNT_CONSISTENCY",
            "applies": ["MICROBIAL", "CRYPTOSPORIDIUM"],
            "rule": "When apName is A, count must be null or 0. When P, count must be null or > 0. Hawaii state REJECT: Presence Indicator A and Count Value is not 0.",
            "citation": _cite(OR_SCHEMA, "A.1.1 sampleResultMicro.count"),
        },
        {
            "id": "METHOD_PAIR",
            "applies": list(FAMILIES),
            "rule": "If methodCd or methodName has a value, both are required (Release 1.11 required change).",
            "citation": _cite(OR_SCHEMA, "Appendix A Required Changes for POST"),
        },
        {
            "id": "CHEM_RESULT_WHEN_DETECTED",
            "applies": ["CHEMS_RADS"],
            "rule": "result, resultUomName, reportingLevel, and reportingLevelUomName are Federally conditionally required when notDetected is false.",
            "citation": _cite(OR_SCHEMA, "A.1.1 sampleResultChem"),
        },
        {
            "id": "SAMPLE_EXISTS",
            "applies": list(FAMILIES),
            "rule": "Sample already exists — re-upload with a different Sample ID (Hawaii example suffix -01).",
            "citation": _cite(HI_VAL, "Part 3 Step 4 {SampleExists}"),
        },
        {
            "id": "UNIQUE_MICRO_VS_CHEM_IDS",
            "applies": ["MICROBIAL", "CHEMS_RADS"],
            "rule": "Sample IDs must be unique (Chemical and microbial Sample IDs must be different).",
            "citation": _cite(SC_DES, "Sample Results Guidelines"),
        },
        {
            "id": "INVALID_FACILITY_OR_POINT",
            "applies": list(FAMILIES),
            "rule": "Invalid Facility Id / Invalid Facility Sampling Point Id when IDs are not stored reference data for that water system.",
            "citation": _cite(HI_VAL, "Part 3 Step 4 XML errors facilityId / facSamplingPointId"),
        },
        {
            "id": "CHILD_NODES_BY_FAMILY",
            "applies": list(FAMILIES),
            "rule": "Microbial: sampleResultMicro + sampleResultField. Chem/Radionuclides: sampleResultChem + sampleResultField. Cryptosporidium: sampleResultCrypto + sampleResultMeasure + sampleResultField.",
            "citation": _cite(OR_SCHEMA, "Table 1"),
        },
    ]


def correction_rejection() -> list[dict[str, Any]]:
    return [
        {
            "id": "DRAFT_JOB_REJECT",
            "phase": "DRAFT",
            "applies": list(FAMILIES),
            "rule": "Only Draft with Reviewer and Draft with Certifier can be rejected. Status returns to Draft with Preparer. Optional reason recorded in Job History.",
            "citation": _cite(HI_MANUAL, "6.8 REJECT A JOB"),
            "this_runner": "DOCUMENTED_ONLY — runner does not reject live jobs",
        },
        {
            "id": "DRAFT_JOB_REMOVE",
            "phase": "DRAFT",
            "applies": list(FAMILIES),
            "rule": "Draft with Preparer / Reviewer / Certifier may be removed. Used after validation errors to delete the draft job, fix the template, and re-upload.",
            "citation": _cite(HI_MANUAL, "6.9 REMOVE A JOB"),
            "this_runner": "DOCUMENTED_ONLY",
        },
        {
            "id": "PRE_STATE_FIX_REUPLOAD",
            "phase": "DRAFT",
            "applies": list(FAMILIES),
            "rule": "Validation-tab errors: note errors, Remove the Sample Job, edit the Excel template, regenerate XML, re-upload.",
            "citation": _cite(HI_VAL, "Part 3 Steps 3 and 5"),
            "this_runner": "DRAFT_PREP_ONLY",
        },
        {
            "id": "POST_STATE_NEW_SAMPLE_ID",
            "phase": "AFTER_STATE",
            "applies": list(FAMILIES),
            "rule": "After state rejection or accepted-then-error: edit the original template and change Sample ID. Hawaii training: rejected Sample IDs cannot be reused; recommend X prefix. SC DES: no delete/correct of submitted results; resubmit with a suffix and notify SCDES.",
            "citation": _cite(HI_TRAIN, "state reject / Sample IDs cannot be reused"),
            "this_runner": "DOCUMENTED_ONLY — runner never submits and never notifies a primacy agency",
        },
        {
            "id": "SUBMITTED_IMMUTABLE",
            "phase": "SUBMITTED",
            "applies": list(FAMILIES),
            "rule": "A Job in Submitted status cannot be modified or edited. Accepted by State cannot be modified. Migration uses DSE to the state compliance system.",
            "citation": _cite(HI_MANUAL, "6.7 notes + 6.10 MIGRATE JOB TO COMPLIANCE SYSTEM"),
            "this_runner": "OUT_OF_SCOPE",
        },
        {
            "id": "CERTIFY_CEREMONY_NOT_PERFORMED",
            "phase": "SUBMIT",
            "applies": list(FAMILIES),
            "rule": "Certify and Submit to State uses SCS username/password plus challenge question. This runner does not perform that ceremony.",
            "citation": _cite(HI_MANUAL, "6.7 / Figure 41 Certification Ceremony"),
            "this_runner": "REFUSED",
        },
    ]


def version_block() -> dict[str, Any]:
    return {
        "xml_schema": {
            "product": "SDWIS CMDP 1.17 – CY19R5",
            "document_version": "1.13",
            "effective_date": "2019-12-09",
            "prior": [
                {"version": "1.11.0", "date": "2018-03-07", "note": "numeric field sizes; XML tag corrections; Appendix A"},
                {"version": "1.12.0", "date": "2019-09-05", "note": "microbial and crypto results accept decimals; composite corrections"},
                {"version": "1.13.0", "date": "2020-02-03", "note": "retain trailing decimal zeros for a Chem/Rad result"},
            ],
            "citation": _cite(OR_SCHEMA, "cover + Modification History"),
        },
        "user_manual": {
            "version": "v1.4.1",
            "effective_date": "2019-06",
            "citation": _cite(HI_MANUAL, "document title / June 2019 Hawaii republish"),
        },
        "epa_landing": {
            "last_updated": "2025-10-28",
            "citation": _cite(EPA_PAGE, "Last updated on October 28, 2025"),
            "note": "Landing page does not publish XML tags.",
        },
        "later_than_1_13": UNKNOWN,
        "sample_data_dictionary_current": UNKNOWN,
        "lims_icd_current": UNKNOWN,
    }


def reconciliation() -> list[dict[str, Any]]:
    return [
        {
            "id": "TEMPLATE_TO_XML_TO_DRAFT",
            "applies": list(FAMILIES),
            "rule": "CMDP_Sample_Result_Template.xlsm sheets Microbiological / Chems-Rads / Cryptosporidium. Generate XML (Excel cannot be uploaded). Successful upload creates a draft Sample Job whose contents appear as web forms.",
            "citation": _cite(HI_VAL, "Part 1 Steps 1–3 and upload notes"),
        },
        {
            "id": "ONE_ROW_ONE_RESULT",
            "applies": list(FAMILIES),
            "rule": "Each template row is one sample result. Additional analytes on the same sample leave Sample Information columns blank after the first row.",
            "citation": _cite(HI_VAL, "Part 1 Workbook 1"),
        },
        {
            "id": "DRAFT_JOB_FEATURES",
            "applies": list(FAMILIES),
            "rule": "Uploaded draft jobs support Add/Remove Attachments, View Job History (from Draft with Reviewer forward), View Validations, Add/Remove Samples.",
            "citation": _cite(HI_VAL, "Part 1 upload notes"),
        },
        {
            "id": "MISSING_SIGNIFICANT_FIELDS_NO_ROWS",
            "applies": list(FAMILIES),
            "rule": "Blank Sample ID, WS ID, or Analyte [Code-Name] yields no Sample Result rows ('No items to show'). Remove the job and fix the template.",
            "citation": _cite(HI_VAL, "Part 2 Step 3"),
        },
        {
            "id": "THIS_RUNNER_STOPS_AT_DRAFT",
            "applies": list(FAMILIES),
            "rule": "This evidence runner prepares citation-backed draft payloads only. It does not upload, send to reviewer, certify, or submit.",
            "citation": _cite(HI_MANUAL, "6.7 / 6.8 workflow documented and refused"),
        },
    ]


def unknowns() -> list[dict[str, str]]:
    return [
        {
            "item": "Current EPA Sample Data Dictionary bytes",
            "status": UNKNOWN,
            "why": "SC DES and CT DPH name the dictionary inside the CMDP Help Center; the ServiceNow portal did not yield a public unauthenticated copy in this run.",
        },
        {
            "item": "CMDP-LIMS Interface Control Document full text",
            "status": UNKNOWN,
            "why": "Named at usepa.servicenowservices.com; viewer required a password in this run.",
        },
        {
            "item": "Complete primacy-agency analyteCd and methodCd catalogs",
            "status": UNKNOWN,
            "why": "Oregon/EPA schema A.1.1 says valid values cannot be listed and depend on user primacyAgency.",
        },
        {
            "item": "Cryptosporidium numeric analyteCd",
            "status": UNKNOWN,
            "why": "Hawaii 6.12.5 lists analyte values as Cryptosporidium by name. No public numeric code in the cited schema table.",
        },
        {
            "item": "Schema versions after 1.13 / CY19R5",
            "status": UNKNOWN,
            "why": "EPA landing last updated 2025-10-28 does not publish a newer XML version number.",
        },
        {
            "item": "Complete state rejection-code catalog",
            "status": UNKNOWN,
            "why": "Hawaii validation guide states its error tables are not all-inclusive.",
        },
        {
            "item": "Exact current Excel column letters / header row bytes",
            "status": UNKNOWN,
            "why": "Cited guides name sheet families and field labels, not a pinned current .xlsm blob.",
        },
        {
            "item": "Buyer or vendor live CMDP XML samples",
            "status": UNKNOWN,
            "why": "No buyer sample was supplied. Synthetic fixtures use documented field names only.",
        },
        {
            "item": "Mapping of 40 CFR 141 Subpart W / Y onto unpublished CMDP columns",
            "status": UNKNOWN,
            "why": "CFR is regulatory context, not an XML tag list. Extra column mappings are not invented.",
        },
        {
            "item": "Seivers M5310C as a CMDP XML element",
            "status": UNKNOWN,
            "why": "Seivers is a buyer instrument label (keep spelling). It is not a documented CMDP XML tag.",
        },
    ]


def sources() -> list[dict[str, Any]]:
    return [OR_SCHEMA, HI_MANUAL, HI_VAL, HI_TRAIN, SC_DES, EPA_PAGE, HELP_CENTER]


def schema_matrix() -> dict[str, Any]:
    fields = schema_fields()
    return {
        "id": DEMAND_ID,
        "schema": SCHEMA,
        "state": STATE,
        "mode": "DRAFT_EXPORT_PREPARATION_ONLY",
        "cash_usd": 0,
        "seivers_spelling": SEIVERS,
        "families": list(FAMILIES),
        "child_nodes": {key: list(value) for key, value in CHILD_NODES.items()},
        "sources": sources(),
        "fields": fields,
        "validations": validations(),
        "correction_rejection": correction_rejection(),
        "version_effective_date": version_block(),
        "source_to_draft_reconciliation": reconciliation(),
        "unknowns": unknowns(),
        "cite_only": CITE_ONLY,
        "off_limits": list(OFF_LIMITS),
        "not_claims": [
            "production",
            "submission",
            "certification",
            "compliance",
            "city_contact",
            "spend",
        ],
    }


def synthetic_fixtures() -> list[dict[str, Any]]:
    """Documented-field drafts only. Values are synthetic. No invented XML tags."""
    return [
        {
            "fixture_id": "SYN-MIC-0001",
            "family": "MICROBIAL",
            "expected": "DRAFT",
            "sample": {
                "wsId": "SY0000001",
                "stateAssignedFacId": "SYN-FAC-01",
                "samplingPointId": "SYN-SP-01",
                "samplingLocation": "SYN-LOC-WELLHEAD",
                "sampleCd": "SYN-MIC-0001",
                "sampleReceivedDt": "2026-08-02",
                "collectionDate": "2026-08-01",
                "collectionTime": "08:00",
                "laboratoryId": "SYN-LAB-01",
                "sampleTypeCd": "RT",
                "sampleVolume": "100.00",
                "sampleCategoryName": "Microbial",
            },
            "results": [
                {
                    "child": "sampleResultMicro",
                    "analyteCd": "3100",
                    "apName": "A",
                    "count": None,
                    "volumeAssayed": "100.00",
                    "analysisStartDt": "2026-08-02",
                    "analysisStartTime": "10:00",
                }
            ],
            "field_results": [
                {
                    "child": "sampleResultField",
                    "analyteCd": "1013",
                    "result": "0.200000000",
                    "uomName": "mg/L",
                }
            ],
        },
        {
            "fixture_id": "SYN-MIC-0002-TCPLUS",
            "family": "MICROBIAL",
            "expected": "DRAFT",
            "sample": {
                "wsId": "SY0000001",
                "stateAssignedFacId": "SYN-FAC-01",
                "samplingPointId": "SYN-SP-02",
                "sampleCd": "SYN-MIC-0002",
                "sampleReceivedDt": "2026-08-03",
                "collectionDate": "2026-08-02",
                "collectionTime": "09:15",
                "laboratoryId": "SYN-LAB-01",
                "sampleTypeCd": "RT",
                "sampleVolume": "100.00",
                "sampleCategoryName": "Microbial",
            },
            "results": [
                {
                    "child": "sampleResultMicro",
                    "analyteCd": "3100",
                    "apName": "P",
                    "count": None,
                    "volumeAssayed": "100.00",
                    "analysisStartDt": "2026-08-03",
                    "analysisStartTime": "07:00",
                },
                {
                    "child": "sampleResultMicro",
                    "analyteCd": "3014",
                    "apName": "A",
                    "count": None,
                    "volumeAssayed": "100.00",
                    "analysisStartDt": "2026-08-03",
                    "analysisStartTime": "07:00",
                },
            ],
            "field_results": [],
        },
        {
            "fixture_id": "SYN-CHR-0001-ND",
            "family": "CHEMS_RADS",
            "expected": "DRAFT",
            "sample": {
                "wsId": "SY0000001",
                "stateAssignedFacId": "SYN-FAC-01",
                "samplingPointId": "SYN-SP-03",
                "sampleCd": "SYN-CHR-0001",
                "sampleReceivedDt": "2026-08-04",
                "collectionDate": "2026-08-03",
                "collectionTime": "11:00",
                "laboratoryId": "SYN-LAB-01",
                "sampleTypeCd": "RT",
                "sampleCategoryName": "Chem/Radionuclides",
            },
            "results": [
                {
                    "child": "sampleResultChem",
                    "analyteCd": UNKNOWN,
                    "notDetected": True,
                    "analysisStartDt": "2026-08-04",
                    "analysisStartTime": "13:00",
                }
            ],
            "field_results": [
                {
                    "child": "sampleResultField",
                    "analyteCd": "1925",
                    "result": "7.200000000",
                    "uomName": "ph",
                }
            ],
        },
        {
            "fixture_id": "SYN-CHR-0002-DETECTED",
            "family": "CHEMS_RADS",
            "expected": "DRAFT",
            "sample": {
                "wsId": "SY0000001",
                "stateAssignedFacId": "SYN-FAC-01",
                "samplingPointId": "SYN-SP-03",
                "sampleCd": "SYN-CHR-0002",
                "sampleReceivedDt": "2026-08-05",
                "collectionDate": "2026-08-04",
                "collectionTime": "12:00",
                "laboratoryId": "SYN-LAB-01",
                "sampleTypeCd": "RT",
                "sampleCategoryName": "Chem/Radionuclides",
            },
            "results": [
                {
                    "child": "sampleResultChem",
                    "analyteCd": UNKNOWN,
                    "notDetected": False,
                    "result": "1.200000000",
                    "resultUomName": "mg/L",
                    "reportingLevel": "0.010000000",
                    "reportingLevelUomName": "mg/L",
                    "analysisStartDt": "2026-08-05",
                    "analysisStartTime": "08:30",
                }
            ],
            "field_results": [],
        },
        {
            "fixture_id": "SYN-CRY-0001",
            "family": "CRYPTOSPORIDIUM",
            "expected": "DRAFT",
            "sample": {
                "wsId": "SY0000001",
                "stateAssignedFacId": "SYN-FAC-01",
                "samplingPointId": "SYN-SP-04",
                "sampleCd": "SYN-CRY-0001",
                "sampleReceivedDt": "2026-08-06",
                "collectionDate": "2026-08-05",
                "collectionTime": "06:00",
                "laboratoryId": "SYN-LAB-01",
                "sampleTypeCd": "RT",
                "sampleVolume": "10.00",
                "sampleCategoryName": "Cryptosporidium",
            },
            "results": [
                {
                    "child": "sampleResultCrypto",
                    "analyteCd": UNKNOWN,
                    "apName": "A",
                    "count": None,
                    "typeCd": "Oocysts",
                    "filteredVolExaminedName": "Y",
                    "sourceTypeName": "Lake",
                    "analysisStartDt": "2026-08-06",
                    "analysisStartTime": "09:00",
                }
            ],
            "measures": [
                {
                    "child": "sampleResultMeasure",
                    "measureCd": "SAMPLE VOL FILTER",
                    "result": "10.00",
                    "uomName": "L",
                }
            ],
            "field_results": [],
        },
        {
            "fixture_id": "SYN-MIC-HOLD-REPEAT-NO-ORIGINAL",
            "family": "MICROBIAL",
            "expected": "HOLD",
            "expected_hold": "ORIGINAL_ID_REQUIRED_RP_TG_CO",
            "sample": {
                "wsId": "SY0000001",
                "stateAssignedFacId": "SYN-FAC-01",
                "samplingPointId": "SYN-SP-01",
                "sampleCd": "SYN-MIC-RP-01",
                "sampleReceivedDt": "2026-08-07",
                "collectionDate": "2026-08-06",
                "collectionTime": "08:00",
                "laboratoryId": "SYN-LAB-01",
                "sampleTypeCd": "RP",
                "sampleVolume": "100.00",
                "sampleCategoryName": "Microbial",
            },
            "results": [
                {
                    "child": "sampleResultMicro",
                    "analyteCd": "3100",
                    "apName": "A",
                    "count": None,
                    "volumeAssayed": "100.00",
                    "analysisStartDt": "2026-08-07",
                    "analysisStartTime": "10:00",
                }
            ],
            "field_results": [],
        },
    ]


ALLOWED_SAMPLE_KEYS = {
    "wsId",
    "stateAssignedFacId",
    "samplingPointId",
    "samplingLocation",
    "sampleCd",
    "sampleReceivedDt",
    "collectionDate",
    "collectionTime",
    "laboratoryId",
    "sampleTypeCd",
    "sampleVolume",
    "sampleCategoryName",
    "repeatLocationName",
    "originalLabSampleCd",
    "originalLaboratoryId",
    "originalCollectionDate",
    "comments",
    "collectorName",
}
ALLOWED_RESULT_KEYS = {
    "child",
    "analyteCd",
    "apName",
    "count",
    "volumeAssayed",
    "analysisStartDt",
    "analysisStartTime",
    "analysisComplDt",
    "analysisComplTime",
    "analyzingLabId",
    "methodCd",
    "methodName",
    "notDetected",
    "result",
    "resultUomName",
    "standardDeviation",
    "reportingLevel",
    "reportingLevelUomName",
    "typeCd",
    "resultVolume",
    "interferenceCd",
    "filteredVolExaminedName",
    "sourceTypeName",
    "comments",
}
ALLOWED_FIELD_KEYS = {"child", "analyteCd", "result", "uomName"}
ALLOWED_MEASURE_KEYS = {"child", "measureCd", "result", "uomName"}
KNOWN_XML = {row["xml_element"] for row in schema_fields()} | {
    "fieldAnalyteCd",
    "fieldResult",
    "measureResult",
    "measureUomName",
}


class EvidenceError(ValueError):
    """Fail-closed evidence contract broken."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def field_index() -> dict[str, dict[str, Any]]:
    return {row["xml_element"]: row for row in schema_fields()}


def _require_citation(row: dict[str, Any], failures: list[str]) -> None:
    cite = row.get("citation") or {}
    if not cite.get("url") or not str(cite.get("url", "")).startswith("https://"):
        failures.append("missing citation url for %s" % row.get("xml_element") or row.get("id"))
    if not cite.get("page_or_section"):
        failures.append("missing page/section for %s" % row.get("xml_element") or row.get("id"))
    if not cite.get("version") or not cite.get("effective_date"):
        failures.append("missing version/effective date for %s" % row.get("xml_element") or row.get("id"))


def validate_matrix(matrix: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if matrix.get("id") != DEMAND_ID:
        failures.append("id drifted")
    if matrix.get("state") != STATE:
        failures.append("state must remain HOLD / BUILD-AND-VERIFY")
    if matrix.get("mode") != "DRAFT_EXPORT_PREPARATION_ONLY":
        failures.append("mode must stay draft/export preparation only")
    if matrix.get("cash_usd") != 0:
        failures.append("cash_usd must be 0")
    if matrix.get("seivers_spelling") != SEIVERS:
        failures.append("Seivers spelling was normalized")
    if matrix.get("families") != list(FAMILIES):
        failures.append("families must stay Microbial / Chems-Rads / Cryptosporidium")
    if "Sievers" in _canonical(matrix.get("seivers_spelling")):
        failures.append("buyer spelling Seivers was normalized to Sievers")
    fields = matrix.get("fields") or []
    names = [row.get("xml_element") for row in fields]
    if len(names) != len(set(names)):
        failures.append("duplicate xml_element in schema matrix")
    if len(fields) < 40:
        failures.append("schema matrix missing documented fields")
    for row in fields:
        _require_citation(row, failures)
        if not row.get("families"):
            failures.append("%s missing families" % row.get("xml_element"))
        if row.get("valid_values_status") == "INVENTED":
            failures.append("invented valid_values_status on %s" % row.get("xml_element"))
        if row.get("valid_values_status") == UNKNOWN and row.get("valid_values"):
            failures.append("silent unknown-as-known on %s" % row.get("xml_element"))
    for bucket in (
        matrix.get("validations") or [],
        matrix.get("correction_rejection") or [],
        matrix.get("source_to_draft_reconciliation") or [],
    ):
        if len(bucket) < 3:
            failures.append("missing required mapping group")
        for row in bucket:
            _require_citation(row, failures)
    unknown_rows = matrix.get("unknowns") or []
    if len(unknown_rows) < 6:
        failures.append("unknowns ledger too thin")
    for row in unknown_rows:
        if row.get("status") != UNKNOWN:
            failures.append("unknown row not written as UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED")
        if not str(row.get("status", "")).startswith("UNKNOWN"):
            failures.append("unknown status lost UNKNOWN prefix")
    version = matrix.get("version_effective_date") or {}
    xml = version.get("xml_schema") or {}
    if xml.get("document_version") != "1.13" or xml.get("effective_date") != "2019-12-09":
        failures.append("schema version/effective date drifted from cited 1.13 / 2019-12-09")
    if version.get("later_than_1_13") != UNKNOWN:
        failures.append("later schema version treated as known")
    for leftover in OFF_LIMITS:
        if leftover not in (matrix.get("off_limits") or []):
            failures.append("off_limits missing %s" % leftover)
    if DEMAND_ID in (matrix.get("off_limits") or []):
        failures.append("this leftover listed itself as off-limits")
    return failures


def _walk_keys(obj: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            keys.append(str(key))
            keys.extend(_walk_keys(value))
    elif isinstance(obj, list):
        for item in obj:
            keys.extend(_walk_keys(item))
    return keys


def validate_fixture_fields(fixture: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    extra_sample = set((fixture.get("sample") or {})) - ALLOWED_SAMPLE_KEYS
    if extra_sample:
        failures.append("invented sample fields: %s" % sorted(extra_sample))
    for row in fixture.get("results") or []:
        extra = set(row) - ALLOWED_RESULT_KEYS
        if extra:
            failures.append("invented result fields: %s" % sorted(extra))
        child = row.get("child")
        family = fixture.get("family")
        if child and child not in CHILD_NODES.get(family, ()):
            failures.append("child %s not valid for %s" % (child, family))
        analyte = row.get("analyteCd")
        if family == "MICROBIAL" and analyte not in MICRO_ANALYTES_NAMED:
            failures.append("microbial analyteCd %s is not among documented 3100/3014 names" % analyte)
        if family in {"CHEMS_RADS", "CRYPTOSPORIDIUM"} and analyte != UNKNOWN:
            failures.append("silent unknown-as-known analyteCd for %s" % family)
        if row.get("methodCd") or row.get("methodName"):
            if not (row.get("methodCd") and row.get("methodName")):
                failures.append("METHOD_PAIR broken on %s" % fixture.get("fixture_id"))
    for row in fixture.get("field_results") or []:
        extra = set(row) - ALLOWED_FIELD_KEYS
        if extra:
            failures.append("invented field-result fields: %s" % sorted(extra))
        if row.get("analyteCd") not in FIELD_ANALYTES:
            failures.append("invented field analyteCd %s" % row.get("analyteCd"))
    for row in fixture.get("measures") or []:
        extra = set(row) - ALLOWED_MEASURE_KEYS
        if extra:
            failures.append("invented measure fields: %s" % sorted(extra))
        if row.get("measureCd") not in MEASURE_CD:
            failures.append("invented measureCd %s" % row.get("measureCd"))
    for key in _walk_keys(fixture):
        if key in {"xml_tags", "csv_columns", "guessed_schema", "invented_fields"}:
            failures.append("guessed schema key %s" % key)
        if key not in KNOWN_XML | ALLOWED_SAMPLE_KEYS | ALLOWED_RESULT_KEYS | ALLOWED_FIELD_KEYS | ALLOWED_MEASURE_KEYS | {
            "fixture_id",
            "family",
            "expected",
            "expected_hold",
            "sample",
            "results",
            "field_results",
            "measures",
            "child",
        }:
            # Allow documented aliases used only inside the matrix, not fixtures.
            if key not in {"fieldAnalyteCd", "fieldResult", "measureResult", "measureUomName"}:
                failures.append("undocumented key %s" % key)
    return failures


def classify_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    sample = fixture.get("sample") or {}
    family = fixture["family"]
    if family == "CRYPTOSPORIDIUM" and sample.get("sampleTypeCd") not in SAMPLE_TYPE_CRYPTO:
        return {"state": "HOLD", "code": "CHILD_NODES_BY_FAMILY"}
    if sample.get("sampleTypeCd") in {"RP", "TG", "CO"} and not sample.get("originalLabSampleCd"):
        return {"state": "HOLD", "code": "ORIGINAL_ID_REQUIRED_RP_TG_CO"}
    received = sample.get("sampleReceivedDt")
    collected = sample.get("collectionDate")
    if received and collected and received < collected:
        return {"state": "HOLD", "code": "RECEIVED_AFTER_COLLECTED"}
    analytes = [row.get("analyteCd") for row in fixture.get("results") or []]
    ap = {row.get("analyteCd"): row.get("apName") for row in fixture.get("results") or []}
    if "3100" in analytes and ap.get("3100") == "P" and "3014" not in analytes:
        return {"state": "HOLD", "code": "TC_PLUS_REQUIRES_ECOLI"}
    if ap.get("3100") == "A" and ap.get("3014") == "P":
        return {"state": "HOLD", "code": "TC_PLUS_REQUIRES_ECOLI"}
    for row in fixture.get("results") or []:
        if row.get("apName") == "A" and row.get("count") not in {None, 0, 0.0, "0", "0.0"}:
            return {"state": "HOLD", "code": "AP_COUNT_CONSISTENCY"}
        if row.get("child") == "sampleResultChem" and row.get("notDetected") is False:
            if row.get("result") in {None, ""} or not row.get("resultUomName") or row.get("reportingLevel") in {None, ""}:
                return {"state": "HOLD", "code": "CHEM_RESULT_WHEN_DETECTED"}
    return {"state": "DRAFT", "code": ""}


def prepare_draft(fixture: dict[str, Any]) -> dict[str, Any]:
    decision = classify_fixture(fixture)
    payload = {
        "mode": "DRAFT_EXPORT_PREPARATION_ONLY",
        "submitted": False,
        "certified": False,
        "live": False,
        "city_contact": False,
        "production_write": False,
        "family": fixture["family"],
        "fixture_id": fixture["fixture_id"],
        "child_nodes": list(CHILD_NODES[fixture["family"]]),
        "sample": deepcopy(fixture.get("sample") or {}),
        "results": deepcopy(fixture.get("results") or []),
        "field_results": deepcopy(fixture.get("field_results") or []),
        "measures": deepcopy(fixture.get("measures") or []),
        "state": decision["state"],
        "hold_code": decision["code"],
        "released": False,
        "released_by": "",
    }
    payload["draft_sha256"] = sha256_hex(payload)
    return payload


def refuse_submission(action: str) -> dict[str, Any]:
    return {
        "ok": False,
        "code": "SUBMISSION_REFUSED",
        "action": action,
        "mode": "DRAFT_EXPORT_PREPARATION_ONLY",
    }


def dispose(draft: dict[str, Any], actor: str, role: str) -> dict[str, Any]:
    if actor in AUTONOMOUS or role in AUTONOMOUS:
        return {"ok": False, "code": "AUTONOMOUS_DISPOSITION_DENIED", "actor": actor}
    if actor != HUMAN or role != HUMAN_ROLE:
        return {"ok": False, "code": "HOLD_NAMED_HUMAN_REQUIRED", "actor": actor}
    if draft["state"] != "DRAFT":
        return {"ok": False, "code": "HOLD_NOT_A_DRAFT", "fixture_id": draft["fixture_id"]}
    draft["released"] = True
    draft["released_by"] = actor
    draft["submitted"] = False
    draft["certified"] = False
    draft["live"] = False
    return {"ok": True, "code": "HUMAN_DRAFT_DISPOSITION", "fixture_id": draft["fixture_id"]}


def empty_ledger() -> dict[str, Any]:
    return {
        "drafts": {},
        "holds": [],
        "seen": {},
        "production_writes": 0,
        "live_submissions": 0,
        "city_contacts": 0,
        "cash_usd": 0,
        "adapters": {"cmdp": "SYNTHETIC_READONLY", "lims": "SYNTHETIC_READONLY"},
    }


def ingest(ledger: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    field_failures = validate_fixture_fields(fixture)
    if field_failures:
        raise EvidenceError("; ".join(field_failures))
    key = fixture["fixture_id"]
    if key in ledger["seen"]:
        return {"kind": "NOOP", "fixture_id": key}
    draft = prepare_draft(fixture)
    ledger["seen"][key] = draft["draft_sha256"]
    if draft["state"] == "HOLD":
        ledger["holds"].append(draft)
        return {"kind": "HOLD", "fixture_id": key, "code": draft["hold_code"]}
    ledger["drafts"][key] = draft
    return {"kind": "DRAFT", "fixture_id": key}


def replay_into(ledger: dict[str, Any], fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    before_d = len(ledger["drafts"])
    before_h = len(ledger["holds"])
    noops = 0
    for row in fixtures:
        result = ingest(ledger, row)
        if result.get("kind") == "NOOP":
            noops += 1
    return {
        "added_drafts": len(ledger["drafts"]) - before_d,
        "added_holds": len(ledger["holds"]) - before_h,
        "replay_noops": noops,
    }


def build_audit(ledger: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    drafts = [
        {
            "fixture_id": item["fixture_id"],
            "family": item["family"],
            "state": item["state"],
            "hold_code": item["hold_code"],
            "draft_sha256": item["draft_sha256"],
            "released": item["released"],
            "submitted": item["submitted"],
        }
        for item in sorted(ledger["drafts"].values(), key=lambda row: row["fixture_id"])
    ]
    holds = [
        {
            "fixture_id": item["fixture_id"],
            "family": item["family"],
            "hold_code": item["hold_code"],
            "draft_sha256": item["draft_sha256"],
        }
        for item in sorted(ledger["holds"], key=lambda row: row["fixture_id"])
    ]
    return {
        "demand_id": DEMAND_ID,
        "schema": SCHEMA,
        "state": STATE,
        "mode": "DRAFT_EXPORT_PREPARATION_ONLY",
        "field_count": len(matrix["fields"]),
        "source_count": len(matrix["sources"]),
        "unknown_count": len(matrix["unknowns"]),
        "families": list(FAMILIES),
        "child_nodes": matrix["child_nodes"],
        "drafts": drafts,
        "holds": holds,
        "production_writes": ledger["production_writes"],
        "live_submissions": ledger["live_submissions"],
        "city_contacts": ledger["city_contacts"],
        "cash_usd": 0,
        "seivers_spelling": SEIVERS,
        "cite_only": CITE_ONLY,
        "xml_schema_version": matrix["version_effective_date"]["xml_schema"]["document_version"],
        "xml_schema_date": matrix["version_effective_date"]["xml_schema"]["effective_date"],
    }


EXPECTED = {
    "fixtures": 6,
    "drafts": 5,
    "holds": 1,
    "families_drafted": 3,
    "replay_added_drafts": 0,
    "replay_added_holds": 0,
    "live_submissions": 0,
    "production_writes": 0,
    "city_contacts": 0,
    "cash_usd": 0,
    "autonomous_released": 0,
}


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "fixtures": result["fixtures"],
        "drafts": result["drafts"],
        "holds": result["holds"],
        "families_drafted": result["families_drafted"],
        "replay_added_drafts": result["replay"]["added_drafts"],
        "replay_added_holds": result["replay"]["added_holds"],
        "live_submissions": result["live_submissions"],
        "production_writes": result["production_writes"],
        "city_contacts": result["city_contacts"],
        "cash_usd": result["cash_usd"],
        "autonomous_released": result["autonomous_released"],
    }
    return {"expected": deepcopy(EXPECTED), "actual": actual, "match": actual == EXPECTED}


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if result.get("matrix_failures"):
        failures.append("matrix")
    if not expected_actual(result)["match"]:
        failures.append("counts")
    if result["replay"]["added_drafts"] or result["replay"]["added_holds"]:
        failures.append("replay")
    if result["audit_sha256"] != result["replay_audit_sha256"]:
        failures.append("replay_hash")
    if result.get("golden_locked") and result["audit_sha256"] != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if result["live_submissions"] or result["production_writes"] or result["city_contacts"]:
        failures.append("live")
    if result["cash_usd"] != 0:
        failures.append("cash")
    if result["state"] != STATE:
        failures.append("state")
    if any(item.get("submitted") for item in result["draft_records"]):
        failures.append("submission")
    return failures


def invented_field_probe(fixtures: list[dict[str, Any]]) -> list[str]:
    poisoned = deepcopy(fixtures[0])
    poisoned["sample"]["InventedColumn"] = "nope"
    return validate_fixture_fields(poisoned)


def missing_citation_probe(matrix: dict[str, Any]) -> list[str]:
    poisoned = deepcopy(matrix)
    poisoned["fields"][0]["citation"] = {"url": "", "page_or_section": "", "version": "", "effective_date": ""}
    return validate_matrix(poisoned)


def unknown_as_known_probe(matrix: dict[str, Any]) -> list[str]:
    poisoned = deepcopy(matrix)
    for row in poisoned["fields"]:
        if row["xml_element"] == "analyteCd":
            row["valid_values"] = ["1040", "1041", "2214"]
            row["valid_values_status"] = UNKNOWN
    return validate_matrix(poisoned)


def submission_probe() -> dict[str, Any]:
    return refuse_submission("Certify and Submit to State")


def render_matrix_md(matrix: dict[str, Any]) -> str:
    lines = [
        "# AT-GROK-CMDP-EVIDENCE-01 schema matrix",
        "",
        "Draft/export preparation only. EPA/state primary sources. Never invent fields.",
        "Unknowns are written exactly as `UNKNOWN / BUYER OR VENDOR SAMPLE REQUIRED`.",
        "",
        "## Sources",
        "",
    ]
    for src in matrix["sources"]:
        lines.append(
            "- **%s** — %s — %s — version %s — effective %s — %s"
            % (
                src["id"],
                src["title"],
                src["url"],
                src["version"],
                src["effective_date"],
                src["page_or_section"],
            )
        )
    lines.extend(["", "## Child nodes (Table 1)", ""])
    for family, nodes in matrix["child_nodes"].items():
        lines.append("- %s: %s" % (family, ", ".join(nodes)))
    lines.extend(["", "## Fields", "", "| xml_element | req | type | families | values | source section | version / date |", "|---|---|---|---|---|---|---|"])
    for row in matrix["fields"]:
        values = ", ".join(row["valid_values"] or []) if row["valid_values"] else row["valid_values_status"]
        cite = row["citation"]
        lines.append(
            "| `%s` | %s | %s | %s | %s | %s | %s / %s |"
            % (
                row["xml_element"],
                row["requirement"],
                row["data_type"],
                ",".join(row["families"]),
                values.replace("|", "/"),
                cite["page_or_section"].replace("|", "/"),
                cite["version"],
                cite["effective_date"],
            )
        )
    lines.extend(["", "## Validations", ""])
    for row in matrix["validations"]:
        lines.append("- **%s** (%s): %s — %s" % (row["id"], ",".join(row["applies"]), row["rule"], row["citation"]["url"]))
    lines.extend(["", "## Correction / rejection", ""])
    for row in matrix["correction_rejection"]:
        lines.append("- **%s** [%s]: %s — runner: %s" % (row["id"], row["phase"], row["rule"], row["this_runner"]))
    lines.extend(["", "## Source-to-draft reconciliation", ""])
    for row in matrix["source_to_draft_reconciliation"]:
        lines.append("- **%s**: %s" % (row["id"], row["rule"]))
    lines.extend(["", "## Version / effective date", ""])
    xml = matrix["version_effective_date"]["xml_schema"]
    lines.append(
        "- XML schema %s document %s effective %s (%s)."
        % (xml["product"], xml["document_version"], xml["effective_date"], xml["citation"]["url"])
    )
    lines.append("- Later than 1.13: %s" % matrix["version_effective_date"]["later_than_1_13"])
    lines.extend(["", "## Unknowns", ""])
    for row in matrix["unknowns"]:
        lines.append("- **%s**: %s — %s" % (row["item"], row["status"], row["why"]))
    lines.extend(["", "State: `%s`. cash_usd=0. Seivers spelling preserved if referenced." % STATE, ""])
    return "\n".join(lines)


def _write_text_preserving_keep_tail(path: Path, body: str) -> None:
    """Leave titanmcp / live-cash KEEP tails on disk. Official CLI rewrite is idempotent."""
    if not body.endswith("\n"):
        body += "\n"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if existing.startswith(body):
        return
    keep = ""
    idx = None
    for marker in ("## Contest product (titanmcp)", "## Live cash"):
        at = existing.find(marker)
        if at != -1:
            idx = at if idx is None else min(idx, at)
    if idx is not None:
        keep = existing[idx:]
        if idx > 0 and existing[idx - 1] == "\n":
            keep = existing[idx - 1 :]
        if keep and not keep.startswith("\n"):
            keep = "\n" + keep
    path.write_text(body.rstrip("\n") + keep, encoding="utf-8")


def write_pack(matrix: dict[str, Any], fixtures: list[dict[str, Any]]) -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (HERE / "schema_matrix.json").write_text(_canonical(matrix) + "\n", encoding="utf-8")
    _write_text_preserving_keep_tail(HERE / "SCHEMA_MATRIX.md", render_matrix_md(matrix))
    (HERE / "sources.json").write_text(_canonical(matrix["sources"]) + "\n", encoding="utf-8")
    (HERE / "unknowns.json").write_text(_canonical(matrix["unknowns"]) + "\n", encoding="utf-8")
    (HERE / "fixtures.json").write_text(_canonical(fixtures) + "\n", encoding="utf-8")
    for row in fixtures:
        (FIXTURE_DIR / ("%s.json" % row["fixture_id"])).write_text(_canonical(row) + "\n", encoding="utf-8")
    _write_text_preserving_keep_tail(
        HERE / "README.md",
        "\n".join(
            [
                "# AT-GROK-CMDP-EVIDENCE-01",
                "",
                "Official CMDP reporting-schema evidence for Microbial, Chems-Rads, and Cryptosporidium.",
                "Working runner, not a spec. Draft/export preparation only.",
                "",
                "```",
                "python3 at_grok_cmdp_evidence.py",
                "python3 test_at_grok_cmdp_evidence.py",
                "```",
                "",
                "Unknowns stay `%s`." % UNKNOWN,
                "HOLD / BUILD-AND-VERIFY. cash_usd=0. No submission.",
                "",
            ]
        ),
    )
    (HERE / "contract.json").write_text(
        _canonical(
            {
                "id": DEMAND_ID,
                "official_command": "python3 at_grok_cmdp_evidence.py",
                "binary": "python3 test_at_grok_cmdp_evidence.py",
                "state": STATE,
                "mode": "DRAFT_EXPORT_PREPARATION_ONLY",
                "cash_usd": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def load_pack() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    matrix_path = HERE / "schema_matrix.json"
    fixture_path = HERE / "fixtures.json"
    if matrix_path.is_file() and fixture_path.is_file():
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
        return matrix, fixtures
    matrix = schema_matrix()
    fixtures = synthetic_fixtures()
    write_pack(matrix, fixtures)
    return matrix, fixtures


def run_evidence(
    matrix: dict[str, Any] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if matrix is None or fixtures is None:
        loaded_matrix, loaded_fixtures = load_pack()
        matrix = matrix if matrix is not None else loaded_matrix
        fixtures = fixtures if fixtures is not None else loaded_fixtures
    matrix_failures = validate_matrix(matrix)
    if matrix_failures:
        raise EvidenceError("; ".join(matrix_failures))
    for row in fixtures:
        field_failures = validate_fixture_fields(row)
        if field_failures:
            raise EvidenceError("; ".join(field_failures))
    ledger = empty_ledger()
    for row in fixtures:
        ingest(ledger, row)
    auto = dispose(next(iter(ledger["drafts"].values())), "robot", "AUTONOMOUS")
    human_effects = [
        dispose(item, HUMAN, HUMAN_ROLE) for item in ledger["drafts"].values()
    ]
    audit = build_audit(ledger, matrix)
    audit_sha = sha256_hex(audit)
    replay = replay_into(ledger, fixtures)
    replay_audit = build_audit(ledger, matrix)
    replay_sha = sha256_hex(replay_audit)
    families_drafted = sorted({item["family"] for item in ledger["drafts"].values()})
    golden_locked = GOLDEN_AUDIT_SHA256 != "PIN_AFTER_FIRST_RUN"
    packed = {
        "demand_id": DEMAND_ID,
        "state": STATE,
        "mode": "DRAFT_EXPORT_PREPARATION_ONLY",
        "fixtures": len(fixtures),
        "drafts": len(ledger["drafts"]),
        "holds": len(ledger["holds"]),
        "families_drafted": len(families_drafted),
        "family_names": families_drafted,
        "hold_codes": sorted({item["hold_code"] for item in ledger["holds"]}),
        "draft_records": [
            deepcopy(item)
            for item in sorted(ledger["drafts"].values(), key=lambda row: row["fixture_id"])
        ],
        "hold_records": deepcopy(ledger["holds"]),
        "autonomous_release_effect": auto,
        "human_release_effects": human_effects,
        "autonomous_released": 0,
        "matrix_failures": matrix_failures,
        "audit": audit,
        "audit_sha256": audit_sha,
        "replay": replay,
        "replay_audit_sha256": replay_sha,
        "production_writes": ledger["production_writes"],
        "live_submissions": ledger["live_submissions"],
        "city_contacts": ledger["city_contacts"],
        "cash_usd": 0,
        "seivers_spelling": SEIVERS,
        "cite_only": CITE_ONLY,
        "golden_locked": golden_locked,
        "official_binary": "python3 at_grok_cmdp_evidence.py",
        "official_test": "python3 test_at_grok_cmdp_evidence.py",
        "sources": matrix["sources"],
        "unknowns": matrix["unknowns"],
    }
    packed["failures"] = pass_contract(packed) if golden_locked else []
    packed["ok"] = (
        expected_actual(packed)["match"]
        and packed["replay"]["added_drafts"] == 0
        and packed["replay"]["added_holds"] == 0
        and packed["audit_sha256"] == packed["replay_audit_sha256"]
        and packed["failures"] == []
    )
    return packed


def write_receipts(result: dict[str, Any]) -> None:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    counts = expected_actual(result)
    (RECEIPT_DIR / "run.json").write_text(
        _canonical(
            {
                "demand_id": DEMAND_ID,
                "ok": result["ok"],
                "expected": counts["expected"],
                "actual": counts["actual"],
                "audit_sha256": result["audit_sha256"],
                "official_binary": result["official_binary"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (RECEIPT_DIR / "audit.json").write_text(_canonical(result["audit"]) + "\n", encoding="utf-8")
    (RECEIPT_DIR / "replay.json").write_text(_canonical(result["replay"]) + "\n", encoding="utf-8")


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    counts = expected_actual(result)
    return {
        "demand_id": DEMAND_ID,
        "ok": result["ok"],
        "failures": result.get("failures") or [],
        "expected": counts["expected"],
        "actual": counts["actual"],
        "match": counts["match"],
        "audit_sha256": result["audit_sha256"],
        "replay_audit_sha256": result["replay_audit_sha256"],
        "replay": result["replay"],
        "state": STATE,
        "mode": "DRAFT_EXPORT_PREPARATION_ONLY",
        "cash_usd": 0,
        "seivers_spelling": SEIVERS,
        "cite_only": CITE_ONLY,
        "official_binary": result["official_binary"],
        "official_test": result["official_test"],
        "families": result["family_names"],
        "hold_codes": result["hold_codes"],
        "source_urls": [row["url"] for row in result["sources"]],
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--write-pack"]:
        matrix = schema_matrix()
        fixtures = synthetic_fixtures()
        write_pack(matrix, fixtures)
        sys.stdout.write(
            _canonical({"wrote": str(HERE), "fields": len(matrix["fields"]), "fixtures": len(fixtures)})
            + "\n"
        )
        return 0
    if args == ["--print-goldens"]:
        write_pack(schema_matrix(), synthetic_fixtures())
        result = run_evidence()
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "expected": expected_actual(result),
                    "ok": result["ok"],
                }
            )
            + "\n"
        )
        return 0
    write_pack(schema_matrix(), synthetic_fixtures())
    try:
        result = run_evidence()
    except EvidenceError as exc:
        sys.stderr.write("AT-GROK-CMDP-EVIDENCE-01 FAIL\n%s\n" % exc)
        return 1
    write_receipts(result)
    payload = cli_payload(result)
    sys.stdout.write("ok %s\n" % ("true" if payload["ok"] else "false"))
    sys.stdout.write("audit_sha256 %s\n" % payload["audit_sha256"])
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] and not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
