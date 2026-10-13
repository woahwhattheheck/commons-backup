# SWFWMD RTFF forecast evidence workstream

Internal source/test/demo + commercial carrier for RFP 26-4972. It supports a qualified flood-forecasting SaaS prime; it is not a flood model or a District proposal.

## Evidence contract
- hashes and timestamps District/USGS/NOAA/operator inputs;
- enforces explicit source-freshness limits;
- binds each run to model artifact, 72h+ horizon, interval, input set, scenario and output hash;
- preserves what-if scenario lineage;
- checks deterministic replay and makes output drift `review_required`;
- permanently denies forecast-accuracy, emergency-action and production-release authority.

The RFP requires a real configurable RTFF SaaS, existing StormWise/SWMM/HEC-RAS use, external gage/NOAA/USGS feeds, hourly updating, what-if analysis and 24/7 U.S.-hosted service. It also requires SOC 2 Type II/equivalent for the proposed solution and associated service providers and three similar public-entity references. Those are prime responsibilities, not claims made here.

The solicitation explicitly permits a Prime Respondent with Sub-Respondent(s), and separately excludes engineering services for developing/calibrating/modifying the RTFF models. This workstream stays inside that seam.

## Verify
`python -m unittest -q tests/test_evidence.py`

Commercial state is `PROPOSED_NOT_ACCEPTED`; see `OFFER.md`. Before any vendor outreach: recheck all addenda, Slack + Gmail collision history, obtain Muse single-writer clearance, send only the cleared message, then DNR that org/opportunity until a genuinely newer provider event.
