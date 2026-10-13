"""Deterministic synthetic cases, not University observations or real infrastructure tests."""
import copy, json
from pathlib import Path

def rng(low,high): return {'low':low,'high':high}
def task(name,low,high,field='hours',owner='Application platform role'):
    return {'name':name,field:rng(low,high),'owner_role':owner}
def stage(name,low,high): return {'name':name,'ms':rng(low,high)}
def portable(state):
    return {key:{'state':state, 'evidence_refs':['SYN-PORT'] if state=='demonstrated' else [],
                 'note':'Fictional retained adapter/replay observation, not a real provider test.' if state=='demonstrated' else 'Owner has proposed this interface; the exit exercise has not been retained.'}
            for key in ['request_response_contract','prompt_export','evaluation_replay','adapter_swap','data_export']}
def flow(ident,source,dest,payload,zone='internal',days=14):
    return {'id':ident,'source':source,'destination':dest,'payload':payload,'zone':zone,'retention_days':days,'minimization':'Only fictional identifiers and the specific excerpt needed by the task.'}
def base(ident,pattern):
    return {'id':ident,'pattern':pattern,'suitable_when':'Revised per pattern below.', 'tradeoffs':'Revised per pattern below.', 'change_option':'Revised per pattern below.',
            'latency_basis':'planning_envelope','evidence_refs':['SYN-LAT','SYN-FLOW','SYN-EFFORT'], 'capabilities':['draft_summary','human_review'],
            'response_stages':[], 'completion_stages':[], 'response_dependencies':[], 'independence_assumed':False,
            'integration_tasks':[task('Versioned request/response adapter',48,80),task('Evaluation and rollback rehearsal',32,56),task('Operator training and runbook',16,32)],
            'maintenance_tasks':[task('Regression replay and version review',8,16,'hours_per_month'),task('Incident handling and runbook upkeep',8,16,'hours_per_month')],
            'migration_tasks':[task('Replacement adapter and schema mapping',20,40),task('Replay, parallel comparison and cutover',16,32)],
            'data_flows':[], 'owners':dict(zip(['integration','support','data','evaluation','change'],['Application integration role','Service operations role','Data stewardship role','Quality engineering role','Release coordination role'])),
            'portability':portable('asserted'), 'degraded_mode':{'behavior':'core_continues','tested':False,'evidence_refs':[],'note':'The underlying human-operated workflow stays available; failure-injection validation remains outstanding.'}}
sync=base('SYNC','synchronous_assist')
sync.update(suitable_when='An optional draft can be returned within the interactive budget and the core transaction does not depend on the draft.',
    tradeoffs='Simple caller experience, but a remote generation dependency stretches response time and can interrupt the core path when coupled inline.',
    change_option='Move generation out of the core transaction or retain an independently tested non-AI response; bound the work and expose the draft as optional.',
    response_stages=[stage('Application/transport',100,300),stage('Generation',900,6000),stage('Output validation',100,400)],
    response_dependencies=[{'name':'application','availability':.9998},{'name':'generation','availability':.995}],
    data_flows=[flow('S1','application','generation endpoint','fictional change description','external_unspecified',None),flow('S2','generation endpoint','review screen','draft text')],
    degraded_mode={'behavior':'blocks_core','tested':False,'evidence_refs':[],'note':'This deliberately flawed reference design waits on generation before the existing change can proceed.'},
    maintenance_tasks=[task('Version and behavior checks',20,35,'hours_per_month'),task('Dependency support',10,20,'hours_per_month')],
    migration_tasks=[task('Embedded client replacement',50,90),task('Replay and cutover',40,70)])
async_=base('ASYNC','asynchronous_job')
async_.update(suitable_when='The core application can acknowledge a job and let a reviewer collect a draft later, with an explicit completion deadline.',
    tradeoffs='Decouples acknowledgement from generation but adds job status, duplicate-delivery handling, queue cleanup, support and eventual-completion semantics.',
    change_option='Prototype the versioned job envelope, cancellation and duplicate-result handling; retain a timed core-continuity and completion rehearsal.',
    response_stages=[stage('Validate/envelope',40,100),stage('Durable enqueue/acknowledge',50,150)],
    completion_stages=[stage('Submit/acknowledge',90,250),stage('Queue wait',1000,10000),stage('Generation and output checks',900,6000),stage('Reviewer queue',60000,300000)],
    response_dependencies=[{'name':'application','availability':.9998},{'name':'job queue','availability':.9997}],
    data_flows=[flow('A1','application','job queue','fictional job id and minimal task excerpt'),flow('A2','job worker','internal generation runtime','bounded fictional excerpt','internal',0),flow('A3','job worker','review inbox','draft with job/source version references')],
    portability=portable('demonstrated'),
    degraded_mode={'behavior':'core_continues','tested':True,'evidence_refs':['SYN-FALLBACK'],'note':'Fictional rehearsal record: generation unavailable; ordinary manual changes still proceed and queued drafts remain visibly pending.'})
