#!/usr/bin/env python3
"""Generate complete fictional change histories and execute the UIOWA-076 rehearsal."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def _load_analyzer():
    """Load this component's sibling, without global path or module aliases."""
    path = Path(__file__).resolve().with_name("ai_coding.py")
    spec = importlib.util.spec_from_file_location("_uiowa076_rehearsal_analyzer", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load local analyzer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_fixture(base: Path) -> Path:
    """Write the synthetic collection into a caller-selected empty directory."""
    base.mkdir(parents=True, exist_ok=True)
    if any(base.iterdir()):
        raise ValueError("fixture destination must be empty; existing work is never reset")
    (base / "synthetic" / "sources").mkdir(parents=True)
    STAGES=('understand','author','test','repair','integrate','maintain')
    CRITERIA=('understanding','verification','revision','integration','maintenance')
    lines=['# Fictional AI-assisted coding change histories','','SYNTHETIC PREPARATION ONLY — no University observations, live model results, or employee data.',
           'Each pair is a fictional alternative-workflow scenario, not two measured real treatments.',
           'Effort is additive person-minutes, with each log ID allocated once. Parallel effort is not wall time.',
           'Fault counts concern the exact 30-day post-acceptance window; extra days must be sliced before comparison.','']
    registry=[]; changes=[]
    def evidence(eid, content, kind='artifact', when='2026-08-31T10:30:00Z'):
        start=len(lines)+1
        lines.extend([f'## {eid}',content,''])
        registry.append({'id':eid,'path':'sources/change_histories.md','sha256':'PENDING','start_line':start,
                         'end_line':start+1,'kind':kind,'observed_at':when})
        return eid
    cases=[
    ('ESS-A','ESS','assisted',[20,8,25,10,12,5],0,'bounded','Display-only registration copy with unchanged transaction semantics.'),
    ('ESS-M','ESS','manual',[20,75,30,5,15,5],0,'bounded','Display-only registration copy with unchanged transaction semantics.'),
    ('RIS-A','RIS','assisted',[15,5,40,90,20,90],3,'moderate','Research-submission mapping with a documented empty-field rule.'),
    ('RIS-M','RIS','manual',[15,50,35,20,20,30],1,'moderate','Research-submission mapping with a documented empty-field rule.'),
    ('IAM-A','IAM','assisted',[10,4,None,12,8,None],None,'broad','Broader sign-in help workflow; authorization and navigation changes are not task-equivalent.'),
    ('IAM-M','IAM','manual',[15,55,25,10,10,15],0,'bounded','Bounded sign-in help text change; no authorization or navigation changes.')]
    for cid,group,mode,amounts,faults,complexity,task in cases:
        partial=cid=='IAM-A'
        taskid=hashlib.sha256(task.encode()).hexdigest()
        accepted=None if partial else '2026-08-01T10:30:00Z'
        accept=evidence('EV-'+cid+'-ACCEPT',f'{cid}: functional acceptance recorded at {accepted}; the task is: {task}') if accepted else None
        effort=[]; coverage={}
        for stage,amount in zip(STAGES,amounts):
            detail=f'{cid}: allocated effort log {cid}-{stage}; {stage} person-minutes = {amount if amount is not None else "not recorded"}.'
            if stage=='author':detail+=' Includes context/prompt preparation, generation or manual drafting, and first-draft inspection; it is not total delivery effort.'
            if stage=='maintain':detail+=' Follow-up counts stop at the exact 30-day endpoint, 2026-08-31T10:30:00Z.' if accepted else 'No accepted release or completed observation window is available.'
            state='partial' if partial and stage in {'test','integrate'} else 'unknown' if amount is None else 'complete'
            detail+=f' Supplied stage coverage = {state}; this is fictional effort-log evidence, not elapsed time.'
            eid=evidence('EV-'+cid+'-'+stage.upper(),detail)
            effort.append({'id':cid+'-'+stage,'stage':stage,'minutes':None if amount is None else str(amount),'evidence_ids':[eid]})
            coverage[stage]={'state':state,'basis':'Retained allocated stage log and explicit coverage statement in this fictional case.','evidence_ids':[eid]}
        rationales={
          'understanding':'The reviewer explains changed assumptions and affected behavior in the retained walkthrough.',
          'verification':'Tests cover the stated acceptance rule, normal inputs and the empty-field boundary; passing checks have a stated scope.',
          'revision':'Review feedback and repair are connected to the acceptance rule, with rerun evidence after edits.',
          'integration':'Accepted revision and operations handoff are linked; acceptance is not inferred from generation.',
          'maintenance':'The complete 30-day support record states observed faults, repairs and ownership.'}
        if cid=='RIS-A':
            rationales['understanding']='The first draft misread the empty-field rule. The walkthrough documented the incorrect assumption, leading to additional repair.'
            rationales['verification']='Tests initially missed empty-field behavior. The retained acceptance packet records the gap and the added regression after repair.'
            rationales['maintenance']='Three faults required 90 person-minutes in the exact 30-day window. Fast drafting did not reduce lifecycle effort in this scenario.'
        if partial:
            rationales['understanding']='An interview asserts that the generated change is understood, but there is no retained walkthrough.'
            rationales['verification']='Test duration and coverage are incomplete; a reviewer cannot infer successful verification.'
            rationales['integration']='No functional acceptance or completed integration evidence is retained.'
            rationales['maintenance']='No completed follow-up window; a missing fault count is not zero faults.'
        practices={}
        for criterion in CRITERIA:
            state='demonstrated';kind='artifact'
            if cid=='RIS-A' and criterion in {'understanding','verification'}:state='gap'
            if partial:
                if criterion=='understanding':kind='interview'
                if criterion in {'verification','integration','maintenance'}:state='unknown'
            eid=evidence('EV-'+cid+'-'+criterion.upper()+'-PRACTICE',rationales[criterion],kind)
            practices[criterion]={'state':state,'rationale':rationales[criterion],'evidence_ids':[eid] if state!='unknown' else []}
        fid=evidence('EV-'+cid+'-FOLLOWUP', f'{cid}: '+(f'Complete fault-log enumeration for 2026-08-01T10:30:00Z through 2026-08-31T10:30:00Z; {faults} delivered faults. Associated maintenance person-minutes = {amounts[-1]}. Coverage includes all reported support records in this fictional service and window.' if accepted else 'No accepted change, no complete follow-up, and no known fault count.'))
        changes.append({'id':cid,'group':group,'mode':mode,'pair_id':'PAIR-'+group,
                        'context':{'task_fingerprint':taskid,'stack':'fictional-python-service','complexity':complexity,'criticality':'ordinary'},
                        'started_at':'2026-08-01T09:00:00Z','accepted_at':accepted,'acceptance_evidence_ids':[accept] if accept else [],
                        'effort':effort,'coverage':coverage,'practices':practices,
                        'followup':{'days':30,'observed_through':'2026-08-31T10:30:00Z' if accepted else None,
                                    'coverage':'complete' if accepted else 'unknown','reported_faults':faults,'evidence_ids':[fid]}})
    raw=('\n'.join(lines)+'\n').encode();(base/'synthetic/sources/change_histories.md').write_bytes(raw)
    digest=hashlib.sha256(raw).hexdigest()
    for source in registry:source['sha256']=digest
    fixture={'schema_version':'1.0','synthetic':True,'as_of':'2026-09-19T12:00:00Z','evidence':registry,'changes':changes}
    (base/'synthetic/changes.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    return base / "synthetic" / "changes.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New or empty rehearsal directory")
    args = parser.parse_args(argv)
    try:
        ai_coding = _load_analyzer()
        path = build_fixture(args.out)
        report = ai_coding.load_report(path)
        ai_coding.write_outputs(report, args.out / "reports")
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f"REHEARSAL ERROR: {exc}\n")
    print(f"OK changes={len(report['changes'])} pairs={len(report['comparisons'])} "
          f"comparable={sum(p['comparable'] for p in report['comparisons'])} sources={len(report['evidence'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
