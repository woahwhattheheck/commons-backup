'use strict';
(() => {
  const view = document.getElementById('view-inbox');
  if (!view) return;
  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text != null) n.textContent = String(text);
    if (cls) n.className = cls;
    return n;
  };
  const card = el('article', null, 'panel'); card.id = 'deathstar-mail';
  const title = el('h2', 'Email tracker');
  const help = el('p', 'Shared thread tracking, not an AI inbox watcher. Waiting describes the last observed conversation turn, not a requirement to reply.', 'field-help');
  const form = el('form', null, 'filter-bar'), search = el('input');
  search.type = 'search'; search.placeholder = 'Search email threads'; search.maxLength = 240;
  search.setAttribute('aria-label', 'Search email threads');
  const mode = el('select'); mode.setAttribute('aria-label', 'Email thread state');
  for (const [value, label] of [['all','All threads'],['waiting_on_us','Last turn: incoming'],['waiting_on_them','Last turn: outgoing'],['unread','Unread'],['overdue','Past recorded deadline'],['unknown','Coverage or direction unknown']]) {
    const option = el('option', label); option.value = value; mode.append(option);
  }
  const refresh = el('button', 'Update shared view', 'button button-small'); refresh.type = 'submit';
  form.append(search, mode, refresh);
  const status = el('p', 'Loading shared email observations…', 'field-help'); status.setAttribute('role', 'status');
  const coverage = el('div'), rows = el('div'), pages = el('div', null, 'button-row');
  const back = el('button', 'Previous', 'text-button'), next = el('button', 'Next', 'text-button');
  back.type = next.type = 'button'; pages.append(back, next);
  card.append(title, help, form, status, coverage, rows, pages); view.prepend(card);
  let offset = 0, displayedOffset = 0, nextOffset = null, busy = false, timer, queued = false, filterVersion = 0;
  const stamp = value => value ? new Date(value).toLocaleString() : 'unknown';
  const line = (label, value) => {
    const p = el('p', null, 'work-next'); p.append(el('strong', label + ' '), document.createTextNode(String(value))); return p;
  };
  function render(data) {
    const freshCoverage = el('div'), freshRows = el('div');
    for (const source of data.sources || []) {
      const state = source.current ? 'current' : 'stale / unknown';
      freshCoverage.append(line(source.account || source.label || source.id,
        state + ' · last provider read ' + stamp(source.last_good_observed_at) + ' · ' +
        (source.coverage?.complete === true ? 'complete for stated scope' : 'partial coverage') +
        ' · ' + (source.sync_mode || 'sync mode unknown')));
    }
    if (!(data.sources || []).length) freshCoverage.append(line('Sync:', 'No email source loaded yet.'));
    for (const thread of data.threads) {
      const row = el('article', null, 'overview-work');
      row.append(el('h3', thread.title || '(No subject)'));
      row.append(line('Conversation:', thread.account || 'Account unknown'));
      row.append(line('Last observed turn:', (thread.observed_waiting_on || 'unknown').replaceAll('_', ' ') +
        (thread.waiting_on === 'unknown' ? ' · not current or complete enough to call waiting' : '')));
      row.append(line('Updated:', stamp(thread.last_activity_at) + ' · ' + thread.message_count + ' messages' + (thread.unread ? ' · unread' : '')));
      row.append(line('Assigned owner:', thread.assigned_owner || 'Unassigned'));
      row.append(line('Next action:', thread.next_action || 'Not recorded'));
      if (thread.priority != null) row.append(line('Priority:', thread.priority));
      if (thread.due_at) row.append(line('Recorded deadline:', stamp(thread.due_at) + (thread.overdue ? ' · overdue' : '')));
      const actions = el('div', null, 'button-row');
      try {
        const url = new URL(thread.url);
        if (url.protocol === 'https:' && !url.username && !url.password) {
          const open = el('a', 'Open original', 'source-link'); open.href = url.href; open.target = '_blank'; open.rel = 'noopener noreferrer'; actions.append(open);
        }
      } catch (_) { /* Missing original link remains missing. */ }
      const ref = thread.directive_ref || thread.record_refs?.[0];
      if (ref) {
        const manage = el('button', 'Priority / next action', 'text-button'); manage.type = 'button';
        manage.addEventListener('click', () => window.dispatchEvent(new CustomEvent('commons-open-work', {detail: ref})));
        actions.append(manage);
      }
      row.append(actions); freshRows.append(row);
    }
    if (!data.threads.length) freshRows.append(el('p', 'No matching threads in the loaded source coverage.', 'field-help'));
    coverage.replaceChildren(...freshCoverage.children); rows.replaceChildren(...freshRows.children);
    displayedOffset = data.pagination.offset; nextOffset = data.pagination.next_offset; back.disabled = data.pagination.offset === 0; next.disabled = nextOffset == null;
    status.textContent = data.threads.length + ' shown of ' + data.pagination.matching_threads + ' matching threads · ' +
      data.counts.messages + ' observed messages · ' + data.counts.duplicate_records + ' duplicate records combined · shared snapshot ' + stamp(data.observed_at);
  }
  async function load() {
    if (document.visibilityState === 'hidden') return;
    if (busy) { queued = true; return; }
    busy = true; refresh.disabled = true; back.disabled = next.disabled = true;
    const requestedFilterVersion = filterVersion;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const params = new URLSearchParams({limit:'100', offset:String(offset), q:search.value, mode:mode.value});
      const response = await fetch('/api/mail?' + params, {signal:controller.signal});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (!Array.isArray(data.threads) || !data.pagination || !data.counts) throw new Error('Invalid shared mail response');
      // A request completed for a filter that is no longer selected. The newer
      // filter read is already queued; never expose obsolete rows or actions.
      if (requestedFilterVersion !== filterVersion) return;
      render(data);
    } catch (error) {
      // An older failed read must not undo a newer queued filter reset.
      if (requestedFilterVersion === filterVersion) offset = displayedOffset;
      status.textContent = 'Email view unavailable (' + error.message + '). Last displayed observations retained; sync freshness is not advanced.';
    } finally {
      clearTimeout(timeout); busy = false; refresh.disabled = false;
      back.disabled = displayedOffset === 0; next.disabled = nextOffset == null;
      clearTimeout(timer);
      if (queued) { queued = false; load(); } else { timer = setTimeout(load, 30000); }
    }
  }
  form.addEventListener('submit', event => {event.preventDefault(); filterVersion++; offset = 0; load();});
  mode.addEventListener('change', () => {filterVersion++; offset = 0; load();});
  back.addEventListener('click', () => {offset = Math.max(0, offset - 100); load();});
  next.addEventListener('click', () => {if (nextOffset != null) {offset = nextOffset; load();}});
  document.addEventListener('visibilitychange', () => {if (document.visibilityState !== 'hidden') load();});
  load();
})();
