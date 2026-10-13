# Walkthrough — synthetic ESS enrollment-period / IAM access-dependency

This is fiction. Not a University finding, live system, or schedule.

## Stage 1 (relative week W10)

1. ESS publishes a new add/drop window (`Window-NEW` / W12) replacing `Window-OLD` / W10.
   Source `SRC-ESS-CAL-01` → evidence `EV-ESS-SD-001` (SUPPORTING).
2. The ESS deploy pipeline excerpt still pins `registration_window_id = Window-OLD`.
   Source `SRC-ESS-DEP-01` → evidence `EV-ESS-DEP-001` (SUPPORTING).
3. Review note: IAM group provisioning binding is unknown.
   Evidence `EV-IAM-SEC-001` stays **HOLD**. Absence of evidence is not promotion.

**Conclusions:** ESS/SD supported, ESS/DEP supported, IAM/SEC HOLD.

## Stage 2 (relative week W13) — append only

4. IAM job definition arrives (`SRC-IAM-JOB-02`): still keyed to `Window-OLD`.
   New row `EV-IAM-SEC-002` (SUPPORTING). Stage 1 rows are not rewritten.
5. Operational outcome note (`SRC-OPS-OUT-03`): after Window-NEW closed, membership
   was not refreshed. New row `EV-IAM-SEC-003` (SUPPORTING).

**Conclusions:** IAM/SEC becomes supported *because new rows were appended*.
The original HOLD row remains HOLD in the register. History is preserved.

Field names are the published UIOWA-023 register plus GRANITE UIOWA-031
`source_id` / `excerpt_locator` / `practice_supported`. No unpublished contract.
