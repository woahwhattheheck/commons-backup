'use strict';
(() => {
  const api=window.CommonsPanel;
  if(!api)return;
  const $=id=>document.getElementById(id), list=v=>Array.isArray(v)?v:[], text=v=>v==null?'':typeof v==='string'?v:JSON.stringify(v);
  const first=(...v)=>v.find(x=>x!==null&&x!==undefined&&x!=='')??null;
  const node=(tag,cls='',value)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=text(value);return n;};
  const btn=(label,fn,cls='button button-small button-quiet')=>{const b=node('button',cls,label);b.type='button';b.addEventListener('click',fn);return b;};
  const url=value=>{if(typeof value!=='string'||!/^(https?:\/\/|codex:\/\/)/i.test(value))return null;try{const u=new URL(value);return u.username||u.password?null:u.href;}catch(_){return null;}};
  const anchor=(label,value)=>{const u=url(value);if(!u)return null;const a=node('a','source-link',label);a.href=u;a.target='_blank';a.rel='noopener noreferrer';return a;};
  const append=(n,...children)=>children.filter(Boolean).forEach(c=>n.append(c));
  const date=(value,fallback='Unknown activity time')=>{if(!value)return fallback;const d=new Date(value);return Number.isNaN(d.getTime())?fallback:d.toLocaleString([],{dateStyle:'medium',timeStyle:'short'});};
  const phase=value=>{const s=text(value||'unknown'),c=/fail|error|blocked|unavailable|rejected/i.test(s)?'bad':/unknown|unmeasured|pending|uncertain|stale|hold|disqualified|degraded/i.test(s)?'warn':'neutral';return node('span','badge '+c,s.replace(/_/g,' '));};
  const md=i=>i.metadata&&typeof i.metadata==='object'&&!Array.isArray(i.metadata)?i.metadata:{};
  const field=(i,key)=>first(i[key],md(i)[key],i.refs&&typeof i.refs==='object'&&!Array.isArray(i.refs)?i.refs[key]:null);
  const actionRows=value=>Array.isArray(value)?value:value&&typeof value==='object'?(value.tool||value.name?[value]:Object.values(value)):[];
  function refRows(value,label='Source'){
    if(Array.isArray(value))return value.flatMap(v=>refRows(v,label));
    if(typeof value==='string')return url(value)?[{label,url:value}]:[];
    if(value&&typeof value==='object'){const u=first(value.url,value.href,value.ref);if(url(u))return[{label:first(value.label,value.title,value.kind,label),url:u}];return Object.entries(value).flatMap(([k,v])=>refRows(v,k));}
    return [];
  }
  function requestID(value){
    if(!value||typeof value!=='object')return null;
    for(const k of ['provider_request_id','request_id']){const v=value[k];if(typeof v==='string'&&v&&v!=='command-center')return v;}
    if(Array.isArray(value)){for(const v of value){const found=requestID(v);if(found)return found;}}
    else{const k=first(value.key,value.path,value.name,''),v=first(value.value,value.id);if(/request_id/.test(text(k))&&typeof v==='string'&&v!=='command-center')return v;for(const k of ['metadata','provider_refs','refs','safe_summary','result_summary','summary']){const found=requestID(value[k]);if(found)return found;}}
    return null;
  }
  const owned=i=>i.owner_work&&typeof i.owner_work==='object'?i.owner_work:{};
  const owner=i=>text(first(owned(i).owner,i.owner,'Unassigned'));
  const next=i=>text(first(owned(i).next_action,i.next_action,'No next action recorded'));
  const nativeTask=i=>i.source_id==='codex-native-fleet'&&i.kind==='native_task';
  const nativeRead=i=>[md(i).list_observed_at,i.refs?.list_observed_at].find(v=>typeof v==='string'&&Number.isFinite(Date.parse(v)))??null;
  const activity=i=>first(i.activity_observed_at);
  const AUTO_REFRESH_MS=300000;
  let lastCollectorRefresh=0;
  let snapshot=null,sourceIndex=new Map(),loading=null,queuedRefresh=null,error='',selected=null,displayedKey=null,peerBusy=false,activePeerOperation=null;
  const kinds={work:null,builds:['build','pull_request','feature'],inbox:['email','slack_thread'],marketing:['campaign','deal']};
  const labels={work:'Work',builds:'Builds',inbox:'Inbox',marketing:'Marketing'};
  const filters=Object.fromEntries(Object.keys(labels).map(k=>[k,{q:'',project:'all',provider:'all',status:'all',freshness:'all',channel:'all',tab:'all'}]));
  filters.marketing.tab='deal';
  const sources=()=>list(snapshot&&snapshot.sources), items=()=>list(snapshot&&snapshot.items);
  const source=i=>sourceIndex.get(i.source_id)||{};
  const sourceRead=s=>s.last_good_observed_at;
  const stale=s=>s.stale===true||s.data_stale===true||!!s.error||s.retained_last_good===true||!sourceRead(s)||!Number.isFinite(Date.parse(sourceRead(s)))||Date.parse(sourceRead(s))-Date.now()>300000||s.stale_after_seconds===null||(typeof s.stale_after_seconds==='number'&&Date.now()-Date.parse(sourceRead(s))>s.stale_after_seconds*1000);
  const latestIngest=i=>typeof i.last_seen_at==='string'&&i.last_seen_at!==''&&i.last_seen_at===source(i).last_success_at;
  const currentObservation=i=>latestIngest(i)&&!stale(source(i));
  const observationLabel=i=>currentObservation(i)?'current observation':'retained / stale observation';
  const provider=i=>text(first(i.provider,source(i).provider,'Unknown provider'));
  const project=i=>text(first(i.project,'Unassigned project'));
  const failed=i=>i.needs_attention===true||/failed|failure|error|blocked|uncertain|needs_attention|rejected/i.test(text(i.status));
  const open=i=>i.countable!==false&&/^(open|assigned|in_progress|in progress|active|queued|pending|blocked|ready|ready for prospecting|qualified|prospect|purchase intent)$/i.test(text(i.status));
  function safe(value,key=''){
    if(/password|secret|token|credential_value|private_key|authorization/i.test(key))return '[not displayed]';
    if(Array.isArray(value))return value.map(v=>safe(v));
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,safe(v,k)]));
    return value;
  }
  function metadata(rows){const dl=node('dl','record-meta work-meta');rows.forEach(([k,v])=>append(dl,node('dt','',k),node('dd','',v==null||v===''?'Unknown':text(v))));return dl;}
  function empty(message){return node('div','empty-inline',message);}
  function section(view,description){
    const n=node('section','view');n.id='view-'+view;n.hidden=true;n.setAttribute('aria-labelledby',view+'-title');
    const h=node('div','page-heading'),title=node('div');
    append(title,node('div','eyebrow','CONNECTED WORK'),node('h1','',labels[view]),node('p','page-intro',description));title.querySelector('h1').id=view+'-title';
    append(h,title,btn('Refresh work',()=>refresh(true)));n.append(h);
    const bar=node('div','filter-bar work-filter-bar'),q=node('input');q.type='search';q.placeholder='Search work, owner, next action…';q.setAttribute('aria-label','Search '+labels[view]);const w=node('label','search-field');w.append(q);bar.append(w);q.addEventListener('input',()=>{filters[view].q=q.value.toLowerCase();renderView(view);});
    ['project','provider','status'].forEach(key=>{const s=node('select');s.id=view+'-filter-'+key;s.setAttribute('aria-label','Filter '+key);s.addEventListener('change',()=>{filters[view][key]=s.value;renderView(view);});bar.append(s);});
    const freshness=node('select');freshness.id=view+'-filter-freshness';freshness.setAttribute('aria-label','Filter observation freshness');
    [['all','All observations'],['current','Current observations'],['retained','Retained / stale observations']].forEach(([value,label])=>{const option=node('option','',label);option.value=value;freshness.append(option);});
    freshness.addEventListener('change',()=>{filters[view].freshness=freshness.value;renderView(view);});bar.append(freshness);
    n.append(bar);
    if(view==='marketing'){const tabs=node('div','work-tabs');[['deal','Canonical pipeline'],['campaign','Campaigns & offers'],['all','All marketing']].forEach(([value,label])=>{const b=btn(label,()=>{filters.marketing.tab=value;renderView('marketing');},'work-tab');b.dataset.marketingTab=value;tabs.append(b);});n.append(tabs);}
    if(view==='inbox'){const tabs=node('div','work-tabs');[['all','All messages'],['email','Email'],['slack_thread','Slack']].forEach(([value,label])=>{const b=btn(label,()=>{filters.inbox.tab=value;renderView('inbox');},'work-tab');b.dataset.inboxTab=value;tabs.append(b);});const ch=node('select');ch.id='inbox-filter-channel';ch.setAttribute('aria-label','Filter Slack channel');ch.addEventListener('change',()=>{filters.inbox.channel=ch.value;renderView('inbox');});tabs.append(ch);n.append(tabs);}
    const note=node('div','work-view-note small muted');note.id=view+'-note';n.append(note);
    const stats=node('div','work-stage-grid');stats.id=view+'-stages';n.append(stats);
    const rows=node('div','panel work-table-wrap');rows.id=view+'-rows';n.append(rows);
    const coverage=node('div','work-coverage');coverage.id=view+'-coverage';n.append(coverage);
    $('main').append(n);
    const b=btn('',()=>api.navigate(view),'nav-item');b.dataset.view=view;b.setAttribute('aria-label',labels[view]);append(b,node('span','nav-icon',{work:'☷',builds:'↗',inbox:'✉',marketing:'◉'}[view]),document.createTextNode(labels[view]));$('navigation').insertBefore(b,document.querySelector('[data-view="fleet"]'));
  }
  section('work','Current jobs, ownership, and next actions across connected sources.');
  section('builds','Source landing, checks, and deployment keep their own receipts.');
  section('inbox','Email and Slack activity with the original conversation one click away.');
  section('marketing','The canonical pipeline, offers, and follow-ups with their source evidence.');
  const detail=node('dialog','work-detail');detail.id='work-detail';document.body.append(detail);
  const peerDialog=node('dialog','work-detail');peerDialog.id='peer-control';document.body.append(peerDialog);
  function base(view){const kk=kinds[view];return items().filter(i=>!kk||kk.includes(i.kind));}
  function fillSelect(id,values,current,caption){
    const s=$(id);if(!s)return;const options=[...new Set(values.filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    if(current!=='all'&&!options.includes(current))options.unshift(current);
    s.replaceChildren();const all=node('option','',caption);all.value='all';s.append(all);options.forEach(v=>{const o=node('option','',v);o.value=v;s.append(o);});s.value=current;
  }
  function renderView(view){
    const all=base(view),f=filters[view];
    fillSelect(view+'-filter-project',all.map(project),f.project,'All projects');
    fillSelect(view+'-filter-provider',all.map(provider),f.provider,'All providers');
    fillSelect(view+'-filter-status',all.map(i=>text(i.status||'unknown')),f.status,'All statuses');
    if(view==='inbox'){fillSelect('inbox-filter-channel',all.filter(i=>i.kind==='slack_thread').map(i=>text(first(field(i,'channel'),field(i,'channel_name'),source(i).label))),f.channel,'All Slack channels');document.querySelectorAll('[data-inbox-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.inboxTab===f.tab);b.setAttribute('aria-pressed',String(b.dataset.inboxTab===f.tab));});}
    if(view==='marketing')document.querySelectorAll('[data-marketing-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.marketingTab===f.tab);b.setAttribute('aria-pressed',String(b.dataset.marketingTab===f.tab));});
    const found=all.filter(i=>(view!=='marketing'||f.tab==='all'||i.kind===f.tab)&&(f.project==='all'||project(i)===f.project)&&(f.provider==='all'||provider(i)===f.provider)&&(f.status==='all'||text(i.status||'unknown')===f.status)&&(f.freshness==='all'||currentObservation(i)===(f.freshness==='current'))&&(view!=='inbox'||(f.tab==='all'||i.kind===f.tab)&&(f.channel==='all'||i.kind==='slack_thread'&&text(first(field(i,'channel'),field(i,'channel_name'),source(i).label))===f.channel))&&[i.title,i.summary,next(i),owner(i),i.id].map(text).join(' ').toLowerCase().includes(f.q));
    found.sort((a,b)=>Number(currentObservation(b))-Number(currentObservation(a))||(Date.parse(activity(b))||0)-(Date.parse(activity(a))||0));
    $(view+'-note').textContent=error?'Refresh failed: '+error+'. Previous work retained.':!snapshot?'Loading connected work…':found.length+' of '+all.length+' source records · '+(snapshot.refresh?'Collector '+text(snapshot.refresh.status||'unknown')+' · ':'')+'open a row for evidence and actions.';
    const panel=$(view+'-rows');panel.replaceChildren();
    if(!found.length)panel.append(empty(snapshot?'No matching records from the returned sources. Check coverage below.':'Waiting for the work source response.'));
    else {const table=node('table','work-table'),head=node('thead'),tr=node('tr');['Work / next action','State','Owner / project','Activity',''].forEach(t=>tr.append(node('th','',t)));head.append(tr);table.append(head);const body=node('tbody');found.slice(0,200).forEach(i=>{const r=node('tr'),title=node('td'),openButton=btn(i.title||i.id,()=>showDetail(i),'work-title');append(title,openButton,node('span','work-row-sub',provider(i)+' · '+text(i.kind).replace(/_/g,' ')),node('p','work-next',next(i)));const st=node('td');st.append(phase(i.status),phase(observationLabel(i)));if(first(owned(i).priority,i.priority)!==null)st.append(node('small','work-row-sub','Priority '+text(first(owned(i).priority,i.priority))));const own=node('td');append(own,node('span','',owner(i)),node('small','work-row-sub',project(i)));const at=node('td','work-activity',date(activity(i)));const action=node('td');action.append(btn('Inspect',()=>showDetail(i),'text-button'));append(r,title,st,own,at,action);body.append(r);});table.append(body);panel.append(table);if(found.length>200)panel.append(empty('Showing 200 matching records. Narrow the filters to inspect the rest.'));}
    renderStages(view,view==='marketing'?all.filter(i=>f.tab==='all'||i.kind===f.tab):all);renderCoverage(view);
  }
  function renderStages(view,rows){
    const container=$(view+'-stages');container.replaceChildren();if(view!=='builds'&&view!=='marketing')return;
    const groups={};rows.forEach(i=>{const key=view==='builds'?(i.kind==='pull_request'?'Pull request · ':i.kind==='feature'?'Feature evidence · ':'Build / CI · ')+text(i.status||'unknown'):text(first(i.record_type,i.crm_record_type,'Record'))+' · '+text(i.status||'unknown');groups[key]=(groups[key]||0)+1;});
    Object.entries(groups).slice(0,18).forEach(([k,v])=>{const c=node('div','work-stage');append(c,node('strong','',v),node('span','',k));container.append(c);});
    if(view==='marketing')container.append(node('p','field-help work-stage-note','Pipeline stages are source labels. Control records, sent messages, listed prices, and public job postings do not establish buyers or cash.'));
    if(view==='builds')container.append(node('p','field-help work-stage-note','Merged code, test results at an exact commit, and deployment are separate. A missing deployment receipt stays unknown.'));
  }
  function renderCoverage(view){
    const root=$(view+'-coverage');root.replaceChildren();const heading=node('div','section-heading');append(heading,node('h2','','Connected source coverage'),node('span','small muted','Read time and underlying activity stay separate'));root.append(heading);
    const rows=sources();if(!rows.length){root.append(empty('No source coverage reported yet.'));return;}
    const grid=node('div','work-source-grid');rows.forEach(s=>{const card=node('article','source-card'),head=node('div','card-top');append(head,node('h3','',s.label||s.id),phase(stale(s)?'stale / unknown read':s.status));card.append(head);const c=s.coverage||{};append(card,metadata([['Provider',s.provider],['Read',date(sourceRead(s),'No successful read time')],['Activity as of',date(s.activity_as_of)],['Sync',s.sync_mode],['Coverage',c.complete===true?'Complete for stated scope':c.complete===false?'Partial':'Unknown'],['More pages',c.pagination_remaining===true?'Yes':c.pagination_remaining===false?'No':c.pagination_remaining]]));if(s.error)card.append(node('p','source-error',text(s.error)));if(s.retained_last_good)card.append(node('p','field-help','Last good observations retained.'));if(c.notes)card.append(node('p','field-help',text(c.notes)));grid.append(card);});root.append(grid);
  }
  function packet(i){
    return JSON.stringify({work_id:i.id,source_id:i.source_id,task_key:workTaskKey(i)||undefined,title:i.title,project:i.project,owner:owner(i),objective:first(owned(i).job,i.objective,i.summary,i.title),next_action:next(i),priority:first(owned(i).priority,i.priority),prepared_job:owned(i).job??null,status:i.status,source_url:i.url,refs:i.refs,activity_observed_at:activity(i),request:"Continue this exact work from its source and latest receipt. Return an operation ID, artifacts, and actual outcome; reconcile existing work before repeating an effect."},null,2);
  }
  function canonicalTask(value){
    if(typeof value!=='string'||!value.trim())return null;
    const raw=value.trim();
    if(/^commons:owner-command:[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(raw))return raw;
    let match=/^github:([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+):(issue|pr):([0-9]+)$/i.exec(raw);
    if(!match){
      try{const source=new URL(raw);if(!['https:','http:'].includes(source.protocol)||source.username||source.password||!['github.com','www.github.com','api.github.com'].includes(source.hostname.toLowerCase()))return null;
        const path=source.hostname.toLowerCase()==='api.github.com'?source.pathname.replace(/^\/repos\//,'/'):source.pathname;
        const ref=/^\/([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)\/(issues|pull|pulls)\/([0-9]+)(?:\/|$)/.exec(path);
        if(!ref)return null;match=[raw,ref[1],ref[2]==='issues'?'issue':'pr',ref[3]];
      }catch(_){return null;}
    }
    const number=Number(match[3]);
    if(!Number.isSafeInteger(number)||number<1||match[1].split('/').some(part=>part==='.'||part==='..'))return null;
    return 'github:'+match[1].toLowerCase()+':'+match[2].toLowerCase()+':'+number;
  }
  function workTaskKey(i){
    // Explicit machine identity and the record's own provider URL outrank
    // supporting links. Multiple different supporting tasks stay ambiguous.
    for(const value of [field(i,'task_key'),owned(i).job?.task_key,i.url,i.source_url]){const key=canonicalTask(value);if(key)return key;}
    const keys=[...new Set(refRows(i.refs).map(row=>canonicalTask(row.url)).filter(Boolean))];
    return keys.length===1?keys[0]:null;
  }
  function dispatchBinding(i,worker){
    const key=i&&workTaskKey(i);
    if(!key||typeof worker!=='string'||!worker.trim())return null;
    const binding={task_key:key,worker};
    const base=first(field(i,'base_sha'),owned(i).job?.base_sha);
    if(typeof base==='string'&&/^[0-9a-f]{40,64}$/i.test(base))binding.base_sha=base;
    return binding;
  }
  function canonicalReceipt(target,receipt,requestedKey){
    const assignment=receipt?.swarm||receipt?.operation?.summary?.swarm;
    if(!assignment||typeof assignment!=='object')return;
    const box=node('div','inline-note');
    const key=canonicalTask(assignment.task_key),worker=text(assignment.worker||'Unknown worker');
    const existing=assignment.status==='existing_dispatch';
    if(existing)box.append(node('p','','The existing provider job for '+worker+' is retained.'));
    if((assignment.status==='assigned'||existing)&&key){
      if(!existing)box.append(node('p','',assignment.rerouted?'Assigned another eligible task to '+worker+'.':'Assigned this work to '+worker+'.'));
      const link=node('a','source-link',key),destination=new URL(location.href);destination.searchParams.set('swarm_task',key);destination.hash='work';link.href=destination.href;box.append(link);
      if(assignment.rerouted)box.append(node('p','field-help','Requested '+text(assignment.requested_task_key||requestedKey)+'. The response above describes the assigned task.'));
    }else if(!existing)box.append(node('p','',assignment.status==='unpublished'?'Task assignment was not published.':'No task was assigned.'));
    if(existing){
      box.append(metadata([['Existing operation',assignment.existing_operation_id],['Existing status',assignment.existing_status]]));
      if(assignment.existing_provider_refs)box.append(node('pre','',JSON.stringify(safe(assignment.existing_provider_refs),null,2)));
    }
    if(assignment.reason)box.append(node('p','field-help',text(assignment.reason).slice(0,600)));
    if(receipt.provider_dispatched===false)box.append(node('p','field-help',existing?'No additional provider job was launched.':'No provider job was launched.'));
    target.append(box);
  }
  async function copy(value){try{await navigator.clipboard.writeText(value);api.showToast('Job packet copied.');}catch(_){api.showToast('Clipboard unavailable. Select and copy the displayed packet.');}}
  function detailValue(value){
    if(Array.isArray(value))return value.map(detailValue);
    if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().filter(k=>k!=='age_seconds').map(k=>[k,detailValue(value[k])]));
    return value;
  }
  const controlKey=n=>JSON.stringify([n.tagName,n.id||'',n.getAttribute('href')||'',n.textContent]);
  function showDetail(i){
    const s0=source(i),key=JSON.stringify([i.source_id,i.id,detailValue(safe(i)),s0.provider,s0.observed_at,s0.last_success_at,s0.last_good_observed_at,currentObservation(i),api.getTools().map(t=>[t.name,t.runtime_id]).sort()]);
    const same=detail.open&&selected&&selected.id===i.id&&selected.source_id===i.source_id;
    selected=i;if(same&&key===displayedKey)return;
    const scroll=[detail.scrollTop,detail.scrollLeft],expanded=new Set(),positions=new Map();
    const focused=same&&detail.contains(document.activeElement)?controlKey(document.activeElement):null;
    if(same)detail.querySelectorAll('details').forEach(n=>{const k=n.querySelector('summary').textContent;if(n.open)expanded.add(k);positions.set(k,[n.scrollTop,n.scrollLeft]);});
    displayedKey=key;detail.replaceChildren();const h=node('div','dialog-heading');append(h,node('h2','',i.title||i.id),btn('×',()=>detail.close(),'icon-button'));detail.append(h,phase(i.status),phase(observationLabel(i)));
    const s=source(i);append(detail,metadata([['Owner',owner(i)],['Project',project(i)],['Kind',i.kind],['Provider',provider(i)],['Record ID',i.id],['Priority',first(owned(i).priority,i.priority)],['Activity',date(activity(i))],['Source read',date(nativeTask(i)?nativeRead(i):sourceRead(s),'Unknown read time')]]));
    if(nativeTask(i))detail.append(metadata([['Conversation metadata updated',date(i.updated_at,'Unknown metadata time')]]));
    if(i.summary)append(detail,node('h3','','Source summary'),node('p','work-detail-copy',i.summary));append(detail,node('h3','','Next action'),node('p','work-detail-copy',next(i)));
    const links=node('div','button-row');append(links,anchor('Open original ↗',i.url));
    refRows(i.refs).forEach(r=>append(links,anchor(r.label+' ↗',r.url)));detail.append(links);
    if(i.kind==='build'||i.kind==='pull_request'||i.kind==='feature')detail.append(metadata([['Source state',first(field(i,'source_status'),field(i,'merged_at')?'merged':null)],['Commit',first(field(i,'head_sha'),field(i,'commit_sha'),field(i,'main_sha'),field(i,'merge_commit_sha'))],['CI',first(field(i,'ci_status'),field(i,'conclusion'),field(i,'test_status'))],['Deployment',first(field(i,'deployment_status'),field(i,'live_status'),'Unknown')]]));
    const actions=node('div','button-row work-detail-actions');actions.append(btn('Set priority / next action',()=>workForm(i)),btn('Copy bounded job packet',()=>copy(packet(i))));
    if(workTaskKey(i)&&api.getTools().some(t=>t.name==='gemini_submit'&&t.runtime_id==='shared-equipment'))actions.append(btn('Delegate this work',()=>{detail.close();peerControl('submit','','MERIDIAN',packet(i),i);}));
    actionRows(i.actions).forEach(a=>{
      const name=first(a.tool,a.name),args=a.arguments||{},route=a.route||a.transport||a.availability||'';
      if(name&&api.getTools().some(t=>t.name===name&&t.runtime_id===(a.runtime_id||'shared-equipment'))&&!/native_harness|mcp__codex_app__/.test(name+' '+route)){
        actions.append(btn(a.label||a.title||'Inspect '+name,()=>{detail.close();api.openTool(name,args,a.runtime_id||'shared-equipment');}));
      } else if(url(a.url)) append(actions,anchor(a.label||'Open existing task ↗',a.url));
      else if(name)actions.append(node('span','field-help',text(a.label||name)+' · native harness route; copy the packet into the existing task.'));
    });
    detail.append(actions);if(field(i,'native_execution_state'))detail.append(metadata([['Native execution',field(i,'native_execution_state')],['Business outcome',i.status||'Unknown']]));if(owned(i).job)detail.append(metadata([['Prepared packet',owned(i).job.id],['Dispatch',owned(i).job.dispatch_status||'not_dispatched']]));const p=node('details','raw-details');append(p,node('summary','','Bounded job packet'),node('pre','',packet(i)));detail.append(p);
    const raw=node('details','raw-details');append(raw,node('summary','','Source record'),node('pre','',JSON.stringify(safe(i),null,2)));detail.append(raw);if(!detail.open)detail.showModal();
    if(same){
      detail.querySelectorAll('details').forEach(n=>{const k=n.querySelector('summary').textContent;n.open=expanded.has(k);const p=positions.get(k);if(p){n.scrollTop=p[0];n.scrollLeft=p[1];}});
      if(focused){const n=Array.from(detail.querySelectorAll('button,a,summary')).find(n=>controlKey(n)===focused);if(n)n.focus({preventScroll:true});}
      detail.scrollTop=scroll[0];detail.scrollLeft=scroll[1];
    }
  }
  // Explicit numeric owner priorities precede unprioritized work; zero is highest.
  function currentWork(rows){
    const priority=i=>{const p=owned(i).priority;return (typeof p==='number'||typeof p==='string'&&p.trim()!=='')&&Number.isFinite(Number(p))&&Number(p)>=0?Number(p):Infinity;};
    return rows.filter(i=>i.countable!==false&&(failed(i)||((open(i)||(i.kind==='email'&&/^(unread|received)$/i.test(text(i.status))))&&(!['email','slack_thread','feature'].includes(i.kind)||Number.isFinite(priority(i))))))
      .sort((a,b)=>priority(a)-priority(b)||Number(currentObservation(b))-Number(currentObservation(a))||Number(failed(b))-Number(failed(a))).slice(0,6);
  }
  function renderOverview(){
    if(!snapshot){
      let cover=$('focus-work-coverage');if(!cover){cover=node('article','panel');cover.id='focus-work-coverage';$('view-focus').querySelector('.side-column').append(cover);}
      cover.replaceChildren(node('h2','','Connected work coverage'),node('p',error?'source-error':'field-help',error?'Work read failed: '+error:'Waiting for the first connected-work observation.'),btn('Retry work read',()=>refresh(true),'text-button'));
      $('focus-stats').replaceChildren(...['Open work records','Needs attention','Source coverage','Conversation records'].map(title=>{const card=node('div','stat-card');append(card,node('div','stat-top',title),node('div','stat-value','—'),node('div','stat-note','Awaiting connected-work evidence'));return card;}));
      return;
    }
    const rows=items(),exceptions=rows.filter(failed),active=rows.filter(i=>open(i)&&!['email','slack_thread','feature'].includes(i.kind)),partial=sources().filter(s=>s.error||stale(s)||s.coverage?.complete!==true);
    const stats=[['Open work records',active.filter(currentObservation).length+' / '+active.length,'Current / total · '+active.filter(i=>!currentObservation(i)).length+' retained or stale','☷'],['Needs attention',exceptions.length,'Failures, blocked, or uncertain','◎'],['Source coverage',sources().length-partial.length+' / '+sources().length,'Fresh, complete sources','◉'],['Conversation records',rows.filter(i=>['email','slack_thread'].includes(i.kind)).length,'Returned email and Slack records','✉']];
    $('focus-stats').replaceChildren(...stats.map(([title,value,note,symbol])=>{const c=node('div','stat-card'),top=node('div','stat-top');append(top,node('span','',title),node('span','stat-symbol',symbol));append(c,top,node('div','stat-value',value),node('div','stat-note',note));return c;}));
    let card=$('focus-current-work');if(!card){card=node('article','panel');card.id='focus-current-work';$('view-focus').querySelector('.main-column').insertBefore(card,$('recent-operations').parentElement);}
    card.replaceChildren();const h=node('div','panel-heading');append(h,node('h2','','Current work'),btn('Open work →',()=>api.navigate('work'),'text-button'));card.append(h);
    card.append(node('p','field-help','Nonnegative numeric owner priority: 0 is highest; lower numbers come first. Unprioritized current observations precede retained or stale records, with blocked work first within each group. Noncountable records remain in Work and source views.'));
    const chosen=currentWork(rows);
    if(!chosen.length)card.append(empty('No open work in returned observations. Source coverage below may be partial.'));
    chosen.forEach(i=>{const r=node('div','overview-work');append(r,btn(i.title||i.id,()=>showDetail(i),'work-title'),phase(i.status),phase(observationLabel(i)),node('p','work-next',owner(i)+' · '+next(i)));card.append(r);});
    let cv=$('focus-work-coverage');if(!cv){cv=node('article','panel');cv.id='focus-work-coverage';$('view-focus').querySelector('.side-column').append(cv);}
    cv.replaceChildren(node('h2','','Coverage to resolve'));if(snapshot.refresh)cv.append(node('p','field-help','Collector '+text(snapshot.refresh.status||'unknown')+'. Source observations refresh independently.'));if(error)cv.append(node('p','source-error','Work refresh failed: '+error+'. Prior observations retained.'));if(!partial.length&&!error)cv.append(node('p','field-help','Returned sources report complete current coverage for their stated scopes.'));
    partial.slice(0,8).forEach(s=>append(cv,node('p','work-next',(s.label||s.id)+' · '+text(first(s.error,stale(s)?'stale or unknown read time':null,s.coverage?.notes,'coverage incomplete')))));
    cv.append(btn('Inspect sources →',()=>api.navigate('work'),'text-button'));
  }
  function workForm(i){
    if(!i.source_id){api.showToast('This record has no stable source ID. Refresh work before editing.');return;}
    const dialog=node('dialog','work-detail'),form=node('form'),head=node('div','dialog-heading');
    append(head,node('h2','','Drive this work'),btn('×',()=>dialog.close(),'icon-button'));form.append(head,node('p','field-help',i.title||i.id),node('p','field-help','Owner remains attributed to the original source. These edits set shared priority, the next action, and an optional prepared packet.'));
    const fields={};
    function add(key,label,value,multi=false){const w=node('div','form-field'),l=node('label','',label),n=node(multi?'textarea':'input');n.id='work-edit-'+key;n.value=value??'';l.htmlFor=n.id;if(multi)n.rows=5;append(w,l,n);form.append(w);fields[key]=n;}
    add('priority','Priority (nonnegative numbers; 0 highest; blank clears)',first(owned(i).priority,i.priority));
    add('next_action','Next action (blank clears the override)',owned(i).next_action??i.next_action,true);
    const j=owned(i).job;const initial=j?Object.fromEntries(Object.entries(j).filter(([k])=>!['id','created_at','source_id','item_id'].includes(k))):null;
    add('job','Prepared job JSON (blank leaves existing packet; null clears)',initial?JSON.stringify(initial,null,2):'',true);
    form.append(node('p','field-help','Saving a packet does not dispatch it. Use the existing provider controls or copy it into the linked native task.'));
    const out=node('div','action-output');out.hidden=true;form.append(out);const conflict=node('div','action-output');conflict.hidden=true;form.append(conflict);const submit=node('button','button button-primary','Save work');submit.type='submit';form.append(submit);
    let saving=false;
    function reconcile(current){
      if(!current||typeof current!=='object'||!Number.isInteger(current.revision)||current.revision<0)return;
      conflict.hidden=false;
      conflict.replaceChildren(node('h3','','Saved direction changed'),node('p','','Your draft is unchanged. Compare it with the saved direction below.'),metadata([['Saved revision',current.revision],['Saved priority',current.priority??'No override'],['Saved next action',current.next_action??'No override']]));
      if(current.job)conflict.append(node('h4','','Saved prepared packet'),node('pre','',JSON.stringify(safe(current.job),null,2)));
      else conflict.append(node('p','field-help','No saved prepared packet.'));
      conflict.append(btn('Use this revision for my draft',()=>{
        i={...i,owner_work:current};conflict.hidden=true;out.hidden=true;submit.textContent='Save work';
        api.showToast('Draft preserved. Save when your changes are ready.');
      },'button button-small button-quiet'));
    }
    form.addEventListener('submit',async e=>{e.preventDefault();if(saving)return;
      let job;try{if(fields.job.value.trim()){job=JSON.parse(fields.job.value);if(job!==null&&(typeof job!=='object'||Array.isArray(job)))throw new Error('Prepared job must be an object or null.');if(job&&(job.status&&!['prepared'].includes(job.status)||job.dispatch_status&&job.dispatch_status!=='not_dispatched'))throw new Error('A prepared packet cannot claim dispatch or completion.');}}catch(error){out.hidden=false;out.replaceChildren(node('p','source-error',error.message));return;}
      const payload={source_id:i.source_id,item_id:i.id,expected_revision:owned(i).revision??0,priority:fields.priority.value.trim()==='0'?0:fields.priority.value.trim()||null,next_action:fields.next_action.value.trim()||null};if(job!==undefined)payload.job=job;
      saving=true;submit.disabled=true;Object.values(fields).forEach(f=>f.disabled=true);
      try{const saved=await api.updateWork('work-item:'+i.source_id+':'+i.id,payload,out,reconcile);await refresh(false,true);if(saved){dialog.close();api.showToast('Work direction saved.');}}
      finally{saving=false;submit.disabled=false;Object.values(fields).forEach(f=>f.disabled=false);submit.textContent='Save / reconcile unchanged edit';}
    });dialog.append(form);document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();
  }
  function peerControl(mode,requestId='',peer='MERIDIAN',message='',workItem=null){
    peerDialog.replaceChildren();const form=node('form'),head=node('div','dialog-heading');append(head,node('h2','',({submit:'Delegate to Gemini',inspect:'Inspect Gemini request',followup:'Follow up existing request',cancel:'Cancel existing request'})[mode]),btn('×',()=>peerDialog.close(),'icon-button'));form.append(head);
    const exact={submit:'gemini_submit',inspect:'gemini_get_request',followup:'gemini_follow_up',cancel:'gemini_cancel'}[mode],route=api.getTools().find(t=>t.name===exact&&t.runtime_id==='shared-equipment');
    if(workItem)form.append(node('p','field-help','Selected work: '+(workItem.title||workItem.id)));
    const fields={};
    function input(key,label,value,multi=false){const w=node('div','form-field'),l=node('label','',label),n=node(multi?'textarea':'input');n.value=value;n.required=true;n.id='peer-'+key;l.htmlFor=n.id;if(multi)n.rows=7;append(w,l,n);form.append(w);fields[key]=n;}
    if(mode==='submit'){const w=node('div','form-field'),l=node('label','','Existing Gemini peer'),s=node('select');s.id='peer-choice';l.htmlFor=s.id;['MERIDIAN','TESSERA'].forEach(v=>{const o=node('option','',v);o.value=v;s.append(o);});s.value=peer;append(w,l,s);form.append(w);fields.peer=s;}
    else input('request_id','Existing provider request ID',requestId);
    if(mode==='submit'||mode==='followup')input('message','Concrete work, source references, and expected receipt',message,true);
    if(mode==='cancel')form.append(node('p','inline-note','Cancellation is cooperative. A request accepted by the provider may already have effects; inspect the returned receipt.'));
    const out=node('div','action-output');out.hidden=true;form.append(out);const submit=node('button','button button-primary',mode==='inspect'?'Read provider status':mode==='cancel'?'Request cancellation':mode==='followup'?'Send follow-up':'Submit job');submit.type='submit';submit.disabled=!route||peerBusy;form.append(submit);
    if(!route)form.append(node('p','source-error','This exact route is not currently exposed by shared-equipment. Refresh the runtime catalog.'));
    form.addEventListener('submit',async e=>{e.preventDefault();if(peerBusy||!route)return;const args=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value.trim()]));if(mode==='inspect')args.wait_ms=0;
      peerBusy=true;submit.disabled=true;Object.values(fields).forEach(f=>f.disabled=true);activePeerOperation={mode,requestId:args.request_id||'',peer:args.peer||peer};
      const swarm=mode==='submit'?dispatchBinding(workItem,args.peer):null;
      const options=swarm?{swarm,onReceipt:receipt=>canonicalReceipt(out,receipt,swarm.task_key)}:undefined;
      try{await api.callTool('peer:'+mode+':'+(args.request_id||args.peer)+(swarm?':'+swarm.task_key:''),exact,args,out,'shared-equipment',options);}
      finally{peerBusy=false;submit.disabled=false;Object.values(fields).forEach(f=>f.disabled=false);submit.textContent='Submit / reconcile unchanged request';renderFleetJobs();}
    });peerDialog.append(form);peerDialog.showModal();
  }
  function renderFleetJobs(){
    const st=api.getState();if(!st)return;let controls=$('gemini-job-controls');
    if(!controls){controls=node('article','panel compact-panel');controls.id='gemini-job-controls';$('view-fleet').insertBefore(controls,$('view-fleet').querySelector('.section-heading'));}controls.replaceChildren(node('h2','','Drive existing Gemini peers'),node('p','field-help','Shared runtime controls retain operation IDs and provider receipts. Use an existing request ID to inspect, follow up, or cancel.'));
    const bs=node('div','button-row work-detail-actions');[['submit','Delegate job'],['inspect','Inspect request'],['followup','Follow up'],['cancel','Cancel request']].forEach(([mode,label])=>bs.append(btn(label,()=>peerControl(mode))));controls.append(bs);
    const jobs=items().filter(i=>/gemini/i.test(provider(i)+' '+text(i.kind)+' '+text(i.id)+' '+text(i.peer)));
    jobs.slice(0,8).forEach(j=>{const rid=requestID(j);if(!rid)return;const r=node('div','overview-work');append(r,node('strong','',j.title||rid),phase(j.status),btn('Inspect',()=>peerControl('inspect',rid)));controls.append(r);});
    const ops=list(st.operations).filter(o=>/^gemini_/.test(o.name||''));const seen=new Set();ops.forEach(o=>{const direct=requestID(o);if(direct&&!seen.has(direct)){seen.add(direct);append(controls,btn('Inspect '+direct,()=>peerControl('inspect',direct),'text-button'));}const refs=o.provider_refs||o.summary?.provider_refs||o.safe_summary?.provider_refs||o.result_summary?.provider_refs;const queue=Array.isArray(refs)?refs:refs&&typeof refs==='object'?Object.entries(refs).map(([path,value])=>({path,value})):[];queue.forEach(ref=>{const key=first(ref.key,ref.path,ref.name,''),value=first(ref.value,ref.id);if(!/request_id/.test(text(key))||typeof value!=='string'||value==='command-center'||seen.has(value))return;seen.add(value);append(controls,btn('Inspect '+value,()=>peerControl('inspect',value),'text-button'));});});
    const sessions=list(st.sessions),cards=[...$('session-list').children];sessions.forEach((s,index)=>{const c=cards[index];if(!c)return;c.querySelectorAll('.fleet-work-binding').forEach(n=>n.remove());const bound=items().filter(i=>field(i,'session_id')===s.id||field(i,'native_task_id')===s.id||field(i,'thread_id')===s.id||i.id===s.id||i.owner_work?.job?.session_id===s.id);const b=node('div','fleet-work-binding');append(b,metadata([['Current job',first(s.current_job,s.job,s.objective)],['Next consumer',first(s.next_consumer,s.consumer)],['Work observed',date(first(s.activity_observed_at,s.objective_observed_at),'Unknown work observation time')]]));bound.slice(0,3).forEach(i=>append(b,btn(i.title||i.id,()=>showDetail(i),'text-button')));const p={id:s.id,title:s.label||s.id,project:s.project,owner:s.peer||s.label,objective:s.objective,next_action:first(s.next_action,s.next_consumer,'Continue the recorded objective from the latest receipt.'),url:s.url,refs:[s.origin?.source_ref].filter(Boolean),activity_observed_at:s.activity_observed_at};b.append(btn('Copy session job packet',()=>copy(packet(p)),'text-button'));c.append(b);});
  }
  function nativeLinks(i,registered){
    const taskURLs=new Set([i.url,...refRows(i.refs).map(r=>r.url)].filter(v=>typeof v==='string'&&url(v)));
    return registered.filter(r=>r.id===i.id||r.origin?.native_thread_id===i.id||[r.url,...refRows(r.refs).map(x=>x.url)].some(u=>taskURLs.has(u)));
  }
  function renderNativeTasks(){
    const fleet=$('view-fleet');if(!fleet)return;
    let panel=$('native-task-panel');
    if(!panel){
      panel=node('article','panel');panel.id='native-task-panel';
      append(panel,node('h2','','Native tasks'),node('p','field-help','Tasks are conversation records, not VMs or a count of active workers. Registered sessions and hardware remain separate.'));
      const search=node('input');search.id='native-task-search';search.type='search';search.placeholder='Search native tasks';search.setAttribute('aria-label','Search native tasks');search.addEventListener('input',renderNativeTasks);
      const filter=node('select');filter.id='native-task-filter';filter.setAttribute('aria-label','Native task relationship');
      [['all','All native tasks'],['linked','Linked to registered records'],['additional','Additional native tasks']].forEach(([value,label])=>{const o=node('option','',label);o.value=value;filter.append(o);});filter.value='all';filter.addEventListener('change',renderNativeTasks);
      const count=node('p','field-help');count.id='native-task-count';const coverage=node('p','field-help');coverage.id='native-task-coverage';const rows=node('div');rows.id='native-task-rows';append(panel,search,filter,count,coverage,rows);fleet.append(panel);
    }
    const registered=list(api.getState()?.sessions),all=items().filter(nativeTask),q=$('native-task-search').value.trim().toLowerCase(),mode=$('native-task-filter').value;
    const mapped=all.map(i=>({i,links:nativeLinks(i,registered)})),linked=mapped.filter(r=>r.links.length).length;
    const matches=mapped.filter(({i,links})=>(mode==='all'||(mode==='linked'?links.length:!links.length))&&(!q||[i.id,i.title,i.status,next(i),...links.map(r=>r.id)].join(' ').toLowerCase().includes(q)));
    $('native-task-count').textContent=matches.length+' returned / '+all.length+' total native tasks · '+linked+' linked · '+(all.length-linked)+' additional';
    const src=sources().find(s=>s.id==='codex-native-fleet');
    $('native-task-coverage').textContent='Source coverage: '+(src?.coverage?.complete===true?'complete for stated scope':'partial or unknown; retained older rows may be present')+'. '+text(src?.coverage||'No scope detail returned')+' Per-task read times use only list_observed_at; absent observations remain unknown.';
    $('native-task-rows').replaceChildren(...matches.map(({i,links})=>{
      const card=node('article','overview-work');append(card,node('h3','',i.title||i.id),phase(i.status),metadata([['Native ID',i.id],['Relationship',links.length?'Linked: '+links.map(r=>r.id).join(', '):'Additional native task'],['List read',date(nativeRead(i),'Unknown read time')],['Activity observed',date(i.activity_observed_at)],['Conversation metadata updated',date(i.updated_at,'Unknown metadata time')]]),btn('Inspect task',()=>showDetail(i)));return card;
    }));
  }
  function refresh(force=false,afterCurrent=false){
    // Manual refreshes and saves need a read begun after the current request.
    // Coalesce waiting callers and retain the strongest (forced) refresh intent.
    if(loading){
      if(!force&&!afterCurrent)return loading;
      if(!queuedRefresh){
        const queued={force,promise:null};
        queued.promise=loading.then(()=>{
          queuedRefresh=null;
          return refresh(queued.force);
        },failure=>{queuedRefresh=null;throw failure;});
        queuedRefresh=queued;
      }
      if(force)queuedRefresh.force=true;
      return queuedRefresh.promise;
    }
    loading=(async()=>{
      try{const {body}=await api.request('/api/work'+(force?'?refresh=1':''));if(!body||!Array.isArray(body.items)||!Array.isArray(body.sources))throw new Error('Work response is missing items or source coverage.');
        const indexed=new Map();body.sources.forEach(s=>{if(!indexed.has(s.id))indexed.set(s.id,s);});
        // Preserve the first matching source, as Array.find did. Index only
        // metadata: heartbeat/freshness calculations still use the current clock.
        snapshot=body;sourceIndex=indexed;error='';}
      catch(e){error=e.message;}
      finally{loading=null;renderAll();}
    })();
    return loading;
  }
  function autoRefresh(){const now=Date.now(),force=lastCollectorRefresh===0||now<lastCollectorRefresh||now-lastCollectorRefresh>=AUTO_REFRESH_MS;if(force)lastCollectorRefresh=now;return refresh(force);}
  function renderAll(){
    Object.keys(labels).forEach(renderView);renderOverview();renderFleetJobs();renderNativeTasks();
    if(detail.open&&selected){
      const current=items().find(i=>i.id===selected.id&&i.source_id===selected.source_id);
      if(current)showDetail(current);
      else{detail.close();selected=null;}
    }
  }
  window.addEventListener('commons-open-work',event=>{
    const ref=event.detail||{};
    const record=items().find(i=>i.id===ref.item_id&&i.source_id===ref.source_id);
    if(record)showDetail(record);
  });
  window.addEventListener('commons-state',renderAll);
  $('refresh-button').addEventListener('click',()=>refresh(true));
  setInterval(()=>{if(!document.hidden)autoRefresh();},30000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)autoRefresh();});
  api.navigate(location.hash.slice(1));renderAll();if(document.hidden)refresh();else autoRefresh();
})();
