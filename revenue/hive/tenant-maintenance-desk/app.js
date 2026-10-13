'use strict';
const $ = id => document.getElementById(id);
let state = {properties: [], vendors: [], requests: []};
let selected = '', tenantSelected = '', view = 'queue';
const operations = new Map();
const labels = {new: 'New request', scheduled: 'Scheduled', needs_reschedule: 'Needs replacement', closed: 'Closed'};
function el(tag, value, cls) {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (cls) node.className = cls;
  return node;
}
function tell(message, error = false) {
  $('message').textContent = message;
  $('message').className = error ? 'error' : '';
  $('message').hidden = false;
}
function action(fn, button) {
  return async (...args) => {
    if (button) button.disabled = true;
    try { await fn(...args); }
    catch (err) { tell(err.message || 'Unable to complete this action.', true); }
    finally { if (button) button.disabled = false; }
  };
}
function form(id, fn) {
  const node = $(id), button = node.querySelector('button[type=submit]');
  node.addEventListener('submit', event => { event.preventDefault(); action(fn, button)(); });
}
async function command(data) {
  const key = JSON.stringify(data);
  if (!operations.has(key)) operations.set(key, crypto.randomUUID());
  const response = await fetch('/api/command', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({command: data, operation_id: operations.get(key)})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Unable to save.');
  operations.delete(key);
  return result;
}
function options(id, items, caption, valueKey = 'id', nameKey = 'name') {
  const select = $(id), previous = select.value;
  select.replaceChildren();
  if (caption !== null) select.append(new Option(caption, ''));
  for (const item of items) select.append(new Option(item[nameKey], item[valueKey]));
  if ([...select.options].some(o => o.value === previous)) select.value = previous;
}
function currentHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  const name = params.get('view');
  if (['queue', 'tenant', 'manage'].includes(name)) view = name;
  if (params.get('request')) selected = tenantSelected = params.get('request');
}
function setView(name) {
  view = name;
  for (const item of ['queue', 'tenant', 'manage']) $(item + '-view').hidden = item !== name;
  for (const button of document.querySelectorAll('nav button')) {
    if (button.dataset.view === name) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  }
}
function date(value) { return new Date(value).toLocaleString(); }
function badge(value) { return el('span', labels[value] || value, 'badge ' + value); }
function requestLabel(request) { return `${request.property_name} · ${request.unit} · ${request.description.slice(0, 45)}`; }
async function refresh() {
  const response = await fetch('/api/state', {cache: 'no-store'});
  if (!response.ok) throw new Error('Could not refresh. Your unsent form values have not been submitted.');
  state = await response.json();
  if (!state.requests.some(r => r.id === selected)) selected = state.requests[0]?.id || '';
  if (!state.requests.some(r => r.id === tenantSelected)) tenantSelected = selected;
  options('intake-property', state.properties, 'Choose property');
  options('property-filter', state.properties, 'All properties');
  options('faq-property', state.properties, null);
  options('tenant-lookup', state.requests.map(r => ({id: r.id, name: requestLabel(r)})), null);
  $('tenant-lookup').value = tenantSelected;
  $('open-count').textContent = state.requests.filter(r => r.status !== 'closed').length;
  $('reschedule-count').textContent = state.requests.filter(r => r.status === 'needs_reschedule').length;
  $('scheduled-count').textContent = state.requests.filter(r => r.status === 'scheduled').length;
  renderList(); renderDetail(); renderTenant(); renderVendors(); faqSelection(); setView(view);
}
function renderList() {
  const list = $('request-list'); list.replaceChildren();
  const wanted = $('status-filter').value, prop = $('property-filter').value;
  const items = state.requests.filter(r => (!prop || r.property_id === prop) &&
    (wanted === 'all' || (wanted === 'open' ? r.status !== 'closed' : r.status === wanted)));
  if (!items.length) { list.append(el('p', 'No requests here. Create one or adjust the filters.', 'empty')); return; }
  for (const request of items) {
    const card = el('button', undefined, 'request-card' + (request.id === selected ? ' selected' : ''));
    card.append(badge(request.status), document.createTextNode(' '), badge(request.urgency),
      el('strong', request.description), el('small', request.property_name + ' · ' + request.unit));
    if (request.appointment) card.append(el('small', request.appointment.vendor_name + ' · ' + date(request.appointment.start)));
    card.addEventListener('click', () => { selected = request.id; renderList(); renderDetail(); });
    list.append(card);
  }
}
function requestBody(root, request) {
  root.append(badge(request.status), document.createTextNode(' '), badge(request.urgency),
    el('h2', request.property_name + ' · ' + request.unit), el('p', request.description, 'pre'),
    el('small', 'Request ' + request.id + ' · version ' + request.version, 'detail-id'));
  if (request.urgency === 'emergency') root.append(el('p', 'Emergency flag: this desk is not emergency dispatch. Contact local emergency services or the property emergency contact for immediate danger.', 'notice'));
  if (request.appointment) {
    const a = request.appointment, block = el('div', undefined, 'appointment');
    block.append(el('strong', 'Current appointment'), el('p', a.vendor_name), el('div', date(a.start) + ' – ' + date(a.end)));
    root.append(block);
  } else if (request.status === 'needs_reschedule') root.append(el('p', 'The previous vendor is unavailable. A replacement appointment is needed.', 'notice'));
  else if (request.status !== 'closed') root.append(el('p', 'No appointment has been set yet.', 'muted'));
  if (request.closure) root.append(el('h3', 'Resolution'), el('p', request.closure, 'pre'));
  if (request.photos.length) {
    root.append(el('h3', 'Original photos'));
    const links = el('div', undefined, 'row');
    for (const photo of request.photos) {
      const link = el('a', photo.name); link.href = '/api/photo/' + encodeURIComponent(photo.id); link.download = photo.name;
      links.append(link);
    }
    root.append(links);
  }
}
function history(root, request) {
  root.append(el('hr'), el('h3', 'Request history'));
  const list = el('ol', undefined, 'timeline');
  for (const event of [...request.events].reverse()) {
    const li = el('li', event.message), time = el('time', date(event.occurred_at)); time.dateTime = event.occurred_at;
    li.append(time); list.append(li);
  }
  root.append(list);
}
function field(formNode, id, caption, node) {
  node.id = id; const label = el('label', caption); label.htmlFor = id; formNode.append(label, node); return node;
}
function renderDetail() {
  const root = $('detail'); root.replaceChildren();
  const request = state.requests.find(r => r.id === selected);
  if (!request) { root.append(el('p', 'Select or create a request to see its next step.', 'empty')); return; }
  requestBody(root, request);
  const tenant = el('button', 'Open tenant status');
  tenant.addEventListener('click', () => { tenantSelected = request.id; $('tenant-lookup').value = request.id;
    location.hash = new URLSearchParams({view: 'tenant', request: request.id}); renderTenant(); setView('tenant'); });
  root.append(tenant);
  if (request.status !== 'closed') {
    root.append(el('hr'), el('h3', request.appointment ? 'Replace / reschedule appointment' : 'Schedule a repair'));
    const f = el('form'), vendor = field(f, 'schedule-vendor', 'Available vendor', el('select'));
    vendor.required = true; vendor.append(new Option('Choose vendor', ''));
    for (const v of state.vendors.filter(v => v.available)) vendor.append(new Option(v.name + ' · ' + v.trade, v.id));
    const start = field(f, 'schedule-start', 'Start (your browser’s local time)', el('input')); start.type = 'datetime-local'; start.required = true;
    const end = field(f, 'schedule-end', 'End (your browser’s local time)', el('input')); end.type = 'datetime-local'; end.required = true;
    const reason = field(f, 'schedule-reason', 'Appointment / change note', el('input')); reason.maxLength = 3000;
    reason.value = request.appointment ? 'Appointment replaced' : 'Appointment scheduled'; reason.required = true;
    const save = el('button', 'Save appointment', 'primary'); save.type = 'submit'; f.append(save);
    f.addEventListener('submit', event => {event.preventDefault(); action(async () => {
      await command({type: 'schedule', request_id: request.id, version: request.version, vendor_id: vendor.value,
        start: new Date(start.value).toISOString(), end: new Date(end.value).toISOString(), reason: reason.value});
      await refresh(); tell('Appointment saved. Tenant status is up to date; no message was sent.');
    }, save)();}); root.append(f);
    const closeForm = el('form'); root.append(el('hr'), el('h3', 'Close this request'));
    const closure = field(closeForm, 'closure', 'What was resolved?', el('textarea')); closure.required = true; closure.maxLength = 3000;
    const close = el('button', 'Close request'); close.type = 'submit'; closeForm.append(close);
    closeForm.addEventListener('submit', event => {event.preventDefault(); action(async () => {
      await command({type: 'close', request_id: request.id, version: request.version, closure: closure.value});
      await refresh(); tell('Request closed. The resolution is visible in tenant status.');
    }, close)();}); root.append(closeForm);
  } else {
    const f = el('form'), reason = field(f, 'reopen-reason', 'Reason to reopen', el('input')); reason.required = true; reason.maxLength = 3000;
    const save = el('button', 'Reopen request'); save.type = 'submit'; f.append(save);
    f.addEventListener('submit', event => {event.preventDefault(); action(async () => {
      await command({type: 'reopen', request_id: request.id, version: request.version, reason: reason.value});
      await refresh(); tell('Request reopened. Previous history is retained.');
    }, save)();}); root.append(f);
  }
  history(root, request);
}
function renderTenant() {
  const root = $('tenant-detail'); root.replaceChildren();
  const request = state.requests.find(r => r.id === tenantSelected);
  if (!request) { root.append(el('p', 'No request selected.', 'empty')); $('tenant-faq').textContent = ''; return; }
  requestBody(root, request); history(root, request);
  $('tenant-faq').textContent = state.properties.find(p => p.id === request.property_id)?.faq || 'No property information has been added yet.';
}
function renderVendors() {
  const root = $('vendor-list'); root.replaceChildren();
  if (!state.vendors.length) root.append(el('p', 'Add a vendor to start scheduling.', 'empty'));
  for (const vendor of state.vendors) {
    const box = el('div', undefined, 'vendor'), row = el('div', undefined, 'row');
    row.append(el('strong', vendor.name), badge(vendor.available ? 'available' : 'unavailable'));
    box.append(row, el('p', vendor.trade, 'muted'));
    const bookings = state.requests.filter(r => r.appointment?.vendor_id === vendor.id);
    for (const r of bookings) box.append(el('small', `${r.unit} · ${date(r.appointment.start)} — ${date(r.appointment.end)}`, 'detail-id'));
    const button = el('button', vendor.available ? 'Mark unavailable' : 'Mark available');
    button.addEventListener('click', action(async () => {
      const result = await command({type: 'vendor_availability', vendor_id: vendor.id, available: !vendor.available});
      await refresh(); tell(`Availability updated. ${result.affected_requests.length} request(s) need a replacement.`);
    }, button)); box.append(button); root.append(box);
  }
}
function faqSelection() { $('faq-text').value = state.properties.find(p => p.id === $('faq-property').value)?.faq || ''; }
function photoData(file) {
  if (file.size > 2 * 1024 * 1024) return Promise.reject(new Error('Each photo must be at most 2 MiB.'));
  return new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onerror = () => reject(new Error('Could not read photo.'));
    reader.onload = () => resolve({name: file.name, base64: reader.result.split(',')[1]}); reader.readAsDataURL(file);
  });
}
form('intake-form', async () => {
  const files = [...$('photos').files]; if (files.length > 3) throw new Error('Attach up to three photos.');
  const result = await command({type: 'request', property_id: $('intake-property').value, unit: $('unit').value,
    description: $('description').value, urgency: $('urgency').value, photos: await Promise.all(files.map(photoData))});
  selected = tenantSelected = result.id; $('intake-form').reset(); $('intake-card').hidden = true;
  $('property-filter').value = ''; $('status-filter').value = 'open'; await refresh(); tell('Request created and saved.');
});
form('property-form', async () => { await command({type: 'property', name: $('property-name').value, faq: $('property-faq').value});
  $('property-form').reset(); await refresh(); tell('Property added.'); });
form('vendor-form', async () => { await command({type: 'vendor', name: $('vendor-name').value, trade: $('vendor-trade').value});
  $('vendor-form').reset(); await refresh(); tell('Vendor added.'); });
form('faq-form', async () => { await command({type: 'faq', property_id: $('faq-property').value, faq: $('faq-text').value});
  await refresh(); tell('Property information saved.'); });
$('new-request').addEventListener('click', () => { $('intake-card').hidden = false; $('intake-property').focus(); });
$('property-filter').addEventListener('change', renderList); $('status-filter').addEventListener('change', renderList);
$('faq-property').addEventListener('change', faqSelection);
$('tenant-lookup').addEventListener('change', () => { tenantSelected = $('tenant-lookup').value; renderTenant(); });
for (const button of document.querySelectorAll('nav button')) button.addEventListener('click', () => { setView(button.dataset.view); location.hash = new URLSearchParams({view}); });
for (const button of document.querySelectorAll('.refresh')) button.addEventListener('click', action(async () => { await refresh(); tell('Updated from saved records.'); }, button));
window.addEventListener('hashchange', () => { currentHash(); setView(view); $('tenant-lookup').value = tenantSelected; renderTenant(); });
currentHash(); action(refresh)();
