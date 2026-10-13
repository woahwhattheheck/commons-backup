"""Resolve PyPI METADATA before downloading any distribution artifacts.

Produces a platform-specific, hash-locked wheel list. Installs are separate.
Only official strands-agents base dependencies are requested, with no extras.
"""
import json
import sys
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.specifiers import SpecifierSet
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
from pip._vendor.packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
TAGS = set(sys_tags())
PYTHON = Version('.'.join(map(str, sys.version_info[:3])))
DENY = ('llama', 'ctransformers', 'ollama', 'gpt4all')
cache = {}

def metadata(name, version=None):
    key = name, version
    if key not in cache:
        url = f'https://pypi.org/pypi/{name}/' + (f'{version}/' if version else '') + 'json'
        with urllib.request.urlopen(url, timeout=30) as response:
            cache[key] = json.load(response)
    return cache[key]

def compatible_wheels(files):
    for entry in files:
        if entry['packagetype'] != 'bdist_wheel' or entry.get('yanked'):
            continue
        if entry.get('requires_python') and PYTHON not in SpecifierSet(entry['requires_python']):
            continue
        if parse_wheel_filename(entry['filename'])[3] & TAGS:
            yield entry

def main():
    constraints, extras = defaultdict(set), defaultdict(set)
    queue, selected = deque(), {}

    def add(text):
        requirement = Requirement(text)
        name = canonicalize_name(requirement.name)
        if any(item in name for item in DENY):
            raise RuntimeError('Prohibited dependency detected before artifact download: ' + name)
        if requirement.url:
            raise RuntimeError('Direct dependency URL needs separate review')
        previous = constraints[name].copy(), extras[name].copy()
        constraints[name].add(str(requirement.specifier))
        extras[name].update(requirement.extras)
        if previous != (constraints[name], extras[name]):
            queue.append(name)

    add('strands-agents==1.0.1')
    add('jsonschema==4.26.0')
    while queue:
        name = queue.popleft()
        spec = SpecifierSet(','.join(sorted(constraints[name])))
        listing = metadata(name)
        versions = sorted((Version(v) for v in listing['releases'] if spec.contains(v)), reverse=True)
        chosen = None
        for version in versions:
            wheels = list(compatible_wheels(listing['releases'][str(version)]))
            if wheels:
                chosen = version, wheels[0]
                break
        if chosen is None:
            raise RuntimeError(f'No compatible audited wheel: {name}{spec}')
        version, wheel = chosen
        info = metadata(name, str(version))['info']
        active = []
        for text in info.get('requires_dist') or []:
            req = Requirement(text)
            if req.marker is None or any(req.marker.evaluate({'extra': extra}) for extra in extras[name] | {''}):
                active.append(text)
                add(text)
        selected[name] = {'version': str(version), 'requirements': active,
                          'metadata_url': f'https://pypi.org/pypi/{name}/{version}/json',
                          'filename': wheel['filename'], 'url': wheel['url'],
                          'sha256': wheel['digests']['sha256']}
    # Ensure that revisiting a dependency did not leave an incompatible selected version.
    for name, entry in selected.items():
        assert SpecifierSet(','.join(constraints[name])).contains(entry['version'])
    report = {'root': 'strands-agents==1.0.1', 'additional_roots': ['jsonschema==4.26.0'], 'extras': [],
              'platform': sys.platform, 'python': str(PYTHON),
              'artifact_downloads_during_audit': 0, 'packages': dict(sorted(selected.items()))}
    (ROOT / 'dependency-audit.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    lines = ['# Windows CPython 3.12; generated from PyPI metadata before artifact downloads.']
    lines += [f"{name} @ {entry['url']} --hash=sha256:{entry['sha256']}" for name, entry in sorted(selected.items())]
    (ROOT / 'requirements-win-py312.lock').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'audited_packages': len(selected), 'names': sorted(selected), 'downloads': 0}))

if __name__ == '__main__':
    main()
