"""Local patch preparation tests. Not execution of upstream compiler suites."""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
import prepare_native_fixture_patch as native
import make_saved_draft_fix as reference

ROOT = Path(__file__).resolve().parent

NODE_SEAMS = '''function deferred() { let resolve; const promise = new Promise(r => resolve=r); return {promise, resolve}; }
function jsonFile(value) {
  const contents = JSON.stringify(value);
  return { size: Buffer.byteLength(contents), text: async () => contents };
}
function delayedFile(value) {
  const wait = deferred();
  const contents = JSON.stringify(value);
  return { file: { size: Buffer.byteLength(contents), text: () => wait.promise }, finish: () => wait.resolve(contents) };
}
const sandbox = { Blob, TextEncoder, URLSearchParams, };
'''
BROWSER_SEAMS = '''# Hold the browser's actual File.text await, then resolve it explicitly.
const original = File.prototype.text;
File.prototype.text = function () {
    if (this.name !== 'delayed-draft.json') return original.call(this);
};
'''

class PatchPreparationTests(unittest.TestCase):
    def test_production_patch_applies_to_exact_reviewed_app(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / native.PREFIX / 'app.js'
            path.parent.mkdir(parents=True)
            original = (ROOT / 'composed_app.js').read_bytes()
            self.assertEqual(native.git_blob(original), '808a89401a7978c4897feb351aee231adcba8dd6')
            path.write_bytes(original)
            expected, patch = reference.derive(original)
            retained = (ROOT/'saved_draft_complete.patch').read_text().split('--- a/revenue/uiowa_rfq_18649_workbench/test_app.js')[0]
            self.assertEqual(patch, retained)
            patch_path = root/'reference.patch'
            patch_path.write_bytes(patch.encode('utf-8'))
            subprocess.run(['git','apply','--check',str(patch_path)],cwd=root,check=True,capture_output=True)
            subprocess.run(['git','apply',str(patch_path)],cwd=root,check=True,capture_output=True)
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(native.git_blob(expected), reference.FIXED_BLOB)

    def test_normal_and_delayed_node_doubles_return_exact_bytes(self):
        source = native.rewrite('test_app.js', NODE_SEAMS)
        checks = r'''
(async () => {
  const value = {note: "café / 観察 / 🧪 / �"};
  const original = JSON.stringify(value);
  const immediate = jsonFile(value);
  const delay = delayedFile(value);
  const pending = delay.file.arrayBuffer();
  delay.finish();
  for (const bytes of [await immediate.arrayBuffer(), await pending]) {
    if (Object.prototype.toString.call(bytes) !== "[object ArrayBuffer]") throw Error("Not ArrayBuffer");
    if (new TextDecoder("utf8", {fatal:true}).decode(bytes) !== original) throw Error("Not exact bytes");
  }
  if (await immediate.text() !== original) throw Error("Candidate text double changed");
  if (sandbox.TextDecoder !== TextDecoder) throw Error("Missing decoder in VM sandbox");
})().catch(e => {console.error(e); process.exitCode=1});
'''
        result=subprocess.run(['node','-e',source+checks],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_browser_delay_seam_tracks_new_io_api(self):
        result = native.rewrite('browser_resume_acceptance.py', BROWSER_SEAMS)
        self.assertNotIn('File.prototype.text', result)
        self.assertEqual(result.count('File.prototype.arrayBuffer'),2)

    def test_unknown_or_ambiguous_replacement_refused(self):
        for source in ['', NODE_SEAMS+NODE_SEAMS]:
            with self.assertRaises(ValueError): native.rewrite('test_app.js',source)
        with self.assertRaises(ValueError): native.rewrite('other.py','')

    def test_drifted_checkout_is_not_modified(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root/native.PREFIX/'test_app.js'
            path.parent.mkdir(parents=True)
            path.write_text(NODE_SEAMS)
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'differs from the reviewed'):
                native.prepare(root)
            self.assertEqual(path.read_bytes(),before)

    def test_repair_only_touches_saved_import(self):
        before = (ROOT/'composed_app.js').read_text()
        after = reference.derive((ROOT/'composed_app.js').read_bytes())[0].decode('utf-8')
        left,rest=before.split('async function importDraft()',1)
        new_left,new_rest=after.split('async function importDraft()',1)
        self.assertEqual(left,new_left)
        self.assertEqual(rest.split('// Export projection',1)[1],new_rest.split('// Export projection',1)[1])
        self.assertIn('new TextDecoder("utf-8", { fatal: true })',new_rest)

if __name__=='__main__': unittest.main(verbosity=2)
