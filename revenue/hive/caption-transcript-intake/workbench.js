'use strict';
const $ = (id) => document.getElementById(id);
const state = {rows: [], active: null, busy: false, next: 1};
const limits = {max_files: 20, max_file_bytes: 2000000, max_batch_bytes: 20000000, max_archive_bytes: 64000000};

function node(tag, text, cls) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (cls) result.className = cls;
  return result;
}
function status(text, error = false) {
  $('global-status').textContent = text;
  $('global-status').className = error ? 'message error' : 'message';
}
function clock(ms) {
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor(ms / 60000) % 60;
  const seconds = Math.floor(ms / 1000) % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
}
function active() { return state.rows.find(row => row.id === state.active); }
function selected() { return state.rows.filter(row => row.selected); }
function summaryLabel(row) {
  if (!row.result) return 'Not previewed / options changed';
  if (row.result.ok) return `${row.result.cue_count} cues · ready to export`;
  return row.result.parsed ? 'Parsed · export needs attention' : 'Input needs attention';
}
function renderList() {
  $('file-list').replaceChildren();
  for (const row of state.rows) {
    const li = node('li', undefined, `file-row${row.id === state.active ? ' active' : ''}`);
    const check = document.createElement('input');
    check.type = 'checkbox'; check.checked = row.selected;
    check.setAttribute('aria-label', `Include ${row.file.name} in batch`);
    check.addEventListener('change', () => { row.selected = check.checked; renderList(); });
    const pick = node('button', undefined, 'pick'); pick.type = 'button';
    pick.append(node('span', row.file.name), node('small', summaryLabel(row), row.result && !row.result.ok ? 'bad' : ''));
    pick.addEventListener('click', () => { state.active = row.id; renderList(); renderDetail(); });
    const remove = node('button', '×', 'remove'); remove.type = 'button';
    remove.setAttribute('aria-label', `Remove ${row.file.name}`);
    remove.addEventListener('click', () => {
      state.rows = state.rows.filter(item => item !== row);
      if (state.active === row.id) state.active = state.rows[0]?.id ?? null;
      renderList(); renderDetail();
    });
    li.append(check, pick, remove); $('file-list').append(li);
  }
  $('empty-list').hidden = state.rows.length > 0;
  $('selection-count').textContent = `${selected().length} of ${state.rows.length} files selected`;
  $('preview-all').disabled = selected().length === 0;
  $('export-batch').disabled = selected().length === 0;
  $('clear').disabled = state.rows.length === 0;
}
function renderDetail() {
  const row = active();
  $('empty-detail').hidden = !!row; $('detail').hidden = !row;
  if (!row) return;
  $('file-name').textContent = row.file.name;
  $('file-size').textContent = `${row.file.size.toLocaleString()} original bytes · original file is not edited${row.reopened ? ' · restored from a saved handoff' : ''}`;
  for (const field of ['title', 'format', 'encoding', 'speaker', 'duration']) $(field).value = row[field];
  $('synthetic').checked = row.synthetic;
  $('query').value = row.query;
  renderResult();
}
function renderResult() {
  const row = active(); if (!row) return;
  const result = row.result;
  $('summary').hidden = !result?.parsed;
  $('preview').hidden = !result?.parsed;
  $('file-status').textContent = result ? (result.ok ? `Ready: ${result.episode_import ? 'generic handoff + episode import' : 'generic handoff'}. Recording not verified.` : result.error) : 'Options are ready to preview. Exports always parse the current options again.';
  $('file-status').className = result && !result.ok ? 'message error' : 'message';
  if (!result?.parsed) return;
  $('metrics').replaceChildren();
  for (const [value, label] of [[result.cue_count, 'caption cues'], [result.speaker_count, 'supplied speaker labels'], [result.overlapping_cues, 'cues overlapping earlier cues']]) {
    const metric = node('div', undefined, 'metric');
    metric.append(node('strong', value), node('span', label)); $('metrics').append(metric);
  }
  $('source-info').replaceChildren(
    node('p', `Caption span ${clock(result.first_caption_ms)} – ${clock(result.last_caption_ms)}. This is not the recording duration.`),
    node('p', `${result.format.toUpperCase()} · ${result.encoding} · ${result.source_bytes.toLocaleString()} original bytes`),
    node('p', `Speaker labels: ${result.speakers.map(item => `${item.name} (${item.cues})`).join(', ')}${result.speaker_count > 100 ? ' · first 100 labels shown' : ''}`),
    node('p', 'Original SHA-256:'), node('code', result.source_sha256));
  const page = result.preview;
  $('cues').replaceChildren();
  for (const cue of page.cues) {
    const article = node('article', undefined, 'cue');
    article.append(node('h3', `${cue.id} · ${cue.speaker}`),
      node('small', `${clock(cue.start_ms)} – ${clock(cue.end_ms)} · source line ${cue.line}`, 'quiet'),
      node('p', cue.text));
    if (cue.text_truncated) article.append(node('small', 'Preview shortened after 4,000 characters; export retains the complete text.', 'quiet'));
    const raw = document.createElement('details');
    raw.append(node('summary', `Original cue ${cue.source_id ?? '(no source ID)'} · timing and markup`),
      node('pre', `${cue.timing}\n${cue.raw_payload}${cue.raw_truncated ? '\n[Preview shortened; original is retained in the export.]' : ''}`));
    article.append(raw); $('cues').append(article);
  }
  if (!page.cues.length) $('cues').append(node('p', 'No cues match this search.', 'quiet'));
  $('page-label').textContent = page.matched ? `${page.offset + 1}–${page.offset + page.cues.length} of ${page.matched} matching cues` : '0 matching cues';
  $('previous').disabled = page.offset === 0;
  $('next').disabled = page.offset + page.page_size >= page.matched;
}
async function busy(task) {
  if (state.busy) return;
  state.busy = true; $('workspace').disabled = true;
  try { await task(); } catch (error) { status(error.message || 'The operation failed.', true); }
  finally { state.busy = false; $('workspace').disabled = false; }
}
function asBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Cannot read ${file.name}. Select it again.`));
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.readAsDataURL(file);
  });
}
async function addFiles(files) {
  await busy(async () => {
    const incoming = Array.from(files);
    if (incoming.length + state.rows.length > limits.max_files) throw new Error(`Keep at most ${limits.max_files} files in a batch.`);
    if (incoming.some(file => file.size === 0 || file.size > limits.max_file_bytes)) throw new Error('Each file must contain 1–2,000,000 bytes. No files from this selection were added.');
    const bytes = [...state.rows.map(row => row.file), ...incoming].reduce((total, file) => total + file.size, 0);
    if (bytes > limits.max_batch_bytes) throw new Error('Original files exceed the 20 MB batch limit. Remove files or split the batch.');
    // Add atomically after every file has been read; a failed read cannot create a partial selection.
    const additions = [];
    for (const file of incoming) {
      const extension = file.name.split('.').pop().toLowerCase();
      additions.push({id: state.next++, file, source: await asBase64(file), selected: true,
        title: file.name.replace(/\.(srt|vtt)$/i, ''), format: ['srt', 'vtt'].includes(extension) ? extension : '',
        encoding: 'utf-8-sig', speaker: 'Unspecified', duration: '', synthetic: false, query: '', result: null});
    }
    state.rows.push(...additions); state.active ??= additions[0]?.id ?? null;
    renderList(); renderDetail(); status(`Added ${additions.length} file(s). Choose a file to edit options, then preview the selected batch.`);
  });
  $('files').value = '';
}
async function reopen(file) {
  if (!file) return;
  await busy(async () => {
    if (!file.size || file.size > limits.max_archive_bytes) throw new Error('Saved handoff ZIP must contain 1–64,000,000 bytes. Selection is unchanged.');
    status(`Reopening ${file.name} and comparing its retained artifacts…`);
    const response = await fetch('/api/reopen', {method: 'POST', headers: {'Content-Type': 'application/zip'}, body: file});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(`${result.error || 'Unable to reopen this saved handoff.'} Selection is unchanged.`);
    const bytes = state.rows.reduce((total, row) => total + row.file.size, 0) + result.results.reduce((total, row) => total + row.source_bytes, 0);
    if (result.files.length + state.rows.length > limits.max_files || bytes > limits.max_batch_bytes) throw new Error('Reopened originals exceed the current selection limit. Clear or remove files, then reopen the handoff. Selection is unchanged.');
    const additions = result.files.map((row, index) => ({id: state.next++, file: {name: row.name, size: result.results[index].source_bytes},
      source: row.source_base64, selected: true, title: row.title, format: row.format, encoding: row.encoding,
      speaker: row.speaker, duration: row.duration_seconds ?? '', synthetic: row.synthetic_demo,
      query: '', result: result.results[index], reopened: true}));
    state.rows.push(...additions); state.active = additions[0].id;
    renderList(); renderDetail();
    status(`Reopened ${additions.length} handoff(s). Retained artifacts match the supplied originals; recording and authorship remain unverified. Options and complete captions are ready to review or export.`);
  });
  $('handoff-file').value = '';
}
function requestRow(row, offset = 0) {
  return {name: row.file.name, source_base64: row.source, title: row.title, format: row.format,
    encoding: row.encoding, speaker: row.speaker, duration_seconds: row.duration || null,
    synthetic_demo: row.synthetic, query: row.query, offset};
}
function applyResults(rows, result) {
  if (Array.isArray(result.results)) {
    result.results.forEach((item, index) => { if (rows[index]) rows[index].result = item; });
    renderList(); renderResult();
  }
}
async function convert(rows, endpoint, offset = 0) {
  if (!rows.length) return;
  await busy(async () => {
    status(endpoint === 'preview' ? `Reading ${rows.length} file(s)…` : `Building ${rows.length} complete handoff(s)…`);
    const response = await fetch(`/api/${endpoint}`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({files: rows.map(row => requestRow(row, offset))})});
    if ((response.headers.get('content-type') || '').includes('application/json')) {
      const result = await response.json(); applyResults(rows, result);
      if (!response.ok || result.error) throw new Error(result.error || 'Nothing downloaded. Fix or deselect the files marked for attention.');
      const ready = (result.results || []).filter(item => item.ok).length;
      status(`${ready} of ${rows.length} file(s) ready to export.${ready < rows.length ? ' Inspect the marked file(s); no captions were dropped.' : ' Words and recording still require human review.'}`, ready < rows.length);
      return;
    }
    if (!response.ok) throw new Error(`Local server returned HTTP ${response.status}; no completed download.`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url;
    const stem = rows[0].file.name.replace(/\.(srt|vtt)$/i, '').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'captions';
    link.download = endpoint === 'batch' ? 'caption-batch.zip' : `${stem}-handoff.zip`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    status(`Download prepared for ${rows.length} file(s). Check your browser downloads. Originals and complete captions are retained; no application import was performed.`);
  });
}
for (const field of ['title', 'format', 'encoding', 'speaker', 'duration']) {
  $(field).addEventListener('input', () => {
    const row = active(); if (!row) return;
    row[field] = $(field).value; row.result = null; renderList(); renderResult();
  });
}
$('synthetic').addEventListener('change', () => {
  const row = active(); if (!row) return;
  row.synthetic = $('synthetic').checked; row.result = null; renderList(); renderResult();
});
$('files').addEventListener('change', () => addFiles($('files').files));
$('handoff-file').addEventListener('change', () => reopen($('handoff-file').files[0]));
$('drop').addEventListener('dragover', event => { event.preventDefault(); if (!state.busy) $('drop').classList.add('drag'); });
$('drop').addEventListener('dragleave', () => $('drop').classList.remove('drag'));
$('drop').addEventListener('drop', event => { event.preventDefault(); $('drop').classList.remove('drag'); if (!state.busy) addFiles(event.dataTransfer.files); });
$('clear').addEventListener('click', () => { state.rows = []; state.active = null; renderList(); renderDetail(); status('Selection cleared. Downloaded files are unchanged.'); });
$('preview-all').addEventListener('click', () => convert(selected(), 'preview'));
$('export-batch').addEventListener('click', () => convert(selected(), 'batch'));
$('preview-one').addEventListener('click', () => { const row = active(); if (row) convert([row], 'preview'); });
$('export-one').addEventListener('click', () => { const row = active(); if (row) convert([row], 'export'); });
function search() { const row = active(); if (row) { row.query = $('query').value; convert([row], 'preview'); } }
$('search').addEventListener('click', search);
$('query').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); search(); } });
$('previous').addEventListener('click', () => { const row = active(); if (row?.result?.preview) convert([row], 'preview', Math.max(0, row.result.preview.offset - row.result.preview.page_size)); });
$('next').addEventListener('click', () => { const row = active(); if (row?.result?.preview) convert([row], 'preview', row.result.preview.offset + row.result.preview.page_size); });
renderList(); renderDetail();
fetch('/api/info').then(response => { if (!response.ok) throw new Error('Local server unavailable.'); return response.json(); })
  .then(info => { Object.assign(limits, info); status('Ready. Choose supplied caption files; nothing is sent to an external service.'); })
  .catch(error => status(`${error.message} Start workbench.py and open its local address.`, true));
