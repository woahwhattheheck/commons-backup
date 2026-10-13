import { analyzeAssociation, buildResearchExport, canonicalJson, normalizeLedger, syntheticDemo } from './core.mjs';

let events = [];
const $ = (selector) => document.querySelector(selector);
const timeline = $('#timeline-body');
const status = $('#status');
const result = $('#analysis-output');

function setStatus(message) {
  status.textContent = message;
}

function makeId(prefix) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function nowIso() {
  return new Date().toISOString();
}

function render() {
  const ledger = normalizeLedger(events);
  timeline.replaceChildren();
  for (const event of [...ledger].reverse()) {
    const row = document.createElement('tr');
    const summary = event.kind === 'diet'
      ? `${event.payload.label} [${event.payload.tags.join(', ')}]`
      : event.kind === 'symptom'
        ? `${event.payload.domain}: ${event.payload.severity}/10`
        : event.kind === 'validated_score'
          ? `${event.payload.instrument} ${event.payload.domain}: ${event.payload.score}`
          : `${event.payload.domain}: ${String(event.payload.value)}`;
    for (const value of [new Date(event.occurred_at).toLocaleString(), event.kind, summary]) {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.append(cell);
    }
    timeline.append(row);
  }
  setStatus(`${ledger.length} session-local events. Nothing has been uploaded.`);
}

function addEvent(event) {
  events = normalizeLedger([...events, event]);
  render();
}

$('#diet-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const tags = String(form.get('tags') || '').split(',').map((value) => value.trim()).filter(Boolean);
  addEvent({
    id: makeId('diet'), kind: 'diet', occurred_at: String(form.get('occurred_at')), recorded_at: nowIso(),
    payload: { label: String(form.get('label')), tags, note: String(form.get('note') || '').trim() || null },
  });
  event.currentTarget.reset();
});

$('#symptom-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  addEvent({
    id: makeId('symptom'), kind: 'symptom', occurred_at: String(form.get('occurred_at')), recorded_at: nowIso(),
    payload: { domain: String(form.get('domain')), severity: Number(form.get('severity')), note: String(form.get('note') || '').trim() || null },
  });
  event.currentTarget.reset();
});

$('#score-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  addEvent({
    id: makeId('score'), kind: 'validated_score', occurred_at: String(form.get('occurred_at')), recorded_at: nowIso(),
    payload: {
      instrument: String(form.get('instrument')), instrument_version: String(form.get('instrument_version')),
      domain: String(form.get('domain')), score: Number(form.get('score')),
      scale_min: Number(form.get('scale_min')), scale_max: Number(form.get('scale_max')),
      source_url: String(form.get('source_url')),
    },
  });
  event.currentTarget.reset();
});

$('#context-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  addEvent({
    id: makeId('context'), kind: 'context', occurred_at: String(form.get('occurred_at')), recorded_at: nowIso(),
    payload: { domain: String(form.get('domain')), value: String(form.get('value')) },
  });
  event.currentTarget.reset();
});

$('#analysis-form').addEventListener('submit', (event) => {
  event.preventDefault();
  try {
    const form = new FormData(event.currentTarget);
    const report = analyzeAssociation(events, {
      exposure_tag: String(form.get('exposure_tag')),
      outcome_domain: String(form.get('outcome_domain')),
      lag_hours: Number(form.get('lag_hours')),
      baseline_hours: Number(form.get('baseline_hours')),
    });
    result.textContent = JSON.stringify(report, null, 2);
  } catch (error) {
    result.textContent = `Analysis refused: ${error.message}`;
  }
});

$('#load-demo').addEventListener('click', () => {
  events = syntheticDemo(new Date());
  render();
  setStatus('Loaded synthetic demo data. It contains no personal health information.');
});

$('#clear-all').addEventListener('click', () => {
  events = [];
  result.textContent = '';
  render();
});

async function sha256(text) {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, '0')).join('');
}

$('#export-research').addEventListener('click', async () => {
  const payload = buildResearchExport(events);
  const canonical = canonicalJson(payload);
  const wrapped = { ...payload, content_sha256: await sha256(canonical) };
  const blob = new Blob([JSON.stringify(wrapped, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'nourish-research-export.json';
  anchor.click();
  URL.revokeObjectURL(url);
  setStatus('Research export generated locally. Free-text notes were removed.');
});

$('#import-file').addEventListener('change', async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const parsed = JSON.parse(await file.text());
    const candidate = Array.isArray(parsed) ? parsed : parsed.events;
    events = normalizeLedger(candidate);
    render();
  } catch (error) {
    setStatus(`Import refused: ${error.message}`);
  } finally {
    event.target.value = '';
  }
});

for (const input of document.querySelectorAll('input[type="datetime-local"]')) {
  const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  input.value = local;
}

render();
