'use strict';
const q = selector => document.querySelector(selector);
const params = new URLSearchParams(location.search);
const portal = Boolean(params.get('event') && params.get('exhibitor'));
const state = {events: [], eventId: params.get('event'), exId: params.get('exhibitor'), detail: null};
function el(tag, value, className) {
  const node = document.createElement(tag);
  if (value !== undefined && value !== null) node.textContent = value;
  if (className) node.className = className;
  return node;
}
function notice(message = '', error = false) { q('#notice').textContent = message; q('#notice').className = error ? 'error' : ''; }
async function api(path, data) {
  const response = await fetch('/api/events' + path, data === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request did not complete');
  return result;
}
function action(label, fn, style = '') {
  const button = el('button', label, style); button.type = 'button';
  button.addEventListener('click', async () => {
    button.disabled = true;
    try { notice(); await fn(); } catch (error) { notice(error.message, true); }
    finally { button.disabled = false; }
  });
  return button;
}
function download(label, path) {
  const a = el('a', label, 'button quiet small');
  a.href = '/api/events/' + state.eventId + path; a.download = ''; return a;
}
function localTime(value) {
  const d = new Date(value); if (Number.isNaN(d.getTime())) return '';
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0,16);
}
function friendlyTime(value) { return new Date(value).toLocaleString([], {dateStyle:'medium', timeStyle:'short'}) + ' (' + Intl.DateTimeFormat().resolvedOptions().timeZone + ')'; }
function field(form, name, label, value = '', type = 'text', wide = false, required = true) {
  const wrapper = el('label', label, wide ? 'wide' : '');
  const input = document.createElement(type === 'textarea' ? 'textarea' : 'input');
  if (type !== 'textarea') input.type = type;
  input.name = name; input.value = value; input.required = required;
  if (type === 'number') { input.min = '0'; input.step = name.endsWith('_m') ? '.01' : '1'; }
  wrapper.append(input); form.append(wrapper); return input;
}
function submit(form, label, fn) {
  const button = el('button', label); button.type = 'submit'; form.append(button);
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (!form.reportValidity()) return;
    button.disabled = true;
    try { notice(); await fn(Object.fromEntries(new FormData(form))); } catch(error) { notice(error.message, true); }
    finally { button.disabled = false; }
  });
}
async function load() {
  if (portal) {
    q('#sidebar').classList.add('hidden'); q('#app').classList.add('portal');
  } else {
    state.events = await api('');
    if (!state.eventId && state.events.length) state.eventId = state.events[0].id;
    renderSidebar();
  }
  if (!state.eventId) { renderNew(); return; }
  state.detail = await api('/' + state.eventId + (portal ? '/exhibitors/' + state.exId : ''));
  if (!state.detail.exhibitors.some(x => x.id === state.exId)) state.exId = null;
  render();
}
function renderSidebar() {
  const box = q('#events'); box.replaceChildren();
  for (const event of state.events) box.append(action(event.name, async () => {
    state.eventId = event.id; state.exId = null; await load();
  }, 'event-button' + (event.id === state.eventId ? ' selected' : '')));
  if (!state.events.length) box.append(el('p', 'Create your first event to start intake.', 'muted'));
}
function eventForm(existing) {
  const form = el('form'); const fields = el('div', null, 'fields'); form.append(fields);
  field(fields,'name','Event name',existing?.name || '');
  field(fields,'venue','Venue',existing?.venue || '');
  field(fields,'starts_at','Event begins · your time zone',existing ? localTime(existing.starts_at) : '', 'datetime-local');
  field(fields,'deadline_at','Materials due · your time zone',existing ? localTime(existing.deadline_at) : '', 'datetime-local');
  field(fields,'brief','Current exhibitor instructions',existing?.brief || '', 'textarea', true, false);
  submit(form, existing ? 'Save event information' : 'Create event', async data => {
    data.starts_at = new Date(data.starts_at).toISOString(); data.deadline_at = new Date(data.deadline_at).toISOString();
    if(existing) data.expected_revision = existing.revision;
    const result = await api(existing ? '/' + existing.id : '', data);
    state.eventId = result.id; await load(); notice('Event information saved. New reminder and calendar downloads use this revision.');
  });
  return form;
}
function renderNew() {
  const card = el('section', null, 'card'); card.append(el('div','GET STARTED','eyebrow'),el('h2','Create an event'), eventForm(null));
  q('#workspace').replaceChildren(card);
}
function render() {
  const workspace = q('#workspace'); workspace.replaceChildren();
  const {event, exhibitors} = state.detail;
  const head = el('section', null, 'card');
  head.append(el('div', portal ? 'EXHIBITOR PORTAL · CURRENT INFORMATION' : 'EVENT INFORMATION', 'eyebrow'),el('h2',event.name));
  head.append(el('p',event.venue),el('p','Materials due: ' + friendlyTime(event.deadline_at)),el('p','Event begins: ' + friendlyTime(event.starts_at),'muted'));
  if (new Date(event.deadline_at) < new Date()) head.append(el('span','Materials deadline has passed','badge pending'));
  head.append(el('p',event.brief,'brief'));
  const exports = el('div',null,'row actions'); exports.append(download('Calendar file','/deadlines.ics'));
  if (!portal) exports.append(download('Floor-plan CSV','/floor-plan.csv'),download('Complete event packet','/packet.zip'));
  head.append(exports);
  if (!portal) { const settings = el('details'); settings.style.marginTop='20px'; settings.append(el('summary','Edit event and deadline'),eventForm(event)); head.append(settings); }
  workspace.append(head);
  if (!portal) {
    const stats = el('div',null,'stats');
    const values = [[exhibitors.length,'Exhibitors'],[exhibitors.reduce((n,x)=>n+x.changes.filter(c=>c.status==='pending').length,0),'Open changes'],[exhibitors.reduce((n,x)=>n+x.assets.length,0),'Original assets']];
    values.forEach(([n,label])=> { const card=el('div',null,'stat');card.append(el('strong',n),el('span',label));stats.append(card); });
    workspace.append(stats);
  }
  const grid = el('div', null, portal ? '' : 'grid');
  if (!portal) {
    const list = el('section', null, 'card'); list.append(el('h3','Exhibitors'));
    list.append(action('+ Add exhibitor', async()=>{state.exId=null;render();}, 'quiet small'));
    for (const ex of exhibitors) {
      const b = action(ex.company, async()=>{state.exId=ex.id;render();}, 'exhibitor' + (ex.id===state.exId?' active':''));
      b.append(el('span',(ex.booth_code || 'Booth unassigned') + ' · ' + ex.width_m + ' × ' + ex.depth_m + ' m'));
      list.append(b);
    }
    grid.append(list);
  }
  const ex = exhibitors.find(x=>x.id===state.exId);
  const panel = el('section', null, 'card');
  panel.append(el('h2',ex ? ex.company : 'New exhibitor'));
  if (ex) panel.append(el('span','Requirements revision ' + ex.revision,'badge'));
  if (ex && !portal) {
    const a=el('a','Open exhibitor portal');a.href='?event='+event.id+'&exhibitor='+ex.id;a.target='_blank';a.rel='noopener';
    panel.append(el('p'));panel.lastChild.append(a);
  }
  panel.append(exhibitorForm(ex));
  if (ex) {
    panel.append(el('hr'));panel.append(el('h3','Original assets'), assetForm(ex));
    if (!ex.assets.length) panel.append(el('p','No assets uploaded yet.','muted'));
    ex.assets.forEach(asset=> {
      const row=el('div',null,'asset');row.append(download(asset.filename,'/exhibitors/'+ex.id+'/assets/'+asset.id));
      row.append(el('p',asset.kind+' · '+asset.size.toLocaleString()+' bytes','muted'),el('code','SHA-256 '+asset.sha256));panel.append(row);
    });
    panel.append(el('hr'),el('h3','Requirement changes'));
    if (!portal) {const d=el('details');d.append(el('summary','Record a requested change'),exhibitorForm(ex,true));panel.append(d);}
    if (!ex.changes.length) panel.append(el('p','No requested changes.','muted'));
    ex.changes.slice().reverse().forEach(change=>panel.append(changeCard(ex,change)));
    const r=el('div',null,'row actions');r.append(download('Download reminder draft','/exhibitors/'+ex.id+'/reminder.eml'));panel.append(r);
  }
  grid.append(panel);workspace.append(grid);
}
function exhibitorForm(ex, requested = portal) {
  const form=el('form');const fields=el('div',null,'fields');form.append(fields);
  field(fields,'company','Company',ex?.company||'');field(fields,'contact_name','Contact name',ex?.contact_name||'');
  field(fields,'email','Email for reminder drafts',ex?.email||'','email');field(fields,'booth_code','Booth code (blank if unassigned)',ex?.booth_code||'','text',false,false);
  field(fields,'width_m','Booth width · metres',ex?.width_m||'3','number');field(fields,'depth_m','Booth depth · metres',ex?.depth_m||'3','number');
  field(fields,'power_w','Requested power · watts',ex?.power_w??0,'number');
  field(fields,'notes','Equipment, access and loading requirements',ex?.notes||'','textarea',true,false);
  if(requested) field(fields,'reason','What changed and why?','','textarea',true);
  submit(form,requested?'Request requirement change':ex?'Save current requirements':'Add exhibitor', async data=> {
    const path='/'+state.eventId+'/exhibitors';
    if (requested) {
      const reason=data.reason;delete data.reason;
      await api(path+'/'+ex.id+'/changes',{expected_revision:ex.revision,proposed:data,reason});
    } else {
      if(ex) data.expected_revision=ex.revision;
      const result=await api(path+(ex?'/'+ex.id:''),data);state.exId=result.id;
    }
    await load();notice(requested?'Change recorded. The current requirements remain in effect until the request is resolved.':'Exhibitor requirements saved.');
  });
  return form;
}
function assetForm(ex) {
  const form=el('form');const fields=el('div',null,'fields');form.append(fields);
  const file=field(fields,'file','File · up to 8 MiB','','file');field(fields,'kind','Asset description','Logo / booth asset');
  submit(form,'Upload original file',async data=> {
    const selected=file.files[0];if(!selected)throw new Error('Choose an asset file');
    if(selected.size===0||selected.size>8*1024*1024)throw new Error('Choose a file from 1 byte to 8 MiB');
    const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('File could not be read'));reader.readAsDataURL(selected);});
    await api('/'+state.eventId+'/exhibitors/'+ex.id+'/assets',{filename:selected.name,kind:data.kind,base64:encoded});
    await load();notice('Original asset stored. Its byte count and SHA-256 are available beside the download.');
  });return form;
}
function changeCard(ex,change) {
  const box=el('section',null,'change');box.append(el('span',change.status,'badge'+(change.status==='pending'?' pending':'')),el('p',change.reason));
  const differences=Object.keys(change.proposed).filter(k=>change.before[k]!==change.proposed[k]).map(k=>k+': '+change.before[k]+' → '+change.proposed[k]);
  box.append(el('pre',differences.join('\n')));
  if(change.resolution)box.append(el('p','Resolution: '+change.resolution,'muted'));
  if(change.status==='pending'&&!portal) {
    const label=el('label','Resolution note');const input=el('textarea');label.append(input);box.append(label);
    const row=el('div',null,'row actions');
    for(const [decision,title] of [['apply','Apply requested change'],['dismiss','Dismiss request']]) row.append(action(title,async()=> {
      if(!input.value.trim())throw new Error('Add a resolution note');
      await api('/'+state.eventId+'/exhibitors/'+ex.id+'/changes/'+change.id,{decision,resolution:input.value});
      await load();notice(decision==='apply'?'Requested requirements applied. New floor-plan exports include them.':'Change request dismissed; requirements were preserved.');
    },decision==='dismiss'?'quiet':''));box.append(row);
    if(change.base_revision!==ex.revision)box.append(el('p','This request refers to an earlier revision. Dismiss and submit a new request against the current requirements.','muted'));
  }
  return box;
}
q('#refresh').addEventListener('click',()=>load().then(()=>notice('Current saved information loaded.')).catch(error=>notice(error.message,true)));
q('#new-event').addEventListener('click',()=>{state.eventId=null;state.exId=null;renderNew();notice();});
load().catch(error=>{q('#workspace').replaceChildren(el('p','Workspace could not load. Refresh after resolving the error.'));notice(error.message,true);});
