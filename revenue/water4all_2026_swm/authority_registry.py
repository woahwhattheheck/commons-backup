"""Repository-pinned trust roots for the Water4All 2026 readiness carrier.

Payloads may prove their own integrity, but they do not get to mint authority.
Only exact records retained here may satisfy source/evidence trust checks.
The TEST_ONLY mappings are intentionally empty in production and are populated
only by the hostile test helper running in-process.
"""

from __future__ import annotations

from types import MappingProxyType


def _source(
    source_id,
    authority_class,
    source_url,
    version,
    observed_at,
    published_at,
    preproposal_deadline_at,
    fact_commitment,
):
    return {
        "source_id": source_id,
        "authority_class": authority_class,
        "source_url": source_url,
        "version": version,
        "observed_at": observed_at,
        "published_at": published_at,
        "call_title": "Water4All 2026 Joint Transnational Call: Sustainable Water Management",
        "preproposal_deadline_at": preproposal_deadline_at,
        "full_proposal_deadline_at": "2027-04-06T13:00:00Z",
        "budget_eur_cents": 3422180410,
        "complete": True,
        "declared_current": True,
        "fact_commitment": fact_commitment,
    }


_PINNED_SOURCES = {
    "water4all-call-page-20260914": _source(
        "water4all-call-page-20260914",
        "OFFICIAL_CALL_PAGE",
        "https://www.water4all-partnership.eu/joint-activities/water4all-2026-joint-transnational-call",
        "live-page-observed-2026-09-14",
        "2026-09-14T03:40:00Z",
        "2026-09-08T00:00:00Z",
        "2026-11-10T14:00:00Z",
        "928f256d659c580f4bd738bdce832462a97b56f8287a4cbcc2e7ae4e035a8dbf",
    ),
    "water4all-call-announcement-v2-20260908": _source(
        "water4all-call-announcement-v2-20260908",
        "OFFICIAL_CALL_ANNOUNCEMENT",
        "https://www.water4all-partnership.eu/sites/default/files/2026-09/Call_Announcement_Water4All_JTC2026_20260908.pdf",
        "V2-2026-09-08",
        "2026-09-14T03:40:00Z",
        "2026-09-08T00:00:00Z",
        "2026-11-10T14:00:00Z",
        "1999a4f7885b90bc378a241ea138fc7895ee9dbb2e5a9694a002f36bcb6944bf",
    ),
    "water4all-national-regulations-v2-20260910": _source(
        "water4all-national-regulations-v2-20260910",
        "OFFICIAL_NATIONAL_REGULATIONS",
        "https://www.water4all-partnership.eu/sites/default/files/2026-06/National_Regulations-Water4All_JTC2026.pdf",
        "V2.0-2026-09-10-cover",
        "2026-09-14T03:40:00Z",
        "2026-09-10T00:00:00Z",
        "2026-11-12T14:00:00Z",
        "a0d568854c853acff6790b83697212be61d6f2132151957120e717b7f36c24bb",
    ),
    "water4all-faq-live-20260914": _source(
        "water4all-faq-live-20260914",
        "OFFICIAL_FAQ",
        "https://www.water4all-partnership.eu/joint-activities/water4all-2026-joint-transnational-call",
        "faq-section-live-observed-2026-09-14",
        "2026-09-14T03:40:00Z",
        None,
        "2026-11-10T14:00:00Z",
        "c29e545b755fb54057eb29a548e91956a86674772d77d185f068b65402b8dcd5",
    ),
}

PINNED_OFFICIAL_SOURCE_GENERATIONS = MappingProxyType(_PINNED_SOURCES)
PINNED_TECHNICAL_EVIDENCE = MappingProxyType({})

# Test fixtures may install exact retained descriptors here. These mappings are
# never consulted before the immutable production trust roots above.
TEST_ONLY_OFFICIAL_SOURCE_GENERATIONS = {}
TEST_ONLY_TECHNICAL_EVIDENCE = {}


def retained_source(source_id):
    return PINNED_OFFICIAL_SOURCE_GENERATIONS.get(source_id) or TEST_ONLY_OFFICIAL_SOURCE_GENERATIONS.get(source_id)


def retained_evidence(evidence_id):
    return PINNED_TECHNICAL_EVIDENCE.get(evidence_id) or TEST_ONLY_TECHNICAL_EVIDENCE.get(evidence_id)
