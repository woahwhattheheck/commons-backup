"""Optional Chromium rendering checks with in-memory response fixtures only.

This is not browser-network or persistence validation. test_ui_transport uses
actual UI functions with real HTTP/SQLite; this file checks DOM and layout.
"""
import json
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from parts_desk import Desk
from test_parts_desk import item, job


class DOMCase(unittest.TestCase):
    def test_rendering_forms_and_layout_with_fixture_responses(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Optional Playwright not installed")
        binary = os.environ.get("CHROMIUM") or shutil.which("chromium")
        if not binary:
            self.skipTest("Optional Chromium not installed")
        checks = []
        def check(name, condition):
            self.assertTrue(condition, name)
            checks.append(name)
        with tempfile.TemporaryDirectory() as temp:
            desk = Desk(Path(temp) / "desk.sqlite3")
            def mutate(operation, identity="", **body):
                return desk.mutate(operation, identity, {"operation_id": uuid.uuid4().hex, **body})
            mutate("catalog", items=[item(description='Fictitious <filter> & original label')])
            req = mutate("request", data=job(description='Replace <filter> & retain label'))
            req = mutate("option", req["id"], revision=req["revision"], catalog_id="CAT-001")
            req = mutate("review", req["options"][0]["id"], revision=req["revision"],
                         fit="compatible", technician="Example Technician", note="Fictitious fit exercise only")
            req = mutate("draft", req["id"], revision=req["revision"], option_id=req["options"][0]["id"])
            fixtures = {"/api/state": desk.state(), "/api/catalog?q=": desk.catalog(),
                        "/api/requests/" + req["id"]: req}
            # Fixtures were computed before browser start; no network bridge exists.
            script = """<script>
window.fixtureResponses = FIXTURES;
window.fixtureCalls = [];
window.fetch = async (url, options={}) => {
 window.fixtureCalls.push({url,options});
 if(options.method === 'POST') return {ok:false,status:409,json:async()=>({error:'Fixture stale revision: saved record preserved'})};
 if(!(url in window.fixtureResponses)) throw new Error('Unconfigured in-memory response: '+url);
 return {ok:true,status:200,json:async()=>structuredClone(window.fixtureResponses[url])};
};
if(!crypto.randomUUID) crypto.randomUUID = ()=> 'dom-fixture-operation';
</script>""".replace("FIXTURES", json.dumps(fixtures).replace("<", "\\u003c"))
            html = Path(__file__).with_name("index.html").read_text()
            with sync_playwright() as driver:
                browser = driver.chromium.launch(executable_path=binary, headless=True, args=["--no-sandbox"])
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.set_content(html.replace("<head>", "<head>" + script, 1))
                    page.locator(".job").wait_for()
                    check("saved job list", "1 saved jobs" in page.locator("#counts").inner_text())
                    page.locator(".job").click()
                    page.locator("#orders .order-total").wait_for()
                    check("saved form values", page.locator('[name="serial"]').input_value() == "6")
                    check("literal label rendering", "Fictitious <filter> & original label" in page.locator("#options").inner_text())
                    check("no label interpreted as element", page.locator("filter").count() == 0)
                    check("compatible badge", page.locator("#options .badge.good").inner_text() == "compatible")
                    check("exact displayed total", page.locator(".order-total").inner_text() == "USD 29.00")
                    check("source reference retained", page.locator("#options a.link").get_attribute("href") == item()["source_url"])
                    check("download points to real handoff route", page.locator("#orders a[download]").get_attribute("href").endswith("/handoff.txt"))
                    check("database backup route", page.locator('a[href="/api/backup"]').count() == 1)
                    page.locator("#options summary").click()
                    check("technician form value", page.locator('[data-review] [name="technician"]').input_value() == "Example Technician")
                    page.locator('[data-review] [name="note"]').fill("Edited DOM-only note")
                    page.locator("[data-review] button").click()
                    page.locator("#message .error").wait_for()
                    call = page.evaluate("window.fixtureCalls.filter(c=>c.options.method==='POST').at(-1)")
                    sent = json.loads(call["options"]["body"])
                    check("form submits revision and notes", sent["note"] == "Edited DOM-only note" and sent["revision"] == req["revision"])
                    check("conflict displayed without losing fields", "Fixture stale revision" in page.locator("#message").inner_text() and page.locator('[data-review] [name="note"]').input_value() == "Edited DOM-only note")
                    changed = mutate("request", req["id"], revision=req["revision"], data=job(serial="7"))
                    page.evaluate("v=>window.fixtureResponses['/api/requests/'+v.id]=v", changed)
                    page.locator("#reload").click()
                    page.wait_for_function("document.querySelector('#options').textContent.includes('request changed')")
                    check("changed request marks review stale", page.locator("#options .badge").inner_text() == "stale")
                    check("historical total retained", page.locator(".order-total").inner_text() == "USD 29.00")
                    page.screenshot(path=str(Path(temp) / "desktop.png"), full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    check("390px no horizontal overflow", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                    page.screenshot(path=str(Path(temp) / "mobile.png"), full_page=True)
                    page.emulate_media(media="print")
                    check("print hides editing controls", page.locator("#intake").is_hidden() and page.locator("aside").is_hidden())
                    check("print keeps handoff", page.locator("#orders").is_visible())
                    check("no uncaught script errors", not errors)
                    output = os.environ.get("DOM_SCREENSHOTS")
                    if output:
                        Path(output).mkdir(parents=True, exist_ok=True)
                        for name in ("desktop.png", "mobile.png"):
                            shutil.copyfile(Path(temp) / name, Path(output) / name)
                finally:
                    browser.close()
        print(json.dumps({"scope": "in-memory DOM fixtures; no browser network", "checks": len(checks), "passed": checks}))


if __name__ == "__main__":
    unittest.main()
