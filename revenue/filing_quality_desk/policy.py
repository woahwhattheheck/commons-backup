from .core import *

def parse_policy(p):
    extra=set(p)-{'cik','filed_on_or_before','selectors','checks'}
    if extra:raise FilingQualityError(f'unknown policy fields: {sorted(extra)}')
    cik=text(p.get('cik'),'cik')
    if not cik.isdigit():raise FilingQualityError('cik must be digits')
    cutoff=p.get('filed_on_or_before');cutoff=day(cutoff,'filed_on_or_before') if cutoff is not None else None
    sels=p.get('selectors');checks=p.get('checks',[])
    if not isinstance(sels,list) or not sels:raise FilingQualityError('selectors must be nonempty array')
    if not isinstance(checks,list):raise FilingQualityError('checks must be array')
    out=[];seen=set()
    for i,q in enumerate(sels):
        if not isinstance(q,dict) or set(q)-{'id','taxonomy','concept','unit','kind','start','end','filed_on_or_before'}:raise FilingQualityError('invalid selector fields')
        sid=ident(q.get('id'),f'selector[{i}].id')
        if sid in seen:raise FilingQualityError(f'duplicate selector {sid}')
        seen.add(sid);kind=text(q.get('kind'),f'{sid}.kind')
        if kind not in {'instant','duration'}:raise FilingQualityError('kind must be instant or duration')
        start=q.get('start');start=day(start,f'{sid}.start') if start is not None else None
        if (kind=='duration')!=(start is not None):raise FilingQualityError('duration requires start; instant forbids start')
        sc=q.get('filed_on_or_before',cutoff);sc=day(sc,f'{sid}.cutoff') if sc is not None else None
        out.append({'id':sid,'taxonomy':ident(q.get('taxonomy','us-gaap'),f'{sid}.taxonomy'),'concept':ident(q.get('concept'),f'{sid}.concept'),'unit':unit(q.get('unit'),f'{sid}.unit'),'kind':kind,'start':start,'end':day(q.get('end'),f'{sid}.end'),'cutoff':sc})
    check_ids=set()
    for c in checks:
        if not isinstance(c,dict) or set(c)-{'id','kind','lhs','rhs','tolerance'}:raise FilingQualityError('invalid check fields')
        cid=ident(c.get('id'),'check.id')
        if cid in check_ids:raise FilingQualityError(f'duplicate check {cid}')
        check_ids.add(cid)
        if c.get('kind')!='sum_equals' or not isinstance(c.get('lhs'),list) or not c['lhs']:raise FilingQualityError('unsupported check')
        refs=[]
        for x in c['lhs']:refs.append(ident(x,'check.lhs'))
        refs.append(ident(c.get('rhs'),'check.rhs'))
        unknown=sorted(set(refs)-seen)
        if unknown:raise FilingQualityError(f'check {cid} references unknown selectors: {unknown}')
        tol=dec(c.get('tolerance','0'),'tolerance')
        if tol<0:raise FilingQualityError('negative tolerance')
    return cik,cutoff,out,checks
