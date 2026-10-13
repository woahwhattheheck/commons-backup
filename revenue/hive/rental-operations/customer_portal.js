'use strict';

const FLEETLINE_PENDING = 'fleetline-pending-request';
const FLEETLINE_LAST = 'fleetline-last-request';
const FLEETLINE_FIELDS = ['asset_id', 'start', 'end', 'customer', 'contact', 'notes'];
function fleetlineDetails(value) {
  if (!value || FLEETLINE_FIELDS.some(key => typeof value[key] !== 'string')) throw new Error('Request details are incomplete.');
  return Object.fromEntries(FLEETLINE_FIELDS.map(key => [key, value[key]]));
}
function fleetlineToken() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
}
async function fleetlineFingerprint(details) {
  const bytes = new TextEncoder().encode(JSON.stringify(fleetlineDetails(details)));
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), value => value.toString(16).padStart(2, '0')).join('');
}

class FleetlineRequestClient {
  constructor(base = '') { this.base = base; this.inFlight = false; this.last = null; this.lastPersisted = false; }
  read(key) {
    try { return JSON.parse(localStorage.getItem(key) || 'null'); }
    catch (_) { throw new Error('Browser request recovery could not be read. Keep the existing browser data and resolve its storage error before sending.'); }
  }
  pending() {
    const value = this.read(FLEETLINE_PENDING);
    if (!value) return null;
    fleetlineDetails(value);
    if (typeof value.request_key !== 'string' || !value.request_key ||
        typeof value.status_token !== 'string' || !/^[A-Za-z0-9_-]{32,160}$/.test(value.status_token) ||
        Object.keys(value).length !== FLEETLINE_FIELDS.length + 2) throw new Error('The saved request recovery record is incomplete.');
    return value;
  }
  persist(key, value) {
    const raw = JSON.stringify(value);
    try {
      localStorage.setItem(key, raw);
      if (localStorage.getItem(key) !== raw) throw new Error('Storage changed.');
    } catch (_) { throw new Error('Browser recovery could not be saved. No replacement request will be sent; keep the existing browser data and resolve its storage error.'); }
  }
  clearPending(payload) {
    const current = this.pending();
    if (current && JSON.stringify(current) === JSON.stringify(payload)) localStorage.removeItem(FLEETLINE_PENDING);
  }
  async prepare(details) {
    const fields = fleetlineDetails(details);
    const pending = this.pending();
    if (pending) {
      if (JSON.stringify(fleetlineDetails(pending)) !== JSON.stringify(fields)) throw new Error('An earlier request still needs a response. Use Retry saved request before sending different details.');
      return pending;
    }
    const contentHash = await fleetlineFingerprint(fields);
    const previous = this.read(FLEETLINE_LAST);
    const reuse = previous && previous.content_hash === contentHash &&
      typeof previous.request_key === 'string' && typeof previous.status_token === 'string';
    const payload = {
      request_key: reuse ? previous.request_key : (crypto.randomUUID ? crypto.randomUUID() : fleetlineToken()),
      status_token: reuse ? previous.status_token : fleetlineToken(), ...fields,
    };
    // Save exact recovery information before the first network request.
    this.persist(FLEETLINE_PENDING, payload);
    return payload;
  }
  async submit(details) {
    if (this.inFlight) throw new Error('A request is already being sent. Wait for its result.');
    this.inFlight = true;
    let payload;
    try {
      payload = details === undefined ? this.pending() : await this.prepare(details);
      if (!payload) throw new Error('No saved request needs a retry.');
      const contentHash = await fleetlineFingerprint(payload);
      const response = await fetch(this.base + '/api/request', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
      const out = await response.json();
      if (!response.ok) {
        // The existing server rolls these explicit input/conflict failures back.
        if ([400, 404, 409, 411, 413, 415].includes(response.status) && typeof out?.error === 'string') this.clearPending(payload);
        throw new Error(out?.error || `HTTP ${response.status}; retry the saved request to recover its result.`);
      }
      if (!out || typeof out.id !== 'string' || !out.id) throw new Error('The response did not identify the request. Retry the saved request to recover its result.');
      this.last = {id: out.id, status_token: payload.status_token, request_key: payload.request_key, content_hash: contentHash};
      this.lastPersisted = false;
      let storageWarning = '';
      try {
        this.persist(FLEETLINE_LAST, this.last);
        this.lastPersisted = true;
        this.clearPending(payload);
      } catch (_) { storageWarning = 'The request was received, but browser recovery could not be updated. Keep this page open; the saved retry retains the original request identity.'; }
      return {request: out, storageWarning};
    } finally { this.inFlight = false; }
  }
  async status() {
    const saved = this.last && !this.lastPersisted ? this.last : this.read(FLEETLINE_LAST);
    if (!saved || typeof saved.id !== 'string' || typeof saved.status_token !== 'string') throw new Error('No completed request is stored in this browser. Retry a saved request first.');
    const response = await fetch(this.base + '/api/status', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: saved.id, status_token: saved.status_token}),
    });
    const out = await response.json();
    if (!response.ok) throw new Error(out?.error || `HTTP ${response.status}`);
    return out;
  }
}

