#!/usr/bin/env python3
"""Deterministic synthetic-only UGC campaign packet builder."""
from __future__ import annotations
import argparse,csv,hashlib,io,json,os,re,sys,tempfile,zipfile
from pathlib import Path
SCHEMA='ugc-campaign-desk/v1'; SHIP='PLANNED_NOT_SHIPPED'; RIGHTS='PROPOSED_NOT_GRANTED'; ZIP_DATE=(2026,9,8,0,0,0)
ID=re.compile(r'^[a-z0-9][a-z0-9-]{2,79}$')
class CampaignError(ValueError): pass
def req(ok,msg):
    if not ok: raise CampaignError(msg)
def exact(v,keys,at):
    req(isinstance(v,dict),f'{at} must be object'); req(set(v)==set(keys),f'{at} keys invalid')
def txt(v,at): req(isinstance(v,str) and v.strip(),f'{at} must be text'); return v.strip()
def valid(doc):
    exact(doc,{'schema','campaign','creators'},'document'); req(doc['schema']==SCHEMA,'schema mismatch')
    c=doc['campaign']; exact(c,{'id','product','product_value_usd','disclosure','usage_terms','sample','brief'},'campaign')
    req(isinstance(c['id'],str) and ID.fullmatch(c['id']),'campaign.id invalid'); [txt(c[k],f'campaign.{k}') for k in ('product','disclosure','usage_terms')]
    req(isinstance(c['product_value_usd'],str) and re.fullmatch(r'\d+\.\d{2}',c['product_value_usd']),'product value invalid')
    s=c['sample']; exact(s,{'sku','units_per_creator','shipping_state'},'sample'); txt(s['sku'],'sample.sku'); req(type(s['units_per_creator']) is int and s['units_per_creator']==1,'units_per_creator must equal 1'); req(s['shipping_state']==SHIP,'sample must remain planned/not shipped')
    b=c['brief']; exact(b,{'objective','required_points','prohibited_claims'},'brief'); txt(b['objective'],'brief.objective')
    for k in ('required_points','prohibited_claims'): req(isinstance(b[k],list) and b[k] and all(isinstance(x,str) and x.strip() for x in b[k]),f'{k} invalid')
    creators=doc['creators']; req(isinstance(creators,list) and len(creators)==5,'exactly 5 creators required'); seen_c=set(); seen_v=set()
    for i,x in enumerate(creators):
        at=f'creator[{i}]'; exact(x,{'id','display_name','audience','match_score','match_reasons','shipping','videos'},at); req(isinstance(x['id'],str) and ID.fullmatch(x['id']),f'{at}.id invalid'); req(x['id'] not in seen_c,'duplicate creator id'); seen_c.add(x['id']); txt(x['display_name'],f'{at}.display_name'); req(x['display_name'].startswith('Synthetic '),'creator names must be explicitly synthetic'); txt(x['audience'],f'{at}.audience'); req(type(x['match_score']) is int and 0<=x['match_score']<=100,'match score invalid'); req(isinstance(x['match_reasons'],list) and x['match_reasons'],'match reasons required')
        sh=x['shipping']; exact(sh,{'status','region'},f'{at}.shipping'); req(sh['status']==SHIP,'creator shipping must remain planned/not shipped'); txt(sh['region'],'shipping.region')
        req(isinstance(x['videos'],list) and len(x['videos'])==2,'exactly 2 videos per creator required')
        for v in x['videos']:
            exact(v,{'id','concept','due_date','usage_permission','disclosure_required','revision_limit','delivery_status'},'video'); req(isinstance(v['id'],str) and ID.fullmatch(v['id']),'video id invalid'); req(v['id'] not in seen_v,'duplicate video id'); seen_v.add(v['id']); txt(v['concept'],'video.concept'); req(isinstance(v['due_date'],str) and re.fullmatch(r'20\d\d-\d\d-\d\d',v['due_date']),'due date invalid'); req(v['usage_permission']==RIGHTS,'usage rights must remain proposed/not granted'); req(v['disclosure_required'] is True,'disclosure required'); req(type(v['revision_limit']) is int and 0<=v['revision_limit']<=5,'revision limit invalid'); req(v['delivery_status'] in {'BRIEF_READY','REVISION_REQUESTED','DELIVERED_UNVERIFIED'},'delivery state invalid')
    req(len(seen_v)==10,'exactly 10 videos required'); return doc
def csv_bytes(headers,rows):
    s=io.StringIO(newline=''); w=csv.writer(s,lineterminator='\n'); w.writerow(headers); w.writerows(rows); return s.getvalue().encode()
