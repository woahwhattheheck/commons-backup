#!/usr/bin/env python3
"""Create an original synthetic-voice episode and frame-exact transcript timings."""
import argparse
import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

SCRIPT = [
    ('Begin with the source', 'Welcome to the Source First Studio. This is an original synthetic voice demonstration, not a customer recording. Today we are turning one short conversation into an editable content folder.'),
    ('Keep a reversible copy', 'Start by keeping the original recording unchanged. Give the episode a clear title and record its duration. Put your transcript beside the recording, so an editor can always return to the source.'),
    ('Mark the moments', 'Divide the transcript into complete thoughts. Add the start and end time for each thought, and check names against the audio. A timestamp is a navigation aid, not a claim that the words have been verified.'),
    ('Build distinct excerpts', 'Choose different source passages for different posts. Keep quotations separate from your own introduction. When you add context, make it clear which words came from the episode and which words are your editorial work.'),
    ('Preserve revisions', 'Save your edited newsletter and show notes before moving on. When the source changes, keep the old drafts visible and mark them for review. Do not quietly replace a paragraph someone has already edited.'),
    ('Hand off working files', 'Finish by exporting the original recording, timestamped transcript, chapters, show notes, newsletter, and five post drafts. Open the folder, review every excerpt, and adapt the working files for your own publishing workflow.'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'data' / 'demo')
    args = parser.parse_args()
    espeak = shutil.which('espeak') or shutil.which('espeak-ng')
    if not espeak:
        parser.error('optional original-voice demo requires espeak or espeak-ng; the workspace itself does not')
    args.output.mkdir(parents=True, exist_ok=True)
    chunks, segments, chapters, frames = [], [], [], 0
    params = None
    with tempfile.TemporaryDirectory() as tmp:
        for i, (heading, sentence) in enumerate(SCRIPT, 1):
            target = Path(tmp) / f'{i}.wav'
            subprocess.run([espeak, '-s', '155', '-w', str(target), sentence], check=True, capture_output=True, timeout=30)
            with wave.open(str(target), 'rb') as source:
                current = (source.getnchannels(), source.getsampwidth(), source.getframerate())
                if params is not None and params != current:
                    raise RuntimeError('speech engine changed audio format between segments')
                params = current
                count = source.getnframes()
                audio = source.readframes(count)
            start, end = frames / params[2], (frames + count) / params[2]
            segments.append({'id': f's{i}', 'start': start, 'end': end,
                             'speaker': 'Synthetic studio voice', 'text': sentence, 'verified': False})
            chapters.append({'start': start, 'title': heading})
            gap = round(params[2] * 0.5)
            chunks.extend([audio, b'\x00' * gap * params[0] * params[1]])
            frames += count + gap
    media = args.output / 'source-first-demo.wav'
    with wave.open(str(media), 'wb') as output:
        output.setnchannels(params[0]); output.setsampwidth(params[1]); output.setframerate(params[2])
        for chunk in chunks:
            output.writeframesraw(chunk)
    doc = {'title': 'Source First Studio — an original workflow demonstration',
           'description': 'Six practical source-editing steps. Original scripted synthetic voice made by eSpeak; no real speaker or customer.',
           'duration': frames / params[2], 'synthetic_demo': True, 'segments': segments, 'chapters': chapters}
    document = args.output / 'transcript.json'
    document.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'document': str(document), 'media': str(media), 'duration_seconds': doc['duration'], 'segments': len(segments)}))


if __name__ == '__main__':
    main()
