"""Actual filesystem, SQLite, HTTP and FFmpeg regressions; no mocked media tools."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from http.client import HTTPConnection
import json
import math
from pathlib import Path
import struct
import tempfile
import threading
import unittest
import zipfile

import roughcut as c
from server import Store, Conflict, make_server


def fixture(path, *, audio=True, offset=0):
    args = ['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'lavfi', '-i',
            'testsrc2=size=320x180:rate=30:duration=6']
    if audio:
        expr = 'if(lt(t,1),0.25*sin(2*PI*440*t),if(lt(t,2),0,if(lt(t,3),0.25*sin(2*PI*660*t),if(lt(t,4),0,0.25*sin(2*PI*880*t)))))'
        if offset:
            args += ['-itsoffset', str(offset)]
        args += ['-f', 'lavfi', '-i', f"aevalsrc='{expr}':s=48000:d={6-offset}", '-map', '0:v', '-map', '1:a', '-c:a', 'aac']
    args += ['-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-threads', '2', str(path)]
    c.run(args, 60)


def sample_project(path):
    p = c.new_project(path, 'Synthetic cut regression')
    p['cues'] = c.parse_captions(json.dumps([
        {'start': 0, 'end': 1, 'text': 'Keep the original recording.'},
        {'start': 2, 'end': 3, 'text': 'Keep the original recording.'},
        {'start': 4, 'end': 6, 'text': 'Restore the cut without moving the remaining audio.'}
    ]), p['source']['frames'])
    return p


class PureTests(unittest.TestCase):
    def setUp(self):
        self.p = {'schema': 'roughcut/1', 'title': 'Example',
                  'source': {'frames': 180, 'fps': 30, 'sha256': 'a'*64, 'has_audio': True},
                  'cuts': [], 'cues': []}

    def test_uncut_mapping(self):
        t = c.timeline(self.p)
        self.assertEqual(t['output_frames'], 180)
        self.assertEqual(t['kept'], [{'source_start': 0, 'source_end': 180, 'output_start': 0, 'output_end': 180}])

    def test_overlap_union_and_restore(self):
        self.p['cuts'] = [c.cut(1, 3, 180, enabled=True), c.cut(2, 4, 180, enabled=True)]
        self.assertEqual(c.timeline(self.p)['output_frames'], 90)
        self.p['cuts'][0]['enabled'] = False
        self.assertEqual(c.timeline(self.p)['output_frames'], 120)
        self.p['cuts'][1]['enabled'] = False
        self.assertEqual(c.timeline(self.p)['output_frames'], 180)

    def test_boundaries_and_all_cut(self):
        self.p['cuts'] = [c.cut(0, 6, 180, enabled=True)]
        t = c.timeline(self.p)
        self.assertEqual(t['kept'], [])
        self.assertIn('Every source', t['warnings'][0])

    def test_adjacent_intervals_combine(self):
        self.p['cuts'] = [c.cut(0, 1, 180, enabled=True), c.cut(1, 2, 180, enabled=True)]
        self.assertEqual(c.timeline(self.p)['kept'][0]['source_start'], 60)

    def test_bad_shapes_and_nonfinite_inputs(self):
        for v in [True, None, [], {}, float('nan'), float('inf'), 10**1000]:
            with self.subTest(v=repr(v)[:30]), self.assertRaises(c.EditError):
                c.cut(v, 2, 180)
        for field, value in [('cuts', {}), ('cuts', [None]), ('cues', 'text'), ('title', [])]:
            p = deepcopy(self.p); p[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(c.EditError):
                c.validate(p)

    def test_duplicate_ids_and_outside_intervals(self):
        item = c.cut(0, 1, 180)
        self.p['cuts'] = [item, deepcopy(item)]
        with self.assertRaises(c.EditError): c.validate(self.p)
        self.p['cuts'] = [item]; item['end'] = 181
        with self.assertRaises(c.EditError): c.validate(self.p)
        item['end'] = 30; item['start'] = False
        with self.assertRaises(c.EditError): c.validate(self.p)

    def test_srt_vtt_unicode_import(self):
        for text in ['1\r\n00:00:01,000 --> 00:00:02,500\r\nCafé 東京\r\nSecond line',
                     'WEBVTT\n\nid\n00:01.000 --> 00:02.500 align:start\nCafé 東京\nSecond line']:
            cues = c.parse_captions(text, 180)
            self.assertEqual((cues[0]['start'], cues[0]['end']), (30, 75))
            self.assertEqual(cues[0]['text'], 'Café 東京\nSecond line')

    def test_caption_rejection(self):
        for text in ['nonsense', '[null]', '[{"start":NaN,"end":1,"text":"x"}]',
                     '[{"start":1,"end":9,"text":"x"}]', '00:70.000 --> 00:71.000\nx',
                     '[{"start":0,"end":0.001,"text":"x"}]']:
            with self.subTest(text=text), self.assertRaises(c.EditError):
                c.parse_captions(text, 180)

    def test_partial_caption_warning_and_restoration(self):
        self.p['cues'] = c.parse_captions('[{"start":0,"end":3,"text":"The full original phrase"}]', 180)
        self.p['cuts'] = [c.cut(1, 2, 180, enabled=True)]
        t = c.timeline(self.p)
        self.assertEqual([(r['start'], r['end']) for r in t['captions']], [(0,30),(30,60)])
        self.assertTrue(all(r['review_required'] for r in t['captions']))
        self.p['cuts'][0]['enabled'] = False
        t = c.timeline(self.p)
        self.assertFalse(t['captions'][0]['review_required'])
        self.assertEqual(t['captions'][0]['end'], 90)

    def test_caption_cut_entirely_removed(self):
        self.p['cues'] = c.parse_captions('[{"start":1,"end":2,"text":"Cut this"}]', 180)
        self.p['cuts'] = [c.cut(1,2,180,enabled=True)]
        self.assertEqual(c.timeline(self.p)['captions'], [])
        self.assertEqual(self.p['cues'][0]['text'], 'Cut this')

    def test_repeat_suggestions_disabled_and_literal(self):
        self.p['cues'] = c.parse_captions(json.dumps([
            {'start':0,'end':1,'text':'Keep the original source file.'},
            {'start':1,'end':2,'text':'KEEP the original source file!'},
            {'start':2,'end':3,'text':'Keep your original source file.'}]),180)
        suggestions = c.repeated_takes(self.p)
        self.assertEqual(len(suggestions),1)
        self.assertFalse(suggestions[0]['enabled'])
        self.assertEqual(suggestions[0]['start'],0)

    def test_captions_escaping_and_hour_stamps(self):
        self.p['cues'] = c.parse_captions('[{"start":0,"end":1,"text":"<b> & title"}]',180)
        text = c.captions_text(c.timeline(self.p))
        self.assertIn('&lt;b&gt; &amp; title', text)
        self.assertTrue(text.startswith('WEBVTT\n'))
        self.assertEqual(c.stamp(108001), '01:00:00.033')
        self.assertIn('00:00:00,000 --> 00:00:01,000', c.captions_text(c.timeline(self.p),srt=True))


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root/'original.mp4'
        fixture(cls.source)
        cls.project = sample_project(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_probe_real_source(self):
        self.assertEqual(self.project['source']['frames'],180)
        self.assertTrue(self.project['source']['has_audio'])
        self.assertEqual(self.project['source']['sha256'],c.digest(self.source))

    def test_real_silence_detection(self):
        suggestions = c.silence_suggestions(self.source,self.project)
        self.assertEqual(len(suggestions),2)
        self.assertTrue(all(not s['enabled'] for s in suggestions))
        self.assertAlmostEqual(suggestions[0]['start']/30,1.15,delta=.06)
        self.assertAlmostEqual(suggestions[1]['end']/30,3.85,delta=.06)

    def test_actual_render_caption_sync_restore_and_source(self):
        p=deepcopy(self.project)
        p['cuts']=[c.cut(1,2,180,enabled=True),c.cut(3,4,180,enabled=True)]
        before=c.digest(self.source)
        packet=self.root/'packet'
        t=c.export_bundle(self.source,p,packet)
        self.assertEqual(t['output_frames'],120)
        self.assertEqual([(r['start'],r['end']) for r in t['captions']],[(0,30),(30,60),(60,120)])
        metadata=c.probe(packet/'roughcut.mp4')
        self.assertEqual(metadata['frames'],120)
        self.assertAlmostEqual(metadata['duration'],4,places=3)
        manifest=json.loads((packet/'manifest.json').read_text())
        for name,sha in manifest.items(): self.assertEqual(c.digest(packet/name),sha)
        with zipfile.ZipFile(packet/'editable-export.zip') as z:
            self.assertIn('roughcut.mp4',z.namelist())
            self.assertEqual(json.loads(z.read('project.json')),p)
        # Inspect actual decoded audio, not just MP4 metadata: distinct source tones
        # must occur at the new segment positions after both cuts.
        pcm=self.root/'decoded.f32'
        c.run(['ffmpeg','-v','error','-y','-i',str(packet/'roughcut.mp4'),'-vn','-ac','1','-ar','48000','-f','f32le',str(pcm)])
        raw=pcm.read_bytes(); samples=struct.unpack('<'+'f'*(len(raw)//4),raw)
        for start,hz in [(0.2,440),(1.2,660),(2.2,880)]:
            portion=samples[round(start*48000):round((start+.25)*48000)]
            crosses=sum(a<=0<b for a,b in zip(portion,portion[1:]))/.25
            self.assertAlmostEqual(crosses,hz,delta=8)
        p['cuts'][0]['enabled']=False
        c.render(self.source,p,self.root/'restored.mp4')
        self.assertEqual(c.probe(self.root/'restored.mp4')['frames'],150)
        self.assertEqual(c.digest(self.source),before)
        self.assertEqual(c.timeline(p)['captions'][1]['start'],60)

    def test_silent_source(self):
        source=self.root/'silent.mp4';fixture(source,audio=False)
        p=c.new_project(source);output=self.root/'silent-export.mp4'
        c.render(source,p,output)
        self.assertTrue(c.probe(output)['has_audio'])
        self.assertEqual(c.probe(output)['frames'],180)
        self.assertIn('no audio',c.timeline(p)['warnings'][0])

    def test_positive_audio_offset_retained(self):
        source=self.root/'offset.mp4';fixture(source,offset=.4)
        p=c.new_project(source);output=self.root/'offset-export.mp4'
        c.render(source,p,output)
        rawpath=self.root/'offset.f32'
        c.run(['ffmpeg','-v','error','-y','-i',str(output),'-vn','-ac','1','-f','f32le',str(rawpath)])
        raw=rawpath.read_bytes();samples=struct.unpack('<'+'f'*(len(raw)//4),raw)
        rms=lambda a,b:math.sqrt(sum(x*x for x in samples[int(a*48000):int(b*48000)])/int((b-a)*48000))
        self.assertLess(rms(.1,.25),.001)
        self.assertGreater(rms(.5,.7),.05)

    def test_changed_original_rejected_before_output(self):
        altered=self.root/'altered.mp4';altered.write_bytes(self.source.read_bytes()+b'changed')
        output=self.root/'not-rendered.mp4'
        with self.assertRaises(c.EditError):c.render(altered,self.project,output)
        self.assertFalse(output.exists())

    def test_existing_output_never_replaced(self):
        output=self.root/'existing.mp4';output.write_bytes(b'keep me')
        with self.assertRaises(c.EditError):c.render(self.source,self.project,output)
        self.assertEqual(output.read_bytes(),b'keep me')

    def test_all_cut_fails_without_packet(self):
        p=deepcopy(self.project);p['cuts']=[c.cut(0,6,180,enabled=True)]
        output=self.root/'empty-packet'
        with self.assertRaises(c.EditError):c.export_bundle(self.source,p,output)
        self.assertFalse(output.exists())


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_tmp=tempfile.TemporaryDirectory();cls.source=Path(cls.media_tmp.name)/'source.mp4';fixture(cls.source)
    @classmethod
    def tearDownClass(cls):cls.media_tmp.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'workspace')
        self.snap=self.store.create(self.source,'my original.mp4');self.ident=self.snap['id']

    def test_reopen_and_history_restore(self):
        newer=self.store.update(self.ident,1,{'cuts':[c.cut(1,2,180,enabled=True)]})
        self.assertEqual(newer['timeline']['output_frames'],150)
        reopened=Store(self.store.root)
        self.assertEqual(reopened.get(self.ident)['revision'],2)
        old=reopened.get(self.ident,1)
        restored=reopened.update(self.ident,2,{'cuts':old['project']['cuts']})
        self.assertEqual(restored['timeline']['output_frames'],180)
        self.assertEqual(len(reopened.history(self.ident)),3)
        self.assertEqual(c.digest(reopened.source(self.ident)),c.digest(self.source))

    def test_stale_concurrent_save_one_winner(self):
        barrier=threading.Barrier(2)
        def save(title):
            barrier.wait()
            try:return self.store.update(self.ident,1,{'title':title})['revision']
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            values=list(pool.map(save,['one','two']))
        self.assertCountEqual(values,[2,'conflict'])
        self.assertEqual(len(self.store.history(self.ident)),2)

    def test_source_metadata_cannot_be_changed(self):
        with self.assertRaises(c.EditError):self.store.update(self.ident,1,{'source':{}})
        self.assertEqual(self.store.get(self.ident)['revision'],1)

    def test_invalid_revision_and_cut_preserve_saved_state(self):
        for expected in [True,None,1.1]:
            with self.assertRaises(c.EditError):self.store.update(self.ident,expected,{})
        with self.assertRaises(c.EditError):self.store.update(self.ident,1,{'cuts':[{}]})
        self.assertEqual(len(self.store.history(self.ident)),1)

    def test_real_http_upload_range_save_transcript_export(self):
        http=make_server(self.store,0)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        def req(method,path,data=None,headers=None):
            conn=HTTPConnection('127.0.0.1',http.server_address[1],timeout=30)
            try:
                conn.request(method,path,body=data,headers=headers or {})
                response=conn.getresponse();body=response.read()
                return response.status,dict(response.getheaders()),body
            finally:conn.close()
        code,_,body=req('POST','/api/upload',self.source.read_bytes(),{'X-Filename':'uploaded.mp4'})
        self.assertEqual(code,201);snap=json.loads(body);prefix='/api/projects/'+snap['id']
        code,headers,body=req('GET',prefix+'/source',headers={'Range':'bytes=3-15'})
        self.assertEqual(code,206);self.assertEqual(body,self.source.read_bytes()[3:16])
        self.assertIn('bytes 3-15/',headers['Content-Range'])
        code,_,body=req('GET',prefix+'/source',headers={'Range':'bytes=-11'})
        self.assertEqual(code,206);self.assertEqual(body,self.source.read_bytes()[-11:])
        self.assertEqual(req('GET',prefix+'/source',headers={'Range':'bytes=999999999-'} )[0],416)
        payload=json.dumps({'expected_revision':1,'changes':{'cuts':[c.cut(1,2,180,enabled=True)]}})
        self.assertEqual(req('POST',prefix+'/save',payload)[0],200)
        self.assertEqual(req('POST',prefix+'/save',payload)[0],409)
        transcript=json.dumps({'expected_revision':2,'text':'1\n00:00:02,000 --> 00:00:03,000\nWords from source'})
        self.assertEqual(req('POST',prefix+'/transcript',transcript)[0],200)
        code,_,body=req('POST',prefix+'/export',json.dumps({'revision':3}))
        self.assertEqual(code,201,body);export=json.loads(body)
        self.assertEqual(export['timeline']['output_frames'],150)
        self.assertEqual(export['timeline']['captions'][0]['start'],30)
        code,_,body=req('GET',export['zip'])
        self.assertEqual(code,200);self.assertTrue(body.startswith(b'PK'))
        self.assertEqual(req('POST',prefix+'/save','[]')[0],400)
        self.assertEqual(req('GET','/api/projects/../../etc/passwd')[0],400)
        self.assertEqual(req('GET','/')[0],200)


if __name__=='__main__':unittest.main(verbosity=2)