def brief(doc,x):
    c=doc['campaign']; lines=[f"# {x['display_name']} — fictional creator brief",'',f"Campaign: `{c['id']}`",f"Product: {c['product']} (fictional demo)",f"Audience: {x['audience']}",f"Match score: {x['match_score']}/100",'', '## Match reasons',*[f'- {z}' for z in x['match_reasons']],'','## Campaign objective',c['brief']['objective'],'','## Required points',*[f'- {z}' for z in c['brief']['required_points']],'','## Prohibited claims',*[f'- {z}' for z in c['brief']['prohibited_claims']],'',f"Disclosure: {c['disclosure']}",f"Usage-rights state: {RIGHTS}. {c['usage_terms']}",f"Sample logistics: {SHIP}; no shipment is represented.",'','## Deliverables']
    for v in x['videos']: lines += [f"- `{v['id']}` — {v['concept']} (due {v['due_date']}; revision limit {v['revision_limit']}; {v['delivery_status']})"]
    lines += ['','Synthetic planning artifact only; not a creator agreement, shipment, rights grant, or accepted delivery.','']; return '\n'.join(lines).encode()
def files(doc):
    valid(doc); c=doc['campaign']; creators=doc['creators']; vids=[(x,v) for x in creators for v in x['videos']]
    packet={'schema':'ugc-campaign-packet/v1','campaign':c,'counts':{'creators':5,'videos':10},'truth_boundary':{'fictional_demo':True,'creator_contacted':False,'samples_shipped':False,'usage_rights_granted':False,'customer_delivery_accepted':False,'cash_usd':0},'creators':creators}
    out={'campaign-packet.json':(json.dumps(packet,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()}
    ship=[]; rights=[]; tracker=[]
    for x in creators:
        ship.append([x['id'],x['display_name'],c['sample']['sku'],1,x['shipping']['region'],SHIP]); out[f"creator-briefs/{x['id']}.md"]=brief(doc,x)
        for v in x['videos']:
            rights.append([v['id'],x['id'],RIGHTS,'YES',c['disclosure'],c['usage_terms']]); tracker.append([v['id'],x['id'],v['due_date'],v['delivery_status'],0,v['revision_limit'],'NOT_REQUESTED',''])
    out['shipping-plan.csv']=csv_bytes(['creator_id','creator_name','sample_sku','units','region','shipping_state'],ship)
    out['rights-disclosures.csv']=csv_bytes(['video_id','creator_id','usage_permission','disclosure_required','disclosure_language','usage_terms'],rights)
    out['delivery-tracker.csv']=csv_bytes(['video_id','creator_id','due_date','delivery_status','revision_count','revision_limit','revision_status','asset_reference'],tracker)
    out['campaign-summary.md']=(f"# Fictional UGC campaign packet\n\n- Campaign: `{c['id']}`\n- Creators: 5 synthetic creators\n- Deliverables: 10 fictional videos\n- Sample logistics: `{SHIP}`\n- Usage rights: `{RIGHTS}`\n- Creator contact: false\n- Samples shipped: false\n- Customer acceptance: false\n- Cash: USD 0\n").encode()
    m={'schema':'ugc-campaign-manifest/v1','files':[{'path':p,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for p,b in sorted(out.items())]}; out['manifest.json']=(json.dumps(m,sort_keys=True,separators=(',',':'))+'\n').encode(); return out
def build_zip(doc):
    out=io.BytesIO();
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p,b in sorted(files(doc).items()):
            i=zipfile.ZipInfo(p,ZIP_DATE); i.compress_type=zipfile.ZIP_DEFLATED; i.external_attr=0o100644<<16; z.writestr(i,b,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    return out.getvalue()
def publish_zip(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=f'.{path.name}.',suffix='.tmp',dir=path.parent); stage=Path(name)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        try: os.link(stage,path)
        except FileExistsError as e: raise CampaignError(f'refusing to overwrite {path}') from e
    finally:
        try: stage.unlink()
        except FileNotFoundError: pass
def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('input',type=Path); p.add_argument('output',type=Path); a=p.parse_args(argv)
    try:
        req(a.output.suffix.lower()=='.zip','output must end in .zip'); doc=json.loads(a.input.read_text(encoding='utf-8')); raw=build_zip(doc); publish_zip(a.output,raw); print(json.dumps({'status':'BUILT_SYNTHETIC_PACKET','output':str(a.output),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'creators':5,'videos':10,'samples_shipped':False,'usage_rights_granted':False,'cash_usd':0},sort_keys=True,separators=(',',':'))); return 0
    except (CampaignError,OSError,ValueError,json.JSONDecodeError) as e: print(f'UGC CAMPAIGN INVALID: {e}',file=sys.stderr); return 1
if __name__=='__main__': raise SystemExit(main())