// The storage/HTTP client also works independently of page presentation.
if (typeof module !== 'undefined' && module.exports) module.exports = FleetlineRequestClient;

if (typeof document !== 'undefined') {
  const $ = id => document.getElementById(id);
  const state = {catalog: null};
  const client = new FleetlineRequestClient();
  function iso(id) {
    const value = $(id).value;
    if (!value) throw new Error('Choose both dates.');
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) throw new Error('Choose valid dates.');
    return date.toISOString();
  }
  function selected() { return state.catalog?.assets.find(item => item.id === $('asset').value); }
  function controls() {
    $('submit').disabled = client.inFlight || !selected()?.available;
    $('check').disabled = client.inFlight;
    $('retry').disabled = client.inFlight;
  }
  function recovery() {
    try {
      const pending = client.pending();
      $('recovery').hidden = !pending;
      $('recovery-detail').textContent = pending ? `Saved request for ${pending.asset_id}, ${pending.start} to ${pending.end}. Retry sends these exact saved details, even if the form has changed.` : '';
    } catch (error) { $('result').textContent = error.message; }
    controls();
  }
  function showQuote() {
    const asset = selected();
    $('quote').textContent = asset ? `Rental $${asset.rental_subtotal} + booking fee $${asset.booking_fee} + refundable deposit $${asset.security_deposit} = $${asset.amount_due} due before unconfigured taxes/delivery. Availability is not held.` : '';
  }
  async function body(response) {
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }
  async function submit(details) {
    if (client.inFlight) return;
    const attempt = client.submit(details);
    controls();
    try {
      const {request, storageWarning} = await attempt;
      $('result').textContent = `Request ${request.id} received. ${request.notice} ${storageWarning}`.trim();
      $('status-result').textContent = JSON.stringify(request, null, 2);
    } catch (error) { $('result').textContent = error.message; }
    finally { recovery(); }
  }
  $('check').addEventListener('click', async () => {
    try {
      const start = iso('start'), end = iso('end');
      state.catalog = await body(await fetch(`/api/catalog?${new URLSearchParams({start, end})}`));
      const available = state.catalog.assets.filter(item => item.available);
      const select = $('asset');
      select.replaceChildren();
      if (available.length) {
        for (const asset of available) {
          const option = document.createElement('option');
          option.value = asset.id; option.textContent = `${asset.name} — $${asset.amount_due}`; select.append(option);
        }
      } else {
        const option = document.createElement('option');
        option.value = ''; option.textContent = 'No assets available'; select.append(option);
      }
      select.disabled = !available.length;
      showQuote(); $('result').textContent = state.catalog.notice; controls();
    } catch (error) { $('result').textContent = error.message; $('submit').disabled = true; }
  });
  $('asset').addEventListener('change', () => { showQuote(); controls(); });
  $('request-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (client.inFlight) return;
    try {
      await submit({asset_id: $('asset').value, start: iso('start'), end: iso('end'),
        customer: $('customer').value, contact: $('contact').value, notes: $('notes').value});
    } catch (error) { $('result').textContent = error.message; }
  });
  $('retry').addEventListener('click', () => submit());
  $('status').addEventListener('click', async () => {
    try { $('status-result').textContent = JSON.stringify(await client.status(), null, 2); }
    catch (error) { $('status-result').textContent = error.message; }
  });
  window.addEventListener('storage', recovery);
  recovery();
}
