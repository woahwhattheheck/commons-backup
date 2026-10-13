import csv,hashlib,json,tempfile,unittest,xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from promotion_desk import build,qr_matrix,qr_words

BRAND={"business_name":"Juniper Corner","primary_color":"#F1C75B","secondary_color":"#FFF8E8"}
OFFERS=[{"offer_id":"lunch","slug":"weekday-lunch","headline":"Weekday Lunch","detail":"Soup and salad","price":"14.50","currency":"USD","starts_on":"2026-09-01","expires_on":"2026-09-30","terms":"Dine-in only."},{"offer_id":"summer","slug":"summer-supper","headline":"Summer Supper","detail":"Seasonal plate","price":"22.00","currency":"USD","starts_on":"2026-07-01","expires_on":"2026-08-31","terms":"While supplies last."}]
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.r=Path(self.t.name);self.b=self.r/"brand.json";self.o=self.r/"offers.json";self.out=self.r/"out"
  self.b.write_text(json.dumps(BRAND));self.o.write_text(json.dumps(OFFERS))
 def tearDown(self):self.t.cleanup()
 def make(self,day="2026-09-08"):return build(self.b,self.o,date.fromisoformat(day),"https://offers.example.test",self.out)
 def test_consistent_active_assets(self):
  self.make()
  for p in [self.out/"site/index.html",self.out/"site/offers/weekday-lunch.html",self.out/"social/lunch.svg",self.out/"print/lunch.svg"]:
   s=p.read_text();self.assertIn("Weekday Lunch",s);self.assertIn("$14.50",s);self.assertIn("2026-09-30",s)
 def test_expired_not_publishable(self):
  self.make();s="".join(p.read_text() for d in ("site","social","print","qr") for p in (self.out/d).rglob("*") if p.is_file())
  self.assertNotIn("Summer Supper",s);self.assertNotIn("$22.00",s)
  with (self.out/"expiry-calendar.csv").open() as f:rows={r["offer_id"]:r["status"] for r in csv.DictReader(f)}
  self.assertEqual(rows["summer"],"EXPIRED_REMOVED")
 def test_rerun_removes_stale_prices_and_assets(self):
  self.make();self.assertTrue((self.out/"social/lunch.svg").exists());self.make("2026-10-01")
  self.assertFalse((self.out/"social/lunch.svg").exists());self.assertNotIn("$14.50",(self.out/"site/index.html").read_text())
 def test_offer_change_refreshes_all_surfaces(self):
  self.make();ps=[self.out/"site/offers/weekday-lunch.html",self.out/"social/lunch.svg",self.out/"print/lunch.svg"];before=[hashlib.sha256(p.read_bytes()).digest() for p in ps]
  changed=[dict(x) for x in OFFERS];changed[0]["price"]="15.25";self.o.write_text(json.dumps(changed));self.make()
  self.assertTrue(all(a!=hashlib.sha256(p.read_bytes()).digest() for a,p in zip(before,ps)))
 def test_qr_structure(self):
  self.make();ET.parse(self.out/"qr/lunch.svg");m=qr_matrix("https://offers.example.test/weekday-lunch.html")
  self.assertEqual(len(m),37);self.assertEqual(len(qr_words("https://offers.example.test/weekday-lunch.html")),134);self.assertTrue(m[29][8])
 def test_manifest_is_unsent_and_source_linked(self):
  m=self.make();self.assertEqual(m["mode"],"LOCAL_EXPORT_ONLY_UNSENT");self.assertEqual(m["sources"][0]["sha256"],hashlib.sha256(self.b.read_bytes()).hexdigest())
 def test_invalid_price_slug_and_range(self):
  for key,val in (("price","1.999"),("slug","Bad Slug"),("expires_on","2026-08-01")):
   x=[dict(v) for v in OFFERS];x[0][key]=val;self.o.write_text(json.dumps(x))
   with self.assertRaises(ValueError):self.make()
 def test_html_escaped(self):
  x=[dict(v) for v in OFFERS];x[0]["headline"]="<script>x</script>";self.o.write_text(json.dumps(x));self.make();s=(self.out/"site/offers/weekday-lunch.html").read_text();self.assertNotIn("<script>",s)
if __name__=="__main__":unittest.main()
