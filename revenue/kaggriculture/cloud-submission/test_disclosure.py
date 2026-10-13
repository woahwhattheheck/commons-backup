import hashlib,io,json,tarfile,tempfile,unittest
from pathlib import Path
import disclosure

class DisclosureTests(unittest.TestCase):
    def test_archive_and_source_preserved_without_running_agent(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);p=d/'submission.tar.gz'
            contents={'main.py':b'raise AssertionError("candidate must not execute during preparation")\n','LICENSE':b'Synthetic test license\n','NOTICE.md':b'Synthetic test attribution\n'}
            with tarfile.open(p,'w:gz') as archive:
                for name,data in contents.items():
                    info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
            sha=hashlib.sha256(p.read_bytes()).hexdigest();disclosure.prepare(p,sha,d/'out','https://example.invalid/test-source')
            manifest=json.loads((d/'out/disclosure-manifest.json').read_text())
            notebook=json.loads((d/'out/frontier-source.ipynb').read_text())
            for name,data in contents.items():
                self.assertEqual(manifest['members'][name]['sha256'],hashlib.sha256(data).hexdigest())
                self.assertTrue(any(data.decode() in c['source'] for c in notebook['cells']))
            self.assertEqual(len([c for c in notebook['cells'] if c['cell_type']=='code']),1)
            self.assertEqual(json.loads((d/'out/kernel-metadata.json').read_text())['competition_sources'],['kaggriculture'])
            self.assertEqual(manifest['status'],'PREPARED_NOT_PUBLISHED')
if __name__=='__main__':unittest.main()
