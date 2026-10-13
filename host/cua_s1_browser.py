"""Direct Chrome CDP adapter for the CUA-S1 form planner.

Attach to one existing tab by exact URL. The planner's opaque element tokens are
bound to live DOM nodes; mutations are verified by a fresh observation. This
module never opens a URL or submits a form implicitly.
"""

from __future__ import annotations

import uuid
from typing import Any

from cua_s1.driver import BaseDriver, DriverError, WindowTarget


_SNAPSHOT_JS = r"""() => {
  const tokens = globalThis.__commonsCuaNodeTokens ||= new WeakMap();
  const controls = Array.from(document.querySelectorAll('input,textarea,select,button'));
  const visible = e => !!(e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
  const nodes = controls.filter(visible);
  return nodes.map((e, i) => {
    if (!tokens.has(e)) tokens.set(e, 'cua-' +
      (globalThis.crypto?.randomUUID?.() || (Date.now().toString(36) + '-' + Math.random().toString(36).slice(2))));
    e.dataset.commonsCuaToken = tokens.get(e);
    const tag = e.tagName.toLowerCase();
    const type = (e.getAttribute('type') || (tag === 'button' ? 'submit' : '')).toLowerCase();
    const label = (e.labels && [...e.labels].map(x => x.innerText).join(' ')) ||
      e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.getAttribute('name') ||
      (tag === 'button' ? e.innerText : '') || '';
    const role = type === 'checkbox' ? 'CheckBox' : type === 'radio' ? 'RadioButton' :
      tag === 'button' || type === 'submit' || type === 'button' ? 'Button' :
      tag === 'select' ? 'ComboBox' : 'Edit';
    const actions = ['CheckBox', 'RadioButton', 'Button'].includes(role) ? ['click'] : ['set_value'];
    return {element_index:i, element_token:e.dataset.commonsCuaToken, role,
      label:label.trim(), value:e.value || '', checked:type === 'checkbox' ? e.checked : null,
      actions, tag, type, disabled:!!e.disabled};
  });
}"""


