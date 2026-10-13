#!/usr/bin/env python3
"""Reversible, source-bound rough cuts. Requires ffmpeg and ffprobe on PATH."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile

FPS = 30
RATE = 48000
SAMPLES_PER_FRAME = RATE // FPS
MAX_CUTS = 128
MAX_CUES = 10000


class EditError(ValueError):
    """A media/input/edit error suitable for presentation to the operator."""


def run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EditError(f"Media command did not finish: {exc}") from exc
    if result.returncode:
        raise EditError(f"{Path(args[0]).name} failed: {result.stderr[-3000:]}")
    return result


def digest(path: Path) -> str:
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EditError(f"{label} must be a number")
    try:
        n = float(value)
    except (OverflowError, ValueError) as exc:
        raise EditError(f"{label} must be finite") from exc
    if not math.isfinite(n):
        raise EditError(f"{label} must be finite")
    return n


def frame(value, label: str) -> int:
    if type(value) is not int:
        raise EditError(f"{label} must be an integer frame number")
    return value


def probe(path: Path) -> dict:
    data = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                           '-of', 'json', str(path)], 60).stdout)
    videos = [s for s in data.get('streams', []) if s.get('codec_type') == 'video'
              and not s.get('disposition', {}).get('attached_pic')]
    if not videos:
        raise EditError('A video stream is required')
    video = videos[0]
    # Attached cover pictures ahead of the video are not supported by the render map.
    first_video = next(s for s in data['streams'] if s.get('codec_type') == 'video')
    if video['index'] != first_video['index']:
        raise EditError('Remove the attached cover picture before importing this video')
    try:
        start = float(video.get('start_time', 0))
        duration = float(video.get('duration', data.get('format', {}).get('duration', 0)))
    except (ValueError, TypeError) as exc:
        raise EditError('Video duration/start time is unavailable') from exc
    if not math.isfinite(duration) or not 0 < duration <= 3600 or not math.isfinite(start):
        raise EditError('Import a video with a finite duration of at most one hour')
    width, height = int(video['width']), int(video['height'])
    if width < 2 or height < 2 or width * height > 3840 * 2160:
        raise EditError('Video must be between 2x2 and 3840x2160 pixels')
    return {'duration': duration, 'frames': math.ceil(duration * FPS - 1e-7),
            'fps': FPS, 'video_start': start, 'width': width, 'height': height,
            'has_audio': any(s.get('codec_type') == 'audio' for s in data['streams']),
            'sha256': digest(path), 'bytes': path.stat().st_size}


def new_project(path: Path, title: str = '') -> dict:
    source = probe(path)
    source['name'] = path.name
    return {'schema': 'roughcut/1', 'title': title or path.stem, 'source': source,
            'cuts': [], 'cues': []}


def validate(project: dict) -> dict:
    if not isinstance(project, dict) or project.get('schema') != 'roughcut/1':
        raise EditError('Expected a roughcut/1 project')
    if not isinstance(project.get('title'), str) or len(project['title']) > 300:
        raise EditError('Title must be text, at most 300 characters')
    source = project.get('source')
    if not isinstance(source, dict) or source.get('fps') != FPS:
        raise EditError('Project source must use the 30 fps edit grid')
    total = frame(source.get('frames'), 'source.frames')
    if not 0 < total <= 3600 * FPS or not re.fullmatch(r'[a-f0-9]{64}', str(source.get('sha256', ''))):
        raise EditError('Invalid source duration or SHA-256')
    for field, maximum in [('cuts', MAX_CUTS), ('cues', MAX_CUES)]:
        rows = project.get(field)
        if not isinstance(rows, list) or len(rows) > maximum:
            raise EditError(f'{field} must be an array with at most {maximum} entries')
        ids = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'] or len(row['id']) > 100:
                raise EditError(f'{field} entries require a nonempty text id')
            if row['id'] in ids:
                raise EditError(f'Duplicate {field} id: {row["id"]}')
            ids.add(row['id'])
            a, b = frame(row.get('start'), 'start'), frame(row.get('end'), 'end')
            if not 0 <= a < b <= total:
                raise EditError(f'{field} interval must be within source frames 0..{total}')
            if field == 'cuts':
                if type(row.get('enabled')) is not bool:
                    raise EditError('Cut enabled must be true or false')
                if not isinstance(row.get('reason', ''), str) or len(row.get('reason', '')) > 2000:
                    raise EditError('Cut reason must be text, at most 2000 characters')
            elif not isinstance(row.get('text'), str) or not row['text'].strip() or len(row['text']) > 10000:
                raise EditError('Caption text must be nonempty and at most 10000 characters')
    return project


def cut(start: float, end: float, total: int, *, reason='Manual cut', enabled=False, kind='manual') -> dict:
    a = max(0, min(total, round(number(start, 'start') * FPS)))
    b = max(0, min(total, round(number(end, 'end') * FPS)))
    if a >= b:
        raise EditError('Cut must cover at least one frame within the source')
    return {'id': uuid.uuid4().hex, 'start': a, 'end': b, 'enabled': enabled,
            'kind': kind, 'reason': reason}


def timeline(project: dict) -> dict:
    validate(project)
    total = project['source']['frames']
    intervals = sorted((r['start'], r['end']) for r in project['cuts'] if r['enabled'])
    merged = []
    for a, b in intervals:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    kept, source_pos, output_pos = [], 0, 0
    for a, b in merged + [[total, total]]:
        if source_pos < a:
            kept.append({'source_start': source_pos, 'source_end': a,
                         'output_start': output_pos, 'output_end': output_pos + a - source_pos})
            output_pos += a - source_pos
        source_pos = b
    warnings = []
    if not kept:
        warnings.append('Every source frame is cut. Restore at least one interval before rendering.')
    if not project['source'].get('has_audio'):
        warnings.append('The source has no audio; export contains a silent audio track.')
    captions = []
    for cue in project['cues']:
        pieces = []
        for k in kept:
            a, b = max(cue['start'], k['source_start']), min(cue['end'], k['source_end'])
            if a < b:
                pieces.append((a, b, k))
        partial = bool(pieces) and sum(b-a for a, b, _ in pieces) != cue['end'] - cue['start']
        if partial:
            warnings.append(f"Caption {cue['id']} crosses a cut: review wording; no word-level timing is inferred.")
        for a, b, k in pieces:
            captions.append({'id': cue['id'], 'start': k['output_start'] + a - k['source_start'],
                             'end': k['output_start'] + b - k['source_start'], 'text': cue['text'],
                             'review_required': partial, 'source_start': a, 'source_end': b})
    return {'schema': 'roughcut-timeline/1', 'fps': FPS, 'sample_rate': RATE,
            'source_sha256': project['source']['sha256'], 'source_frames': total,
            'output_frames': output_pos, 'removed_frames': total-output_pos,
            'kept': kept, 'captions': sorted(captions, key=lambda c: (c['start'], c['end'])),
            'warnings': warnings}


def timestamp(text: str) -> float:
    parts = text.replace(',', '.').split(':')
    if len(parts) not in (2, 3):
        raise EditError(f'Invalid caption timestamp: {text}')
    try:
        values = [float(p) for p in parts]
    except ValueError as exc:
        raise EditError(f'Invalid caption timestamp: {text}') from exc
    if not all(math.isfinite(v) and v >= 0 for v in values) or values[-1] >= 60 or values[-2] >= 60:
        raise EditError(f'Invalid caption timestamp: {text}')
    return sum(v * 60**i for i, v in enumerate(reversed(values)))


def parse_captions(text: str, total: int) -> list[dict]:
    """Import basic SRT/WebVTT or [{start: seconds, end: seconds, text: ...}]."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > 5_000_000:
        raise EditError('Transcript must be text, at most 5 MB')
    text = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return []
    if text.startswith('['):
        try:
            rows = json.loads(text)
        except (ValueError, RecursionError) as exc:
            raise EditError('Invalid transcript JSON') from exc
        if not isinstance(rows, list):
            raise EditError('Transcript JSON must be an array')
    else:
        rows = []
        for block in re.split(r'\n\s*\n', text):
            lines = block.splitlines()
            if not lines or lines[0].startswith(('WEBVTT', 'NOTE', 'STYLE', 'REGION')):
                continue
            timing = next((i for i, line in enumerate(lines) if '-->' in line), None)
            if timing is None:
                raise EditError('Every caption block must contain a timestamp arrow')
            left, right = lines[timing].split('-->', 1)
            rows.append({'start': timestamp(left.strip()), 'end': timestamp(right.strip().split()[0]),
                         'text': '\n'.join(lines[timing+1:])})
    if len(rows) > MAX_CUES:
        raise EditError(f'Transcript exceeds {MAX_CUES} cues')
    cues = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise EditError('Each caption must be an object')
        a, b = number(row.get('start'), 'caption.start'), number(row.get('end'), 'caption.end')
        if not 0 <= a < b <= total / FPS + 1e-6:
            raise EditError('Caption time is outside the source')
        cue = {'id': f'cue-{i+1}', 'start': round(a * FPS), 'end': min(total, round(b * FPS)),
               'text': row.get('text')}
        if cue['start'] >= cue['end'] or not isinstance(cue['text'], str) or not cue['text'].strip() or len(cue['text']) > 10000:
            raise EditError('Each caption needs text and at least one frame')
        cues.append(cue)
    return cues


