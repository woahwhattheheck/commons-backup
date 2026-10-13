/* Browser controller. Imported text is rendered through textContent/value. */
(function () {
  'use strict';
  const M=window.Parcel, KEY='parcel.workspace.v1', $=id=>document.getElementById(id);
  let state=M.empty(), selected=null, dirty=false, tab='brief', storage=null, corrupt=false;
  try {storage=window.ParcelStorage||window.localStorage;} catch (_) {}
  function notice(message,error=false){$('notice').textContent=message;$('notice').className=error?'error':'';$('notice').hidden=false;}
  function safely(fn){try{return fn();}catch(e){notice(e.message||String(e),true);return null;}}
  function saved(){if(!storage)return null;const s=storage.getItem(KEY);return s===null?null:M.validateState(JSON.parse(s));}
  function load(){try{state=saved()||M.empty();corrupt=false;}catch(e){corrupt=true;notice('Saved data could not be read. It has not been overwritten. Use a known backup or export this working copy. '+e.message,true);}
    $('storage-status').textContent=storage&&!corrupt?'Browser-local workspace':'Memory only — export to keep changes';}
  function persist(next,nextSelected=selected){
    if(storage&&!corrupt){
      let current=null;
      try{current=saved();}catch(e){notice('Browser storage is unavailable. Changes remain in memory; export a workspace file now.',true);storage=null;$('storage-status').textContent='Memory only — export to keep changes';}
      if(storage){
        if(current&&current.revision!==state.revision)throw Error('Another tab changed this workspace. Export your draft, then reload saved data before continuing.');
        try{storage.setItem(KEY,JSON.stringify(next));}catch(e){notice('Browser storage is unavailable. Changes remain in memory; export a workspace file now.',true);storage=null;$('storage-status').textContent='Memory only — export to keep changes';}
      }
    }
    state=next;selected=nextSelected;dirty=false;render();
  }
  function el(tag,cls,value){const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=value;return n;}
  function active(){return M.find(state,selected);}
  function leaveDraft(){return !dirty||window.confirm('Discard unsaved brief changes? Cancel to save or export them first.');}
  function setTab(name){tab=name;for(const t of ['brief','install','delivery']){$(t+'-panel').hidden=t!==name;$('tab-'+t).setAttribute('aria-selected',String(t===name));}if(name==='delivery')$('handoff').textContent=M.handoff(active());}
  function markDirty(){dirty=true;$('save-status').textContent='Unsaved changes';updateTotals();}
  function formPatch(){const f=$('brief-form').elements;return {agency:f.agency.value,client:f.client.value,title:f.title.value,workflowId:f.workflowId.value,stage:f.stage.value,scope:f.scope.value,support:f.support.value,brand:f.brand.value,notes:f.notes.value,setupCents:M.dollars(f.setup.value),monthlyCents:M.dollars(f.monthly.value),quantity:Number(f.quantity.value),includeSupport:f.includeSupport.checked,mapping:Object.fromEntries(Object.keys(M.DEFAULT_MAPPING).map(k=>[k,$('map-'+k).value]))};}
  function updateTotals(){try{const p=formPatch(),q=M.quote({...active(),...p});$('setup-total').textContent=M.money(q.setup);$('monthly-total').textContent=M.money(q.monthly);$('first-total').textContent=M.money(q.firstMonth);}catch(_){$('first-total').textContent='Check price fields';}}
  function download(name,content,type='application/json'){const url=URL.createObjectURL(new Blob([content],{type}));const a=el('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function exportDraft(){let s=state;if(dirty&&selected)s=M.updateOrder(state,selected,formPatch(),active().revision);return JSON.stringify(s,null,2)+'\n';}
  function renderList(){const query=$('search').value.toLowerCase();$('order-count').textContent=state.orders.length;const host=$('orders');host.replaceChildren();for(const o of state.orders){if(![o.client,o.agency,o.title].join(' ').toLowerCase().includes(query))continue;const li=el('li'),b=el('button',o.id===selected?'active':'');b.append(el('strong','',o.title),el('small','',o.client+' · '+o.stage));b.onclick=()=>{if(!leaveDraft())return;selected=o.id;dirty=false;render();};li.append(b);host.append(li);}if(!host.children.length)host.append(el('li','empty',query?'No matching briefs.':'Your first brief starts here.'));}
  function render(){renderList();$('catalog-view').hidden=!!selected;$('workspace').hidden=!selected;if(!selected)return;
    const o=active(),p=M.progress(o),f=$('brief-form').elements;
    $('order-label').textContent=o.agency+' / specification '+o.specRevision;$('order-title').textContent=o.title;$('progress').textContent=p.done+'/'+p.total+' current checks · '+(p.installed?'installation recorded':'installation not recorded');
    for(const k of ['agency','client','title','workflowId','stage','scope','support','brand','notes'])f[k].value=o[k];
    f.setup.value=(o.setupCents/100).toFixed(2);f.monthly.value=(o.monthlyCents/100).toFixed(2);f.quantity.value=o.quantity;f.includeSupport.checked=o.includeSupport;
    for(const k of Object.keys(M.DEFAULT_MAPPING))$('map-'+k).value=o.mapping[k];
    $('save-status').textContent=storage&&!corrupt?'Saved in this browser':'In memory — export to keep';
    const checks=$('checklist');checks.replaceChildren();for(const c of p.items){const row=el('div','check-row'),label=el('label','check-label'),input=el('input');input.type='checkbox';input.checked=c.done&&c.current;input.id='check-'+c.id;label.htmlFor=input.id;label.append(input,el('span','',c.label));const note=el('input');note.type='text';note.maxLength=2000;note.placeholder='Installation location, result or handoff note';note.value=c.note;note.setAttribute('aria-label',c.label+' note');const button=el('button','quiet small','Save note');
      function commit(done){if(dirty){input.checked=c.done&&c.current;notice('Save the brief before recording an installation check, so the check is tied to the right specification.',true);return;}safely(()=>{persist(M.checkItem(state,o.id,c.id,done,note.value,active().revision));notice('Installation record saved.');});}
      input.onchange=()=>commit(input.checked);button.onclick=()=>commit(input.checked);row.append(label,note,el('div','check-meta',c.done&&!c.current?'Earlier specification '+c.specRevision+' — note retained; recheck for this version.':c.at?'Recorded '+new Date(c.at).toLocaleString():'Not yet recorded.'),button);checks.append(row);}
    $('history').replaceChildren(...o.history.slice(-8).reverse().map(h=>el('li','',new Date(h.at).toLocaleString()+' · '+h.action)));
    setTab(tab);updateTotals();
  }
  function start(preset,sample=false){if(!leaveDraft())return;safely(()=>{const fields={workflowId:preset};if(sample)Object.assign(fields,{agency:'Northstar Studio (example)',client:'Alder Services (example)',title:'Client intake · synthetic example',support:'support@example.invalid',notes:'Fictional sample brief. No customer installation or payment.'});const o=M.newOrder(fields);persist(M.addOrder(state,o));selected=o.id;tab='brief';render();notice(sample?'Synthetic example created. All installation checks start unrecorded.':'New brief created. Edit the details and save.');});}
  for(const preset of M.CATALOG){const b=el('button','template');b.append(el('span','eyebrow',preset.tag),el('b','',preset.name),el('p','',preset.description),el('span','arrow','Create brief →'));b.onclick=()=>start(preset.id);$('catalog').append(b);const option=el('option','',preset.name);option.value=preset.id;$('brief-form').elements.workflowId.append(option);}
  for(const stage of M.STAGES){const option=el('option','',stage[0].toUpperCase()+stage.slice(1));option.value=stage;$('brief-form').elements.stage.append(option);}
  for(const key of Object.keys(M.DEFAULT_MAPPING)){const label=el('label','',key[0].toUpperCase()+key.slice(1)),input=el('input');input.id='map-'+key;input.maxLength=80;input.required=true;label.append(input);$('mapping').append(label);}
  $('brief-form').addEventListener('input',markDirty);$('brief-form').addEventListener('change',markDirty);
  $('brief-form').onsubmit=e=>{e.preventDefault();safely(()=>{persist(M.updateOrder(state,selected,formPatch(),active().revision));notice('Brief saved. Exports now use this version.');});};
  $('preset-scope').onclick=()=>{const f=$('brief-form').elements;f.scope.value=M.CATALOG.find(x=>x.id===f.workflowId.value).scope;markDirty();};
  for(const b of document.querySelectorAll('[data-tab]'))b.onclick=()=>setTab(b.dataset.tab);
  $('new').onclick=()=>{if(!leaveDraft())return;selected=null;dirty=false;render();};$('sample').onclick=()=>start('client-intake',true);$('search').oninput=renderList;
  $('backup').onclick=()=>safely(()=>{download('parcel-workspace.json',exportDraft());notice(dirty?'Workspace exported with your unsaved draft; browser storage is unchanged.':'Workspace backup exported. Keep it in your intended private workspace.');});
  $('csv').onclick=()=>safely(()=>download('parcel-orders.csv',M.exportCSV(state),'text/csv;charset=utf-8'));
  $('restore').onclick=()=>{if(leaveDraft())$('restore-file').click();};
  $('restore-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>12000000)throw Error('Import is limited to 12 MB.');const raw=JSON.parse(await file.text());let next;if(raw.format==='parcel.order'&&raw.version===1){const o=M.validateOrder(raw.order);if(state.orders.some(x=>x.id===o.id))throw Error('This order ID is already present. Import a workspace backup to replace it, or remove the existing copy first.');next=M.addOrder(state,o);}else{next=M.validateState(raw);if(state.orders.length&&!window.confirm('Replace the current workspace with this backup? Export your current workspace first to keep both.'))return;next.revision=state.revision+1;next.updatedAt=new Date().toISOString();}persist(next,next.orders[0]?.id||null);notice('Import complete. Imported installation checks are user records, not an independent installation result.');}catch(err){notice(err.message,true);}finally{e.target.value='';}};
  $('duplicate').onclick=()=>{if(!leaveDraft())return;safely(()=>{const old=active(),o=M.newOrder({...old,title:old.title+' (copy)',stage:'draft'});persist(M.addOrder(state,o));selected=o.id;render();notice('Duplicate created with installation checks reset.');});};
  $('delete').onclick=()=>{if(!leaveDraft()||!window.confirm('Remove this brief? Export an editable order file first to keep a copy.'))return;safely(()=>{const old=active(),next=M.removeOrder(state,old.id,old.revision);selected=null;persist(next);notice('Brief removed from this workspace.');});};
  $('reload').onclick=()=>{if(!leaveDraft())return;selected=null;dirty=false;load();render();};
  $('download-handoff').onclick=()=>safely(()=>download(active().id+'-handoff.md',M.handoff(active()),'text/markdown;charset=utf-8'));
  $('download-deployment').onclick=()=>safely(()=>download(active().id+'-deployment.json',JSON.stringify(M.deployment(active()),null,2)+'\n'));
  $('download-order').onclick=()=>safely(()=>download(active().id+'.json',JSON.stringify({format:'parcel.order',version:1,order:active()},null,2)+'\n'));
  $('print').onclick=()=>{$('print-sheet').textContent=M.handoff(active());window.print();};
  window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
  window.addEventListener('storage',e=>{if(e.key===KEY)notice('Another tab changed this workspace. Export any draft, then reload saved data.',true);});
  load();render();
})();
