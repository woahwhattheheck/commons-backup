'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');

// Exercise the shipped presentation functions, without network calls or mutations.
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.value='';this.checked=false;this.open=false;this.attributes={};this.classList={toggle(){}};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
  setAttribute(k,v){this.attributes[k]=v;}
  removeAttribute(k){delete this.attributes[k];}
  addEventListener(){}
}
const source=fs.readFileSync(path.join(__dirname,'web/app.js'),'utf8');
const boundary=source.indexOf("  $('tool-form').addEventListener");
assert.ok(boundary>0,'UI initialization boundary is present');
function harness(state={sources:[],sessions:[],operations:[],feed:[]}) {
  const elements=new Map(),scrolls=[];
  const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const context=vm.createContext({document:{getElementById:get,createElement:tag=>new Element(tag),querySelectorAll:()=>[]},sessionStorage:{getItem:()=>null},location:{origin:'http://localhost',hash:'#focus'},history:{replaceState(){}},window:{scrollTo:options=>scrolls.push(options)},URL,console});
  vm.runInContext(source.slice(0,boundary)+`globalThis.ui={renderFleet,renderBudgets,time,sessionStats,operationSummary,routineRefresh,renderFeed,renderFocus,navigate,setState:value=>state=value};})();`,context);
  context.ui.setState(state);
  return {ui:context.ui,get,scrolls};
}
const walk=n=>[n,...n.children.flatMap(walk)];
const text=n=>walk(n).map(e=>e.textContent||'').join(' ');
const refresh=(id,overrides={})=>({id,kind:'source',source_status:'live',source_id:'runtime:shared-equipment',title:'Shared equipment — live',body:'Source observation refreshed.',observed_at:'2026-09-07T21:00:00Z',...overrides});

test('owner-reported and reported_active statuses stay in the reported-active count',()=>{
  const {ui}=harness();
  const counts=ui.sessionStats([{kind:'machine',status:'active'},{status:'owner_reported_in_use'},{status:'reported_active'},{status:'observed'}]);
  assert.equal(counts.sessions,3);assert.equal(counts.machines,1);assert.equal(counts.active,2);
});

test('fleet records separate machines and reported activity without guessing availability',()=>{
  const {ui,get}=harness({sources:[],operations:[],feed:[],sessions:[{kind:'machine',status:'active'},...['active_reported','active reported','RUNNING','in-progress','inactive','observed','existing_reported','stale','unknown'].map(status=>({status}))]});
  const counts=ui.sessionStats([{kind:'machine',status:'active'},{status:'active_reported'},{status:'observed'}]);
  assert.equal(counts.sessions,2);assert.equal(counts.machines,1);assert.equal(counts.active,1);
  ui.renderFocus();const card=get('focus-stats').children[0];
  assert.equal(card.children.find(n=>n.className==='stat-value').textContent,'9');
  assert.equal(card.children.find(n=>n.className==='stat-note').textContent,'4 reported active · 1 machine');
  assert.match(text(card),/Recorded sessions/);
});

test('receipts get plain outcomes while failure and uncertain status take precedence',()=>{
  const {ui}=harness();
  assert.match(ui.operationSummary({status:'succeeded',summary:{receipt_received:true,execution_complete:true}}),/Execution completed/);
  assert.match(ui.operationSummary({status:'accepted',summary:{record_id:'one'}}),/not established/);
  assert.match(ui.operationSummary({status:'failed',summary:{record_id:'one'}}),/failure/);
  assert.match(ui.operationSummary({status:'succeeded',summary:{provider_reported_error:true}}),/failure/);
  assert.match(ui.operationSummary({status:'succeeded',summary:{execution_complete:false}}),/not established/);
  assert.match(ui.operationSummary({status:'cancelled',summary:{}}),/cancelled/);
  assert.equal(ui.operationSummary({name:'sessions',status:'succeeded',summary:'{"record_id":"one"}'}),'Session record saved.');
  assert.match(ui.operationSummary({status:'succeeded',summary:{hidden:true}}),/original is retained/);
  assert.equal(ui.operationSummary({status:'succeeded',summary:'A useful provider message.'}),'A useful provider message.');
  assert.doesNotMatch(ui.operationSummary({status:'succeeded',summary:'{"broken"'}),/broken/);
});

