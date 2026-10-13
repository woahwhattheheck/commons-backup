/* SPDX-License-Identifier: Apache-2.0 */
'use strict';
(() => {
  const byId = id => document.getElementById(id);
  let revision = null, selected = null, pending = null, busy = false;
  function status(message) { byId('status').textContent = message; }
  function controls() {
    byId('save').disabled = busy || revision === null || (selected === null && pending === null);
    for (const id of ['download', 'refresh', 'erase', 'backup']) byId(id).disabled = busy;
    byId('save').textContent = pending ? 'Retry pending operation' : 'Save to SQLite';
  }
  async function api(data) {
    const response = await fetch('/api/state', data === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || 'Persistence request failed');
    return body;
  }
  async function refresh() {
    if (busy) return null;
    busy = true; controls();
    try {
      const current = await api();
      revision = current.revision;
      pending = null;
      status(`Server revision ${revision}. ${current.present ? 'A backup is saved; download it before replacing unfamiliar work.' : 'No server backup saved.'}`);
      return current;
    } catch (error) { status(error.message); return null; }
    finally { busy = false; controls(); }
  }
  async function write(deleting = false) {
    if (busy) return;
    if (revision === null) { status('Read the server revision first.'); return; }
    if (!deleting && pending === null && selected === null) {
      status('Select a workspace backup before saving.'); controls(); return;
    }
    busy = true; controls();
    try {
      if (!pending) pending = {payload: deleting ? null : selected,
        expected_revision: revision, operation_id: crypto.randomUUID()};
      const receipt = await api(pending);
      revision = receipt.revision;
      pending = null;
      status(`Operation revision ${revision}: ${receipt.present ? 'backup saved' : 'server backup deleted'}. Browser records are unchanged.`);
    } catch (error) {
      status(error.message + '\nRetry uses the same operation ID and exact bytes. For a revision conflict, download the latest backup, refresh the revision, then explicitly choose what to save.');
    } finally { busy = false; controls(); }
  }
  byId('backup').onchange = async () => {
    if (busy) return;
    selected = null; pending = null; busy = true; controls();
    try {
      const file = byId('backup').files[0];
      if (!file) { status('No file selected.'); return; }
      if (file.size > 2000000) throw new Error('Backup exceeds 2 MB.');
      const text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
      const data = JSON.parse(text);
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Select an object-format workspace JSON backup.');
      selected = text;
      status(`${file.name} selected, not saved. Saving will replace the single server backup at revision ${revision}.`);
    } catch (error) { status(error.message); }
    finally { busy = false; controls(); }
  };
  byId('save').onclick = () => write();
  byId('refresh').onclick = () => {
    if (busy) return;
    if (pending && !confirm('Discard this retry receipt and read the latest server revision? No data will be saved.')) return;
    refresh();
  };
  byId('download').onclick = async () => {
    if (busy) return;
    busy = true; controls();
    try {
      const current = await api();
      if (!current.present) throw new Error('No server backup is saved.');
      const url = URL.createObjectURL(new Blob([current.payload], {type: 'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = `hive-prospect-backup-r${current.revision}.json`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status(`Downloaded revision ${current.revision}. Restore it using the existing workspace backup control. The panel did not replace browser records.`);
    } catch (error) { status(error.message); }
    finally { busy = false; controls(); }
  };
  byId('erase').onclick = () => {
    if (busy) return;
    if (revision === null) { status('Read the server revision first.'); return; }
    if (pending) { status('Resolve or explicitly discard the pending operation before deleting.'); return; }
    if (confirm('Delete the current server backup? Browser records, existing downloads and external backups are not removed.')) write(true);
  };
  refresh();
})();
