(() => {
  'use strict';

  // Compatibility asset for pages that still request /operator-auth.js.
  // Creator Desk is a shared workspace: the page's own controls and fetch
  // implementation remain available without an operator unlock layer.
  // Previously stored keys are neither read nor transmitted.
})();
