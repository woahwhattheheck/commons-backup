'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');

// DOM flow harness for the shipped detail, editor, refresh and clipboard code.
// Unrelated inventory panels are stubbed; this is not a browser test.
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.open=false;this.scrollTop=0;this.scrollLeft=0;}
  append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  querySelector(selector){return walk(this).find(n=>selector.startsWith('.')?n.className?.split(' ').includes(selector.slice(1)):n.tagName===selector);}
  querySelectorAll(selector){return walk(this).slice(1).filter(n=>selector.split(',').includes(n.tagName));}
  contains(n){return walk(this).includes(n);}
  setAttribute(key,value){this[key]=value;}
  getAttribute(key){return this[key]??null;}
  focus(){this.ownerDocument.activeElement=this;}
  insertBefore(n,before){n.parent=this;const i=this.children.indexOf(before);if(i<0)this.children.push(n);else this.children.splice(i,0,n);}
  addEventListener(type,fn){this.listeners[type]=fn;}
  async fire(type){return this.listeners[type]?.({preventDefault(){}});}
  showModal(){assert.equal(this.open,false,'Do not reopen an already modal dialog');this.open=true;}
  close(){this.open=false;this.listeners.close?.();}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
}
const walk=n=>[n,...n.children.flatMap(walk)];
const content=n=>walk(n).map(x=>x.textContent||'').join(' ');
const button=(n,label)=>{const b=walk(n).find(x=>x.tagName==='button'&&x.textContent===label);assert.ok(b,label);return b;};
const clone=v=>JSON.parse(JSON.stringify(v));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const item={id:'task-1',source_id:'source-1',title:'Fixture task',status:'open',next_action:'Source next action',owner_work:{priority:3,next_action:'Old next action',job:{id:'existing/job',objective:'Old objective',dispatch_status:'not_dispatched',status:'prepared'}}};
function harness(records=null,registered=[],sourceRows=[]){
  const body=new Element('body'),copies=[],updates=[],requests=[];let stored=clone(item),readGate=null,reads=0;
  const document={body,createElement:tag=>{const n=new Element(tag);n.ownerDocument=document;return n;},getElementById:id=>walk(body).find(n=>n.id===id)};
  const focus=new Element('section');focus.id='view-focus';const main=new Element('div');main.className='main-column';const side=new Element('div');side.className='side-column';focus.append(main,side);body.append(focus);const stats=new Element('div');stats.id='focus-stats';body.append(stats);const ops=new Element('div');ops.id='recent-operations';const panel=new Element('div');panel.append(ops);main.append(panel);
  const api={getState:()=>({sessions:registered}),showToast(){},getTools:()=>[],request:async endpoint=>{requests.push(endpoint);reads++;const response={body:{sources:clone(sourceRows),items:records?clone(records):[clone(stored)]}};if(readGate){const gate=readGate;readGate=null;const outcome=await gate.promise;if(outcome instanceof Error)throw outcome;if(outcome?.body)return outcome;}return response;},updateWork:async(key,payload)=>{
    updates.push(clone(payload));stored.owner_work={...stored.owner_work,priority:payload.priority,next_action:payload.next_action};
    if(Object.hasOwn(payload,'job'))stored.owner_work.job=payload.job===null?null:{...payload.job,id:'saved-operation/job',status:'prepared',dispatch_status:'not_dispatched'};
    return true;
  }};
  let source=fs.readFileSync(process.env.WORK_DETAIL_SOURCE||path.join(__dirname,'web/work.js'),'utf8');
  source=source.replace(/^  section\('[^\n]+\n/gm,'');
  const boundary=source.indexOf("  $('refresh-button').addEventListener");assert.ok(boundary>0);
  const events={};const ctx=vm.createContext({document,window:{CommonsPanel:api,addEventListener:(name,fn)=>events[name]=fn},navigator:{clipboard:{writeText:async s=>copies.push(JSON.parse(s))}},URL,console});
  vm.runInContext(source.slice(0,boundary)+`const overview=renderOverview;renderView=()=>{};renderOverview=()=>{};renderFleetJobs=()=>{};globalThis.ui={state:()=>({snapshot,error}),refresh,overview,native:renderNativeTasks,inspect:(id)=>showDetail(id?items().find(i=>i.id===id):items()[0])};})();`,ctx);
  return {ui:ctx.ui,body,document,copies,updates,requests,coreEvent:()=>events['commons-state'](),advanceAge:()=>stored.age_seconds=(stored.age_seconds||0)+1,get reads(){return reads;},holdRead(){readGate=deferred();return readGate;},reloadFixture(){stored=JSON.parse(JSON.stringify(stored));},externalChange(){stored.owner_work.next_action='Externally refreshed action';}};
}
async function edit(h,{priority='0',next='Saved next action',job='{"objective":"Saved objective"}'}={}){
  const detail=h.document.getElementById('work-detail');await button(detail,'Set priority / next action').fire('click');
  const editor=h.body.children.at(-1),form=editor.children[0];
  h.document.getElementById('work-edit-priority').value=priority;
  h.document.getElementById('work-edit-next_action').value=next;
  h.document.getElementById('work-edit-job').value=job;
  return {editor,submit:()=>form.fire('submit')};
}
test('save, close editor, inspect and copy use persisted zero priority and the new prepared packet',async()=>{
  const h=harness();await h.ui.refresh();h.ui.inspect();const e=await edit(h);await e.submit();await button(e.editor,'×').fire('click');
  const detail=h.document.getElementById('work-detail');assert.match(content(detail),/Saved next action/);assert.doesNotMatch(content(detail),/Old next action/);
  await button(detail,'Copy bounded job packet').fire('click');const packet=h.copies.at(-1);
  assert.equal(packet.priority,0);assert.equal(packet.next_action,'Saved next action');assert.equal(packet.prepared_job.id,'saved-operation/job');assert.equal(packet.prepared_job.dispatch_status,'not_dispatched');
  // Reload the provider fixture under the accepted backend persistence contract.
  // This flow does not independently test a real backend restart.
  h.reloadFixture();await h.ui.refresh();await button(detail,'Copy bounded job packet').fire('click');assert.deepEqual(h.copies.at(-1),packet);
});
test('save during an in-flight old read performs a post-save read before updating detail and copy',async()=>{
  const h=harness();await h.ui.refresh();h.ui.inspect();const gate=h.holdRead(),oldRead=h.ui.refresh();const e=await edit(h);let done=false;const save=e.submit().then(()=>done=true);
  await new Promise(resolve=>setImmediate(resolve));assert.equal(done,false,'Save waits for refresh reconciliation');gate.resolve();await oldRead;await save;await button(e.editor,'×').fire('click');
  assert.equal(h.reads,3,'Initial, old in-flight, and post-save reads');await button(h.document.getElementById('work-detail'),'Copy bounded job packet').fire('click');assert.equal(h.copies.at(-1).next_action,'Saved next action');assert.equal(h.copies.at(-1).prepared_job.id,'saved-operation/job');
});
test('clearing a prepared packet removes its ID and keeps the source next-action fallback',async()=>{
  const h=harness();await h.ui.refresh();h.ui.inspect();const e=await edit(h,{next:'',job:'null'});await e.submit();await button(e.editor,'×').fire('click');const detail=h.document.getElementById('work-detail');
  assert.doesNotMatch(content(detail),/existing\/job|Prepared packet/);await button(detail,'Copy bounded job packet').fire('click');assert.equal(h.copies.at(-1).prepared_job,null);assert.equal(h.copies.at(-1).next_action,'Source next action');
});
test('blank job edit retains its stable identity and an ordinary refresh updates the open detail',async()=>{
  const h=harness();await h.ui.refresh();h.ui.inspect();const e=await edit(h,{job:''});await e.submit();await button(e.editor,'×').fire('click');assert.equal(Object.hasOwn(h.updates[0],'job'),false);
  h.externalChange();await h.ui.refresh();const detail=h.document.getElementById('work-detail');assert.match(content(detail),/Externally refreshed action/);await button(detail,'Copy bounded job packet').fire('click');assert.equal(h.copies.at(-1).prepared_job.id,'existing/job');assert.equal(h.copies.at(-1).next_action,'Externally refreshed action');
});

test('Current work prioritizes eligible owner work while blocked noncountable evidence stays inspectable',async()=>{
  const records=[
    {id:'listing',title:'Blocked listing',kind:'listing',source_id:'s',countable:false,status:'BLOCKED_PROVIDER_ACCOUNT',needs_attention:true,url:'https://example.com/listing',refs:['https://example.com/source']},
    {id:'real-job',title:'Blocked real job',kind:'task',source_id:'s',countable:true,status:'blocked'},
    {id:'ranked',title:'Owner priority zero',kind:'task',source_id:'s',countable:true,status:'open',owner_work:{priority:0}},
    {id:'ranked-two',title:'Owner priority two',kind:'task',source_id:'s',countable:true,status:'open',owner_work:{priority:2}}
  ];
  const before=JSON.stringify(records),h=harness(records);await h.ui.refresh();h.ui.overview();
  const card=h.document.getElementById('focus-current-work');
  assert.deepEqual(walk(card).filter(n=>n.className==='work-title').map(n=>n.textContent),['Owner priority zero','Owner priority two','Blocked real job']);
  assert.match(content(card),/0 is highest; lower numbers come first/);
  const attention=h.document.getElementById('focus-stats').children[1];assert.match(content(attention),/Needs attention.*2/);
  h.ui.inspect('listing');const detail=h.document.getElementById('work-detail');assert.match(content(detail),/BLOCKED PROVIDER ACCOUNT/);assert.ok(walk(detail).some(n=>n.href==='https://example.com/listing'));assert.ok(walk(detail).some(n=>n.href==='https://example.com/source'));
  assert.equal(JSON.stringify(records),before,'Focus selection does not mutate source evidence');
});

test('stored string zero outranks valid priorities without promoting blank invalid or negative values',async()=>{
  const records=[
    ...['', '   ', 'invalid', '-1', -2, null, false].map((priority,index)=>({id:'unranked-'+index,title:'Unranked '+index,kind:'task',source_id:'s',status:'open',countable:true,owner_work:{priority}})),
    {id:'one',title:'Priority one',kind:'task',source_id:'s',status:'open',countable:true,owner_work:{priority:'1'}},
    {id:'zero',title:'Stored string zero',kind:'task',source_id:'s',status:'open',countable:true,owner_work:{priority:'0'}}
  ];
  const h=harness(records);await h.ui.refresh();h.ui.overview();
  const titles=walk(h.document.getElementById('focus-current-work')).filter(n=>n.className==='work-title').map(n=>n.textContent);
  assert.deepEqual(titles,['Stored string zero','Priority one','Unranked 0','Unranked 1','Unranked 2','Unranked 3']);
  h.ui.inspect('zero');await button(h.document.getElementById('work-detail'),'Copy bounded job packet').fire('click');assert.equal(h.copies.at(-1).priority,'0');
});


test('unchanged core and work refreshes preserve detail DOM; material saves and clearing retain UI state and fresh copies',async()=>{
  const h=harness();await h.ui.refresh();h.ui.inspect();const detail=h.document.getElementById('work-detail');
  const accordions=detail.querySelectorAll('details');assert.equal(accordions.length,2);
  for(const n of accordions)n.open=true;
  const copyButton=button(detail,'Copy bounded job packet');copyButton.focus();detail.scrollTop=180;detail.scrollLeft=7;
  const children=[...detail.children];
  for(let n=0;n<3;n++)h.coreEvent();
  h.advanceAge();await h.ui.refresh(); // Provider returns newly cloned objects.
  assert.deepEqual(detail.children,children);assert.equal(documentActive(h),copyButton);
  assert.equal(detail.scrollTop,180);assert.equal(detail.scrollLeft,7);assert.ok(accordions.every(n=>n.open));
  let e=await edit(h);await e.submit();await button(e.editor,'×').fire('click');
  assert.notEqual(detail.children[0],children[0]);assert.ok(detail.querySelectorAll('details').every(n=>n.open));
  assert.equal(documentActive(h),button(detail,'Copy bounded job packet'));assert.equal(detail.scrollTop,180);
  await button(detail,'Copy bounded job packet').fire('click');assert.equal(h.copies.at(-1).next_action,'Saved next action');assert.equal(h.copies.at(-1).prepared_job.id,'saved-operation/job');
  e=await edit(h,{job:'null'});await e.submit();await button(e.editor,'×').fire('click');
  assert.ok(detail.querySelectorAll('details').every(n=>n.open));await button(detail,'Copy bounded job packet').fire('click');assert.equal(h.copies.at(-1).prepared_job,null);
});
const documentActive=h=>h.document.activeElement;

test('Current work includes prioritized actionable conversations and failed features but excludes closed and noncountable rows',async()=>{
  const row=(id,kind,status,priority,countable=true,needs_attention=false)=>({id,title:id,source_id:'s',kind,status,countable,needs_attention,owner_work:{priority}});
  const records=[row('ordinary-email','email','open',null),row('ordinary-slack','slack_thread','open',null),row('ordinary-feature','feature','open',null),row('closed-priority','email','closed',0),row('done-priority','task','completed',0),row('noncountable','feature','failed',0,false),row('failed-feature','feature','failed',null),row('priority-email','email','open','0'),row('priority-slack','slack_thread','active',1),row('priority-feature','feature','ready',2),row('closed-attention','task','closed',null,true,true)];
  const h=harness(records);await h.ui.refresh();h.ui.overview();
  assert.deepEqual(walk(h.document.getElementById('focus-current-work')).filter(n=>n.className==='work-title').map(n=>n.textContent),['priority-email','priority-slack','priority-feature','failed-feature','closed-attention']);
});


test('detail synchronization uses exact source and item identity and refreshes displayed source fields',async()=>{
  const records=[{...clone(item),source_id:'one',title:'First source'},{...clone(item),source_id:'two',title:'Second source'}];
  const h=harness(records);await h.ui.refresh();h.ui.inspect('task-1');const detail=h.document.getElementById('work-detail');
  records.reverse();await h.ui.refresh();assert.match(content(detail),/First source/);assert.doesNotMatch(content(detail),/Second source/);
  records[1].summary='Material source update';await h.ui.refresh();assert.match(content(detail),/Material source update/);
  records.splice(1,1);await h.ui.refresh();assert.equal(detail.open,false,'A same-ID row from another source must not replace the removed selection');
});


test('owner string zero selects actual unread and received Gmail records without inventing open status',async()=>{
  const rows=['unread','received','sent','completed','closed'].map(status=>({id:status,title:status,source_id:'gmail',kind:'email',status,owner_work:{priority:'0'}}));
  rows.push({id:'attention',title:'attention',source_id:'gmail',kind:'email',status:'closed',needs_attention:true,owner_work:{priority:'0'}});
  const h=harness(rows);await h.ui.refresh();h.ui.overview();
  assert.deepEqual(walk(h.document.getElementById('focus-current-work')).filter(n=>n.className==='work-title').map(n=>n.textContent),['attention','unread','received']);
});

test('Native tasks project all matches separately with exact links, unknown retained reads, and unchanged packet dispatch',async()=>{
  const registered=[{id:'exact-id',kind:'session'},{id:'codex-sanskrit',origin:{native_thread_id:'sanskrit-id'}},{id:'gpt-titan-economic-stress',url:'https://chatgpt.com/c/econ'},{id:'machine',kind:'machine',cpu:8,ram_gib:20}];
  const rows=Array.from({length:81},(_,n)=>({id:'native-'+n,title:'Same title',source_id:'codex-native-fleet',kind:'native_task',status:'unknown',updated_at:'2026-09-08T04:30:00Z',metadata:n<71?{list_observed_at:'2026-09-08T03:43:16Z'}:{},owner_work:{priority:'0',job:{id:'stable/job',dispatch_status:'not_dispatched'}}}));
  rows[0].id='exact-id';rows[1].id='sanskrit-id';rows[2].url='https://chatgpt.com/c/econ';rows[3].url='https://chatgpt.com/c/econ-other';
  const sourceRows=[{id:'codex-native-fleet',observed_at:'2026-09-08T04:30:00Z',coverage:{complete:false,pinned:21,recent:50,retained:10}}];
  const before=JSON.stringify({registered,rows,sourceRows}),h=harness(rows,registered,sourceRows);
  const fleet=h.document.createElement('section');fleet.id='view-fleet';const sessions=h.document.createElement('div');sessions.id='session-list';const hardware=h.document.createElement('article');hardware.textContent='8 CPU / 20 GiB';sessions.append(hardware);fleet.append(sessions);h.body.append(fleet);
  await h.ui.refresh();
  assert.equal(h.document.getElementById('session-list'),sessions);assert.equal(sessions.children.length,1);assert.equal(sessions.children[0],hardware);
  assert.match(content(h.document.getElementById('native-task-count')),/81 returned \/ 81 total native tasks · 3 linked · 78 additional/);
  const cards=h.document.getElementById('native-task-rows').children;assert.equal(cards.length,81);assert.match(content(cards[70]),/List read/);assert.match(content(cards[71]),/Unknown read time/);
  assert.match(content(h.document.getElementById('native-task-coverage')),/partial.*"pinned":21.*"recent":50/);
  const filter=h.document.getElementById('native-task-filter');filter.value='linked';await filter.fire('change');assert.equal(h.document.getElementById('native-task-rows').children.length,3);
  filter.value='all';const search=h.document.getElementById('native-task-search');search.value='Same title';await search.fire('input');assert.equal(h.document.getElementById('native-task-rows').children.length,81,'Same-title tasks retain distinct IDs and all matches');
  search.value='native-80';await search.fire('input');assert.match(content(h.document.getElementById('native-task-count')),/1 returned \/ 81 total/);
  await button(h.document.getElementById('native-task-rows'),'Inspect task').fire('click');const detail=h.document.getElementById('work-detail');assert.match(content(detail),/Conversation metadata updated/);assert.match(content(detail),/Unknown read time/);assert.match(content(detail),/Unknown activity time/);
  await button(detail,'Copy bounded job packet').fire('click');const packet=h.copies.at(-1);assert.equal(packet.work_id,'native-80');assert.equal(packet.source_id,'codex-native-fleet');assert.equal(packet.priority,'0');assert.equal(packet.prepared_job.id,'stable/job');assert.equal(packet.prepared_job.dispatch_status,'not_dispatched');assert.equal(packet.activity_observed_at,null);
  assert.equal(h.updates.length,0);assert.equal(JSON.stringify({registered,rows,sourceRows}),before);
});

// Refresh concurrency uses the actual work.js body, with controlled API replies.
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('manual refresh during an ordinary read issues one forced request and waits for it',async()=>{
  const h=harness(),first=h.holdRead(),ordinary=h.ui.refresh();
  let done=false;const manual=h.ui.refresh(true).then(()=>done=true);
  const forced=h.holdRead();first.resolve();await ordinary;await tick();
  assert.deepEqual(h.requests,['/api/work','/api/work?refresh=1']);
  assert.equal(done,false,'Manual refresh resolves only after its forced read');
  forced.resolve();await manual;assert.equal(done,true);
});
test('repeated manual refreshes waiting on one read coalesce without request fanout',async()=>{
  const h=harness(),first=h.holdRead(),ordinary=h.ui.refresh();
  const callers=Array.from({length:20},()=>h.ui.refresh(true));
  first.resolve();await Promise.all([ordinary,...callers]);
  assert.deepEqual(h.requests,['/api/work','/api/work?refresh=1']);
});
test('ordinary polls share their active read without queuing another request',async()=>{
  const h=harness(),first=h.holdRead(),ordinary=h.ui.refresh();
  const polls=Array.from({length:20},()=>h.ui.refresh());
  assert.ok(polls.every(p=>p===ordinary));first.resolve();await Promise.all(polls);
  assert.deepEqual(h.requests,['/api/work']);
});
test('a manual request upgrades a queued post-save read without losing saved detail',async()=>{
  const h=harness();await h.ui.refresh();h.ui.inspect();
  const first=h.holdRead(),ordinary=h.ui.refresh(),e=await edit(h);
  const save=e.submit();await tick();const manual=h.ui.refresh(true);
  first.resolve();await Promise.all([ordinary,save,manual]);
  assert.deepEqual(h.requests,['/api/work','/api/work','/api/work?refresh=1']);
  await button(h.document.getElementById('work-detail'),'Copy bounded job packet').fire('click');
  assert.equal(h.copies.at(-1).next_action,'Saved next action');
  assert.equal(h.copies.at(-1).priority,0);
});
test('a save can share a queued forced read that has not started before the edit',async()=>{
  const h=harness();await h.ui.refresh();h.ui.inspect();
  const first=h.holdRead(),ordinary=h.ui.refresh(),manual=h.ui.refresh(true);
  const e=await edit(h),save=e.submit();await tick();first.resolve();
  await Promise.all([ordinary,manual,save]);
  assert.deepEqual(h.requests,['/api/work','/api/work','/api/work?refresh=1']);
  await button(h.document.getElementById('work-detail'),'Copy bounded job packet').fire('click');
  assert.equal(h.copies.at(-1).prepared_job.id,'saved-operation/job');
});
test('a save after the forced read starts still requires a new post-save read',async()=>{
  const h=harness();await h.ui.refresh();h.ui.inspect();
  const first=h.holdRead(),ordinary=h.ui.refresh(),manual=h.ui.refresh(true);
  const forced=h.holdRead();first.resolve();await ordinary;await tick();
  assert.deepEqual(h.requests,['/api/work','/api/work','/api/work?refresh=1']);
  const e=await edit(h),save=e.submit();await tick();forced.resolve();
  await Promise.all([manual,save]);
  assert.deepEqual(h.requests,['/api/work','/api/work','/api/work?refresh=1','/api/work']);
  await button(h.document.getElementById('work-detail'),'Copy bounded job packet').fire('click');
  assert.equal(h.copies.at(-1).next_action,'Saved next action');
});
test('a queued manual refresh runs after a failed active read and clears the error',async()=>{
  const h=harness();await h.ui.refresh();const prior=h.ui.state().snapshot;
  const first=h.holdRead(),ordinary=h.ui.refresh(),manual=h.ui.refresh(true);
  const forced=h.holdRead();first.resolve(new Error('Fixture read failure'));await ordinary;await tick();
  assert.equal(h.ui.state().error,'Fixture read failure');assert.equal(h.ui.state().snapshot,prior);
  assert.deepEqual(h.requests,['/api/work','/api/work','/api/work?refresh=1']);
  forced.resolve();await manual;assert.equal(h.ui.state().error,'');
});
test('a failed forced read preserves old data and permits a subsequent manual retry',async()=>{
  const h=harness();await h.ui.refresh();
  const first=h.holdRead(),ordinary=h.ui.refresh(),manual=h.ui.refresh(true);
  const forced=h.holdRead();first.resolve();await ordinary;await tick();
  const prior=h.ui.state().snapshot;forced.resolve(new Error('Fixture forced failure'));await manual;
  assert.equal(h.ui.state().error,'Fixture forced failure');assert.equal(h.ui.state().snapshot,prior);
  await h.ui.refresh(true);
  assert.deepEqual(h.requests,['/api/work','/api/work','/api/work?refresh=1','/api/work?refresh=1']);
  assert.equal(h.ui.state().error,'');
});
test('manual refresh when idle and ordinary refresh after completion keep their distinct URLs',async()=>{
  const h=harness();await h.ui.refresh(true);await h.ui.refresh();
  assert.deepEqual(h.requests,['/api/work?refresh=1','/api/work']);
});


test('current observations outrank retained claims while owner zero remains first',async()=>{
  const seen=new Date().toISOString(), older=new Date(Date.now()-7200000).toISOString();
  const sourceRows=[{id:'s',last_success_at:seen,last_good_observed_at:seen,observed_at:seen,
    stale_after_seconds:3600,coverage:{complete:true}}];
  const records=[
    {id:'old',title:'Retained blocked',source_id:'s',kind:'task',status:'blocked',last_seen_at:older},
    {id:'current',title:'Current open',source_id:'s',kind:'task',status:'open',last_seen_at:seen},
    {id:'zero',title:'Owner zero',source_id:'s',kind:'task',status:'open',last_seen_at:older,owner_work:{priority:'0'}}
  ];
  const before=JSON.stringify(records), h=harness(records,[],sourceRows);
  await h.ui.refresh(); h.ui.overview();
  const card=h.document.getElementById('focus-current-work');
  assert.deepEqual(walk(card).filter(n=>n.className==='work-title').map(n=>n.textContent),
    ['Owner zero','Current open','Retained blocked']);
  assert.match(content(h.document.getElementById('focus-stats').children[0]),/1 \/ 3/);
  assert.match(content(card),/retained \/ stale observation/);
  assert.equal(JSON.stringify(records),before);
  sourceRows[0].last_good_observed_at=older;
  sourceRows[0].observed_at=new Date().toISOString(); sourceRows[0].error='Fixture failed refresh';
  await h.ui.refresh(); h.ui.overview();
  assert.match(content(h.document.getElementById('focus-stats').children[0]),/0 \/ 3/);
});