rag=base('RETRIEVAL','retrieval_assist')
rag.update(suitable_when='Answers need source excerpts and version locators from a maintained knowledge collection, with a human validating the draft.',
    tradeoffs='Adds retrieval/index freshness, source-version maintenance and evaluation work. Exported text alone does not prove equivalent behavior after an index or embedding change.',
    change_option='Retain export/rebuild and answer-support replay records, define source freshness ownership, and compare the rebuilt retrieval set before switching an adapter.',
    capabilities=['draft_summary','human_review','source_citations'],
    response_stages=[stage('Application/transport',80,160),stage('Retrieve excerpts',100,400),stage('Generate cited draft',700,2200)],
    response_dependencies=[{'name':'application','availability':.9998},{'name':'retrieval index','availability':.998},{'name':'generation','availability':.995}],
    data_flows=[flow('R1','source collection','retrieval index','fictional source excerpts and version locators','internal',90),flow('R2','retrieval index','generation runtime','selected fictional excerpts','internal',0),flow('R3','generation runtime','review screen','draft with source citations')],
    integration_tasks=[task('Versioned retrieval and draft adapter',72,120),task('Index export/rebuild and replay',60,100),task('Source ownership and support training',24,48)],
    maintenance_tasks=[task('Source/index freshness reviews',24,40,'hours_per_month'),task('Answer-support replay and support',21,35,'hours_per_month')],
    migration_tasks=[task('Index/embedding rebuild and mappings',80,140),task('Retrieved-set replay and cutover',60,100)])
rag['portability']['data_export']={'state':'unknown','evidence_refs':[],'note':'Source text exists, but no retained export/rebuild exercise connects it to equivalent retrieval results.'}
req={'availability_window':'SYN-COMMON-30-DAY-BASIS','response_budget_ms':2500,'completion_deadline_ms':1800000,'response_availability_target':.999,'allowed_zones':['internal'],'max_retention_days':30,'required_capabilities':['draft_summary','human_review'],'monthly_maintenance_hours':40,'migration_budget_hours':120,'core_must_continue_without_ai':True}
cases=[{'id':'SYN-APP','title':'Fictional multi-application release-summary assistant','recommendation_id':'SYN-REC-080-A','requirements':req,'alternatives':[sync,async_,rag]}]
c2=copy.deepcopy(cases[0]); c2.update(id='SYN-KNOWLEDGE',title='Fictional research-support knowledge assistant',recommendation_id='SYN-REC-080-B')
c2['requirements'].update(response_budget_ms=5000,completion_deadline_ms=None,response_availability_target=.99,max_retention_days=365,required_capabilities=['source_citations','human_review'],monthly_maintenance_hours=60,migration_budget_hours=160)
cases.append(c2)
c3=copy.deepcopy(cases[0]); c3.update(id='SYN-SUPPORT',title='Fictional identity-service support drafting (no identity decisions)',recommendation_id='SYN-REC-080-C')
c3['requirements'].update(response_budget_ms=800,completion_deadline_ms=600000,response_availability_target=.9999,max_retention_days=7,monthly_maintenance_hours=None,migration_budget_hours=80)
c3['alternatives'][2]['response_stages'][1]['ms']['high']=None
c3['alternatives'][2]['response_dependencies'][2]['availability']=None
c3['alternatives'][2]['data_flows'][0]['zone']=None
c3['alternatives'][2]['data_flows'][0]['retention_days']=None
c3['alternatives'][2]['owners']['support']=None
cases.append(c3)
doc={'schema_version':'1.0','synthetic':True,'basis':'Fictional design estimates and fictional retained observations only. No University data, supplier commitment, real infrastructure measurement or productivity claim.',
     'evidence':{'SYN-LAT':{'kind':'synthetic','locator':'cases.json#/cases/*/alternatives/*/response_stages','note':'Authored serial lower/upper planning envelopes; neither sampled percentiles nor confidence intervals.'},
                 'SYN-FLOW':{'kind':'synthetic','locator':'cases.json#/cases/*/alternatives/*/data_flows','note':'Authored fictional payload/zone/retention inventory, not a compliance determination.'},
                 'SYN-EFFORT':{'kind':'synthetic','locator':'cases.json#/cases/*/alternatives/*/integration_tasks','note':'Authored staffing-hour ranges; one-time integration, recurring upkeep and later migration are separate.'},
                 'SYN-PORT':{'kind':'synthetic','locator':'PATTERNS.md#fictional-observation-records','note':'Fictional adapter-swap/export/replay record exercising the demonstrated field. This tool did not execute a real provider migration.'},
                 'SYN-FALLBACK':{'kind':'synthetic','locator':'PATTERNS.md#fictional-observation-records','note':'Fictional manual-workflow-continuity observation, not a deployed fallback test.'}},'cases':cases}
for case in doc['cases']:
    for alt in case['alternatives']:
        for dependency in alt['response_dependencies']:
            dependency['window'] = 'SYN-COMMON-30-DAY-BASIS'

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Write the deterministic, fictional three-system architecture fixture.')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(doc["cases"])} SYNTHETIC systems to {args.out}')
