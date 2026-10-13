'use strict';
const $ = id => document.getElementById(id);
const fields = ['title', 'transcript', 'context', 'intent', 'reply', 'question', 'draft'];
let current = null, dirty = false, working = false, ocrAvailable = false;
function status(text, error = false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', error);
}
function changed(value = true) {
  dirty = value;
  $('dirty').textContent = dirty ? 'Unsaved changes' : '';
}
function mayLeave() { return !dirty || window.confirm('Discard unsaved edits?'); }
async function api(path, method = 'GET', body) {
  const response = await fetch(path, {method, headers: body === undefined ? {} : {'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
function holdControls(held) {
  document.querySelectorAll('button, input[type=file], select').forEach(element => { element.disabled = held; });
  document.querySelectorAll('input:not([type=file]), textarea').forEach(element => { element.readOnly = held; });
}
async function run(action) {
  if (working) return;
  working = true;
  holdControls(true);
  try { await action(); } catch (error) { status(error.message, true); }
  finally { working = false; holdControls(false); }
}
function button(label, action, className = '') {
  const result = document.createElement('button');
  result.type = 'button'; result.textContent = label; result.className = className;
  result.addEventListener('click', () => run(action));
  return result;
}
function path(suffix = '') { return `/api/conversations/${current.id}${suffix}`; }
function values() { return Object.fromEntries(fields.map(key => [key, $(key).value])); }
async function refreshList() {
  const state = await api('/api/state');
  ocrAvailable = state.ocr_available;
  $('ocr-capability').textContent = ocrAvailable ? 'Tesseract is installed. English transcription runs locally; review every result.' : 'Local OCR is not installed. Paste or type a transcript; screenshots can still be saved and viewed.';
  $('conversations').replaceChildren();
  for (const row of state.conversations) {
    const item = document.createElement('li');
    const open = button(row.title, async () => {
      if (!mayLeave()) return;
      show(await api(`/api/conversations/${row.id}`));
      await refreshList(); status('Saved conversation opened.');
    }, `conversation${current?.id === row.id ? ' selected' : ''}`);
    const revision = document.createElement('small'); revision.textContent = `Revision ${row.revision}`;
    open.append(revision); item.append(open); $('conversations').append(item);
  }
}
function show(record) {
  current = record;
  $('empty').hidden = !!record; $('editor').hidden = !record;
  $('candidates').replaceChildren(); $('ocr-editor').hidden = true;
  $('ocr-text').value = ''; $('image-file').value = '';
  if (record) {
    for (const key of fields) $(key).value = record[key];
    $('revision').textContent = `Saved r${record.revision}`;
    renderImages();
  } else {
    for (const key of fields) $(key).value = key === 'intent' ? 'respond' : '';
    $('images').replaceChildren(); $('revision').textContent = '';
  }
  changed(false);
}
async function save() {
  const record = await api(path(), 'POST', {...values(), expected_revision: current.revision});
  current = record; $('revision').textContent = `Saved r${record.revision}`; changed(false);
  await refreshList(); return record;
}
function renderImages() {
  $('images').replaceChildren();
  for (const image of current.images) {
    const card = document.createElement('div'); card.className = 'image-card';
    const link = document.createElement('a'); link.href = path(`/images/${image.id}`); link.target = '_blank'; link.rel = 'noopener noreferrer';
    const preview = document.createElement('img'); preview.src = link.href; preview.alt = image.name;
    link.append(preview);
    const name = document.createElement('div'); name.className = 'name'; name.textContent = `${image.name} · ${image.size.toLocaleString()} bytes`;
    const actions = document.createElement('div'); actions.className = 'row';
    actions.append(button('Transcribe locally', async () => {
      if (!ocrAvailable) throw new Error('Install local Tesseract with English data, or enter the transcript manually.');
      status('Transcribing locally. Your saved transcript will not be replaced.');
      const result = await api(path(`/images/${image.id}/ocr`), 'POST', {expected_revision: current.revision});
      $('ocr-text').value = result.text; $('ocr-editor').hidden = false;
      status(result.text ? 'Review and correct the extracted text before appending it.' : 'No text found. Enter the transcript manually or try a clearer image.');
    }));
    actions.append(button('Remove image', async () => {
      if (!mayLeave() || !window.confirm('Remove this saved image? Text already copied into the transcript remains until you edit it.')) return;
      show(await api(path(`/images/${image.id}`), 'DELETE', {expected_revision: current.revision}));
      await refreshList(); status('Image removed. Previously copied text is unchanged.');
    }, 'danger'));
    card.append(link, name, actions); $('images').append(card);
  }
}
for (const key of fields) $(key).addEventListener('input', () => { changed(); $('candidates').replaceChildren(); });
$('new').addEventListener('click', () => run(async () => {
  if (!mayLeave()) return;
  show(await api('/api/conversations', 'POST', {})); await refreshList(); $('title').focus();
  status('New conversation saved. Add your own words or a screenshot.');
}));
$('sample').addEventListener('click', () => run(async () => {
  if (!mayLeave()) return;
  show(await api('/api/conversations', 'POST', {title: 'Fictional example · weekend walk',
    transcript: 'Alex: Do you prefer an easy walk or a longer hike?', context: 'Fictional demo only. I want a low-key first meeting.',
    intent: 'respond', reply: 'I prefer an easy walk, and Saturday afternoon works for me.', question: 'Which trail would you recommend?'}));
  await refreshList(); status('Fictional example loaded. Edit any field, then draft three options.');
}));
$('editor').addEventListener('submit', event => { event.preventDefault(); run(async () => { await save(); status('Conversation and draft saved.'); }); });
$('generate').addEventListener('click', () => run(async () => {
  await save(); const result = await api(path('/suggest'), 'POST', {expected_revision: current.revision});
  $('candidates').replaceChildren();
  for (const option of result.suggestions) {
    const card = document.createElement('article'); card.className = 'candidate';
    const heading = document.createElement('h3'); heading.textContent = option.tone;
    const text = document.createElement('p'); text.textContent = option.text;
    card.append(heading, text, button(`Use ${option.tone.toLowerCase()} draft`, async () => {
      $('draft').value = option.text; changed(); $('draft').focus(); status('Draft selected. Edit it, then save or copy.');
    })); $('candidates').append(card);
  }
  status('Three template options are ready. No message has been sent.');
}));
$('copy').addEventListener('click', () => run(async () => {
  if (!$('draft').value.trim()) throw new Error('Choose or write a draft first.');
  try { await navigator.clipboard.writeText($('draft').value); status('Draft copied. Nothing has been sent.'); }
  catch (_) { $('draft').focus(); $('draft').select(); status('Clipboard is unavailable here. Your draft is selected; use your device’s Copy command.'); }
}));
$('reload').addEventListener('click', () => run(async () => { if (mayLeave()) { show(await api(path())); await refreshList(); status('Saved version reloaded.'); } }));
$('delete').addEventListener('click', () => run(async () => {
  if (!window.confirm('Delete this conversation, all its saved text, drafts and screenshots? Unsaved edits will also be cleared.')) return;
  await api(path(), 'DELETE', {expected_revision: current.revision}); show(null); await refreshList(); status('Conversation and its screenshots deleted.');
}));
$('erase').addEventListener('click', () => run(async () => {
  if (window.prompt('This removes all saved conversations and screenshots. Export first to keep a copy. Type ERASE to continue.') !== 'ERASE') return;
  await api('/api/erase', 'POST', {confirmation: 'ERASE'}); show(null); await refreshList(); status('All saved conversation text and images deleted from this workspace. Separate exports and backups are not deleted.');
}));
function readFile(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(new Error('The image could not be read.')); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.readAsDataURL(file); }); }
$('upload').addEventListener('click', () => run(async () => {
  const file = $('image-file').files[0];
  if (!file) throw new Error('Choose a screenshot first.');
  if (file.size > 6 * 1024 * 1024) throw new Error('Choose an image no larger than 6 MiB.');
  const encoded = await readFile(file); await save();
  show(await api(path('/images'), 'POST', {name: file.name, data_base64: encoded, expected_revision: current.revision}));
  await refreshList(); status('Original screenshot saved. Transcribe it locally or enter its text manually.');
}));
$('apply-ocr').addEventListener('click', () => {
  const addition = $('ocr-text').value.trim();
  const combined = [$('transcript').value.trim(), addition].filter(Boolean).join('\n\n');
  if (!addition) { status('Correct or enter the extracted text first.', true); return; }
  if (combined.length > 30000) { status('The combined transcript is longer than 30,000 characters.', true); return; }
  $('transcript').value = combined; changed(); $('candidates').replaceChildren(); $('ocr-editor').hidden = true; $('ocr-text').value = '';
  status('Corrected text appended. Save the conversation to keep it.');
});
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
run(async () => { await refreshList(); status('Workspace ready. Drafts stay here until you copy them yourself.'); });
