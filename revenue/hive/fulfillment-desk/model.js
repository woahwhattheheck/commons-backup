/* Parcel: an offline partner fulfillment workspace. No network calls. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Parcel = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const VERSION = 1;
  const CATALOG = Object.freeze([
    {id:'client-intake', name:'Client intake', tag:'NEW BUSINESS', description:'Turn a new service enquiry into a customer record, a job and a tracked task list.', scope:'One intake form, one customer/job mapping, task checklist and notification outbox.', service:'New client enquiry',tasks:['Review intake details and contact preferences','Confirm service scope and next step','Complete client onboarding handoff']},
    {id:'quote-request', name:'Quote request', tag:'SALES HANDOFF', description:'Capture a quote enquiry with service details and keep the follow-up in one job.', scope:'One quote-request form, customer deduplication, quote-follow-up job and notification outbox.', service:'Quote requested',tasks:['Review service details for quote','Prepare and send quote using the chosen channel','Record quote follow-up outcome']},
    {id:'service-request', name:'Service request', tag:'CLIENT OPERATIONS', description:'Route an existing client’s service request into a new tracked job without duplicating the customer.', scope:'One service-request form, existing-customer matching, service job and notification outbox.', service:'Service requested',tasks:['Triage requested service','Assign service owner and confirm timing','Complete work and record follow-up']}
  ]);
  const CHECKLIST = Object.freeze([
    {id:'brief', label:'Client brief and fixed scope recorded'},
    {id:'mapping', label:'Source fields mapped with a synthetic example'},
    {id:'installed', label:'Runner installed in the intended environment'},
    {id:'retry', label:'Same intake retried; customer and job remain single'},
    {id:'handoff', label:'Client walkthrough and support route delivered'}
  ]);
  const STAGES = ['draft','building','installed','support','archived'];
  const DEFAULT_MAPPING = {name:'name',email:'email',phone:'phone',address:'address',service:'service',preferred_date:'preferred_date',notes:'notes'};
  const clone = x => JSON.parse(JSON.stringify(x));
  const own = (o,k) => Object.prototype.hasOwnProperty.call(o,k);
  function record(x, label) {
    if (!x || typeof x !== 'object' || Array.isArray(x)) throw Error(label+' must be an object.');
    return x;
  }
  function text(x, label, max=2000, required=false) {
    if (typeof x !== 'string' || x.length > max) throw Error(label+' must be text of at most '+max+' characters.');
    const s=x.trim(); if (required && !s) throw Error(label+' is required.'); return s;
  }
  function integer(x, label, min, max) {
    if (!Number.isSafeInteger(x) || x < min || x > max) throw Error(label+' is out of range.');
    return x;
  }
  function iso(x) {
    if (typeof x !== 'string' || !/^\d{4}-\d\d-\d\dT/.test(x) || !Number.isFinite(Date.parse(x))) throw Error('Invalid saved date.');
    return x;
  }
  function uid() {
    if (typeof globalThis.crypto?.randomUUID === 'function') return 'order-'+globalThis.crypto.randomUUID();
    return 'order-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,12);
  }
  function empty(now=new Date().toISOString()) { return {version:VERSION, revision:0, updatedAt:iso(now), orders:[]}; }
  function dollars(value) {
    if (typeof value !== 'string' || !/^\d{1,7}(?:\.\d{1,2})?$/.test(value.trim())) throw Error('Use a non-negative dollar amount with at most two decimals.');
    const [a,b='']=value.trim().split('.'); return Number(a)*100+Number(b.padEnd(2,'0'));
  }
  function money(cents) { return '$'+(integer(cents,'Amount',0,199999999800)/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
  function mapping(value) {
    record(value,'Field mapping'); const result={};
    for (const k of Object.keys(DEFAULT_MAPPING)) result[k]=text(value[k],k+' source field',80,true);
    if (new Set(Object.values(result)).size!==Object.keys(result).length) throw Error('Each source field must map to one destination.');
    for (const v of Object.values(result)) if (['__proto__','prototype','constructor'].includes(v)) throw Error('Use ordinary source-field names.');
    return result;
  }
  function validateOrder(raw) {
    record(raw,'Order');
    const o={}; o.id=text(raw.id,'Order ID',100,true);
    if (!/^[A-Za-z0-9_-]+$/.test(o.id)) throw Error('Invalid order ID.');
    o.revision=integer(raw.revision,'Order revision',1,1000000000);
    o.specRevision=integer(raw.specRevision,'Specification revision',1,o.revision);
    for (const key of ['agency','client','title']) o[key]=text(raw[key],key,160,true);
    o.support=text(raw.support,'Support route',300);
    o.scope=text(raw.scope,'Scope',6000); o.notes=text(raw.notes,'Notes',10000);
    o.workflowId=text(raw.workflowId,'Workflow',80,true);
    if (!CATALOG.some(x=>x.id===o.workflowId)) throw Error('Unknown workflow preset.');
    o.stage=text(raw.stage,'Stage',30,true); if (!STAGES.includes(o.stage)) throw Error('Unknown stage.');
    o.brand=text(raw.brand,'Brand color',7,true); if (!/^#[0-9a-fA-F]{6}$/.test(o.brand)) throw Error('Use a six-digit brand color.');
    o.mapping=mapping(raw.mapping);
    o.setupCents=integer(raw.setupCents,'Setup price',0,999999999);
    o.monthlyCents=integer(raw.monthlyCents,'Monthly support price',0,999999999);
    o.quantity=integer(raw.quantity,'Install count',1,100);
    if (typeof raw.includeSupport!=='boolean') throw Error('Support choice must be true or false.');
    o.includeSupport=raw.includeSupport; o.createdAt=iso(raw.createdAt); o.updatedAt=iso(raw.updatedAt);
    record(raw.checklist,'Checklist'); o.checklist={};
    for (const c of CHECKLIST) {
      const v=record(raw.checklist[c.id],'Checklist entry');
      if (typeof v.done!=='boolean') throw Error('Checklist state must be true or false.');
      o.checklist[c.id]={done:v.done,note:text(v.note,'Checklist note',2000),specRevision:integer(v.specRevision,'Checklist specification revision',1,o.specRevision),at:v.at===null?null:iso(v.at)};
    }
    if (!Array.isArray(raw.history)||raw.history.length>200) throw Error('Invalid order history.');
    o.history=raw.history.map(e=>({at:iso(e.at),action:text(e.action,'History action',300,true),revision:integer(e.revision,'History revision',1,o.revision)}));
    return o;
  }
  function validateState(raw) {
    record(raw,'Workspace'); if (raw.version!==VERSION) throw Error('Unsupported workspace version.');
    if (!Array.isArray(raw.orders)||raw.orders.length>1000) throw Error('A workspace supports up to 1,000 orders.');
    const orders=raw.orders.map(validateOrder);
    if (new Set(orders.map(o=>o.id)).size!==orders.length) throw Error('Workspace contains duplicate order IDs.');
    return {version:VERSION,revision:integer(raw.revision,'Workspace revision',0,1000000000),updatedAt:iso(raw.updatedAt),orders};
  }
  function newOrder(fields={}, now=new Date().toISOString(), id=uid()) {
    const preset=CATALOG.find(x=>x.id===(fields.workflowId||CATALOG[0].id));
    if (!preset) throw Error('Unknown workflow preset.');
    const checklist=Object.fromEntries(CHECKLIST.map(c=>[c.id,{done:false,note:'',specRevision:1,at:null}]));
    return validateOrder({id, revision:1,specRevision:1,agency:'Your agency',client:'New client',title:preset.name,
      support:'',scope:preset.scope,notes:'',workflowId:preset.id,stage:'draft',brand:'#315c4b',
      mapping:clone(DEFAULT_MAPPING),setupCents:90000,monthlyCents:29900,includeSupport:false,quantity:1,
      ...fields,id,revision:1,specRevision:1,createdAt:now,updatedAt:now,checklist,history:[{at:now,action:'Brief created',revision:1}]});
  }
  function addOrder(state, order, now=new Date().toISOString()) {
    const next=validateState(state), o=validateOrder(order);
    if(next.orders.some(x=>x.id===o.id)) throw Error('Order ID already exists.');
    next.orders.unshift(o);next.revision++;next.updatedAt=iso(now);return validateState(next);
  }
  function find(state,id) { const o=state.orders.find(x=>x.id===id);if(!o) throw Error('Order not found.');return o; }
  function signature(o) { return JSON.stringify([o.agency,o.client,o.title,o.workflowId,o.scope,o.support,o.brand,Object.entries(o.mapping).sort()]); }
  function updateOrder(state,id,patch,expectedRevision,now=new Date().toISOString()) {
    const next=validateState(state), old=find(next,id);
    if(old.revision!==expectedRevision) throw Error('This order changed. Reload before saving; your draft has not been applied.');
    record(patch,'Order changes');
    const allowed=['agency','client','title','support','scope','notes','workflowId','stage','brand','mapping','setupCents','monthlyCents','includeSupport','quantity'];
    const merged=clone(old);for(const k of allowed) if(own(patch,k)) merged[k]=clone(patch[k]);
    merged.revision++; merged.updatedAt=iso(now);
    // Validate before comparing specifications or changing recorded checkpoints.
    let checked=validateOrder(merged);
    const changed=signature(old)!==signature(checked);
    if(changed) checked.specRevision++;
    checked.history=[...old.history,{at:now,action:changed?'Specification changed; earlier installation checks are stale':'Brief updated',revision:checked.revision}].slice(-200);
    next.orders[next.orders.findIndex(x=>x.id===id)]=validateOrder(checked);
    next.revision++;next.updatedAt=now;return validateState(next);
  }
  function checkItem(state,id,item,done,note,expectedRevision,now=new Date().toISOString()) {
    const next=validateState(state), o=find(next,id);
    if(o.revision!==expectedRevision) throw Error('This order changed. Reload before saving the checklist.');
    if(!CHECKLIST.some(x=>x.id===item)||typeof done!=='boolean') throw Error('Invalid checklist update.');
    o.revision++;o.updatedAt=iso(now);o.checklist[item]={done,note:text(note,'Checklist note',2000),specRevision:o.specRevision,at:done?now:null};
    o.history=[...o.history,{at:now,action:CHECKLIST.find(x=>x.id===item).label+(done?' — recorded':' — reopened'),revision:o.revision}].slice(-200);
    next.revision++;next.updatedAt=now;return validateState(next);
  }
  function removeOrder(state,id,expectedRevision,now=new Date().toISOString()) {
    const next=validateState(state);if(find(next,id).revision!==expectedRevision) throw Error('This order changed. Reload before removing it.');
    next.orders=next.orders.filter(o=>o.id!==id);next.revision++;next.updatedAt=iso(now);return next;
  }
  function progress(order) {
    const o=validateOrder(order);const items=CHECKLIST.map(c=>({...c,...o.checklist[c.id],current:o.checklist[c.id].specRevision===o.specRevision}));
    return {done:items.filter(x=>x.done&&x.current).length,total:items.length,items,installed:o.checklist.installed.done&&o.checklist.installed.specRevision===o.specRevision};
  }
  function quote(order) {
    const o=validateOrder(order),setup=o.setupCents*o.quantity,monthly=o.includeSupport?o.monthlyCents*o.quantity:0;
    return {setup,monthly,firstMonth:setup+monthly,currency:'USD',taxIncluded:false,paymentRecorded:false};
  }
  function csvCell(x) { let v=String(x);if(/^[\s]*[=+@-]/.test(v)) v="'"+v;return '"'+v.replace(/"/g,'""')+'"'; }
  function exportCSV(state) {
    const s=validateState(state), rows=[['Order','Agency','Client','Workflow','Stage (recorded)','Setup USD','Monthly USD','Current checks','Installation recorded']];
    for(const o of s.orders){const q=quote(o),p=progress(o);rows.push([o.id,o.agency,o.client,CATALOG.find(x=>x.id===o.workflowId).name,o.stage,(q.setup/100).toFixed(2),(q.monthly/100).toFixed(2),p.done+'/'+p.total,p.installed?'Yes':'No']);}
    return rows.map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';
  }
  function deployment(order) {
    const o=validateOrder(order),preset=CATALOG.find(x=>x.id===o.workflowId),p=progress(o);
    const sample={};
    const values={name:'Example Client',email:'example@example.invalid',phone:'555-0100',address:'Synthetic service address',service:preset.service,preferred_date:'',notes:'Synthetic installation check. No customer data.'};
    for(const [target,source] of Object.entries(o.mapping)) sample[source]=values[target];
    return {format:'parcel.intake-handoff',version:1,orderId:o.id,specRevision:o.specRevision,agency:o.agency,client:o.client,title:o.title,support:o.support,brand:o.brand,
      preset:o.workflowId,scope:o.scope,fieldMapping:clone(o.mapping),tasks:clone(preset.tasks),
      runner:{project:'woahwhattheheck/commons',path:'revenue/hive/intake-crm-workflow',contract:'POST /api/intakes',remoteEffects:'Remote receiver must deduplicate by Idempotency-Key to avoid duplicate effects.'},
      exampleIntake:{id:o.id+'-smoke-v'+o.specRevision,payload:sample},
      recordedInstallation:p.installed,checklist:clone(p.items),quote:quote(o)};
  }
  function handoff(order) {
    const o=validateOrder(order),q=quote(o),p=progress(o);
    const literal=s=>String(s).replace(/[\\`*_{}\[\]<>#]/g,'\\$&').replace(/\r/g,'');
    return '# '+literal(o.agency)+' — '+literal(o.title)+'\n\n'+
      'Client: '+literal(o.client)+'\n\nOrder: '+o.id+' · Specification '+o.specRevision+'\n\n'+
      '## Working scope\n\n'+literal(o.scope)+'\n\n'+
      '## Proposed pricing (USD)\n\nSetup: '+money(q.setup)+'\n\nMonthly support: '+money(q.monthly)+'\n\nFirst month: '+money(q.firstMonth)+' before any applicable tax. This is a proposal, not a payment receipt.\n\n'+
      '## Installation record\n\nRecorded stage: '+o.stage+'. Current specification checks: '+p.done+'/'+p.total+'.\n\n'+
      p.items.map(c=>'- ['+(c.done&&c.current?'x':' ')+'] '+c.label+(c.done&&!c.current?' (earlier specification; recheck)':'')+(c.note?' — '+literal(c.note):'')).join('\n')+'\n\n'+
      '## Support\n\n'+literal(o.support||'Support route not yet recorded.')+'\n\n'+
      '## Operator notes\n\n'+literal(o.notes||'No notes.')+'\n\n'+
      '## Delivery boundary\n\nThe deployment handoff describes one of three intake presets on the existing intake-to-CRM runner. Generating files does not install a service, contact a customer, collect payment, or establish third-party delivery. Keep this client handoff and all real intake data in the intended private workspace.\n';
  }
  return {VERSION,CATALOG,CHECKLIST,STAGES,DEFAULT_MAPPING,empty,dollars,money,validateOrder,validateState,newOrder,addOrder,find,updateOrder,checkItem,removeOrder,progress,quote,exportCSV,deployment,handoff};
});
