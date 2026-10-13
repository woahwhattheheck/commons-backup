"""Executable Chromium acceptance for Hive Study's browser composition.

The environment running this test blocks browser navigation by administrator
policy, so this harness uses Playwright ``set_content`` plus an in-page transport
bridge. It exercises the real HTML/CSS/JS bytes and the documented API shapes,
not study.py itself. The landed backend remains covered by its SQLite/HTTP suite.
The bridge deliberately simulates a review that commits before its response is
lost, then proves reload/retry reuses the same request_id without double-counting.

Run: python -B test_browser_acceptance.py
Requires: Playwright's Python package and /usr/bin/chromium.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC_ID = "a" * 64


def require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("SKIP: Python Playwright is not installed") from exc
    return sync_playwright


def clean_html() -> str:
    text = (ROOT / "index.html").read_text(encoding="utf-8")
    text = re.sub(r'<link rel="stylesheet" href="/style\.css">', "", text)
    text = re.sub(r'<script src="/workspace\.js" defer></script>', "", text)
    return text


BRIDGE = r"""
(() => {
  if (!window.__hiveStorage) window.__hiveStorage = Object.create(null);
  Object.defineProperty(window, 'localStorage', { configurable: true, value: {
    getItem(key) { return Object.prototype.hasOwnProperty.call(window.__hiveStorage, key) ? window.__hiveStorage[key] : null; },
    setItem(key, value) { window.__hiveStorage[key] = String(value); },
    removeItem(key) { delete window.__hiveStorage[key]; }
  }});
  if (!window.__hiveBackend) window.__hiveBackend = {
    document: null, card: null, reviews: Object.create(null), attempts: 0,
    dropFirstReviewResponse: true, requestIds: []
  };
  const B = window.__hiveBackend;
  const DOC = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  const CARD = 'card-0001';
  const json = (value, status = 200) => new Response(JSON.stringify(value), {status, headers: {'Content-Type':'application/json; charset=utf-8'}});
  const route = (input) => {
    const raw = typeof input === 'string' ? input : input.url;
    return new URL(raw, 'https://hive-study.test').pathname + new URL(raw, 'https://hive-study.test').search;
  };
  window.fetch = async (input, options = {}) => {
    const target = route(input);
    const [path, query = ''] = target.split('?');
    const method = String(options.method || 'GET').toUpperCase();
    const body = options.body ? JSON.parse(options.body) : null;
    const now = Date.now() / 1000;
    if (method === 'GET' && path === '/api/capabilities') return json({pdf:true,max_upload:8388608,generation:'source-bound definition and cloze rules'});
    if (method === 'GET' && path === '/api/documents') {
      const documents = B.document ? [{
        id:DOC,title:B.document.title,filename:B.document.filename,kind:'text',created_at:B.document.created_at,
        cards:1,due:Number(B.card.due_at <= now),attempts:B.attempts
      }] : [];
      return json({documents});
    }
    if (method === 'POST' && path === '/api/import') {
      B.document = {id:DOC,title:body.title || 'chapter',filename:body.filename,kind:'text',pages:['Mitochondria: The organelle that produces most cellular ATP.'],created_at:now};
      B.card = {id:CARD,document_id:DOC,prompt:'Which term matches this definition?\\n\\nThe organelle that produces most cellular ATP.',answer:'Mitochondria',aliases:[],kind:'definition',page:1,line_start:1,line_end:1,quote:'Mitochondria: The organelle that produces most cellular ATP.',explanation:'Compare your answer with the quoted source and the editable answer key.',revision:1,due_at:0,interval_days:0,repetitions:0,lapses:0,attempts:0,source_url:'/source/'+DOC+'#p1-l1'};
      return json({id:DOC,cards:1,duplicate:false,notice:'Review the generated prompts and keys before studying.'});
    }
    if (!B.document) return json({message:'Document not found.'}, 404);
    if (method === 'GET' && path === '/api/documents/'+DOC) return json(B.document);
    if (method === 'GET' && path === '/api/documents/'+DOC+'/cards') {
      const dueOnly = new URLSearchParams(query).get('due') === '1';
      return json({cards: dueOnly && B.card.due_at > now ? [] : [B.card]});
    }
    if (method === 'POST' && path === '/api/cards/'+CARD) {
      if (body.revision !== B.card.revision) return json({message:'The card changed in another tab. Reload its current key before editing.'}, 409);
      B.card.prompt = body.prompt; B.card.answer = body.answer; B.card.aliases = body.aliases || []; B.card.explanation = body.explanation;
      B.card.revision += 1; B.card.due_at = 0; B.card.repetitions = 0; B.card.interval_days = 0;
      return json(B.card);
    }
    if (method === 'POST' && path === '/api/review') {
      B.requestIds.push(body.request_id);
      if (B.reviews[body.request_id]) {
        const previous = B.reviews[body.request_id];
        if (previous.submitted !== body.answer || previous.revision !== body.revision) return json({message:'Review identifier already describes another answer.'}, 409);
        return json(previous);
      }
      if (body.revision !== B.card.revision) return json({message:'The answer key changed. Reload this card before checking your answer.'}, 409);
      const accepted = [B.card.answer, ...B.card.aliases].map(x => x.toLocaleLowerCase());
      const correct = accepted.includes(String(body.answer).toLocaleLowerCase());
      const interval = correct ? 1 : 0;
      const dueAt = now + (correct ? 86400 : 600);
      const result = {card_id:CARD,correct,answer:B.card.answer,submitted:body.answer,explanation:B.card.explanation,quote:B.card.quote,source_url:B.card.source_url,page:1,line_start:1,revision:B.card.revision,due_at:dueAt,interval_days:interval,request_id:body.request_id,feedback:correct?'Matches the editable answer key.':'Does not match the editable key. Compare the source; a valid wording variant can be added by the tutor.'};
      B.reviews[body.request_id] = result; B.attempts += 1; B.card.attempts = B.attempts; B.card.due_at = dueAt;
      if (B.dropFirstReviewResponse) { B.dropFirstReviewResponse = false; throw new TypeError('simulated lost response after commit'); }
      return json(result);
    }
    if (method === 'DELETE' && path === '/api/documents/'+DOC) {
      B.document = null; B.card = null; B.reviews = Object.create(null); return json({deleted:DOC});
    }
    return json({message:'This route was not found.'}, 404);
  };
})();
"""


def install(page, html: str, css: str, js: str):
    page.set_content(html, wait_until="domcontentloaded")
    page.add_style_tag(content=css)
    page.evaluate(BRIDGE)
    page.add_script_tag(content=js)
    page.locator("#capability-badge").wait_for(state="visible")


def run():
    sync_playwright = require_playwright()
    html = clean_html()
    css = (ROOT / "style.css").read_text(encoding="utf-8")
    js = (ROOT / "workspace.js").read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        install(page, html, css, js)
        assert page.get_by_role("heading", name="Practice from your source, not a black box.").is_visible()

        page.locator("#import-title").fill("Cell Energy")
        page.locator("#import-file").set_input_files({"name": "chapter.txt", "mimeType": "text/plain", "buffer": b"Mitochondria: The organelle that produces most cellular ATP.\n"})
        page.locator("#import-submit").click()
        page.locator("#document-title").wait_for(state="visible")
        assert page.locator("#document-title").inner_text() == "Cell Energy"
        assert "1 cards" in page.locator("#document-meta").inner_text()

        page.locator("#tutor-editor summary").click()
        page.locator("#edit-answer").fill("Mitochondrion")
        page.locator("#edit-aliases").fill("Mitochondria")
        page.locator("#edit-explanation").fill("Use the exact organelle named in the source sentence.")
        page.locator("#edit-card-form button[type=submit]").click()
        page.get_by_text("Tutor key saved.").wait_for(state="visible")

        page.locator("#review-answer").fill("chloroplast")
        page.locator("#check-answer").click()
        page.get_by_text("The workspace server could not be reached.").wait_for(state="visible")
        assert page.locator("#pending-banner").is_visible()
        first_request = page.evaluate("window.__hiveBackend.requestIds.at(-1)")
        assert page.evaluate("window.__hiveBackend.attempts") == 1

        # Rebuild the document while preserving window-scoped browser storage and
        # contract state; this is the executable equivalent of a page reload in
        # this navigation-blocked container.
        install(page, html, css, js)
        page.locator("#pending-banner").wait_for(state="visible")
        assert "Saved-answer recovery" in page.locator("#queue-summary").inner_text()
        assert page.locator("#review-answer").input_value() == "chloroplast"
        page.locator("#retry-pending").click()
        page.locator("#feedback").wait_for(state="visible")
        assert page.locator("#feedback-title").inner_text() == "Check the source"
        assert "Mitochondrion" in page.locator("#feedback-answer").inner_text()
        assert page.evaluate("window.__hiveBackend.attempts") == 1
        assert page.evaluate("window.__hiveBackend.requestIds.at(-1)") == first_request

        page.locator("#next-card").click()
        page.locator("#no-cards").wait_for(state="visible")
        page.locator("#show-all").click()
        page.locator("#card-stage").wait_for(state="visible")
        page.locator("#review-answer").fill("Mitochondria")
        page.locator("#check-answer").click()
        page.locator("#feedback").wait_for(state="visible")
        assert page.locator("#feedback-title").inner_text() == "Matches the key"
        assert "1 day" in page.locator("#feedback-schedule").inner_text()
        assert page.locator("#export-link").get_attribute("href") == f"/api/documents/{DOC_ID}/export"
        assert page.locator("#original-link").get_attribute("href") == f"/original/{DOC_ID}"

        page.on("dialog", lambda dialog: dialog.accept())
        page.locator("#delete-document").click()
        page.locator("#welcome").wait_for(state="visible")
        assert page.locator("#empty-library").is_visible()
        browser.close()
    print("PASS browser acceptance: import/edit/review/lost-response retry/reload/source feedback/export paths/delete")


if __name__ == "__main__":
    run()
