/* Fleetline browser controller. The SQLite service owns pricing and conflicts. */
'use strict';
const $ = id => document.getElementById(id);
let state = {assets: [], reservations: []};
let assetEdit = null, reservationEdit = null, checklistEdit = null;
const pending = new Map();
const labels = {condition_recorded:'Condition recorded', accessories_counted:'Accessories counted',
  instructions_shared:'Operating / pickup instructions shared', issues_noted:'Issues and follow-up recorded'};
const statusLabels = {reserved:'Reserved', out:'Handed over', returned:'Returned', cancelled:'Cancelled'};

function feedback(message, error = false) {
  $('feedback').textContent = message;
  $('feedback').classList.toggle('error', error);
  $('feedback').hidden = false;
  const local = document.querySelector('dialog[open] .dialog-error');
  if (local) { local.textContent = error ? message : ''; local.hidden = !error; }
}
function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (className) node.className = className;
  return node;
}
function button(label, action, className = 'secondary mini') {
  const node = element('button', label, className);
  node.type = 'button';
  node.addEventListener('click', () => perform(action));
  return node;
}
async function perform(action) {
  try { await action(); } catch (error) { feedback(error.message, true); }
}
async function api(path, options) {
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) { const error = new Error(value.error || `Request ${response.status}`); error.status = response.status; throw error; }
  return value;
}
function requestID() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(n => n.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
function operation(command) {
  const key = JSON.stringify(command);
  if (!pending.has(key)) pending.set(key, requestID());
  return {key, id: pending.get(key)};
}
async function send(command) {
  const attempt = operation(command);
  try {
    const result = await api('/api/command', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({command, operation_id:attempt.id})});
    pending.delete(attempt.key);
    return result.record;
  } catch (error) {
    if (error.status >= 400 && error.status < 500) pending.delete(attempt.key);
    throw error;
  }
}
function localInput(iso) {
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function inputISO(id) {
  const value = $(id).value;
  if (!value) throw new Error('Choose start and end times.');
  const original = reservationEdit?.[id === 'reservation-start' ? 'start' : 'end'];
  if (original && localInput(original) === value) return original;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime()) || localInput(date) !== value) {
    throw new Error('That local time is not valid in this timezone. Choose a time outside the clock-change gap.');
  }
  return date.toISOString();
}
function when(value) {
  return new Date(value).toLocaleString(undefined, {month:'short', day:'numeric', year:'numeric', hour:'2-digit', minute:'2-digit', timeZoneName:'shortOffset'});
}
function terms(value) {
  return `rental $${value.rental_subtotal} + fee $${value.booking_fee} + refundable deposit $${value.security_deposit}`;
}
async function refresh() {
  state = await api('/api/state');
  render();
}
function render() {
  $('asset-count').textContent = state.assets.length;
  $('booking-count').textContent = state.reservations.filter(r => r.kind === 'booking' && ['reserved','out'].includes(r.status)).length;
  $('hold-count').textContent = state.reservations.filter(r => r.kind === 'maintenance' && r.status !== 'cancelled').length;
  const assets = $('assets'); assets.replaceChildren();
  if (!state.assets.length) assets.append(element('p', 'Add your first asset to begin booking.', 'empty'));
  for (const asset of state.assets) {
    const card = element('div', undefined, 'asset');
    card.append(element('strong', asset.name), element('small', `$${asset.rate} / ${asset.unit} · ${asset.minimum_units} minimum`),
      element('small', `Booking fee $${asset.booking_fee} · refundable deposit $${asset.security_deposit}`));
    if (asset.notes) card.append(element('small', asset.notes));
    card.append(button('Edit rate & details', () => editAsset(asset)));
    assets.append(card);
  }
  const select = $('reservation-asset');
  const selected = select.value;
  select.replaceChildren();
  for (const asset of state.assets) { const option = element('option', asset.name); option.value = asset.id; select.append(option); }
  if (state.assets.some(asset => asset.id === selected)) select.value = selected;
  renderSchedule();
}
function renderSchedule() {
  const body = $('schedule'); body.replaceChildren();
  const chosen = $('schedule-date').value;
  const from = chosen ? new Date(`${chosen}T00:00:00`) : null;
  const to = from ? new Date(from) : null;
  if (to) to.setDate(to.getDate() + 1);
  const shown = state.reservations.filter(row => ($('schedule-status').value === 'all' || row.status !== 'cancelled') &&
    (!from || (new Date(row.start) < to && new Date(row.end) > from)));
  if (!shown.length) {
    const tr = element('tr'), td = element('td', 'No reservations in this view.', 'empty'); td.colSpan = 4; tr.append(td); body.append(tr);
  }
  for (const row of shown) {
    const asset = state.assets.find(item => item.id === row.asset_id);
    const tr = element('tr');
    const identity = element('td'); identity.append(element('strong', asset ? asset.name : row.asset_id), element('small', row.customer));
    if (row.contact) identity.append(element('small', row.contact));
    const timing = element('td'); timing.append(element('span', when(row.start)), element('small', `to ${when(row.end)}`));
    const status = element('td');
    status.append(element('span', row.kind === 'maintenance' && row.status === 'reserved' ? 'Maintenance hold' : statusLabels[row.status],
      `tag ${row.status === 'cancelled' ? 'cancelled' : row.kind === 'maintenance' ? 'maintenance' : ''}`));
    if (row.kind === 'maintenance') {
      status.append(element('small', 'No rental charge'));
    } else {
      status.append(element('small', `$${row.amount_due} due · ${terms(row)}`));
      status.append(element('small', `${row.billed_units} ${row.unit} units · pricing snapshot`));
    }
    status.append(element('small', `Revision ${row.revision}`));
    const work = element('td'), actions = element('div', undefined, 'actions');
    if (row.status === 'reserved') {
      actions.append(button('Edit', () => editReservation(row)), button('Cancel', async () => {
        if (!confirm(`Cancel ${row.customer}'s ${row.kind}? The interval will become available.`)) return;
        await send({action:'cancel', id:row.id, expected_revision:row.revision});
        await refresh(); feedback('Reservation cancelled. The interval is available again.');
      }, 'danger mini'));
    }
    if (row.kind === 'booking' && ['reserved','out'].includes(row.status)) {
      actions.append(button(row.status === 'reserved' ? 'Handover' : 'Return', () => openChecklist(row)));
    }
    if (row.kind === 'booking') actions.append(button('Message draft', () => openMessage(row)));
    work.append(actions); tr.append(identity, timing, status, work); body.append(tr);
  }
}
function resetAsset() {
  assetEdit = null; $('asset-form').reset(); $('asset-title').textContent = 'Add an asset';
  $('asset-booking-fee').value = '0.00'; $('asset-security-deposit').value = '0.00';
}
function editAsset(asset) {
  assetEdit = asset;
  $('asset-name').value = asset.name; $('asset-unit').value = asset.unit;
  $('asset-rate').value = asset.rate; $('asset-minimum').value = asset.minimum_units;
  $('asset-booking-fee').value = asset.booking_fee; $('asset-security-deposit').value = asset.security_deposit;
  $('asset-notes').value = asset.notes;
  $('asset-title').textContent = `Edit asset · revision ${asset.revision}`;
  $('asset-name').focus();
}
function resetReservation() {
  reservationEdit = null; $('reservation-form').reset();
  $('reservation-asset').disabled = false; $('reservation-kind').disabled = false;
  const start = new Date(); start.setDate(start.getDate() + 1); start.setHours(9, 0, 0, 0);
  const end = new Date(start); end.setDate(end.getDate() + 1);
  $('reservation-start').value = localInput(start); $('reservation-end').value = localInput(end);
  $('reservation-title').textContent = 'Make a reservation'; $('availability').replaceChildren();
}
function editReservation(row) {
  reservationEdit = row;
  $('reservation-asset').value = row.asset_id; $('reservation-kind').value = row.kind;
  $('reservation-asset').disabled = true; $('reservation-kind').disabled = true;
  $('reservation-start').value = localInput(row.start); $('reservation-end').value = localInput(row.end);
  $('reservation-customer').value = row.customer; $('reservation-contact').value = row.contact; $('reservation-notes').value = row.notes;
  $('reservation-title').textContent = `Edit reservation · revision ${row.revision}`;
  $('reservation-start').focus();
}
function openChecklist(row) {
  const stage = row.status === 'reserved' ? 'handover' : 'return';
  checklistEdit = {row, stage};
  const prior = stage === 'handover' ? row.handover : row.returned;
  const keys = stage === 'handover' ? ['condition_recorded','accessories_counted','instructions_shared'] : ['condition_recorded','accessories_counted','issues_noted'];
  $('check-title').textContent = stage === 'handover' ? 'Handover checklist' : 'Return checklist';
  $('check-description').textContent = `${row.customer} · revision ${row.revision}. Save partial progress or complete the stage.`;
  $('check-items').replaceChildren();
  for (const key of keys) {
    const label = element('label', undefined, 'check'), input = element('input');
    input.type = 'checkbox'; input.name = key; input.checked = !!prior.checks?.[key];
    label.append(input, document.createTextNode(labels[key])); $('check-items').append(label);
  }
  $('check-notes').value = prior.notes || '';
  $('check-dialog').querySelector('.dialog-error').hidden = true;
  $('check-dialog').showModal();
}
async function openMessage(row) {
  const result = await api(`/api/message?id=${encodeURIComponent(row.id)}`);
  $('message-to').textContent = `To: ${result.to || 'not supplied'} · current reservation revision ${result.reservation_revision}`;
  $('message-body').value = `Subject: ${result.subject}\n\n${result.body}`;
  $('message-dialog').showModal();
}
$('asset-form').addEventListener('submit', event => {
  event.preventDefault(); perform(async () => {
    await send({action:'save_asset', id:assetEdit?.id || null, expected_revision:assetEdit?.revision || 0,
      name:$('asset-name').value, unit:$('asset-unit').value, rate:$('asset-rate').value,
      minimum_units:Number($('asset-minimum').value), booking_fee:$('asset-booking-fee').value,
      security_deposit:$('asset-security-deposit').value, notes:$('asset-notes').value});
    resetAsset(); await refresh(); feedback('Asset saved. Existing booking pricing snapshots are unchanged.');
  });
});
$('reservation-form').addEventListener('submit', event => {
  event.preventDefault(); perform(async () => {
    const row = await send({action:'save_reservation', id:reservationEdit?.id || null,
      expected_revision:reservationEdit?.revision || 0, asset_id:$('reservation-asset').value,
      kind:$('reservation-kind').value, start:inputISO('reservation-start'), end:inputISO('reservation-end'),
      customer:$('reservation-customer').value, contact:$('reservation-contact').value, notes:$('reservation-notes').value});
    resetReservation(); await refresh();
    feedback(row.kind === 'maintenance' ? 'Maintenance hold saved. This interval is unavailable for bookings.' :
      `Reservation saved. Amount due: USD ${row.amount_due} (${terms(row)}). No payment recorded.`);
  });
});
$('check-form').addEventListener('submit', event => {
  event.preventDefault(); perform(async () => {
    const checks = Object.fromEntries([...$('check-items').querySelectorAll('input')].map(input => [input.name, input.checked]));
    const {row, stage} = checklistEdit;
    await send({action:'checklist', id:row.id, expected_revision:row.revision, stage, checks,
      complete:event.submitter?.value === 'complete', notes:$('check-notes').value});
    $('check-dialog').close(); await refresh(); feedback('Checklist and booking state saved.');
  });
});
$('check-availability').addEventListener('click', () => perform(async () => {
  const result = await api('/api/availability?' + new URLSearchParams({start:inputISO('reservation-start'), end:inputISO('reservation-end')}));
  $('availability').replaceChildren();
  for (const asset of result.assets) {
    const text = asset.available ? `available · $${asset.amount_due} due (${terms(asset)})` : 'unavailable';
    $('availability').append(element('span', `${asset.name}: ${text}`, asset.available ? '' : 'busy'));
  }
  if (!result.assets.length) $('availability').append(element('span', 'Add an asset first.'));
}));
$('refresh').addEventListener('click', () => perform(async () => { await refresh(); feedback('Schedule refreshed. Unsaved form edits remain; reopen an edited record to load its latest revision.'); }));
$('export-workspace').addEventListener('click', event => {
  event.preventDefault(); perform(async () => {
    const data = await api('/api/export');
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type:'application/json'}));
    const link = element('a'); link.href = url; link.download = 'fleetline-export.json';
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    feedback('Workspace export prepared. The file includes customer details, pricing snapshots and audit history.');
  });
});
$('print').addEventListener('click', () => window.print());
$('asset-reset').addEventListener('click', resetAsset);
$('reservation-reset').addEventListener('click', resetReservation);
$('schedule-date').addEventListener('change', renderSchedule);
$('schedule-status').addEventListener('change', renderSchedule);
$('schedule-clear').addEventListener('click', () => {$('schedule-date').value = ''; renderSchedule();});
$('check-close').addEventListener('click', () => $('check-dialog').close());
$('message-close').addEventListener('click', () => $('message-dialog').close());
$('message-copy').addEventListener('click', () => perform(async () => {
  try { await navigator.clipboard.writeText($('message-body').value); feedback('Draft copied. No message has been sent.'); }
  catch (_) { $('message-body').select(); throw new Error('Select and copy the draft manually in this browser.'); }
}));
$('zone').textContent = Intl.DateTimeFormat().resolvedOptions().timeZone;
resetAsset();
resetReservation();
perform(refresh);