def repeated_takes(project: dict) -> list[dict]:
    validate(project)
    seen, suggestions = {}, []
    for cue in sorted(project['cues'], key=lambda c: (c['start'], c['end'])):
        key = ' '.join(re.findall(r'\w+', cue['text'].casefold()))
        if len(key.split()) >= 4 and len(key) >= 12:
            prior = seen.get(key)
            if prior is not None and prior['end'] <= cue['start']:
                suggestions.append({'id': uuid.uuid4().hex, 'start': prior['start'], 'end': prior['end'],
                                    'enabled': False, 'kind': 'repeated_take',
                                    'reason': f"Exact transcript repeat before {cue['start']/FPS:.3f}s; review in context."})
            seen[key] = cue
    return suggestions[:MAX_CUTS]


def verify_source(path: Path, project: dict) -> None:
    validate(project)
    if digest(path) != project['source']['sha256']:
        raise EditError('Original source bytes changed; re-import instead of applying this timeline')


def silence_suggestions(path: Path, project: dict, noise_db=-35, minimum=0.65, padding=0.15) -> list[dict]:
    verify_source(path, project)
    noise_db, minimum, padding = number(noise_db, 'noise_db'), number(minimum, 'minimum'), number(padding, 'padding')
    if not -90 <= noise_db <= -10 or not 0.2 <= minimum <= 30 or not 0 <= padding <= 2:
        raise EditError('Silence settings: -90..-10 dB, 0.2..30s minimum, 0..2s padding')
    if not project['source']['has_audio']:
        return []
    s = project['source']
    audio = (f"asetpts=PTS-({s['video_start']:.9f})/TB,aresample={RATE}:async=1:first_pts=0,"
             f"apad,atrim=end_sample={s['frames']*SAMPLES_PER_FRAME},"
             f"silencedetect=noise={noise_db}dB:d={minimum}")
    result = run(['ffmpeg', '-hide_banner', '-nostdin', '-copyts', '-i', str(path),
                  '-map', '0:a:0', '-af', audio, '-f', 'null', '-'])
    events = re.findall(r'silence_(start|end):\s*(-?\d+(?:\.\d+)?)', result.stderr)
    start, intervals = None, []
    for typ, value in events:
        point = float(value)
        if typ == 'start':
            start = point
        elif start is not None:
            intervals.append((start, point))
            start = None
    if start is not None:
        intervals.append((start, s['frames']/FPS))
    result = []
    for a, b in intervals:
        a, b = max(0, a+padding), min(s['frames']/FPS, b-padding)
        if b-a >= 0.1:
            result.append(cut(a, b, s['frames'], reason=f'Silence below {noise_db:g} dB; review breathing and context.', kind='silence'))
    return result[:MAX_CUTS]


