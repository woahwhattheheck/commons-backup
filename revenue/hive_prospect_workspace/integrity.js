/* Fieldnote customer-state integrity shim. Browser-local only; no network or provider calls. */
(function (root, factory) {
  const patch = factory();
  if (typeof module === 'object' && module.exports) module.exports = patch;
  else root.FieldnoteIntegrity = patch;
  if (root && root.FieldnoteApp) patch.install(root.FieldnoteApp, root);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const installedApis = new WeakSet();
  const FILTER_IDS = new Set(['filter-q', 'filter-industry', 'filter-tag', 'filter-stage', 'filter-email']);

  function cloneFilters(filters) {
    const f = filters || {};
    return {
      q: String(f.q || ''),
      industry: String(f.industry || ''),
      tag: String(f.tag || ''),
      stage: String(f.stage || ''),
      withEmail: Boolean(f.withEmail)
    };
  }

  function patchStorageBridge(api) {
    const proto = api.StorageBridge && api.StorageBridge.prototype;
    if (!proto || proto.__fieldnoteIntegrityLoad) return;
    Object.defineProperty(proto, '__fieldnoteIntegrityLoad', { value: true, enumerable: false });
    proto.load = function (model) {
      if (!model || typeof model.empty !== 'function' || typeof model.clone !== 'function' || typeof model.validateState !== 'function') {
        throw new Error('Fieldnote model.js is missing or incompatible.');
      }
      const empty = model.empty();
      if (!this.storage) return { state: empty, status: this.status };
      let raw;
      try {
        raw = this.storage.getItem(this.key);
      } catch (_) {
        this.storage = null;
        this.persistent = false;
        this.status = 'Memory only; browser storage could not be read.';
        return { state: empty, status: this.status };
      }
      if (raw === null) return { state: empty, status: this.status };
      try {
        const parsed = JSON.parse(raw);
        model.validateState(parsed);
        this.writeBlocked = false;
        return { state: model.clone(parsed), status: this.status };
      } catch (_) {
        this.writeBlocked = true;
        this.status = 'Saved browser data is invalid; it was left untouched. Edits stay in memory until you restore a known-good backup or reset locally.';
        return { state: empty, status: this.status };
      }
    };
  }

  function selectValue(doc, id, value) {
    const select = doc.getElementById(id);
    if (!select) return;
    const wanted = String(value || '');
    if (wanted && !Array.from(select.options || []).some(option => option.value === wanted)) {
      const option = doc.createElement('option');
      option.value = wanted;
      option.textContent = wanted + ' (saved segment; no current matches)';
      select.appendChild(option);
    }
    select.value = wanted;
  }

  function syncSegmentControls(doc, filters) {
    if (!filters) return;
    const q = doc.getElementById('filter-q');
    const email = doc.getElementById('filter-email');
    if (q) q.value = filters.q;
    selectValue(doc, 'filter-industry', filters.industry);
    selectValue(doc, 'filter-tag', filters.tag);
    selectValue(doc, 'filter-stage', filters.stage);
    if (email) email.checked = Boolean(filters.withEmail);
  }

  function clearVisibleSelections(doc) {
    if (!doc || typeof doc.querySelectorAll !== 'function') return;
    for (const checkbox of doc.querySelectorAll('#accounts-body input[type="checkbox"]:checked')) {
      if (typeof checkbox.click === 'function') checkbox.click();
      else checkbox.checked = false;
    }
  }

  function visibleMergeIds(ids, accounts) {
    const visible = new Set((accounts || []).map(account => account.id));
    return [...new Set(ids || [])].filter(id => visible.has(id));
  }

  function attachUiIntegrity(doc, controller) {
    if (!doc || !controller || typeof doc.getElementById !== 'function') return controller;
    let activeSegmentFilters = null;

    const originalQuery = controller.query.bind(controller);
    controller.query = function (filters) {
      const effective = activeSegmentFilters ? cloneFilters(activeSegmentFilters) : cloneFilters(filters);
      if (activeSegmentFilters) syncSegmentControls(doc, effective);
      return originalQuery(effective);
    };

    const originalExport = controller.exportCSV.bind(controller);
    controller.exportCSV = function (filters) {
      const effective = activeSegmentFilters ? cloneFilters(activeSegmentFilters) : cloneFilters(filters);
      return originalExport(effective);
    };

    const originalMerge = controller.merge.bind(controller);
    controller.merge = function (ids) {
      const visibleAccounts = controller.query({
        q: (doc.getElementById('filter-q') || {}).value || '',
        industry: (doc.getElementById('filter-industry') || {}).value || '',
        tag: (doc.getElementById('filter-tag') || {}).value || '',
        stage: (doc.getElementById('filter-stage') || {}).value || '',
        withEmail: Boolean((doc.getElementById('filter-email') || {}).checked)
      });
      const safeIds = visibleMergeIds(ids, visibleAccounts);
      if (safeIds.length < 2) throw new Error('Select at least two visible accounts to merge.');
      return originalMerge(safeIds);
    };

    for (const name of ['restoreText', 'reset']) {
      const original = controller[name].bind(controller);
      controller[name] = function (...args) {
        const result = original(...args);
        activeSegmentFilters = null;
        clearVisibleSelections(doc);
        return result;
      };
    }

    if (typeof doc.addEventListener === 'function') {
      doc.addEventListener('change', event => {
        const target = event.target || {};
        if (target.id === 'segment-list') {
          activeSegmentFilters = null;
          if (target.value !== '') {
            const segment = controller.getState().segments[Number(target.value)];
            if (segment) activeSegmentFilters = cloneFilters(segment.filters);
          }
          clearVisibleSelections(doc);
          return;
        }
        if (FILTER_IDS.has(target.id)) {
          activeSegmentFilters = null;
          clearVisibleSelections(doc);
        }
      }, true);
      doc.addEventListener('input', event => {
        if ((event.target || {}).id === 'filter-q') {
          activeSegmentFilters = null;
          clearVisibleSelections(doc);
        }
      }, true);
      doc.addEventListener('click', event => {
        if ((event.target || {}).id === 'clear-filters') {
          activeSegmentFilters = null;
          clearVisibleSelections(doc);
        }
      }, true);
    }
    return controller;
  }

  function install(api, root) {
    if (!api || installedApis.has(api)) return api;
    installedApis.add(api);
    patchStorageBridge(api);

    const originalMount = api.mount.bind(api);
    api.mount = function (doc, model, storage) {
      return attachUiIntegrity(doc, originalMount(doc, model, storage), root);
    };
    return api;
  }

  return {
    install,
    attachUiIntegrity,
    cloneFilters,
    clearVisibleSelections,
    visibleMergeIds,
    syncSegmentControls
  };
});