test('routine refreshes group after updates, retaining each original and link',()=>{
  const feed=[refresh('r2'),{id:'note',kind:'note',title:'Work delivered',body:'A useful update'},refresh('r1')];
  const {ui,get}=harness({sources:[],feed});const before=JSON.stringify(feed);
  ui.renderFeed();const nodes=get('feed-list').children;
  assert.equal(nodes.length,2);assert.match(text(nodes[0]),/Work delivered/);
  assert.equal(nodes[1].tagName,'details');assert.equal(nodes[1].open,false);
  assert.match(text(nodes[1]),/2 routine source refreshes/);
  const links=walk(nodes[1]).filter(n=>n.tagName==='a').map(n=>n.href);
  assert.ok(links.includes('/api/event?event_id=r1'));assert.ok(links.includes('/api/event?event_id=r2'));
  assert.equal(JSON.stringify(feed),before,'Grouping never moderates or mutates source events');
  get('show-refreshes').checked=true;ui.renderFeed();assert.equal(get('feed-list').children.length,3);
  assert.ok(get('feed-list').children.every(n=>n.tagName==='article'));
});

test('search opens matching refreshes directly and included hidden originals retain controls',()=>{
  const {ui,get}=harness({sources:[],feed:[refresh('r1'),refresh('hidden',{hidden:true,moderation:{reason:'Duplicate observation'}})]});
  get('feed-search').value='r1';ui.renderFeed();assert.equal(get('feed-list').children.length,1);assert.equal(get('feed-list').children[0].tagName,'article');
  get('feed-search').value='';get('show-hidden').checked=true;ui.renderFeed();
  assert.match(text(get('feed-list').children[0]),/Restore to default view/);
  assert.match(text(get('feed-list').children[0]),/Duplicate observation/);
});

test('source errors, status changes, and failure events are never routine groups',()=>{
  const events=[refresh('error',{source_status:'error',body:'Source request failed.'}),refresh('stale',{source_status:'stale'}),refresh('change',{body:'Source version changed.'}),{id:'failed',kind:'failure',hidden:true,title:'Failed operation',body:'Useful evidence'}];
  const {ui,get}=harness({sources:[],feed:events});
  for(const event of events)assert.equal(ui.routineRefresh(event),false);
  ui.renderFeed();assert.equal(get('feed-list').children.length,4);
  assert.ok(get('feed-list').children.every(n=>n.tagName==='article'));
  assert.match(text(get('feed-list')),/Useful evidence/);
});

test('view changes reset scroll and repeated renders preserve the current position',()=>{
  const {ui,scrolls}=harness();ui.navigate('fleet');assert.equal(scrolls.length,1);assert.equal(scrolls[0].top,0);
  ui.navigate('fleet');assert.equal(scrolls.length,1);ui.navigate('focus');assert.equal(scrolls.length,2);
});