def stamp(frames: int, comma=False) -> str:
    ms = round(frames * 1000 / FPS)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{"," if comma else "."}{ms:03}'


def captions_text(t: dict, *, srt=False) -> str:
    out = [] if srt else ['WEBVTT', '']
    for i, c in enumerate(t['captions'], 1):
        # Prevent user text from becoming WebVTT markup or terminating a cue block.
        text = c['text'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        text = '\n'.join(line if line.strip() else ' ' for line in text.splitlines())
        out.extend([str(i), f"{stamp(c['start'], srt)} --> {stamp(c['end'], srt)}", text, ''])
    return '\n'.join(out) + '\n'


def render(path: Path, project: dict, destination: Path) -> dict:
    verify_source(path, project)
    t = timeline(project)
    if not t['kept']:
        raise EditError(t['warnings'][0])
    if destination.exists():
        raise EditError('Render destination already exists; choose a new filename')
    destination.parent.mkdir(parents=True, exist_ok=True)
    total, output = t['source_frames'], t['output_frames']
    selection = '+'.join(f"between(n,{k['source_start']},{k['source_end']-1})" for k in t['kept'])
    filters = [f"[0:v:0]setpts=PTS-STARTPTS,fps={FPS},tpad=stop_mode=clone:stop_duration=1,"
               f"trim=end_frame={total},select='{selection}',settb=1/{FPS},setpts=N,"
               "scale=trunc(iw/2)*2:trunc(ih/2)*2[v]"]
    count = len(t['kept'])
    if project['source']['has_audio']:
        labels = ''.join(f'[s{i}]' for i in range(count))
        start = number(project['source'].get('video_start'), 'video_start')
        filters.append(f'[0:a:0]asetpts=PTS-({start:.9f})/TB,aresample={RATE}:async=1:first_pts=0,'
                       f'apad,atrim=end_sample={total*SAMPLES_PER_FRAME},asplit={count}{labels}')
        for i, k in enumerate(t['kept']):
            filters.append(f"[s{i}]atrim=start_sample={k['source_start']*SAMPLES_PER_FRAME}:"
                           f"end_sample={k['source_end']*SAMPLES_PER_FRAME},asetpts=PTS-STARTPTS[a{i}]")
        filters.append(''.join(f'[a{i}]' for i in range(count)) + f'concat=n={count}:v=0:a=1[a]')
    else:
        filters.append(f'anullsrc=r={RATE}:cl=stereo,atrim=end_sample={output*SAMPLES_PER_FRAME}[a]')
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.render-') as temp:
        folder = Path(temp)
        script, staged = folder/'filters.txt', folder/'video.mp4'
        script.write_text(';\n'.join(filters), encoding='utf-8')
        run(['ffmpeg', '-hide_banner', '-nostdin', '-y', '-copyts', '-i', str(path),
             '-filter_complex_threads', '1', '-filter_complex_script', str(script),
             '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'veryfast',
             '-crf', '20', '-pix_fmt', 'yuv420p', '-threads', '2', '-r', str(FPS),
             '-fps_mode', 'cfr', '-c:a', 'aac',
             '-b:a', '128k', '-movflags', '+faststart', str(staged)])
        # Exclusive publication: another render never replaces an existing result.
        try:
            os.link(staged, destination)
        except OSError as exc:
            raise EditError(f'Render publication failed without replacing the destination: {exc}') from exc
    return t


def export_bundle(path: Path, project: dict, destination: Path) -> dict:
    """Publish a NEW directory containing real video and editable source-bound files."""
    if destination.exists():
        raise EditError('Export directory already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.export-') as tmp:
        folder = Path(tmp)/'packet'
        folder.mkdir()
        t = render(path, project, folder/'roughcut.mp4')
        for name, data in [('project.json', project), ('timeline.json', t)]:
            (folder/name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        (folder/'captions.vtt').write_text(captions_text(t), encoding='utf-8')
        (folder/'captions.srt').write_text(captions_text(t, srt=True), encoding='utf-8')
        with (folder/'kept-intervals.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['source_start', 'source_end', 'output_start', 'output_end'])
            writer.writeheader()
            writer.writerows(t['kept'])
        (folder/'REVIEW.txt').write_text(
            'Editable timeline: 30 fps, half-open frame intervals. project.json retains ALL source cues and reversible decisions.\n'
            'Keep the original source beside your working archive; it is not duplicated in this export.\n'
            'Caption wording across partial cuts needs human review; no word alignment or transcription is inferred.\n\n'
            + '\n'.join(t['warnings']) + '\n', encoding='utf-8')
        manifest = {p.name: digest(p) for p in folder.iterdir()}
        (folder/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        with zipfile.ZipFile(folder/'editable-export.zip', 'w', zipfile.ZIP_STORED) as z:
            for p in sorted(folder.iterdir()):
                if p.name != 'editable-export.zip':
                    z.write(p, p.name)
        # mkdir is the exclusive reservation. Rename into it only after it is ours.
        try:
            destination.mkdir()
        except FileExistsError as exc:
            raise EditError('Another export already reserved this destination') from exc
        try:
            for p in folder.iterdir():
                os.replace(p, destination/p.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return t


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init'); init.add_argument('source', type=Path); init.add_argument('project', type=Path)
    for name in ['analyze', 'export']:
        p = sub.add_parser(name); p.add_argument('source', type=Path); p.add_argument('project', type=Path)
        if name == 'export': p.add_argument('output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            data = new_project(args.source)
            with args.project.open('x', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            data = json.loads(args.project.read_text(encoding='utf-8'))
            if args.command == 'analyze':
                proposals = silence_suggestions(args.source, data) + repeated_takes(data)
                print(json.dumps({'suggestions': proposals[:MAX_CUTS], 'automatically_applied': False}, indent=2))
            else:
                print(json.dumps(export_bundle(args.source, data, args.output), indent=2))
        return 0
    except (EditError, OSError, ValueError) as exc:
        print(f'Error: {exc}', file=__import__('sys').stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
