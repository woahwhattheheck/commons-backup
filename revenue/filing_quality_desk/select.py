from .core import *

def _public(x):
    return {'value':dec_text(x['v']),'filed':x['filed'],'accession':x['accn'],'form':x['form']}

def select(facts,q):
    try:rows=facts[q['taxonomy']][q['concept']]['units'][q['unit']]
    except (KeyError,TypeError) as e:raise FilingQualityError(f"missing fact path for {q['id']}") from e
    if not isinstance(rows,list):raise FilingQualityError('fact unit must be array')
    candidates=[]
    for r in rows:
        if not isinstance(r,dict) or r.get('end')!=q['end']:continue
        if q['kind']=='instant' and r.get('start') is not None:continue
        if q['kind']=='duration' and r.get('start')!=q['start']:continue
        filed=day(r.get('filed'),f"{q['id']}.filed")
        if q['cutoff'] and filed>q['cutoff']:continue
        candidates.append({'v':dec(r.get('val'),f"{q['id']}.val"),'filed':filed,'accn':text(r.get('accn'),f"{q['id']}.accn"),'form':text(r.get('form','UNKNOWN'),f"{q['id']}.form")})
    if not candidates:raise FilingQualityError(f"no in-scope fact for {q['id']}")
    latest=max(x['filed'] for x in candidates);same=[x for x in candidates if x['filed']==latest]
    if len({dec_text(x['v']) for x in same})!=1:raise FilingQualityError(f"ambiguous same-day differing values for {q['id']}")
    same.sort(key=lambda x:(x['accn'],x['form'],dec_text(x['v'])))
    best=same[0];value=best['v']
    prior=sorted((_public(x) for x in candidates if x['filed']<latest),key=lambda x:(x['filed'],x['accession'],x['form'],x['value']))
    provenance=[_public(x) for x in same]
    return {'selector_id':q['id'],'taxonomy':q['taxonomy'],'concept':q['concept'],'unit':q['unit'],'kind':q['kind'],'start':q['start'],'end':q['end'],'period':f"{q['start'] or ''}/{q['end']}",'value':dec_text(value),'filed':latest,'accession':best['accn'],'form':best['form'],'provenance_accessions':sorted({x['accn'] for x in same}),'provenance':provenance,'prior_values':sorted({x['value'] for x in prior if x['value']!=dec_text(value)}),'prior_observations':prior}