// Metadata activity is not a measurement, even when it is recent.
const measurementCases=[
  {observed_at:null,observed_at_utc:null,updated_at:'2026-09-08T02:00:00Z',started_at:'2026-09-08T01:59:00Z'},
  {observed_at:null,observed_at_utc:null,started_at:'2026-09-08T01:59:00Z'},
  {observed_at:'2026-09-01T10:00:00Z',observed_at_utc:'2026-09-02T10:00:00Z',updated_at:'2026-09-08T02:00:00Z'},
  {observed_at:null,observed_at_utc:'2026-09-02T10:00:00Z',updated_at:'2026-09-08T02:00:00Z'}
];
const metaValue=(card,key)=>{const nodes=walk(card);const i=nodes.findIndex(n=>n.tagName==='dt'&&n.textContent===key);assert.ok(i>=0,key+' is rendered');return nodes[i+1].textContent;};
test('hardware measurement freshness excludes metadata update and start times',()=>{
  for(const stamps of measurementCases){
    const {ui,get}=harness({sessions:[{id:'fixture-machine',kind:'machine',cpu:0,ram_gib:0,...stamps}],sources:[],runtimes:[]});
    ui.renderFleet();const card=get('session-list').children[0];
    assert.equal(metaValue(card,'Observed'),ui.time(stamps.observed_at||stamps.observed_at_utc));
    assert.equal(String(metaValue(card,'CPU')),'0');assert.equal(metaValue(card,'RAM'),'0 GiB');
    if(stamps.updated_at)assert.equal(metaValue(card,'Metadata updated'),ui.time(stamps.updated_at));
  }
});
test('budget measurement freshness excludes metadata update and start times',()=>{
  for(const stamps of measurementCases)for(const kind of ['cash_balance','quota']){
    const {ui,get}=harness({budgets:[{id:'fixture-budget',kind,balance:kind==='cash_balance'?0:null,pending:0,limit:0,used:0,remaining:0,committed:0,...stamps}]});
    ui.renderBudgets();const card=get('budget-list').children[0];
    assert.equal(metaValue(card,'Observed'),ui.time(stamps.observed_at||stamps.observed_at_utc));
    assert.equal(String(metaValue(card,'Remaining')),'0');assert.equal(String(metaValue(card,'Committed')),'0');
    assert.deepEqual(walk(card).filter(n=>n.tagName==='strong').map(n=>n.textContent),['0','0']);
  }
});

test('business activity keeps its update time separate from measurement freshness',()=>{
  const stamp='2026-09-08T02:00:00Z';
  const {ui,get}=harness({sources:[],feed:[{id:'activity',kind:'note',title:'Business activity',body:'Synthetic fixture',observed_at:null,observed_at_utc:null,updated_at:stamp}]});
  ui.renderFeed();assert.match(text(get('feed-list')),new RegExp(ui.time(stamp).replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
});


test('invalid measurement observations stay unknown or use a valid UTC fallback',()=>{
  const cases=[
    {observed_at:'not-a-date',observed_at_utc:'also-invalid',expected:null},
    {observed_at:'not-a-date',observed_at_utc:null,expected:null},
    {observed_at:'   ',observed_at_utc:null,expected:null},
    {observed_at:false,observed_at_utc:null,expected:null},
    {observed_at:'not-a-date',observed_at_utc:'2026-09-02T10:00:00Z',expected:'2026-09-02T10:00:00Z'}
  ];
  for(const {expected,...stamps} of cases){
    const metadata={updated_at:'2026-09-08T04:00:00Z',started_at:'2026-09-08T03:59:00Z'};
    const {ui,get}=harness({sessions:[{id:'machine',kind:'machine',cpu:0,ram_gib:0,...metadata,...stamps}],sources:[],runtimes:[],budgets:['cash_balance','quota'].map(kind=>({id:kind,kind,balance:0,pending:0,limit:0,used:0,remaining:0,committed:0,...metadata,...stamps}))});
    ui.renderFleet();ui.renderBudgets();
    const machine=get('session-list').children[0];
    assert.equal(metaValue(machine,'Observed'),expected?ui.time(expected):'Observation time unknown');
    assert.equal(metaValue(machine,'Metadata updated'),ui.time(metadata.updated_at));
    assert.equal(String(metaValue(machine,'CPU')),'0');assert.equal(metaValue(machine,'RAM'),'0 GiB');
    for(const card of get('budget-list').children){
      assert.equal(metaValue(card,'Observed'),expected?ui.time(expected):'Observation time unknown');
      assert.equal(String(metaValue(card,'Remaining')),'0');
      assert.deepEqual(walk(card).filter(n=>n.tagName==='strong').map(n=>n.textContent),['0','0']);
    }
  }
});
