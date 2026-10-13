/* Read-only view of CURRENT_WORK.json; every observation belongs to one main SHA. */
(function (root) {
  'use strict';
  const API = 'https://api.github.com/repos/woahwhattheheck/commons';
  const WEB = 'https://github.com/woahwhattheheck/commons';
  const SHA = /^[0-9a-f]{40}$/;
  const KINDS = ['BUILDABLE', 'OWNER_PLATFORM', 'DEVICE_PINNED'];
  const pathPart = path => {
    if (typeof path !== 'string' || !path.length) throw new Error('Expected a relative repository path.');
    const parts = path.split('/');
    if (parts.some((part, index) => part === '.' || part === '..' || part.includes('\0') ||
        (!part && (index === 0 || index !== parts.length - 1)))) {
      throw new Error('Expected a relative repository path without dot or empty interior segments.');
    }
    // Encode literal percent signs and separators before constructing a URL.
    // encodeURIComponent also diagnoses unpaired Unicode surrogates.
    return parts.map(encodeURIComponent).join('/');
  };
  const sourceURL = (sha, path) => `${WEB}/blob/${sha}/${pathPart(path)}`;

  async function request(fetcher, url, signal) {
    const response = await fetcher(url, {signal, cache: 'no-store'});
    if (!response.ok) throw new Error(`GitHub HTTP ${response.status}`);
    return response.json();
  }

  async function loadSnapshot(fetcher, signal) {
    const ref = await request(fetcher, `${API}/git/ref/heads/main`, signal);
    const sha = ref && ref.object && ref.object.sha;
    if (typeof sha !== 'string' || !SHA.test(sha)) throw new Error('No valid official-main SHA returned.');
    const file = await request(fetcher, `${API}/contents/ground/CURRENT_WORK.json?ref=${sha}`, signal);
    if (!file || file.encoding !== 'base64' || typeof file.content !== 'string') {
      throw new Error('Ledger content was not returned as a readable file.');
    }
    const bytes = Uint8Array.from(atob(file.content.replace(/\s/g, '')), c => c.charCodeAt(0));
    const catalog = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
    if (!catalog || catalog.schema !== 'commons-current-work-v1' || !Array.isArray(catalog.items)) {
      throw new Error('Ledger schema or items array is invalid.');
    }
    return {sha, items: catalog.items, observed: new Date().toISOString(), cache: new Map()};
  }

  function pathsFor(item) {
    if (!item || typeof item !== 'object' || Array.isArray(item) || !KINDS.includes(item.kind)) return null;
    const paths = item.claimed_paths == null ? [] : item.claimed_paths;
    if (!Array.isArray(paths)) return null;
    try { paths.forEach(pathPart); } catch (_) { return null; }
    return paths;
  }

  function initialStatus(item) {
    if (pathsFor(item) === null) return 'INVALID ROW';
    if (item.kind === 'DEVICE_PINNED') return 'PINNED';
    if (!pathsFor(item).length) return item.kind === 'OWNER_PLATFORM' ? 'NEEDS_OWNER' : 'OPEN';
    return 'UNVERIFIED';
  }

  async function verifyItem(item, snapshot, fetcher, signal) {
    const paths = pathsFor(item);
    if (paths === null || initialStatus(item) !== 'UNVERIFIED') return {status: initialStatus(item), missing: []};
    if (!snapshot || !SHA.test(snapshot.sha)) throw new Error('Path checks require an official-main snapshot.');
    const results = [];
    // Sequential, shared path checks avoid a request burst and duplicate API work.
    for (const path of paths) {
      if (!snapshot.cache.has(path)) {
        snapshot.cache.set(path, fetcher(`${API}/contents/${pathPart(path)}?ref=${snapshot.sha}`,
          {signal, cache: 'no-store'}).then(response => {
            if (response.ok) return true;
            if (response.status === 404) return false;
            throw new Error(`GitHub HTTP ${response.status}`);
          }).catch(error => { snapshot.cache.delete(path); throw error; }));
      }
      results.push(await snapshot.cache.get(path));
    }
    const missing = paths.filter((path, index) => !results[index]);
    return {status: missing.length ? (item.kind === 'OWNER_PLATFORM' ? 'NEEDS_OWNER' : 'OPEN') : 'CLOSED', missing};
  }

  function mount(doc, fetcher) {
    const list = doc.getElementById('cw-items');
    if (!list) return null;
    const status = doc.getElementById('cw-source');
    const search = doc.getElementById('cw-search');
    const kind = doc.getElementById('cw-kind');
    const refresh = doc.getElementById('cw-refresh');
    let epoch = 0, controller = null, snapshot = null, rows = [];
    function element(tag, text, parent) {
      const node = doc.createElement(tag);
      if (text !== undefined) node.textContent = text;
      if (parent) parent.appendChild(node);
      return node;
    }
    // Catalog metadata can be valid JSON without being renderable text.
    const textField = (value, fallback) => typeof value === 'string' && value ? value : fallback;
    function render() {
      const focusedRow = rows.find(row => row.button === doc.activeElement);
      for (const row of rows) {
        if (row.details && row.details.isConnected) row.detailsOpen = row.details.open;
      }
      list.replaceChildren();
      if (!snapshot) { doc.getElementById('cw-count').textContent = ''; return; }
      const query = search.value.trim().toLowerCase();
      const visible = rows.filter(row => {
        const item = row.item || {};
        const text = [item.id, item.title, item.from, item.kind, item.acceptance, item.notes,
          ...(pathsFor(item) || [])].filter(value => typeof value === 'string').join(' ').toLowerCase();
        return (!kind.value || item.kind === kind.value) && (!query || text.includes(query));
      });
      doc.getElementById('cw-count').textContent = `${visible.length} of ${rows.length} ledger items`;
      if (!visible.length) element('p', rows.length ? 'No items match these filters.' : 'No items in this ledger snapshot.', list);
      for (const row of visible) {
        const item = row.item || {};
        const card = element('article', undefined, list);
        card.className = 'cw-item';
        element('h3', typeof item.title === 'string' ? item.title : 'Invalid ledger row', card);
        element('p', `${textField(item.id, '(missing id)')} · ${textField(item.kind, '(missing kind)')} · From: ${textField(item.from, 'unspecified')}`, card);
        const invalidText = ['id', 'title', 'from', 'kind', 'acceptance', 'notes']
          .filter(field => item[field] != null && typeof item[field] !== 'string');
        if (invalidText.length) element('p', `Invalid text fields: ${invalidText.join(', ')}`, card);
        const outcome = element('p', `${row.status}${row.detail ? ' — ' + row.detail : ''}`, card);
        outcome.setAttribute('role', 'status');
        if (typeof item.acceptance === 'string') element('p', 'Acceptance: ' + item.acceptance, card);
        if (typeof item.notes === 'string') element('p', item.notes, card);
        const paths = pathsFor(item);
        if (paths && paths.length) {
          const details = element('details', undefined, card);
          row.details = details;
          details.open = !!row.detailsOpen;
          element('summary', `${paths.length} claimed paths at ${snapshot.sha.slice(0, 12)}`, details);
          const links = element('ul', undefined, details);
          for (const path of paths) {
            const link = element('a', path, element('li', undefined, links));
            link.href = sourceURL(snapshot.sha, path);
          }
        }
        if (initialStatus(item) === 'UNVERIFIED') {
          const button = element('button', row.busy ? 'Checking paths…' : 'Check listed paths', card);
          row.button = button;
          button.type = 'button';
          // Keep keyboard focus available while preventing duplicate work.
          button.setAttribute('aria-disabled', String(!!row.busy));
          button.addEventListener('click', async () => {
            if (row.busy) return;
            const version = epoch, current = snapshot, signal = controller.signal;
            row.busy = true; row.status = 'CHECKING'; row.detail = ''; render();
            try {
              const result = await verifyItem(item, current, fetcher, signal);
              if (version !== epoch) return;
              row.status = result.status;
              row.detail = result.missing.length ? `Missing: ${result.missing.join(', ')}` :
                `All claimed paths exist at ${current.sha.slice(0, 12)}; not a test, payment, or live-service result.`;
            } catch (error) {
              if (version !== epoch) return;
              row.status = 'UNVERIFIED';
              row.detail = `${error.message}. No closure inferred; retry or use the source links.`;
            }
            row.busy = false; render();
          });
        }
      }
      if (focusedRow && focusedRow.button && focusedRow.button.isConnected) {
        focusedRow.button.focus();
      }
    }
    async function reload() {
      const version = ++epoch;
      if (controller) controller.abort();
      controller = new AbortController(); snapshot = null; rows = [];
      list.replaceChildren(); doc.getElementById('cw-count').textContent = '';
      status.textContent = 'Reading official main and its ledger…';
      refresh.textContent = 'Restart refresh';
      try {
        const next = await loadSnapshot(fetcher, controller.signal);
        if (version !== epoch) return;
        snapshot = next;
        rows = next.items.map(item => ({item, status: initialStatus(item)}));
        status.textContent = `Observed main ${next.sha} at ${next.observed}. `;
        const link = element('a', 'Read this ledger snapshot', status);
        link.href = sourceURL(next.sha, 'ground/CURRENT_WORK.json');
        render();
      } catch (error) {
        if (version !== epoch) return;
        status.textContent = `Ledger unavailable: ${error.message}. No empty-queue or completion claim is made. Use the existing ledger links or refresh.`;
      }
      if (version === epoch) refresh.textContent = 'Refresh from main';
    }
    search.addEventListener('input', render);
    kind.addEventListener('change', render);
    refresh.addEventListener('click', reload);
    return {reload, ready: reload()};
  }
  const exported = {loadSnapshot, pathsFor, initialStatus, verifyItem, sourceURL, mount};
  if (typeof module === 'object' && module.exports) module.exports = exported;
  else {
    root.CommonsCurrentWork = exported;
    mount(root.document, root.fetch.bind(root));
  }
}(typeof window === 'object' ? window : globalThis));
