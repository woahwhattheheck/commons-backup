/* Progressive enhancement only. Channel links are static and need no request. */
(function (root) {
  'use strict';
  function normalize(value) {
    return String(value == null ? '' : value).normalize('NFKC').toLowerCase().replace(/[#_-]/g, ' ');
  }
  function matches(text, query) {
    const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
    const haystack = normalize(text);
    return terms.every(function (term) { return haystack.includes(term); });
  }
  function init(doc) {
    if (!doc) return false;
    const form = doc.getElementById('channel-search');
    const input = doc.getElementById('channel-query');
    const clear = doc.getElementById('channel-clear');
    const count = doc.getElementById('channel-count');
    const empty = doc.getElementById('channel-empty');
    const directory = doc.getElementById('channel-directory');
    if (!form || !input || !clear || !count || !empty || !directory) return false;
    const cards = Array.from(directory.querySelectorAll('[data-channel]'));
    if (!cards.length) return false;
    function update() {
      let shown = 0;
      cards.forEach(function (card) {
        const text = card.textContent + ' ' + (card.getAttribute('data-keywords') || '') + ' ' + (card.getAttribute('data-channel') || '');
        card.hidden = !matches(text, input.value);
        if (!card.hidden) shown += 1;
      });
      count.textContent = shown + ' of ' + cards.length + ' channels shown.';
      empty.hidden = shown !== 0;
    }
    input.addEventListener('input', update);
    form.addEventListener('submit', function (event) { event.preventDefault(); update(); });
    clear.addEventListener('click', function () { input.value = ''; update(); input.focus(); });
    update();
    form.hidden = false;
    return true;
  }
  if (typeof module === 'object' && module.exports) module.exports = {normalize: normalize, matches: matches, init: init};
  if (root.document) init(root.document);
})(typeof globalThis === 'object' ? globalThis : this);
