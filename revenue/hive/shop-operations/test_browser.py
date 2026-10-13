"""Optional DOM tests with explicit fetch/UUID adapters; not native HTTP E2E."""
import json
import os
import shutil
from pathlib import Path
import unittest
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

CHROMIUM = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")

HTML = Path(__file__).with_name('desk.html').read_text(encoding='utf-8')
EMPTY = {table: [] for table in ('products','orders','lines','returns','return_lines','movements','receipts','stocktakes')}


@unittest.skipUnless(sync_playwright and CHROMIUM, "Optional Playwright and Chromium are needed")
class BrowserControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROMIUM, headless=True,
                                            args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':1280,'height':900})
        self.addCleanup(self.page.close)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        # These are test adapters: responses are fixtures, not server/network calls.
        init = '''<script>
        window.fixtureState=EMPTY;window.requests=[];window.nextError=null;
        let serial=0;Object.defineProperty(crypto,'randomUUID',{value:()=>`fixture-${++serial}`});
        window.fetch=async(url,options={})=>{
          if(options.method==='POST'){
            requests.push(JSON.parse(options.body));
            if(nextError==='lost'){nextError=null;throw Error('Fixture: response lost');}
            if(nextError==='conflict'){nextError=null;return{ok:false,status:409,json:async()=>({error:'Fixture stale version'})};}
            return{ok:true,status:200,json:async()=>({operation_key:requests.at(-1).key})};
          }
          return{ok:true,status:200,json:async()=>structuredClone(fixtureState)};
        };
        </script>'''.replace('EMPTY',json.dumps(EMPTY))
        self.page.set_content(HTML.replace('<script>', init+'<script>',1))
        self.page.wait_for_function("document.getElementById('status').textContent==='Workspace ready.'")

    def tearDown(self):
        self.assertEqual(self.errors, [])

    def wait_saved(self):
        self.page.wait_for_function("document.getElementById('status').textContent.startsWith('Saved:')")

    def test_product_form_types_and_reset_after_save(self):
        for key,value in dict(sku='FIX-1',title='Synthetic product',source_url='https://example.invalid/fixture',
                              description='Operator supplied fixture',price_minor='1250').items():
            self.page.locator('#'+key).fill(value)
        self.page.locator('#listing_state').select_option('ready')
        self.page.locator('#product-form button[type=submit]').click()
        self.wait_saved()
        payload = self.page.evaluate('requests[0]')
        self.assertEqual(payload['action'],'product')
        self.assertEqual(payload['data']['version'],0)
        self.assertEqual(payload['data']['price_minor'],1250)
        self.assertEqual(self.page.locator('#sku').input_value(),'')

    def test_order_form_compiles_multiple_lines_and_sample_kind(self):
        self.page.locator('#order-id').fill('sample-fixture')
        self.page.locator('#kind').select_option('sample')
        self.page.locator('#recipient_ref').fill('fixture-creator')
        self.page.locator('#order-lines').fill('SKU-A,2\nSKU-B,3')
        self.page.locator('#order-form button').click()
        self.wait_saved()
        data = self.page.evaluate('requests[0].data')
        self.assertEqual(data['kind'],'sample')
        self.assertEqual(data['lines'],[dict(sku='SKU-A',quantity=2),dict(sku='SKU-B',quantity=3)])

    def test_lost_response_retry_keeps_same_key_and_payload(self):
        self.page.evaluate("nextError='lost'")
        for key,value in [('receive-sku','FIX'),('receive-quantity','2'),('receive-reference','receipt-fixture')]:
            self.page.locator('#'+key).fill(value)
        self.page.locator('#receive-form button').click()
        self.page.wait_for_function("document.getElementById('status').textContent.includes('Result uncertain')")
        self.assertTrue(self.page.locator('#receive-form button').is_disabled())
        self.page.locator('#retry').click()
        self.wait_saved()
        requests = self.page.evaluate('requests')
        self.assertEqual(len(requests),2)
        self.assertEqual(requests[0],requests[1])
        self.assertTrue(self.page.locator('#retry').is_hidden())

    def test_conflict_retains_editable_form_and_clears_retry(self):
        self.page.evaluate("nextError='conflict'")
        for key,value in [('receive-sku','FIX'),('receive-quantity','2'),('receive-reference','receipt-fixture')]:
            self.page.locator('#'+key).fill(value)
        self.page.locator('#receive-form button').click()
        self.page.wait_for_function("document.getElementById('status').textContent.includes('stale version')")
        self.assertFalse(self.page.locator('#receive-form button').is_disabled())
        self.assertEqual(self.page.locator('#receive-sku').input_value(),'FIX')
        self.assertTrue(self.page.locator('#retry').is_hidden())

    def test_return_inspection_is_boolean_not_string(self):
        for key,value in [('return-id','ret-fixture'),('return-order','order-fixture'),('return-sku','FIX'),('return-quantity','1')]:
            self.page.locator('#'+key).fill(value)
        self.page.locator('#restock').select_option('false')
        self.page.locator('#return-form button').click()
        self.wait_saved()
        self.assertIs(self.page.evaluate('requests[0].data.restock'),False)

    def test_text_rendering_edit_version_and_mobile_layout(self):
        fixture = dict(sku='FIX',title='<b>literal title</b>',source_url='https://example.invalid/fixture',
                       description='Synthetic description',uncertainties='',price_minor=1250,currency='USD',
                       listing_state='ready',on_hand=5,reserved=2,available=3,version=7)
        self.page.evaluate('(p)=>{fixtureState.products=[p]}',fixture)
        self.page.locator('#refresh').click()
        self.page.wait_for_function("document.querySelectorAll('#products tr').length===1")
        self.assertIn('<b>literal title</b>',self.page.locator('#products').inner_text())
        self.assertEqual(self.page.locator('#products b').count(),0)
        self.page.locator('#products button').click()
        self.assertEqual(self.page.locator('#product-form input[name=version]').input_value(),'7')
        self.assertTrue(self.page.locator('#sku').evaluate('(e)=>e.readOnly'))
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))

    def test_catalog_import_reads_real_file_and_submits_exact_metadata(self):
        self.page.locator('summary').first.click()
        content = json.dumps([dict(sku='FIX',version=0,title='Fixture')])
        self.page.locator('#catalog-file').set_input_files(dict(name='fixture.json',mimeType='application/json',buffer=content.encode()))
        self.page.locator('#import').click()
        self.wait_saved()
        self.assertEqual(self.page.evaluate('requests[0].data.products'),json.loads(content))

    def count_fixture(self):
        fixture = dict(sku='COUNT-FIX',title='Synthetic counted item',source_url='https://example.invalid/fixture',
                       description='Fixture',uncertainties='',price_minor=100,currency='USD',
                       listing_state='ready',on_hand=5,reserved=0,available=5,version=7)
        self.page.evaluate('(p)=>{fixtureState.products=[p]}',fixture)
        self.page.locator('#count-sku').fill('COUNT-FIX')
        self.page.locator('#load-count').click()
        self.page.wait_for_function("document.getElementById('count-version').value==='7'")

    def test_physical_count_loads_version_submits_zero_and_resets(self):
        self.count_fixture()
        self.assertIn('on hand 5',self.page.locator('#count-baseline').inner_text())
        self.page.locator('#count-quantity').fill('0')
        self.page.locator('#count-reference').fill('fixture-count')
        self.page.locator('#count-note').fill('Synthetic count')
        self.page.get_by_role('button',name='Record physical count').click()
        self.wait_saved()
        request = self.page.evaluate('requests[0]')
        self.assertEqual(request['action'],'stocktake')
        self.assertEqual(request['data'],dict(sku='COUNT-FIX',version=7,quantity=0,
                         reference='fixture-count',note='Synthetic count'))
        self.assertEqual(self.page.locator('#count-version').input_value(),'')
        self.assertIn('Load the ledger',self.page.locator('#count-baseline').inner_text())
        self.assertEqual(self.page.locator('a[download="stock-counts.csv"]').get_attribute('href'),
                         '/export/stocktakes.csv')

    def test_refresh_does_not_silently_rebase_a_physical_count(self):
        self.count_fixture()
        self.page.evaluate('fixtureState.products[0].version=8')
        self.page.locator('#refresh').click()
        self.page.wait_for_function("document.getElementById('status').textContent==='Workspace refreshed.'")
        self.assertEqual(self.page.locator('#count-version').input_value(),'7')
        self.page.locator('#count-sku').fill('OTHER')
        self.assertEqual(self.page.locator('#count-version').input_value(),'')
        self.page.locator('#count-quantity').fill('2')
        self.page.locator('#count-reference').fill('fixture-count')
        self.page.get_by_role('button',name='Record physical count').click()
        self.assertEqual(self.page.evaluate('requests.length'),0)
        self.assertIn('Load the current ledger',self.page.locator('#status').inner_text())

    def test_missing_count_sku_clears_prior_version_without_mutation(self):
        self.count_fixture()
        self.page.locator('#count-sku').fill('MISSING')
        self.page.locator('#load-count').click()
        self.page.wait_for_function("document.getElementById('status').textContent==='Unknown SKU: MISSING'")
        self.assertEqual(self.page.locator('#count-version').input_value(),'')
        self.assertEqual(self.page.evaluate('requests.length'),0)

    def test_fulfillment_requires_reference_and_emits_selected_order(self):
        order=dict(id='order-fixture',kind='sale',recipient_ref='fixture',status='reserved',shipment_ref='')
        self.page.evaluate('(order)=>{fixtureState.orders=[order]}',order)
        self.page.locator('#refresh').click()
        self.page.wait_for_function("document.querySelectorAll('#orders tr').length===1")
        self.page.get_by_role('button',name='Record fulfillment').click()
        self.assertEqual(self.page.evaluate('requests.length'),0)
        self.page.get_by_label('Shipment reference for order-fixture').fill('handoff-fixture')
        self.page.get_by_role('button',name='Record fulfillment').click()
        self.wait_saved()
        self.assertEqual(self.page.evaluate('requests[0].data'),dict(id='order-fixture',shipment_ref='handoff-fixture'))


if __name__=='__main__':
    unittest.main(verbosity=2)