class BrowserFormDriver(BaseDriver):
    """CUA-S1 BaseDriver backed by an injected Playwright Page."""

    def __init__(self, page: Any, *, browser: Any = None, playwright: Any = None,
                 expected_url: str | None = None, allow_submit: bool = False) -> None:
        super().__init__(session="cua-s1-browser")
        self.page = page
        self.browser = browser
        self.playwright = playwright
        self.expected_url = expected_url or page.url
        self.allow_submit = allow_submit
        self.target = WindowTarget(pid=1, window_id=1)
        self._snapshot_seq = 0
        self._last_elements: dict[str, dict[str, Any]] = {}

    def _check_page(self) -> None:
        if self.page.is_closed() or self.page.url != self.expected_url:
            raise DriverError("stale_browser_target", "The exact Chrome tab is closed or changed URL",
                              details={"expected_url": self.expected_url, "current_url": self.page.url})

    def supports_value_mutation(self) -> bool:
        return True

    def _check_target(self, args: dict[str, Any]) -> None:
        if args.get("pid") not in (None, 1) or args.get("window_id") not in (None, 1):
            raise DriverError("window_not_found", "The requested window is not this exact tab")
        target = args.get("target")
        if target is not None and target != self.target.to_driver_target():
            raise DriverError("window_not_found", "The requested window is not this exact tab")
        self._check_page()

    def _observe(self) -> dict[str, Any]:
        self._check_page()
        elements = self.page.evaluate(_SNAPSHOT_JS)
        if not isinstance(elements, list):
            raise DriverError("window_elements_unavailable", "Chrome did not return form controls")
        tokens = [x.get("element_token") for x in elements]
        if any(not token for token in tokens) or len(tokens) != len(set(tokens)):
            raise DriverError("element_not_uniquely_resolved", "Form control tokens are missing or duplicate")
        self._last_elements = {x["element_token"]: x for x in elements}
        self._snapshot_seq += 1
        return {"snapshot_id": f"browser-{self._snapshot_seq}-{uuid.uuid4().hex[:8]}",
                "elements_complete": True, "elements": elements,
                "tree_markdown": "\n".join(f"{x['element_index']}: {x['role']} {x['label']}" for x in elements),
                "url": self.page.url}

    def _locator(self, token: str) -> tuple[Any, dict[str, Any]]:
        self._check_page()
        if not isinstance(token, str) or token not in self._last_elements:
            raise DriverError("element_stale", "Token is absent from the latest form snapshot")
        locator = self.page.locator(f'[data-commons-cua-token="{token}"]')
        if locator.count() != 1:
            raise DriverError("element_stale", "Form control is missing or ambiguous")
        previous = self._last_elements[token]
        current = locator.evaluate("""e => ({
          tag:e.tagName.toLowerCase(),
          type:(e.getAttribute('type')||(e.tagName.toLowerCase()==='button'?'submit':'')).toLowerCase(),
          disabled:!!e.disabled,
          liveToken:globalThis.__commonsCuaNodeTokens?.get(e),
          value:e.value || '',
          checked:e.type === 'checkbox' ? e.checked : null,
          label:((e.labels && [...e.labels].map(x => x.innerText).join(' ')) ||
            e.getAttribute('aria-label') || e.getAttribute('placeholder') ||
            e.getAttribute('name') || (e.tagName.toLowerCase() === 'button' ? e.innerText : '') || '').trim()
        })""")
        if (current["tag"] != previous["tag"] or current["type"] != previous["type"]
                or current["disabled"] or current["liveToken"] != token
                or current["value"] != previous["value"]
                or current["checked"] != previous["checked"]
                or current["label"] != previous["label"]):
            raise DriverError("element_stale", "Form control identity or availability changed")
        return locator, previous

    def call(self, tool: str, **args: Any) -> dict[str, Any]:
        self._check_target(args)
        if tool in {"start_session", "end_session"}:
            return {"ok": True}
        if tool == "list_windows":
            return {"windows": [{"pid": 1, "window_id": 1, "title": self.page.title(),
                                  "app_name": "Chrome", "is_on_screen": True, "url": self.page.url}]}
        if tool == "get_window_state":
            return self._observe()
        if tool not in {"set_value", "click"}:
            raise DriverError("unsupported_driver_capability", f"Unsupported browser action: {tool}")
        locator, prior = self._locator(args.get("element_token"))
        if tool == "set_value":
            if "set_value" not in prior["actions"]:
                raise DriverError("unsupported_element_action", "Control does not accept a value")
            value = args.get("value")
            if not isinstance(value, str):
                raise DriverError("invalid_value", "Value must be a string")
            locator.fill(value)
            observed = locator.input_value()
            if observed != value:
                raise DriverError("action_effect_unconfirmed", "Filled value did not read back", outcome_unknown=True)
        else:
            if "click" not in prior["actions"]:
                raise DriverError("unsupported_element_action", "Control does not support click")
            if prior["type"] == "submit" and not self.allow_submit:
                raise DriverError("submit_not_enabled", "Submitting requires explicit allow_submit")
            before = locator.is_checked() if prior["role"] == "CheckBox" else None
            locator.click()
            if before is not None and locator.is_checked() == before:
                raise DriverError("action_effect_unconfirmed", "Checkbox state did not change", outcome_unknown=True)
        return {"effect": "confirmed", "route": "playwright-direct-cdp", "element_token": prior["element_token"]}

    def close(self) -> None:
        # The browser belongs to the user. Stopping Playwright disconnects our
        # CDP transport without issuing Browser.close or closing existing tabs.
        if self.playwright is not None:
            self.playwright.stop()


def connect_cdp(url: str, endpoint: str = "http://127.0.0.1:9222",
                *, allow_submit: bool = False) -> tuple[BrowserFormDriver, WindowTarget]:
    """Connect to one already-open Chrome tab whose URL matches exactly."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("An exact tab URL is required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise DriverError("transport_unconfigured", "Install the optional playwright Python package") from exc
    runtime = sync_playwright().start()
    browser = None
    try:
        browser = runtime.chromium.connect_over_cdp(endpoint)
        matches = [page for context in browser.contexts for page in context.pages
                   if not page.is_closed() and page.url == url]
        if len(matches) != 1:
            raise DriverError("window_not_found" if not matches else "ambiguous_window",
                              "Expected exactly one Chrome tab with the requested URL",
                              details={"url": url, "matches": len(matches)})
        driver = BrowserFormDriver(matches[0], browser=browser, playwright=runtime,
                                   expected_url=url, allow_submit=allow_submit)
        return driver, driver.target
    except Exception as exc:
        runtime.stop()
        if isinstance(exc, DriverError):
            raise
        raise DriverError("transport_unconfigured", "Direct Chrome CDP connection failed",
                          details={"endpoint": endpoint, "error": str(exc)}) from exc
