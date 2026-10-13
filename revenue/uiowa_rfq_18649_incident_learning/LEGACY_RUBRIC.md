# UIOWA-067 — Incident learning and follow-through

This is an offline assessment kit for examining incident timelines, coordination, restoration, postmortem quality, and corrective-action follow-through without rating individuals.

All checked-in examples are fictional. The kit assesses supplied records only.

## Core distinction

A detailed incident narrative is useful evidence of reconstruction and analysis. It is **not** by itself evidence that the organization changed a recurring condition.

The assessment therefore separates:

1. **Timeline and restoration evidence** — what happened, when coordination occurred, and when the affected service behavior was restored.
2. **Postmortem evidence** — contributing conditions, retained sources, and lessons that are supported by the record.
3. **Corrective-action disposition** — open, completed, overdue, changed approach, or unknown.
4. **Completion evidence** — proof that the action itself was performed.
5. **Effectiveness evidence** — later evidence that the completed or revised action changed the condition, detection, response, or service outcome it was intended to improve.

## Behavior-anchored rubric

| Area | Useful evidence | Weak or unresolved evidence | Interview prompt |
|---|---|---|---|
| Timeline | Timestamped events distinguish detection, coordination, diagnosis, mitigation, restoration, and verification. | Narrative chronology without source/time semantics; missing restoration verification. | Which source is authoritative for each key time, and what event does the timestamp actually represent? |
| Coordination | Roles and handoffs are visible without turning the review into individual blame. | Only names or chat volume; unclear decision authority. | Who coordinated the response, who owned service decisions, and how were dependency owners engaged? |
| Restoration | User/service behavior is rechecked after mitigation and restoration time has defined endpoints. | “Resolved” marker with no user-facing verification. | What evidence showed the necessary business function had actually returned? |
| Contributing conditions | Conditions are tied to retained evidence and distinguish trigger, latent condition, dependency, and response constraint. | Single unsupported “root cause” label or person-centered explanation. | Which conditions made the event possible or prolonged it, and what evidence supports each? |
| Corrective actions | Action has accountable role, due/review point, explicit disposition, and traceable completion evidence. | Action list copied into a postmortem but never tracked. | Where does this action live after the postmortem is closed? |
| Changed approach | Decision record explains why the original action was replaced and identifies the replacement. | Action quietly disappears or is marked closed with no rationale. | What changed in the evidence or constraints, and what new action addresses the original intent? |
| Effectiveness | Later exercise, recurrence data, control observation, or service evidence tests whether the change worked. | Completion treated as proof of effectiveness. | What observation would show this change reduced recurrence, impact, or response friction? |

## Synthetic trace

`examples.json` contains two fictional incidents.

### SYN-INC-001 — detailed narrative, follow-through still incomplete

The postmortem is deliberately detailed and evidence-linked. Its three actions demonstrate:

- **overdue:** fallback-capacity assumptions were not revalidated by the fictional due date;
- **completed:** an investigation guide was updated, with completion evidence but no later effectiveness evidence;
- **changed approach:** a proposed duplicate monitor was rejected with a recorded rationale and replacement action.

Because no completed action has effectiveness evidence, the assessor reports `NARRATIVE_WITH_ACTIONS_PENDING`. The example is intentionally designed to prevent “good postmortem” from becoming “lasting improvement proved.”

### SYN-INC-002 — completed action with later evidence

The second fictional incident has a concise postmortem and one corrective action with both completion evidence and a later exercise reference. The assessor reports `FOLLOW_THROUGH_EVIDENCED`.

That state means follow-through evidence exists for the supplied example; it is not a department-wide maturity rating.

## Run

```bash
cd revenue/uiowa_rfq_18649_incident_learning
python incident_learning.py examples.json
python incident_learning.py examples.json --out /tmp/uiowa-067-result.json
python -m unittest -v test_incident_learning.py
```

## Assessment guardrails

- Focus findings on systems, conditions, coordination, and work design rather than personal blame.
- Keep restoration evidence separate from postmortem quality.
- Keep action completion separate from action effectiveness.
- An overdue action is not automatically the wrong action; ask about blockers, changed constraints, and disposition.
- A changed approach is acceptable when rationale, decision, and replacement are retained.
- Missing due dates or missing evidence remain `UNKNOWN`; do not silently call them overdue or failed.
- Do not infer team-wide prevalence from one incident sample.
- Use measured restoration time only when the start/end timestamp semantics are established.

## Discovery questions

- Show one incident where the initial hypothesis was wrong. How was the investigation redirected?
- Where is service restoration verified from the user or business-function perspective?
- Which corrective actions from the last several postmortems remain open, overdue, or changed?
- How are completed actions checked later for effectiveness?
- What happens when an action becomes disproportionate, obsolete, or blocked by a dependency?
- Which recurring incident conditions are visible across several records, and how is recurrence measured?
- How are lessons transferred into design, testing, release, support, or operational practice?
