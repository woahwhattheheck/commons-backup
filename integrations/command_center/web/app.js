'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const views = ['focus','work','builds','inbox','marketing','fleet','resources','tools','access','budget','feed'];
  let state = null, currentView = 'focus', lastSync = null, syncError = '', refreshing = null, queuedRefresh = null;
  let tools = [], selectedKey = '', busy = false, dialogSpec = null, toastTimer;
  let publicationAdmission=null, admissionSeen=null, admissionUnavailable=false, admissionReading=null, admissionTimer, admissionUI=null;
  const attemptKey = 'commons.command-center.operations.v1';
  let attempts = {};
  try { attempts = JSON.parse(sessionStorage.getItem(attemptKey) || '{}'); } catch (_) {}
  const arr = v => Array.isArray(v) ? v : [];
  const str = v => v == null ? '' : typeof v === 'string' ? v : JSON.stringify(v);
  const first = (...v) => v.find(x => x !== undefined && x !== null && x !== '') ?? null;
  const label = r => str(first(r.label,r.name,r.title,r.resource_id,r.id,r.provider,'Unnamed record'));
  const status = r => str(first(r.status,r.condition,r.state,'unknown'));
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  const terminal = s => /^(completed|complete|succeeded|success|done|failed|error|rejected|cancelled|canceled)$/i.test(s || '');
  const pending = s => /pending|unknown|uncertain|accepted|running|executing|queued|submitted|submitting|dispatching|cancel_requested|paused|awaiting_input|needs_attention|timeout/i.test(s || '');
  const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = str(text); return n; };
  const replace = (id, nodes) => $(id).replaceChildren(...nodes);
  const time = value => { if (!value) return 'Observation time unknown'; const d = new Date(value); return Number.isNaN(d.getTime()) ? str(value) : d.toLocaleString([], {dateStyle:'medium',timeStyle:'short'}); };
  // Measurement freshness never comes from record creation or metadata updates.
  const observed = r => [r.observed_at,r.observed_at_utc].find(v => typeof v === 'string' && v.trim() !== '' && Number.isFinite(Date.parse(v))) ?? null;
  const activityTime = r => first(observed(r),r.updated_at,r.started_at);
  function safeURL(value) {
    if (typeof value !== 'string' || !value.trim()) return null;
    try { const u = new URL(value, location.origin); return ['http:','https:','codex:'].includes(u.protocol) ? u.href : null; } catch (_) { return null; }
  }
  function sessionURL(r) {
    return typeof r.url === 'string' && /^(https?:\/\/|codex:\/\/)/i.test(r.url.trim()) ? safeURL(r.url) : null;
  }
  function sourceLabel(r) {
    const source = arr(state && state.sources).find(s => s.id === r.source_id);
    const name = first(typeof r.source === 'string' ? r.source : null,r.source_ref,r.source_id,r.origin,r.path);
    const freshness = first(r.source_status,source && source.status);
    return name ? str(name)+(freshness?' · '+str(freshness).replace(/_/g,' '):'') : null;
  }
  function sourceURL(r) {
    const explicit = safeURL(first(r.source_url,r.url,r.html_url,r.web_url,r.permalink,r.display_url,r.source && r.source.url));
    if (explicit) return explicit;
    const source = arr(state && state.sources).find(s => s.id === r.source_id || s === r || (s.id === r.id && s.path === r.path));
    if (!source) return null;
    if (/^https?:\/\//i.test(str(source.path))) return safeURL(source.path);
    if (!/^[0-9a-f]{40}$/i.test(str(source.sha)) || typeof source.path !== 'string' || !source.path || source.path.startsWith('/') || source.path.split('/').includes('..')) return null;
    return 'https://github.com/woahwhattheheck/commons/blob/' + source.sha + '/' + source.path.split('/').map(encodeURIComponent).join('/');
  }
  function link(text, url, cls='source-link') { const n = make('a',cls,text); n.href = url; n.target = '_blank'; n.rel = 'noopener noreferrer'; return n; }
  function button(text, handler, cls='text-button') { const n = make('button',cls,text); n.type = 'button'; n.addEventListener('click',handler); return n; }
  function badge(value) {
    const s = str(value || 'unknown'), tone = /fail|error|offline|refused|unavailable/i.test(s) ? 'bad' : /unknown|pending|stale|constrain|degraded|held/i.test(s) ? 'warn' : /live|online|running|active|success|complete|healthy|ready/i.test(s) ? 'good' : 'neutral';
    return make('span','badge '+tone,s.replace(/_/g,' '));
  }
  function clean(value, key='') {
    if (/^(password|secret|token|api[_-]?key|access[_-]?token|refresh[_-]?token|private[_-]?key|credential[_-]?value|authorization|plaintext)$/i.test(key)) return '[secret value not displayed]';
    if (Array.isArray(value)) return value.map(x=>clean(x));
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,clean(v,k)]));
    return value;
  }
  function raw(r, title='Inspect original record') {
    const d = make('details','raw-details'), s = make('summary','',title), p = make('pre','',JSON.stringify(clean(r),null,2));
    d.append(s,p); return d;
  }
  function empty(text) { return make('div','empty-inline',text); }
  function meta(rows) {
    const d = make('dl','record-meta');
    rows.forEach(([k,v])=>{ d.append(make('dt','',k),make('dd','',v === null || v === undefined || v === '' ? 'Unknown' : str(v))); }); return d;
  }
  function recordCard(r, kind='resource') {
    const card = make('article','panel resource-card'), top = make('div','card-top'), title = make('div');
    title.append(make('h3','card-label',label(r)),make('div','card-kind',first(r.kind,r.type,r.provider,kind)));
    top.append(title,badge(status(r))); card.append(top);
    const desc = first(r.description,r.summary,r.purpose,r.value && typeof r.value === 'string' ? r.value : null);
    if (desc) card.append(make('p','card-description',str(desc)));
    const details = [['ID',first(r.id,r.resource_id)],['Observed',time(observed(r))],['Source',sourceLabel(r)]];
    if(r.origin)details.push(['Origin',r.origin]);
    if(r.telemetry_source)details.push(['Telemetry source',r.telemetry_source]);
    if(r.source_observed_at)details.push(['Source fetched',time(r.source_observed_at)]);
    if(r.updated_at && r.updated_at!==observed(r))details.push(['Metadata updated',time(r.updated_at)]);
    card.append(meta(details));
    const url = sourceURL(kind==='session VM'?{...r,url:null,html_url:null,web_url:null,permalink:null,display_url:null}:r); if (url) card.append(link('Open original source ↗',url)); card.append(raw(r)); return card;
  }
  function showToast(text) { clearTimeout(toastTimer); $('toast').textContent=text; $('toast').hidden=false; toastTimer=setTimeout(()=>$('toast').hidden=true,5500); }
  function navigate(view) {
    if (!views.includes(view)) view='focus'; const changed=currentView!==view; currentView=view;
    views.forEach(v=>{const el=$('view-'+v); if(el) el.hidden=v!==view;});
    document.querySelectorAll('[data-view]').forEach(n=>{ n.classList.toggle('active',n.dataset.view===view); if(n.dataset.view===view)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current'); });
    $('breadcrumb-view').textContent=view[0].toUpperCase()+view.slice(1);
    if(location.hash!=='#'+view) history.replaceState(null,'','#'+view);
    if(changed)window.scrollTo({top:0,left:0,behavior:'instant'});
    if(view==='resources')renderPublicationAdmission();
  }
  async function request(path, method='GET', data) {
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),45000);
    try {
      const response=await fetch(path,{method,credentials:'same-origin',headers:data ? {'Content-Type':'application/json'} : {},body:data ? JSON.stringify(data) : undefined,signal:controller.signal,cache:'no-store'});
      const text=await response.text(); let body; try { body=text ? JSON.parse(text) : {}; } catch (_) { const e=new Error('Server returned an unreadable response (HTTP '+response.status+').'); e.uncertain=method!=='GET'; throw e; }
      if(!response.ok) { const e=new Error(str(first(body.message,body.error && body.error.message,body.error,'HTTP '+response.status))); e.workRevisionConflict=path==='/api/work/item'&&response.status===409&&body.code==='work_revision_conflict';e.uncertain=response.status>=500 || response.status===408 || (response.status===409&&!e.workRevisionConflict); e.body=body; throw e; }
      return {body,httpStatus:response.status};
    } catch(e) { if(e.name==='AbortError') {e.message='Request timed out. The server may still be processing it.';e.uncertain=true;} else if(e.uncertain===undefined) e.uncertain=true; throw e; }
    finally { clearTimeout(timeout); }
  }
  function flatten(runtimeRows, extra=[]) {
    const map=new Map();
    arr(runtimeRows).forEach(r=>arr(r.tools).forEach(t=>{
      const name=first(t.name,t.function && t.function.name,t.id); if(!name)return;
      const tool={raw:t,name:str(name),runtime_id:str(r.id),runtime:r,schema:first(t.inputSchema,t.input_schema,t.parameters,t.function && t.function.parameters,{}),description:str(first(t.description,t.function && t.function.description,''))};
      map.set(tool.runtime_id+'::'+tool.name,tool);
    }));
    arr(extra).forEach(t=>{const rid=first(t.runtime_id,t.runtime && t.runtime.id);if(!rid)return;const runtime=arr(runtimeRows).find(r=>str(r.id)===str(rid))||{id:rid,label:rid,status:'unknown'};const name=first(t.name,t.function&&t.function.name);if(name)map.set(str(rid)+'::'+name,{raw:t,name:str(name),runtime_id:str(rid),runtime,schema:first(t.inputSchema,t.input_schema,t.parameters,{}),description:str(t.description)});});
    return [...map.values()].sort((a,b)=>(a.name+a.runtime_id).localeCompare(b.name+b.runtime_id));
  }
  function connectionState() {
    renderPublicationAdmission();
    const stale=lastSync && Date.now()-lastSync>65000;
    const n=$('connection-state'); n.className='connection-state'+(syncError?' offline':stale?' stale':'');
    n.replaceChildren(make('span','status-dot'),make('span','',syncError?'Refresh failed':!lastSync?'Connecting':stale?'Stale observation':'Synced'));
    $('last-sync').textContent=lastSync?'Last sync '+new Date(lastSync).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}):'No successful sync yet';
    $('sync-error').hidden=!syncError; $('sync-error').textContent=syncError?(syncError+' Prior observations are retained. Use Refresh to try the read again.'):'';
  }
  function refresh(force=false,afterCurrent=false) {
    if(refreshing){
      if(!force&&!afterCurrent)return refreshing;
      // Explicit refreshes and completed saves need a read started after the
      // current request. Coalesce callers while retaining forced refresh intent.
      if(!queuedRefresh){
        const queued={force,promise:null};
        queued.promise=refreshing.then(()=>{queuedRefresh=null;return refresh(queued.force);},
          error=>{queuedRefresh=null;throw error;});
        queuedRefresh=queued;
      }
      if(force)queuedRefresh.force=true;
      return queuedRefresh.promise;
    }
    refreshing=(async()=>{
      $('refresh-button').disabled=true;
      readPublicationAdmission();
      try { const response=await request(force===true?'/api/state?refresh=1':'/api/state'); const next=response.body;
        if(!next || typeof next!=='object' || !Array.isArray(next.sources)) throw new Error('State response is missing its source catalog.');
        state=next; tools=flatten(state.runtimes); lastSync=Date.now();syncError='';
        arr(state.operations).forEach(op=>Object.values(attempts).forEach(a=>{if(a.id===op.operation_id&&terminal(op.status))a.status=op.status;})); saveAttempts();render();
      } catch(e) {syncError=e.message;connectionState();}
      finally {refreshing=null;$('refresh-button').disabled=false;connectionState();}
    })();
    return refreshing;
  }
  async function reloadTools() {
    $('reload-tools').disabled=true;
    try {const {body}=await request('/api/tools');const runtimes=Array.isArray(body.runtimes)?body.runtimes:arr(state&&state.runtimes);const extra=Array.isArray(body)?body:arr(body.tools);tools=flatten(runtimes,extra);$('tool-catalog-error').hidden=true;renderTools();renderAccess();}
    catch(e){$('tool-catalog-error').textContent='Tool catalog refresh failed: '+e.message+'. Previous catalog retained.';$('tool-catalog-error').hidden=false;}
    finally{$('reload-tools').disabled=false;}
  }
  function sessionStats(records) {
    const machines=records.filter(r=>r.kind==='machine'),sessions=records.filter(r=>r.kind!=='machine');
    const active=sessions.filter(r=>/^(running|active|in_progress|inprogress|executing|busy|owner_reported_in_use|reported_active)(?:_reported)?$/i.test(status(r).trim().replace(/[\s-]+/g,'_'))).length;
    return {sessions:sessions.length,machines:machines.length,active};
  }
  function operationSummary(o) {
    let summary=o.summary;
    if(typeof summary==='string') {try {summary=JSON.parse(summary);} catch(_) {summary=null;}}
    const s=summary&&typeof summary==='object'&&!Array.isArray(summary)?summary:{};
    const outcome=status(o);
    if(/^(failed|error|rejected)$/i.test(outcome)||s.provider_reported_error===true)return 'Operation reported a failure. Inspect the receipt for details.';
    if(/^(cancelled|canceled)$/i.test(outcome))return 'Operation was cancelled.';
    if(pending(outcome))return 'Completion is not established. Inspect the latest receipt before retrying.';
    if(typeof o.summary==='string'&&!summary&&o.summary.trim()&&!/^[\[{]/.test(o.summary.trim()))return o.summary;
    if(!/^(completed|complete|succeeded|success|done)$/i.test(outcome))return 'No completed outcome is recorded. Inspect the receipt for details.';
    if(s.receipt_received===false||s.execution_complete===false)return 'A response was recorded; completion is not established by the receipt.';
    if(typeof s.hidden==='boolean')return s.hidden?'Entry hidden from the default feed; the original is retained.':'Entry restored to the default feed.';
    if(s.record_id) {
      const names={focus:'Current objective saved.',sessions:'Session record saved.',budgets:'Budget observation saved.',runtimes:'Runtime route recorded.',janny:'Housekeeping responsibility saved.',feed:'Feed note saved.'};
      return names[o.name]||'Record saved. Inspect the receipt for its ID.';
    }
    if(s.receipt_received===true&&s.execution_complete===true)return 'Execution completed; the runtime returned a receipt.';
    return 'Operation reported success. Inspect the receipt for details.';
  }
  function routineRefresh(e) {
    return e.kind==='source'&&e.source_status==='live'&&!e.error&&e.body==='Source observation refreshed.';
  }
  function operationRows(records, limit) {
    if(!state)return [empty('Waiting for a successful state read.')]; if(!records.length)return [empty('No operation records returned. No execution is inferred.')];
    return records.slice(0,limit).map(o=>{const row=make('div','operation-row'),main=make('div','operation-main'),info=make('div','operation-info');
      info.append(make('strong','',first(o.name,o.summary,'Operation')),make('small','',str(o.operation_id||'ID unavailable')+' · '+time(o.started_at)));
      main.append(make('span','operation-icon','↗'),info,badge(o.status));row.append(main);row.append(make('p','operation-summary',operationSummary(o)));row.append(raw(o,'Inspect result and receipt'));return row;});
  }
  function attentionItems() {
    if(!state)return [];const items=[];
    arr(state.sources).filter(s=>s.error||/error|failed|offline|unavailable/i.test(status(s))).forEach(s=>items.push({title:'Source: '+label(s),body:str(s.error||status(s)),at:observed(s)}));
    arr(state.runtimes).filter(r=>r.error||/error|failed|offline|unavailable|degraded/i.test(status(r))).forEach(r=>items.push({title:'Runtime: '+label(r),body:str(r.error||status(r)),at:observed(r)}));
    arr(state.operations).filter(o=>/failed|error|uncertain|unknown/i.test(status(o))).slice(0,5).forEach(o=>items.push({title:str(first(o.name,'Operation needs reconciliation')),body:operationSummary(o),at:o.started_at}));
    arr(state.feed).filter(e=>(!e.hidden||protectedEvent(e))&&/attention|decision|failure|error|incident/i.test(str(e.kind))).slice(0,5).forEach(e=>items.push({title:e.title,body:e.body,at:activityTime(e)}));return items;
  }
  function renderFocus() {
    const sessions=arr(state&&state.sessions),resources=arr(state&&state.resources),attention=attentionItems();
    const counts=sessionStats(sessions);
    const stats=[['Recorded sessions',counts.sessions,counts.active+' reported active · '+counts.machines+' '+(counts.machines===1?'machine':'machines'),'◈'],['Resources',resources.length,'Existing inventory records','▦'],['Tool routes',tools.length,'Exposed runtime schemas','⌘'],['Attention',attention.length,'Reported exceptions','◎']];
    replace('focus-stats',stats.map(([title,value,note,symbol],i)=>{const c=make('div','stat-card'+(i===3?' attention':'')),top=make('div','stat-top');top.append(make('span','',title),make('span','stat-symbol',symbol));c.append(top,make('div','stat-value',state?value:'—'),make('div','stat-note',state?note:'Observation unavailable'));return c;}));
    $('objective-text').textContent=state?str(first(state.focus&&state.focus.objective,'No current objective recorded.')):'Waiting for the operation state.';
    $('next-action-text').textContent=state?str(first(state.focus&&state.focus.next_action,'Set one concrete next action.')):'The current objective will appear after a successful sync.';
    const ops=arr(state&&state.operations);$('operations-count').textContent=state?ops.length:'—';replace('recent-operations',operationRows(ops,8));replace('fleet-operations',operationRows(ops,30));
    $('attention-count').textContent=state?attention.length:'—';
    replace('attention-list',attention.length?attention.slice(0,7).map(a=>{const c=make('div','attention-item'),b=make('div');b.append(make('h3','',a.title),make('p','',a.body),make('span','small',time(a.at)));c.append(make('span','attention-marker'),b);return c;}):[empty(state?'No exceptions in the returned observations. Unknown coverage is visible in Source health.':'Waiting for source observations.')]);
    const j=state&&state.janny,peer=first(j&&j.peer,'Unassigned');const p=make('div','janny-peer'),t=make('div');t.append(make('strong','',peer),make('span','','Existing peer responsibility'));p.append(make('div','peer-avatar','↺'),t);
    replace('janny-summary',[p,make('p','janny-scope',str(first(j&&j.scope,'Catalog freshness, receipts, disposable artifacts, and reversible feed moderation. Original evidence and shared access remain intact.')))]);
  }
  function renderFleet() {
    const sessions=arr(state&&state.sessions),counts=sessionStats(sessions);$('session-count').textContent=state?counts.sessions+' sessions · '+counts.machines+' '+(counts.machines===1?'machine':'machines')+' · activity is last reported':'Unknown';
    replace('session-list',sessions.length?sessions.map(s=>{
      const c=recordCard(s,'session VM');c.className='panel session-card';
      const gib=value=>finite(value)?value.toLocaleString([], {maximumFractionDigits:2})+' GiB':null;
      const machine=s.kind==='machine',capacityCPU=machine&&finite(s.cpu_capacity),capacityRAM=machine&&finite(s.ram_capacity_gib);
      const metrics=[['Provider',s.provider],[capacityCPU?'CPU capacity':'CPU',capacityCPU?s.cpu_capacity:s.cpu],[capacityRAM?'RAM capacity':'RAM',gib(capacityRAM?s.ram_capacity_gib:s.ram_gib)],['GPU',s.gpu],['Workspace',s.workspace]];
      if(capacityCPU)metrics.push(['Host logical CPUs',s.cpu]);
      if(capacityRAM)metrics.push(['Host RAM',gib(s.ram_gib)]);
      if(machine&&finite(s.ram_cgroup_headroom_gib)){const bytes=s.process_limits&&s.process_limits.memory_headroom_bytes;const headroom=finite(bytes)&&bytes>0&&bytes<0.01*2**30?'<0.01 GiB':gib(s.ram_cgroup_headroom_gib);metrics.push(['Container memory headroom',headroom]);}
      if(machine){
        const diskTotal=finite(s.disk_total_bytes)?s.disk_total_bytes/2**30:s.disk_gib;
        const diskFree=finite(s.disk_free_bytes)?s.disk_free_bytes/2**30:s.disk_free_gib;
        const diskPercent=finite(s.disk_used_bytes)&&finite(s.disk_free_bytes)&&s.disk_used_bytes+s.disk_free_bytes>0?100*s.disk_used_bytes/(s.disk_used_bytes+s.disk_free_bytes):null;
        metrics.push(['Filesystem capacity',gib(diskTotal)],['Filesystem available',finite(diskFree)&&diskFree>0&&diskFree<0.01?'<0.01 GiB':gib(diskFree)],['Filesystem used',finite(diskPercent)?diskPercent.toLocaleString([], {maximumFractionDigits:1})+'%':null]);
      }
      c.append(meta(metrics));
      if(machine)c.append(make('p','source-note','Available disk space is shared across workloads on the filesystem containing the workspace path. Usage percentage is used space divided by used plus available space, excluding reserved space.'));
      if(machine&&s.process_limits)c.append(make('p','source-note','CPU capacity is a sustained ceiling. Memory headroom reflects current usage across processes sharing the limit and excludes possible cache reclaim. Limit coverage: '+str(s.process_limits.cgroup_status)+'.'));
      if(machine){
        const limits=s.process_limits||{},events=arr(limits.memory_events),isEventSource=value=>/(^|\/)memory\.events(?:\.local)?$/.test(str(value));
        const unavailable=arr(limits.unavailable_interfaces).filter(isEventSource),errors=arr(limits.read_errors).filter(error=>error&&isEventSource(error.source));
        const section=make('section','memory-events');section.append(make('h4','card-kind','Memory events · cumulative'));
        section.append(make('p','source-note','Counters accumulate per cgroup source. Sources can overlap; each is shown separately. These observations do not identify a particular process failure.'));
        events.forEach(event=>{
          if(!event||typeof event!=='object')return;
          const counters=event.counters&&typeof event.counters==='object'&&!Array.isArray(event.counters)?event.counters:{};
          const count=value=>Number.isSafeInteger(value)&&value>=0?value:null;
          const highlights=['oom','oom_kill'].filter(key=>Object.prototype.hasOwnProperty.call(counters,key)).map(key=>key+' '+(count(counters[key])??'Unknown'));
          const details=make('details','raw-details');details.append(make('summary','',str(event.scope||'Scope unknown')+(highlights.length?' · '+highlights.join(' · '):' · Counters')));
          const values=Object.entries(counters).map(([key,value])=>[key,count(value)]);
          details.append(meta([['Source',event.source],['Scope',event.scope],...values]));
          if(!values.length)details.append(make('p','source-note','Counters unavailable for this source.'));
          section.append(details);
        });
        unavailable.forEach(source=>section.append(make('p','source-note','Unavailable: '+str(source))));
        errors.forEach(error=>section.append(make('p','source-error','Read error: '+str(error.source)+' · '+str(error.error||'Unknown error'))));
        if(!events.length&&!unavailable.length&&!errors.length)section.append(make('p','source-note','Memory-event observations unavailable.'));
        c.append(section);
      }
      if(s.objective)c.append(make('div','session-objective',s.objective));const existingSessionURL=sessionURL(s);if(existingSessionURL)c.append(link('Open existing session ↗',existingSessionURL,'button button-small button-quiet'));c.append(button('Update record',()=>sessionForm(s)));return c;
    }):[empty('No session records returned. Existing GPT/Claude VM capacity must be bound to its actual session and route.')]);
    const runtimes=arr(state&&state.runtimes);
    replace('runtime-list',runtimes.length?runtimes.map(r=>{const c=recordCard(r,'runtime');c.append(meta([['Gateway',r.gateway_url],['Schemas',arr(r.tools).length]]));if(r.error)c.append(make('p','source-error',r.error));c.append(button('Inspect tools →',()=>{ $('tool-search').value=str(r.id);renderTools();navigate('tools');}));return c;}):[empty('No runtime catalog returned. Account metadata alone does not make service operations callable here.')]);
  }
  function allRecords(){return [...arr(state&&state.resources).map(r=>({r,kind:'resource'})),...arr(state&&state.connections).map(r=>({r,kind:'connection'}))];}
  function readPublicationAdmission() {
    if(!$('publication-admission') || admissionReading)return admissionReading;
    // One independent read: a slow authority must not hold up state refreshes,
    // completed saves, or the Refresh button. Failure retains the last snapshot.
    admissionReading=(async()=>{
      try {
        const {body:r}=await request('/api/provider/admission');
        const capacity=r&&r.capacity, active=r&&r.active;
        const timestamp=value=>typeof value==='string' && /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
        if(!r || r.ok!==true || r.scope!=='github:publication' ||
          !(capacity===null || Number.isInteger(capacity)&&capacity>=1&&capacity<=64) ||
          !Number.isSafeInteger(active) || active<0 || typeof r.admission_available!=='boolean' ||
          !(r.reason===null || typeof r.reason==='string'&&r.reason.trim().length>0) ||
          !(r.retry_not_before===null || timestamp(r.retry_not_before)) ||
          !Array.isArray(r.leases) || r.leases.length!==active || r.leases.some(x=>!x || !timestamp(x.expires_at)) ||
          (r.admission_available && (capacity===null || active>=capacity || r.reason!==null || r.retry_not_before!==null)) ||
          (!r.admission_available && r.reason===null) ||
          (r.reason==='capacity_unconfigured' && capacity!==null) ||
          (r.reason==='capacity_exhausted' && (capacity===null || active<capacity || r.retry_not_before===null)) ||
          (r.reason==='rate_limited' && r.retry_not_before===null))throw new Error('Invalid admission status');
        // Display fields only; do not retain holders, lease IDs or raw receipts.
        publicationAdmission={capacity,active,available:r.admission_available,reason:r.reason,
          deadline:r.retry_not_before,expiries:r.leases.map(x=>x.expires_at)};
        admissionSeen=Date.now();admissionUnavailable=false;
      } catch(_) {admissionUnavailable=true;}
      finally {admissionReading=null;renderPublicationAdmission();}
    })();
    return admissionReading;
  }
  function renderPublicationAdmission() {
    const panel=$('publication-admission');if(!panel)return;
    if(!admissionUI){
      const top=make('div','panel-heading'),heading=make('div'),title=make('h2','','GitHub publication capacity');title.id='publication-admission-title';
      heading.append(title,make('p','','Cooperating publishers using this command-center authority.'));
      const summary=make('span','badge neutral');summary.setAttribute('role','status');summary.setAttribute('aria-live','polite');summary.setAttribute('aria-atomic','true');
      top.append(heading,summary);
      const values=make('div','budget-values'),cells=['Capacity','Active leases','Available at read'].map(name=>{
        const cell=make('div','budget-value'),value=make('strong','','—'),label=make('span','',name);cell.append(value,label);values.append(cell);return {name,value,label};
      });
      const note=make('p','card-description'),details=make('dl','record-meta');
      panel.replaceChildren(top,values,note,details);admissionUI={summary,cells,note,details,rows:''};
    }
    const r=publicationAdmission,now=Date.now();
    const expired=!!r&&((r.deadline!==null&&Date.parse(r.deadline)<=now)||r.expiries.some(x=>Date.parse(x)<=now));
    const stale=admissionSeen!==null&&now-admissionSeen>=65000;
    const fresh=!!r&&!admissionUnavailable&&!stale&&!expired;
    let summary='Waiting for status',tone='neutral',note='Publication capacity has not been read yet.';
    if(admissionUnavailable){summary='Unavailable';tone='bad';note=r?'Status could not be read. The last observation is retained; current availability is unknown.':'Status could not be read from this command center. Capacity and availability are unknown.';}
    else if(expired){summary='Expiry reached · refresh needed';tone='warn';note='A recorded deadline or lease expiry has passed. Refresh to read current admission; expiry does not confirm an in-flight write has finished.';}
    else if(stale){summary='Stale status';tone='warn';note='The last admission read is at least 65 seconds old. Refresh to read current availability.';}
    else if(r){
      summary=r.available?'Ready':r.reason==='rate_limited'?'Provider cooldown':r.reason==='capacity_exhausted'?'All slots occupied':r.reason==='capacity_unconfigured'?'Capacity not configured':'Admission deferred';
      tone=r.available?'good':'warn';
      note=r.available?'Slots were available at the last read. Acquire and renew a lease before publication.':r.reason==='capacity_unconfigured'?'A coordinator must configure capacity for this authority.':'Publication admission is deferred by the shared authority.';
    }
    // Keep the live node stable and announce only actual status changes, not
    // every connection-state render or observation timestamp update.
    const text=(node,value)=>{if(node.textContent!==value)node.textContent=value;};
    text(admissionUI.summary,summary);admissionUI.summary.className='badge '+tone;text(admissionUI.note,note);
    const available=fresh&&r.capacity!==null?(r.available?Math.max(0,r.capacity-r.active):0):null;
    [r?r.capacity:null,r?r.active:null,available].forEach((value,i)=>{
      const cell=admissionUI.cells[i];text(cell.value,value===null?'—':value.toLocaleString());
      text(cell.label,cell.name+(!fresh&&r&&i<2?' · last observed':''));
    });
    const detailedTime=value=>new Date(value).toLocaleString([], {dateStyle:'medium',timeStyle:'medium'});
    const earliest=r&&r.expiries.length?[...r.expiries].sort((a,b)=>Date.parse(a)-Date.parse(b))[0]:null;
    const rows=[['Status fetched',admissionSeen===null?'Not observed':detailedTime(admissionSeen)]];
    if(r){rows.push(['Admission reason',r.reason||'ready']);if(r.deadline)rows.push([r.reason==='rate_limited'?'Provider retry deadline':'Admission retry deadline',detailedTime(r.deadline)]);if(earliest)rows.push(['Earliest recorded lease expiry',detailedTime(earliest)]);}
    const rowsKey=JSON.stringify(rows);
    if(admissionUI.rows!==rowsKey){admissionUI.details.replaceChildren(...meta(rows).childNodes);admissionUI.rows=rowsKey;}
    clearTimeout(admissionTimer);
    if(fresh){
      const boundaries=[admissionSeen+65000,...r.expiries.map(Date.parse)];if(r.deadline)boundaries.push(Date.parse(r.deadline));
      // This only invalidates the display. It makes no request, grants no slot,
      // and does not add another polling cadence or replay a publication.
      admissionTimer=setTimeout(renderPublicationAdmission,Math.max(1,Math.min(...boundaries)-now));
    }
  }
  function renderResources() {
    renderPublicationAdmission();
    const q=$('resource-search').value.toLowerCase(),kind=$('resource-kind').value;
    const found=allRecords().filter(x=>(kind==='all'||x.kind===kind)&&JSON.stringify(clean(x.r)).toLowerCase().includes(q));
    $('resource-results').textContent=state?found.length+' matching records':'Waiting for data';
    replace('resource-list',found.length?found.map(x=>recordCard(x.r,x.kind)):[empty(state?'No matching records. Try a wider search.':'No state has been read yet.')]);
  }
  function toolKey(t){return t.runtime_id+'::'+t.name;}
  function chooseTool(t) {
    if(busy){showToast('A tool request is still in flight. Its operation ID is retained.');return;}
    if(selectedKey===toolKey(t))return;
    selectedKey=toolKey(t);$('tool-arguments').value='{}';$('tool-output').hidden=true;$('tool-validation').hidden=true;renderTools();
  }
  function renderTools() {
    const q=$('tool-search').value.toLowerCase(),found=tools.filter(t=>(t.name+' '+t.description+' '+t.runtime_id+' '+label(t.runtime)).toLowerCase().includes(q));
    $('tool-results').textContent=found.length+' exposed routes';
    replace('tool-list',found.length?found.map(t=>{const b=button('',()=>chooseTool(t),'tool-list-button'+(toolKey(t)===selectedKey?' selected':''));b.append(make('strong','',t.name),make('small','',label(t.runtime)+' · '+status(t.runtime)));b.setAttribute('aria-pressed',String(toolKey(t)===selectedKey));return b;}):[empty('No matching runtime schemas. Connected account metadata is listed under Resources.')]);
    const t=tools.find(x=>toolKey(x)===selectedKey);$('tool-empty').hidden=!!t;$('tool-selected').hidden=!t;if(!t)return;
    $('tool-runtime').textContent=label(t.runtime)+' / '+t.runtime_id;$('tool-name').textContent=t.name;$('tool-description').textContent=t.description||'No description provided by this runtime.';
    $('tool-schema').textContent=JSON.stringify(clean(t.schema),null,2);
    const ro=t.raw.annotations&&t.raw.annotations.readOnlyHint;$('tool-readonly').textContent=ro===true?'Read-only hint':ro===false?'May change state':'Effect not declared';
    $('tool-health').textContent='Runtime: '+status(t.runtime)+' · '+time(observed(t.runtime))+'. Schema exposure is not a successful execution receipt.';
  }
  function renderAccess() {
    const refs=tools.filter(t=>t.name==='credential_references'),sealed=tools.filter(t=>t.name==='credential_retrieve_sealed');
    $('vault-route-note').textContent='Reference routes: '+refs.length+' · Sealed retrieval routes: '+sealed.length+'. No plaintext credential output is rendered.';
    $('vault-references').disabled=!refs.length;$('vault-sealed').disabled=!sealed.length;
    const rows=arr(state&&state.connections);$('connection-count').textContent=state?rows.length+' metadata records':'Unknown';
    replace('connection-list',rows.length?rows.map(r=>recordCard(r,'connection')):[empty('No connected-account metadata returned. This is an observation gap, not a peer access restriction.')]);
  }
  function renderBudgets() {
    const rows=arr(state&&state.budgets);replace('budget-list',rows.length?rows.map(b=>{
      const c=make('article','panel budget-card'),top=make('div','card-top'),title=make('div');title.append(make('h3','card-label',label(b)),make('div','card-kind',first(b.kind,b.measure_type,'observation')));top.append(title,badge(b.unit||'Unit unknown'));c.append(top);
      const isBalance=/balance/i.test(str(first(b.kind,b.measure_type,'')))||finite(b.balance);
      const measures=isBalance?[['Balance',b.balance],['Pending',b.pending]]:[['Limit',b.limit],['Used',b.used]];
      const values=make('div','budget-values');measures.forEach(([name,v])=>{const n=make('div','budget-value');n.append(make('strong','',finite(v)?v.toLocaleString():'—'),make('span','',name+' · '+str(b.unit||'unit unknown')));values.append(n);});c.append(values);
      if(!isBalance&&finite(b.limit)&&b.limit>0&&finite(b.used)){const meter=make('div','meter'),fill=make('div','meter-fill'+(b.used>=b.limit?' low':''));fill.style.width=Math.max(0,Math.min(100,b.used/b.limit*100))+'%';meter.append(fill);c.append(meter);}
      c.append(meta([['Remaining',finite(b.remaining)?b.remaining:!isBalance&&finite(b.limit)&&finite(b.used)?b.limit-b.used:null],['Committed',b.committed],['Period',b.period],['Observed',time(observed(b))]]));
      if(sourceURL(b))c.append(link('Original observation ↗',sourceURL(b)));c.append(raw(b));return c;
    }):[empty('No budget or quota observations returned. Missing values remain unknown; no cross-provider total is inferred.')]);
  }
  function protectedEvent(e){return /^(failure|error|incident|critical)$/i.test(str(e.kind));}
  function feedCard(e) {
    const c=make('article','panel feed-card'+(e.hidden?' is-hidden':'')),top=make('div','feed-card-top');top.append(badge(e.kind||'event'),make('h3','feed-title',e.title||e.id));if(e.hidden)top.append(badge(protectedEvent(e)?'Failure kept visible':'Hidden from default'));c.append(top);
    if(e.hidden&&e.moderation)c.append(make('p','moderation-reason',str(first(e.moderation.reason,e.moderation,'Reason unavailable'))));
    const original=make('details','feed-original');original.open=!e.hidden||protectedEvent(e);original.append(make('summary','','Original event'),make('p','feed-body',e.body||'No body returned.'),raw(e));c.append(original);
    const foot=make('div','feed-footer'),left=make('div');left.append(make('span','small muted',time(activityTime(e))));if(sourceURL(e))left.append(link('Open source ↗',sourceURL(e)));left.append(link('Preserved event ↗','/api/event?event_id='+encodeURIComponent(e.id)));
    if(e.kind==='swarm-task'&&typeof e.task_key==='string'&&e.task_key.trim()){const target=new URL(location.href);target.searchParams.set('swarm_task',e.task_key);target.hash='work';left.append(link('Open current task ↗',target.href));}
    foot.append(left);if(e.id&&(e.hidden||!protectedEvent(e)))foot.append(button(e.hidden?'Restore to default view':'Hide from default view',()=>moderationForm(e)));else if(protectedEvent(e))foot.append(make('span','small muted','Failures remain visible'));c.append(foot);return c;
  }
  function renderFeed() {
    const rows=arr(state&&state.feed),q=$('feed-search').value.trim().toLowerCase(),show=$('show-hidden').checked;
    const filtered=rows.filter(e=>(show||!e.hidden||protectedEvent(e))&&JSON.stringify(clean(e)).toLowerCase().includes(q));
    const grouped=!$('show-refreshes').checked&&!q;
    const refreshes=grouped?filtered.filter(e=>routineRefresh(e)&&!e.hidden):[];
    const updates=grouped?filtered.filter(e=>!routineRefresh(e)||e.hidden):filtered;
    $('feed-summary').textContent=state?updates.length+' shown'+(refreshes.length?' · '+refreshes.length+' routine refreshes grouped':'')+' · '+rows.filter(e=>e.hidden).length+' marked hidden · originals retained':'Waiting for feed observations';
    const nodes=updates.map(feedCard);
    if(refreshes.length) {
      const group=make('details','panel refresh-group');
      group.open=!!$('routine-refreshes')?.open;group.id='routine-refreshes';
      group.append(make('summary','',refreshes.length+' routine source refreshes · latest '+time(observed(refreshes[0]))));
      const originals=make('div','feed-list');originals.append(...refreshes.map(feedCard));group.append(originals);nodes.push(group);
    }
    replace('feed-list',nodes.length?nodes:[empty('No matching feed entries. Try a broader search or include hidden entries.')]);
  }
  function renderSources() {
    replace('source-list',arr(state&&state.sources).length?state.sources.map(s=>{const c=make('article','source-card'),top=make('div','card-top');top.append(make('h3','',label(s)),badge(status(s)));c.append(top,meta([['Path',s.path],['Version',s.sha],['Observed',time(observed(s))]]));if(s.error)c.append(make('p','source-error',s.error));if(sourceURL(s))c.append(link('Open original source ↗',sourceURL(s)));c.append(raw(s,'Inspect source envelope'));return c;}):[empty('No source observations have been read.')]);
  }
  function render() {
    renderFocus();renderFleet();renderResources();renderTools();renderAccess();renderBudgets();renderFeed();renderSources();
    $('nav-fleet').textContent=arr(state.sessions).length;$('nav-resources').textContent=arr(state.resources).length;$('nav-tools').textContent=tools.length;$('nav-feed').textContent=arr(state.feed).filter(e=>(!e.hidden||protectedEvent(e))&&!routineRefresh(e)).length;
    $('nav-feed').title='Updates; routine source refreshes are grouped in Feed.';
    $('footer-sources').textContent=arr(state.sources).length+' source observations · '+arr(state.sources).filter(s=>s.error).length+' reporting errors';connectionState();window.dispatchEvent(new CustomEvent('commons-state',{detail:state}));
  }
  function observationTime(key){const a=attempts[key];return a&&pending(a.status)&&a.observed_at?a.observed_at:new Date().toISOString();}
  function saveAttempts(){try{sessionStorage.setItem(attemptKey,JSON.stringify(attempts));}catch(_){}}
  async function fingerprint(payload) {
    if(!globalThis.crypto||!crypto.subtle)return null;
    const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(payload)));return [...new Uint8Array(bytes)].map(x=>x.toString(16).padStart(2,'0')).join('');
  }
  function id(){return globalThis.crypto&&crypto.randomUUID?'cc-'+crypto.randomUUID():'cc-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);}
  function output(target,a,title,message,result,name='') {
    target.hidden=false;target.className='action-output'+(pending(a.status)?' pending':/failed|error|rejected/i.test(a.status)?' failed':'');
    target.replaceChildren(make('h3','',title),make('span','operation-id',a.id),make('p','',message));
    if(result!==undefined) {
      const sealed=/credential|secret|vault/i.test(name)&&name!=='credential_references';
      const safe=sealed?{status:a.status,operation_id:a.id,note:'Sealed retrieval output is not rendered. Consume the envelope directly in the requesting runtime using its ephemeral private key.'}:clean(result);
      target.append(make('pre','',JSON.stringify(safe,null,2)));
    }
    const buttons=make('div','button-row');buttons.append(button('Copy operation ID',async()=>{try{await navigator.clipboard.writeText(a.id);showToast('Operation ID copied.');}catch(_){showToast('Copy the displayed operation ID manually.');}},'button button-small button-quiet'),button('Refresh operation state',()=>refresh(true),'button button-small button-quiet'));target.append(buttons);
  }
  async function mutate(key,path,payload,target,name='',onReceipt=null,onConflict=null) {
    const fp=await fingerprint(payload);let a=attempts[key];
    if(a&&pending(a.status)&&(fp===null||a.fingerprint!==fp)){output(target,a,'Previous outcome still uncertain','Reconcile the displayed operation before changing its request. Restore the original arguments to retry with the same operation ID.');return false;}
    if(!a||terminal(a.status))a={id:id(),fingerprint:fp,status:'submitting',path,started_at:new Date().toISOString(),observed_at:first(payload.session&&payload.session.observed_at,payload.budget&&payload.budget.observed_at)};
    attempts[key]=a;a.status='submitting';saveAttempts();output(target,a,'Request in flight','The operation ID is retained. No automatic mutation retry will occur.');
    try {
      const {body,httpStatus}=await request(path,'POST',{...payload,operation_id:a.id});
      const reported=str(first(body.status,body.operation&&body.operation.status,body.result&&body.result.status,''));
      a.status=httpStatus===202||pending(reported)?reported||'accepted':terminal(reported)?reported:'uncertain';saveAttempts();
      output(target,a,pending(a.status)?'Request accepted; completion not established':/fail|error|reject/i.test(a.status)?'Operation reported a failure':'Response received',pending(a.status)?'Inspect the operation history. If a manual retry is needed, submit unchanged arguments; the same operation ID will be reused.':'The server response is below. The operation history carries the actual execution status.',body,name);
      if(typeof onReceipt==='function'){
        try{await onReceipt(body);}catch(_){showToast('Response received. Inspect the receipt for the current assignment.');}
      }
      await refresh(false,true);return !pending(a.status)&&!/fail|error|reject/i.test(a.status);
    } catch(e) {a.status=e.uncertain?'uncertain':'failed';saveAttempts();output(target,a,e.uncertain?'Outcome uncertain':'Request rejected',e.message+(e.uncertain?' Do not assume failure or issue a replacement operation. Inspect provider state; unchanged manual retries retain this operation ID.':''),e.body,name);if(e.workRevisionConflict&&typeof onConflict==='function')onConflict(e.body.current_work);return false;}
  }
  function form(title,description,fields,callback) {
    dialogSpec={fields,callback};$('dialog-title').textContent=title;$('dialog-description').textContent=description;$('dialog-output').hidden=true;$('dialog-submit').disabled=false;
    replace('dialog-fields',fields.map(f=>{const w=make('div','form-field'),l=make('label','',f.label),n=make(f.multiline?'textarea':'input');n.id='field-'+f.key;n.name=f.key;if(!f.multiline)n.type=f.type||'text';if(f.required)n.required=true;if(f.type==='number'){n.step='any';n.min='0';}n.value=f.value??'';if(f.placeholder)n.placeholder=f.placeholder;l.htmlFor=n.id;w.append(l,n);return w;}));
    $('form-dialog').showModal();
  }
  const field=(key,label,value='',extra={})=>({key,label,value,...extra});
  function focusForm(){form('Set the current focus','A shared objective and one concrete next action.',[field('objective','Objective',state&&state.focus&&state.focus.objective,{required:true,multiline:true}),field('next_action','Next useful action',state&&state.focus&&state.focus.next_action,{multiline:true})],v=>mutate('focus','/api/focus',v,$('dialog-output')));}
  function sessionForm(s={}){form('Record an existing session','This records a session/VM and its existing URL. It does not create, restart, or message a native session.',[field('id','Stable session ID',s.id,{required:true}),field('label','Label',s.label,{required:true}),field('url','Existing session URL',s.url),field('provider','Provider',s.provider),field('cpu','CPU',s.cpu),field('ram_gib','RAM (GiB)',s.ram_gib,{type:'number'}),field('gpu','GPU',s.gpu),field('workspace','Workspace or artifact route',s.workspace),field('status','Observed status',s.status||'unknown'),field('objective','Current objective',s.objective,{multiline:true})],v=>{if(v.url&&!safeURL(v.url))throw new Error('Use an existing HTTP, HTTPS, or Codex URL.');v.ram_gib=v.ram_gib===''?null:Number(v.ram_gib);v.observed_at=observationTime('session:'+v.id);return mutate('session:'+v.id,'/api/sessions',{session:v},$('dialog-output'));});}
  function runtimeForm(){form('Connect an existing gateway','Register an existing runtime route. Service account metadata alone is not a gateway. No runtime is launched.',[field('id','Runtime ID','',{required:true}),field('label','Runtime label','',{required:true}),field('gateway_url','Existing gateway URL','',{required:true})],v=>{const url=safeURL(v.gateway_url);if(!url||!/^https?:/.test(url))throw new Error('Use an HTTP or HTTPS gateway URL.');return mutate('runtime:'+v.id,'/api/runtimes',{runtime:v},$('dialog-output'));});}
  function budgetForm(){form('Record a budget or quota observation','Measurements stay in their source units. This does not spend, transfer, or allocate provider funds.',[field('id','Observation ID','',{required:true}),field('label','Label','',{required:true}),field('kind','Kind (quota, budget, spend, cash_balance)','quota',{required:true}),field('limit','Limit','',{type:'number'}),field('used','Used','',{type:'number'}),field('balance','Balance (cash_balance only)','',{type:'number'}),field('remaining','Reported remaining','',{type:'number'}),field('committed','Committed','',{type:'number'}),field('unit','Unit (USD, credits, tokens…)','',{required:true}),field('period','Period'),field('source_url','Source URL')],v=>{['limit','used','balance','remaining','committed'].forEach(k=>v[k]=v[k]===''?null:Number(v[k]));v.observed_at=observationTime('budget:'+v.id);return mutate('budget:'+v.id,'/api/budgets',{budget:v},$('dialog-output'));});}
  function jannyForm(){form('Assign an existing peer','This records limited maintenance responsibility, never exclusive access. No model or background service is created.',[field('peer','Existing peer ID',state&&state.janny&&state.janny.peer,{required:true})],v=>mutate('janny','/api/janny',v,$('dialog-output')));}
  function moderationForm(e){form(e.hidden?'Restore original entry':'Hide from default feed','The original is retained. Use content/evidence criteria; keep genuine failures and useful unfavorable findings visible.',[field('reason','Reason and supporting evidence',e.hidden?'Restore to default view':'',{required:true,multiline:true})],v=>mutate('moderation:'+e.id,'/api/feed/moderate',{event_id:e.id,hidden:!e.hidden,reason:v.reason,peer:str(first(state&&state.janny&&state.janny.peer,'Owner panel'))},$('dialog-output')));}
  function schemaTemplate(schema){const out={};Object.entries(schema.properties||{}).forEach(([key,p])=>{if(p.default!==undefined)out[key]=p.default;else if(arr(schema.required).includes(key))out[key]=p.type==='number'||p.type==='integer'?0:p.type==='boolean'?false:p.type==='array'?[]:p.type==='object'?{}:'';});return out;}
  function validateArgs(value,schema){if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('Arguments must be a JSON object.');arr(schema.required).forEach(k=>{if(!(k in value))throw new Error('Required argument missing: '+k);});Object.entries(value).forEach(([k,v])=>{const p=schema.properties&&schema.properties[k];if(!p)return;const type=p.type;if(typeof type!=='string')return;if(type==='object'&&(v===null||typeof v!=='object'||Array.isArray(v)))throw new Error(k+' must be an object.');if(type==='array'&&!Array.isArray(v))throw new Error(k+' must be an array.');if(['string','number','boolean'].includes(type)&&typeof v!==type)throw new Error(k+' must be '+type+'.');if(type==='integer'&&!Number.isInteger(v))throw new Error(k+' must be an integer.');});}
  $('tool-form').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;const t=tools.find(x=>toolKey(x)===selectedKey);if(!t)return;let args;try{args=JSON.parse($('tool-arguments').value);validateArgs(args,t.schema);$('tool-validation').hidden=true;}catch(error){$('tool-validation').textContent=error.message;$('tool-validation').hidden=false;return;}
    busy=true;$('run-tool').disabled=true;try{await mutate('tool:'+selectedKey,'/api/tools/call',{runtime_id:t.runtime_id,name:t.name,arguments:args},$('tool-output'),t.name);}finally{busy=false;$('run-tool').disabled=false;const a=attempts['tool:'+selectedKey];$('tool-operation-hint').textContent=a?a.id+' · '+a.status:'Operation ID unavailable';$('run-tool').textContent=a&&pending(a.status)?'Retry unchanged request':'Call tool →';}});
  $('tool-template').addEventListener('click',()=>{const t=tools.find(x=>toolKey(x)===selectedKey);if(t&&!busy)$('tool-arguments').value=JSON.stringify(schemaTemplate(t.schema),null,2);});
  $('record-form').addEventListener('submit',async e=>{e.preventDefault();if(!dialogSpec)return;$('dialog-submit').disabled=true;try{const values=Object.fromEntries(dialogSpec.fields.map(f=>[f.key,$('field-'+f.key).value]));await dialogSpec.callback(values);}catch(error){$('dialog-output').hidden=false;$('dialog-output').className='action-output failed';$('dialog-output').replaceChildren(make('p','',error.message));}finally{$('dialog-submit').disabled=false;}});
  document.querySelectorAll('[data-view]').forEach(n=>n.addEventListener('click',()=>navigate(n.dataset.view)));window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));
  $('refresh-button').addEventListener('click',()=>refresh(true));$('reload-tools').addEventListener('click',reloadTools);
  ['edit-focus','focus-edit-inline'].forEach(x=>$(x).addEventListener('click',focusForm));$('add-session').addEventListener('click',()=>sessionForm());$('add-budget').addEventListener('click',budgetForm);$('assign-janny').addEventListener('click',jannyForm);
  $('resource-search').addEventListener('input',renderResources);$('resource-kind').addEventListener('change',renderResources);$('tool-search').addEventListener('input',renderTools);$('feed-search').addEventListener('input',renderFeed);$('show-hidden').addEventListener('change',renderFeed);$('show-refreshes').addEventListener('change',renderFeed);
  ['vault-references','vault-sealed'].forEach((id,i)=>$(id).addEventListener('click',()=>{const t=tools.find(t=>t.name===(i?'credential_retrieve_sealed':'credential_references'));if(t){$('tool-search').value='';chooseTool(t);navigate('tools');}}));
  ['source-button','resources-source-button'].forEach(id=>$(id).addEventListener('click',()=>{$('source-dialog').showModal();renderSources();}));$('close-sources').addEventListener('click',()=>$('source-dialog').close());
  ['close-dialog','cancel-dialog'].forEach(id=>$(id).addEventListener('click',()=>$('form-dialog').close()));
  $('view-fleet').querySelector('.page-heading').append(button('Connect gateway +',runtimeForm,'button button-quiet'));
  window.addEventListener('unhandledrejection',event=>{syncError='Client action error: '+str(event.reason&&event.reason.message||event.reason);connectionState();});
  window.CommonsPanel={
    getState:()=>state,getTools:()=>tools,request,navigate,showToast,
    updateWork:(key,payload,target,onConflict=null)=>mutate(key,'/api/work/item',payload,target,'',null,onConflict),
    callTool:(key,name,args,target,runtime='shared-equipment',options={})=>mutate(key,'/api/tools/call',
      {runtime_id:runtime,name,arguments:args,...(options.swarm===undefined?{}:{swarm:options.swarm})},target,name,options.onReceipt),
    openTool:(name,args={},runtime='shared-equipment')=>{if(busy){showToast('A tool operation is still in flight.');return false;}const t=tools.find(x=>x.name===name&&x.runtime_id===runtime);if(!t){showToast('This tool is not exposed by the selected gateway.');return false;}chooseTool(t);$('tool-arguments').value=JSON.stringify(args,null,2);$('tool-search').value='';renderTools();navigate('tools');return true;}
  };
  navigate(location.hash.slice(1));renderFocus();renderResources();renderTools();renderAccess();renderBudgets();renderFeed();refresh();
  setInterval(()=>{connectionState();if(!document.hidden)refresh();},30000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){renderPublicationAdmission();if(!lastSync||Date.now()-lastSync>30000)refresh();}});
})();
