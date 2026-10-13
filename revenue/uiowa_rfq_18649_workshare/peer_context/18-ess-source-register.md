# UIOWA-018 — Official source register and retrieval limits

**Access date:** 2026-09-19  
**Classification:** `PUBLIC_PEER_CONTEXT_NOT_IOWA_EVIDENCE`  
**Companions:** [peer pack](18-ess-peer-pack.md) · [discovery matrix](18-ess-discovery-matrix.md)

## Reading the register

The nine entries identify pages read from official institutional websites. The locator names the relevant heading or paragraph; it is not a fabricated PDF page number. Publication/update dates were not stated in the retrieved pages and remain `null`. The access date says when this research read the page, not when the institution last maintained it. Dated entries inside a page are separately typed as notices, index entries or planned events. Search-crawl dates and copyright footers are not publication dates.

Each entry is a source of public context only. The classifications describe the evidence obtained, not the quality of the institution's operation. No source-content checksum is claimed because a preserved byte-exact source snapshot was not collected. The JSON below is bibliographic metadata, not authenticated operational evidence. To reproduce a time-sensitive claim, reread the official URL and its named section; retain any changed wording as a new research generation.

## Source directory

| Source | Institution / issuer | Relevant locator | Evidence type |
|---|---|---|---|
| [ESS18-S01](https://its.umich.edu/enterprise/administrative-systems/m-pathways/student-administration-system) | University of Michigan / Information and Technology Services | Opening service description; Student Administration Modules: Campus Community, Student Financials, Student Records | `PUBLISHED_SERVICE_DESCRIPTION` |
| [ESS18-S02](https://its.umich.edu/enterprise/administrative-systems/m-pathways/student-administration-system/curriculum-module) | University of Michigan / Information and Technology Services | Course Information; Class Information | `PUBLISHED_RESPONSIBILITY_DESCRIPTION` |
| [ESS18-S03](https://its.umich.edu/about/advisory-groups/administrative/srcaa) | University of Michigan / Information and Technology Services | Opening purpose and representation paragraphs; Goals; Meetings | `PUBLISHED_GOVERNANCE_DESCRIPTION` |
| [ESS18-S04](https://its.umich.edu/enterprise/administrative-systems/unit-liaisons) | University of Michigan / Information and Technology Services | Opening role paragraph; Announcements: September meeting, July cancellation, May cancellation | `PUBLISHED_COMMUNICATION_DESCRIPTION_AND_DATED_INDEX` |
| [ESS18-S05](https://it.umn.edu/resources-it-staff-partners/enterprise-applications) | University of Minnesota / Office of Information Technology / IT@UMN | Opening module list; integration paragraph; OIT maintenance and test-environment paragraph | `PUBLISHED_SERVICE_DESCRIPTION` |
| [ESS18-S06](https://sis.berkeley.edu/) | University of California, Berkeley / Student Integrated Systems | Campus Solutions and CalCentral descriptions; About SIS | `PUBLISHED_SERVICE_AND_TEAM_DESCRIPTION` |
| [ESS18-S07](https://sis.berkeley.edu/maintenance) | University of California, Berkeley / Student Integrated Systems | Opening planned-maintenance paragraph; Upcoming Planned Maintenance Schedule | `PUBLISHED_PLANNED_MAINTENANCE` |
| [ESS18-S08](https://registrar.berkeley.edu/calendars/) | University of California, Berkeley / Office of the Registrar | Opening paragraph; Enrollment Calendar; Academic Calendar; Final Exam Groups | `PUBLISHED_FUNCTIONAL_CALENDAR_DIRECTORY` |
| [ESS18-S09](https://its.umich.edu/enterprise/administrative-systems/unit-liaisons/announcements/september-unit-liaison-meeting-1) | University of Michigan / Information and Technology Services | Meeting invitation; Tentative Meeting Agenda | `DATED_MEETING_NOTICE_NOT_MINUTES` |

## Retrieval and interpretation limitations

The Berkeley SIS service-level-agreement landing page linked to a Google document whose destination returned **HTTP 401**. Its contents were not read. No service-level targets, exclusions, support hours, penalties or recovery obligations have been extracted or inferred from that link. This does not imply that an agreement does not exist.

The calendar directory was read, but no full calendar event export was retained. The pack does not assert a particular enrollment or examination deadline. The maintenance schedule was read as a plan; listed past dates were not relabeled as completed events. The September liaison page was read as an invitation with a tentative agenda, not as minutes or evidence of attendance.

No private peer system was accessed, no login or production endpoint was tested, and no institutional representative was contacted. The source set does not establish staff-size comparability, actual change failure rates, observed recovery times, adoption across all units, or any Iowa architecture or finding. The local discovery questions intentionally expose those unknowns.

## Bibliographic interchange

```json
{
  "schema": "uiowa-018-peer-source-register/v1",
  "classification": "PUBLIC_PEER_CONTEXT_NOT_IOWA_EVIDENCE",
  "accessed_on": "2026-09-19",
  "sources": [
    {
      "id": "ESS18-S01",
      "institution": "University of Michigan",
      "issuer": "Information and Technology Services",
      "title": "M-Pathways Student Administration System (SA)",
      "url": "https://its.umich.edu/enterprise/administrative-systems/m-pathways/student-administration-system",
      "locator": "Opening service description; Student Administration Modules: Campus Community, Student Financials, Student Records",
      "kind": "PUBLISHED_SERVICE_DESCRIPTION",
      "boundary": "Ann Arbor student administration; described interfaces with other administrative modules",
      "accessed_on": "2026-09-19",
      "published_or_updated_on": null,
      "date_status": "NOT_STATED_IN_RETRIEVED_PAGE",
      "measurement_status": "NO_MEASURED_OPERATIONAL_OUTCOME_RETAINED",
      "iowa_evidence": false
    },
    {
      "id": "ESS18-S02",
      "institution": "University of Michigan",
      "issuer": "Information and Technology Services",
      "title": "M-Pathways Curriculum Module",
      "url": "https://its.umich.edu/enterprise/administrative-systems/m-pathways/student-administration-system/curriculum-module",
      "locator": "Course Information; Class Information",
      "kind": "PUBLISHED_RESPONSIBILITY_DESCRIPTION",
      "boundary": "Course and term-specific class information, not an IT release calendar",
      "accessed_on": "2026-09-19",
      "published_or_updated_on": null,
      "date_status": "NOT_STATED_IN_RETRIEVED_PAGE",
      "measurement_status": "NO_MEASURED_OPERATIONAL_OUTCOME_RETAINED",
      "iowa_evidence": false
    },
    {
      "id": "ESS18-S03",
      "institution": "University of Michigan",
      "issuer": "Information and Technology Services",
      "title": "Student Records, Curriculum, & Academic Advising Advisory Group",
      "url": "https://its.umich.edu/about/advisory-groups/administrative/srcaa",
      "locator": "Opening purpose and representation paragraphs; Goals; Meetings",
      "kind": "PUBLISHED_GOVERNANCE_DESCRIPTION",
      "boundary": "Student records, curriculum and academic advising stakeholder forum",
      "accessed_on": "2026-09-19",
      "published_or_updated_on": null,
      "date_status": "NOT_STATED_IN_RETRIEVED_PAGE",
      "measurement_status": "NO_MEASURED_OPERATIONAL_OUTCOME_RETAINED",
      "iowa_evidence": false
    },
    {
      "id": "ESS18-S04",
      "institution": "University of Michigan",
      "issuer": "Information and Technology Services",
      "title": "Unit Liaisons",
      "url": "https://its.umich.edu/enterprise/administrative-systems/unit-liaisons",
      "locator": "Opening role paragraph; Announcements: September meeting, July cancellation, May cancellation",
      "kind": "PUBLISHED_COMMUNICATION_DESCRIPTION_AND_DATED_INDEX",
      "boundary": "Central administrative systems liaison network; broader than student systems",
      "accessed_on": "2026-09-19",
      "published_or_updated_on": null,
      "date_status": "NOT_STATED_IN_RETRIEVED_PAGE",
      "measurement_status": "NO_MEASURED_OPERATIONAL_OUTCOME_RETAINED",
      "iowa_evidence": false,
      "dated_content": [
        {
          "date": "2026-09-09",
          "meaning": "September meeting/index entry"
        },
        {
          "date": "2026-07-02",
          "meaning": "Index date for July 8 cancellation notice"
        },
        {
          "date": "2026-05-08",
          "meaning": "Index date for May 13 cancellation notice"
        }
      ]
    },
    {
      "id": "ESS18-S05",
      "institution": "University of Minnesota",
      "issuer": "Office of Information Technology / IT@UMN",
      "title": "Enterprise Applications",
      "url": "https://it.umn.edu/resources-it-staff-partners/enterprise-applications",
      "locator": "Opening module list; integration paragraph; OIT maintenance and test-environment paragraph",
      "kind": "PUBLISHED_SERVICE_DESCRIPTION",
      "boundary": "Enterprise applications including student administration, finance and HR; not all are ESS comparators",
      "accessed_on": "2026-09-19",
      "published_or_updated_on": null,
      "date_status": "NOT_STATED_IN_RETRIEVED_PAGE",
      "measurement_status": "NO_MEASURED_OPERATIONAL_OUTCOME_RETAINED",
      "iowa_evidence": false
    },
    {
      "id": "ESS18-S06",
      "institution": "University of California, Berkeley",
      "issuer": "Student Integrated Systems",
      "title": "Student Integrated Systems home",
      "url": "https://sis.berkeley.edu/",
      "locator": "Campus Solutions and CalCentral descriptions; About SIS",
      "kind": "PUBLISHED_SERVICE_AND_TEAM_DESCRIPTION",
      "boundary": "Student academic and financial applications and processes",
      "accessed_on": "2026-09-19",
      "published_or_updated_on": null,
      "date_status": "NOT_STATED_IN_RETRIEVED_PAGE",
      "measurement_status": "NO_MEASURED_OPERATIONAL_OUTCOME_RETAINED",
      "iowa_evidence": false
    },
    {
      "id": "ESS18-S07",
      "institution": "University of California, Berkeley",
      "issuer": "Student Integrated Systems",
      "title": "Maintenance",
      "url": "https://sis.berkeley.edu/maintenance",
      "locator": "Opening planned-maintenance paragraph; Upcoming Planned Maintenance Schedule",
      "kind": "PUBLISHED_PLANNED_MAINTENANCE",
      "boundary": "Campus Solutions, CalCentral and SIS APIs; schedule is not completed-work history",
      "accessed_on": "2026-09-19",
      "published_or_updated_on": null,
      "date_status": "NOT_STATED_IN_RETRIEVED_PAGE",
      "measurement_status": "NO_MEASURED_OPERATIONAL_OUTCOME_RETAINED",
      "iowa_evidence": false,
      "dated_content": [
        {
          "date": "2026-10-04",
          "meaning": "Future planned maintenance as of access date"
        },
        {
          "date": "2026-10-11",
          "meaning": "Published deferral date for October 4 plan"
        }
      ]
    },
    {
      "id": "ESS18-S08",
      "institution": "University of California, Berkeley",
      "issuer": "Office of the Registrar",
      "title": "Calendars",
      "url": "https://registrar.berkeley.edu/calendars/",
      "locator": "Opening paragraph; Enrollment Calendar; Academic Calendar; Final Exam Groups",
      "kind": "PUBLISHED_FUNCTIONAL_CALENDAR_DIRECTORY",
      "boundary": "Supplementary functional context, not a central-IT change policy",
      "accessed_on": "2026-09-19",
      "published_or_updated_on": null,
      "date_status": "NOT_STATED_IN_RETRIEVED_PAGE",
      "measurement_status": "NO_MEASURED_OPERATIONAL_OUTCOME_RETAINED",
      "iowa_evidence": false
    },
    {
      "id": "ESS18-S09",
      "institution": "University of Michigan",
      "issuer": "Information and Technology Services",
      "title": "September Unit Liaison Meeting",
      "url": "https://its.umich.edu/enterprise/administrative-systems/unit-liaisons/announcements/september-unit-liaison-meeting-1",
      "locator": "Meeting invitation; Tentative Meeting Agenda",
      "kind": "DATED_MEETING_NOTICE_NOT_MINUTES",
      "boundary": "Liaison communication about ERP modernization; not proof of delivery or attendance",
      "accessed_on": "2026-09-19",
      "published_or_updated_on": null,
      "date_status": "NOT_STATED_IN_RETRIEVED_PAGE",
      "measurement_status": "NO_MEASURED_OPERATIONAL_OUTCOME_RETAINED",
      "iowa_evidence": false,
      "dated_content": [
        {
          "date": "2026-09-09",
          "meaning": "Advertised event date; year supplied by ESS18-S04 index, not a completion record"
        }
      ]
    }
  ]
}
```
