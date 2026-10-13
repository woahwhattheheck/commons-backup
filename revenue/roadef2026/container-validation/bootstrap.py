#!/usr/bin/env python3
"""Stage the exact frozen ROADEF source, documentation and B01/B11/B12 inputs."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

FROZEN_COMMIT = '6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055'
FROZEN_ROOT = 'revenue/roadef2026/fleet-candidate'
FROZEN_NAME = 'FROZEN-CANDIDATE-20260908.json'
FROZEN_SHA256 = '6a5127cbf56305cfa46e5f26b52b4105c6c8b8aaa4ce12ed7643a076f82c9c51'
INSTANCES = ('B01', 'B11', 'B12')
INPUTS = {f'setB/setB-{instance[1:]}-{suffix}.json': (instance, name)
          for instance in INSTANCES
          for suffix, name in (('net', 'network.json'), ('tm', 'traffic.json'),
                               ('scenario', 'scenario.json'))}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def blob_digest(raw):
    return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()


def relative_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or not path.parts:
        raise ValueError(f'Invalid published source path: {name}')
    return path


def verify_identity(raw, expected, description):
    if ('bytes' in expected and len(raw) != expected['bytes'] or
            'sha256' in expected and digest(raw) != expected['sha256'] or
            'git_blob_sha1' in expected and blob_digest(raw) != expected['git_blob_sha1']):
        raise ValueError(f'Published identity differs: {description}')


def fetch(name, *, commit, root=FROZEN_ROOT):
    url = f'https://raw.githubusercontent.com/woahwhattheheck/commons/{commit}/{root}/{name}'
    request = urllib.request.Request(url,
                                     headers={'User-Agent': 'ROADEF-container-validation/1'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    frozen_raw = fetch(FROZEN_NAME, commit=FROZEN_COMMIT)
    verify_identity(frozen_raw, {'sha256': FROZEN_SHA256}, FROZEN_NAME)
    (output / FROZEN_NAME).write_bytes(frozen_raw)
    frozen = json.loads(frozen_raw)
    if frozen['schema_version'] != 1 or frozen['repository'] != 'woahwhattheheck/commons':
        raise ValueError('Unsupported frozen publication')
    source_commit, source_root = frozen['base_source_commit'], frozen['runtime_root']
    source, archives, data = (output / name for name in ('source', 'archives', 'data'))
    for path in (source, archives, data):
        path.mkdir()
    manifest_raw = fetch('PUBLIC-SOURCE-MANIFEST.json', commit=source_commit, root=source_root)
    manifest = json.loads(manifest_raw)
    (source / 'PUBLIC-SOURCE-MANIFEST.json').write_bytes(manifest_raw)
    source_files = []
    for row in manifest['files']:
        name = relative_path(row['path'])
        raw = fetch(name.as_posix(), commit=source_commit, root=source_root)
        verify_identity(raw, row, str(name))
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        source_files.append(row)
    # Preserve all original publication bytes. The frozen runtime is staged apart.
    runtime = output / 'runtime-source'
    runtime.mkdir()
    runtime_files = []
    runtime_entries = list(frozen['runtime_files'])
    if len({row['path'] for row in runtime_entries}) != len(runtime_entries):
        raise ValueError('Duplicate frozen runtime entry')
    # The published LINK preparer requires README, which the freeze inherits from
    # its original publication. Keep this dependency explicit in the report.
    if not any(row['path'] == 'README.md' for row in runtime_entries):
        original_readme = next(row for row in source_files if row['path'] == 'README.md')
        runtime_entries.append({**original_readme, 'commit': source_commit,
                                'supplement': 'Original README required by the frozen preparer'})
    for row in runtime_entries:
        name = relative_path(row['path'])
        original = (source / name).read_bytes()
        used = (original if row['commit'] == source_commit else
                fetch(name.as_posix(), commit=row['commit'], root=source_root))
        verify_identity(used, row, str(name))
        target = runtime / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(used)
        context_path = {'ATTRIBUTION.md': 'attribution/ATTRIBUTION.md',
                        'LICENSE': 'attribution/FLEET-LICENSE'}.get(str(name), str(name))
        runtime_files.append({**row, 'source_path': f'{source_root}/{name}',
                              'context_path': context_path,
                              'original_bytes': len(original), 'original_sha256': digest(original),
                              'used_bytes': len(used), 'used_sha256': digest(used),
                              'used_git_blob_sha1': blob_digest(used)})
    preparer_entry = frozen['preparer']
    used_preparer = fetch(relative_path(preparer_entry['path']).as_posix(),
                          commit=preparer_entry['commit'], root=source_root)
    verify_identity(used_preparer, preparer_entry, 'frozen preparer')
    preparer = output / 'PREPARER.py'
    preparer.write_bytes(used_preparer)
    spec = importlib.util.spec_from_file_location('frozen_roadef_prepare', preparer)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    for archive in module.ARCHIVES.values():
        module.fetch_verified(archive, archives, None)
    candidate_entry = frozen['candidate_source']
    parent_name = relative_path(candidate_entry['parent_path'])
    parent_raw = (source / parent_name).read_bytes()
    if candidate_entry['parent_commit'] != source_commit:
        raise ValueError('Frozen candidate parent differs from the preserved baseline')
    verify_identity(parent_raw, {'sha256': candidate_entry['parent_sha256']}, 'candidate parent')
    patch_path = relative_path(candidate_entry['patch_path'])
    patch_raw = fetch(patch_path.name, commit=candidate_entry['patch_commit'],
                      root=patch_path.parent.as_posix())
    verify_identity(patch_raw, {'git_blob_sha1': candidate_entry['patch_git_blob_sha1']},
                    'CEDAR-JOIN patch')
    patch = output / 'CANDIDATE.patch'
    patch.write_bytes(patch_raw)
    candidate = output / 'CANDIDATE.cpp'
    candidate.write_bytes(parent_raw)
    applied = subprocess.run(['patch', '--batch', '--fuzz=0', '--forward', str(candidate), str(patch)],
                             capture_output=True, timeout=30, check=False)
    (output / 'CANDIDATE-PATCH.stdout').write_bytes(applied.stdout)
    (output / 'CANDIDATE-PATCH.stderr').write_bytes(applied.stderr)
    if applied.returncode:
        raise ValueError('Frozen CEDAR-JOIN patch did not apply to the exact parent')
    candidate_raw = candidate.read_bytes()
    verify_identity(candidate_raw, {'bytes': candidate_entry['result_bytes'],
                                    'sha256': candidate_entry['result_sha256']}, 'frozen candidate')
    documentation = []
    for name_key, bytes_key, sha_key in (('method_source', 'method_bytes', 'method_sha256'),
                                        ('generator', 'generator_bytes', 'generator_sha256')):
        entry = frozen['documentation']
        name = relative_path(entry[name_key])
        raw = fetch(name.as_posix(), commit=FROZEN_COMMIT, root=source_root)
        identity = {'bytes': entry[bytes_key], 'sha256': entry[sha_key]}
        verify_identity(raw, identity, str(name))
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        documentation.append({'path': str(name), 'source_path': f'{source_root}/{name}',
                              'commit': FROZEN_COMMIT, **identity})
    context = output / 'context'
    context_manifest = module.prepare(context, runtime, candidate, archives)
    # LINK retains dependency licenses but omits the portfolio LICENSE. This
    # explicit attribution addition also reaches the unchanged final Docker image.
    license_row = next(row for row in runtime_files if row['path'] == 'LICENSE')
    license_target = context / license_row['context_path']
    with license_target.open('xb') as stream:
        stream.write((runtime / 'LICENSE').read_bytes())
    context_manifest['files'].append({'path': license_row['context_path'],
                                      'sha256': license_row['used_sha256']})
    context_manifest['files'].sort(key=lambda row: row['path'])
    (context / 'source-manifest.json').write_text(json.dumps(context_manifest, indent=2) + '\n')
    staged = {row['path']: row['sha256'] for row in context_manifest['files']}
    for row in runtime_files:
        target = row['context_path']
        if staged.get(target) != row['used_sha256'] or digest((context / target).read_bytes()) != row['used_sha256']:
            raise ValueError(f'Build context differs from frozen runtime: {target}')
    if staged['sources/candidate/main.cpp'] != digest(candidate_raw):
        raise ValueError('Build context differs from frozen candidate source')
    official = module.ARCHIVES['checker']
    input_files = []
    with zipfile.ZipFile(archives / official['file']) as archive:
        for info, relative in module.archive_members(archive, official):
            if str(relative) in INPUTS:
                raw = archive.read(info)
                instance, name = INPUTS[str(relative)]
                (data / instance).mkdir(exist_ok=True)
                (data / instance / name).write_bytes(raw)
                input_files.append({'archive_member': info.filename, 'instance': instance, 'path': name,
                                    'bytes': len(raw), 'sha256': digest(raw)})
    if (len(input_files) != len(INPUTS) or
            {(row['instance'], row['path']) for row in input_files} != set(INPUTS.values())):
        raise ValueError('Pinned official archive does not provide exactly the nine requested inputs')
    report = {'source_commit': source_commit, 'source_root': source_root,
              'frozen': {'commit': FROZEN_COMMIT, 'path': f'{FROZEN_ROOT}/{FROZEN_NAME}',
                         'bytes': len(frozen_raw), 'sha256': digest(frozen_raw),
                         'candidate_id': frozen['candidate_id'], 'manifest': frozen},
              'configuration': frozen['configuration'],
              'documentation': {**frozen['documentation'], 'commit': FROZEN_COMMIT,
                                'files': documentation},
              'public_manifest_sha256': digest(manifest_raw), 'source_files': source_files,
              'runtime_files': runtime_files,
              'candidate': {**candidate_entry, 'used_bytes': len(candidate_raw),
                            'used_sha256': digest(candidate_raw),
                            'patch_bytes': len(patch_raw), 'patch_sha256': digest(patch_raw),
                            'patch_git_blob_sha1': blob_digest(patch_raw),
                            'original_sha256': digest(parent_raw)},
              'preparer': {**preparer_entry, 'source_path': f'{source_root}/{preparer_entry["path"]}',
                           'used_sha256': digest(used_preparer),
                           'original_sha256': digest((source / preparer_entry['path']).read_bytes())},
              'context_additions': [{'path': license_row['context_path'],
                                     'source_path': license_row['source_path'],
                                     'sha256': license_row['used_sha256'],
                                     'change': 'Retain the exact frozen portfolio license in final-image attribution'}],
              'archives': context_manifest['archives'], 'inputs': input_files,
              'context_manifest_sha256': digest((context / 'source-manifest.json').read_bytes()),
              'scope': 'Frozen source and configuration; B01/B11/B12 container smoke and TERM behavior; submission held'}
    (output / 'PREPARATION.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'frozen_sha256': digest(frozen_raw), 'source_files': len(source_files),
                      'archives_verified': len(module.ARCHIVES), 'inputs': len(input_files)}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output.resolve())


if __name__ == '__main__':
    main()
