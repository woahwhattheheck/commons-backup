#!/usr/bin/env python3
"""Install pinned language tools for the current cloud work lanes."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request


DEFAULT_ROOT = Path('/workspace/shared/swarm/toolchains')
PINS = {
    'rust': {'version': '1.98.1', 'target': 'wasm32-unknown-unknown',
             'wasm_bindgen': '0.2.128', 'directory': 'rust-fluxer',
             'metadata_url': 'https://static.rust-lang.org/dist/channel-rust-1.98.1.toml'},
    'go': {
        'version': 'go1.24.4', 'archive': 'go1.24.4.linux-amd64.tar.gz',
        'url': 'https://dl.google.com/go/go1.24.4.linux-amd64.tar.gz',
        'metadata_url': 'https://go.dev/dl/?mode=json&include=all',
        'sha256': '77e5da33bb72aeaef1ba4418b6fe511bc4d041873cbf82e5aa6318740df98717',
        'directory': 'go-1.24.4', 'binary': 'go/bin/go', 'version_args': ['version'],
    },
    'node18': {
        'version': 'v18.20.4', 'archive': 'node-v18.20.4-linux-x64.tar.xz',
        'url': 'https://nodejs.org/dist/v18.20.4/node-v18.20.4-linux-x64.tar.xz',
        'metadata_url': 'https://nodejs.org/dist/v18.20.4/SHASUMS256.txt',
        'sha256': '592eb35c352c7c0c8c4b2ecf9c19d615e78de68c20b660eb74bd85f8c8395063',
        'directory': 'node-v18.20.4-linux-x64', 'binary': 'bin/node', 'version_args': ['--version'],
    },
    'node24': {
        'version': 'v24.19.0', 'archive': 'node-v24.19.0-linux-x64.tar.xz',
        'url': 'https://nodejs.org/dist/v24.19.0/node-v24.19.0-linux-x64.tar.xz',
        'metadata_url': 'https://nodejs.org/dist/v24.19.0/SHASUMS256.txt',
        'sha256': '14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647',
        'directory': 'node-v24.19.0-linux-x64', 'binary': 'bin/node', 'version_args': ['--version'],
    },
    'llvm': {
        'version': '20.1.2', 'archive': 'LLVM-20.1.2-Linux-X64.tar.xz',
        'url': 'https://github.com/llvm/llvm-project/releases/download/llvmorg-20.1.2/LLVM-20.1.2-Linux-X64.tar.xz',
        'metadata_url': 'https://github.com/llvm/llvm-project/releases/download/llvmorg-20.1.2/LLVM-20.1.2-Linux-X64.tar.xz.jsonl',
        'sha256': '3a392f151375eeed4fd50c6b6f7c7203da37b373a57f220ae58ef62b8aade3cc',
        'directory': 'LLVM-20.1.2-Linux-X64', 'binary': 'bin/clang', 'version_args': ['--version'],
        'selection': 'bin, shared libraries, lib/clang resources',
    },
    'pnpm': {
        'version': '11.27.0', 'archive': 'pnpm-11.27.0.tgz',
        'url': 'https://registry.npmjs.org/pnpm/-/pnpm-11.27.0.tgz',
        'metadata_url': 'https://registry.npmjs.org/pnpm/11.27.0',
        'sha256': '40a32515a25507f8f226dfbbe25380e2f053944c2ecc64c0c1cb98b41cbb91ef',
        'integrity': 'sha512-rRKCFGO7FDKV8fo+zed6a5uXp5kDhtqAD/V7/8OWTcZLexx1WdXb5cM3rqZZ7ZyJN9Q3C9GYyiAJvG+gJJgI5w==',
        'shasum': '22d92a3b6b179aa9068602674632ad4d2b37c20e',
        'directory': 'pnpm-11.27.0', 'binary': 'bin/pnpm', 'version_args': ['--version'],
    },
}


# Exact component digests from the official Rust channel/release assets.
RUST_VERSION = '1.98.1'
RUST_TOOLCHAIN = '1.98.1-x86_64-unknown-linux-gnu'
RUST_WASM_TARGET = 'wasm32-unknown-unknown'
RUST_BINDGEN_VERSION = '0.2.128'
RUST_MANIFEST_URL = 'https://static.rust-lang.org/dist/channel-rust-1.98.1.toml'
RUST_MANIFEST_SHA256 = 'a7c8774a5fd8441c997d94c029776cbc5eb111e9d72ab5d256fa69866644347e'
RUST_ARTIFACTS = (
    {'component': 'rustc', 'target': 'x86_64-unknown-linux-gnu',
     'url': 'https://static.rust-lang.org/dist/2026-09-03/rustc-1.98.1-x86_64-unknown-linux-gnu.tar.xz',
     'sha256': 'e974f036b28565f37c0f3bd92ddefa809bee16c04f9dcf07b9ed96e05aaaf7c4'},
    {'component': 'cargo', 'target': 'x86_64-unknown-linux-gnu',
     'url': 'https://static.rust-lang.org/dist/2026-09-03/cargo-1.98.1-x86_64-unknown-linux-gnu.tar.xz',
     'sha256': 'ea1de9f9e23107d97ee2b41a72c552f34064a593da503789218387aee59f3ba4'},
    {'component': 'rust-std', 'target': 'x86_64-unknown-linux-gnu',
     'url': 'https://static.rust-lang.org/dist/2026-09-03/rust-std-1.98.1-x86_64-unknown-linux-gnu.tar.xz',
     'sha256': 'fa3ff450172a16c026944030230c5069947af93c728d9179971d44e5e0cfb561'},
    {'component': 'rust-std', 'target': RUST_WASM_TARGET,
     'url': 'https://static.rust-lang.org/dist/2026-09-03/rust-std-1.98.1-wasm32-unknown-unknown.tar.xz',
     'sha256': 'cf1fcf68880d8b2b90128cede7416cfb82ad3584357ce9fb668f2b6244c26e55'},
    {'component': 'wasm-bindgen', 'target': 'x86_64-unknown-linux-musl',
     'url': 'https://github.com/wasm-bindgen/wasm-bindgen/releases/download/0.2.128/wasm-bindgen-0.2.128-x86_64-unknown-linux-musl.tar.gz',
     'sha256': 'b51f0208fdff83515a787bd8ab9ac5865ed84dabb66d0c709957bb59793c645f'},
    {'component': 'rustup-init', 'target': 'x86_64-unknown-linux-gnu',
     'url': 'https://static.rust-lang.org/rustup/archive/1.29.1/x86_64-unknown-linux-gnu/rustup-init',
     'sha256': 'dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71'},
)


def _rust_paths(root: Path) -> dict[str, Path]:
    destination = Path(root).expanduser().resolve() / 'rust-fluxer'
    return {'root': destination, 'rustup': destination / 'rustup-home',
            'cargo': destination / 'cargo-home',
            'prefix': destination / 'rustup-home' / 'toolchains' / RUST_TOOLCHAIN,
            'bootstrap': destination / 'toolchain',
            'bindgen': destination / 'wasm-bindgen-0.2.128',
            'downloads': destination / 'downloads',
            'manifest': destination / 'rust-runtime-manifest.json'}


def _rust_environment(paths: dict[str, Path], *, installing: bool = False) -> dict[str, str]:
    environment = dict(os.environ, RUSTUP_HOME=str(paths['rustup']))
    # Installed proxies are shared; registry/build state belongs to an invocation.
    environment['CARGO_HOME'] = str(paths['cargo'] if installing else paths['root'] / 'runtime-cache')
    if installing:
        environment.pop('RUSTUP_TOOLCHAIN', None)
    else:
        environment['RUSTUP_TOOLCHAIN'] = RUST_TOOLCHAIN
        environment['RUSTUP_AUTO_INSTALL'] = '0'
    return environment


def _rust_command(arguments: list[str | Path], paths: dict[str, Path], *, installing: bool = False,
                  timeout: int = 60) -> str:
    result = subprocess.run([str(value) for value in arguments],
                            cwd=paths['root'], env=_rust_environment(paths, installing=installing),
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        detail = (result.stderr.strip() or result.stdout.strip())[-3000:]
        raise RuntimeError(f'Rust command exited {result.returncode}: {arguments[0]}: {detail}')
    return result.stdout.strip()


def _rust_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _rust_download(url: str, sha256: str, destination: Path) -> Path:
    if destination.is_file():
        if _rust_sha256(destination) != sha256:
            raise RuntimeError(f'Rust cached official artifact SHA256 mismatch; retained {destination}')
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=destination.name + '.', suffix='.partial',
                                        dir=destination.parent)
    partial = Path(name)
    context = ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE')
                                         or os.environ.get('REQUESTS_CA_BUNDLE'))
    try:
        with os.fdopen(descriptor, 'wb') as output:
            # urllib uses the inherited proxy settings; TLS verification stays enabled.
            with urllib.request.urlopen(url, context=context, timeout=60) as response:
                for chunk in iter(lambda: response.read(1024 * 1024), b''):
                    output.write(chunk)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'Required exact Rust artifact unavailable: HTTP {error.code}: {url}; retained {partial}') from error
    except Exception as error:
        raise RuntimeError(f'Required exact Rust artifact download failed: {url}; retained {partial}: {error}') from error
    if _rust_sha256(partial) != sha256:
        raise RuntimeError(f'Official Rust artifact SHA256 mismatch: {url}; retained {partial}')
    partial.replace(destination)
    return destination


def _rust_unpack(archive: Path, paths: dict[str, Path]) -> Path:
    staging = Path(tempfile.mkdtemp(prefix='.rust-unpack-', dir=paths['root']))
    with tarfile.open(archive) as source:
        source.extractall(staging, filter='data')
    children = list(staging.iterdir())
    if len(children) != 1 or not children[0].is_dir():
        raise RuntimeError(f'Unexpected official Rust archive layout; retained {staging}')
    return children[0]


@contextmanager
def _rust_install_lock(paths: dict[str, Path]):
    paths['root'].mkdir(parents=True, exist_ok=True)
    with (paths['root'] / '.install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def status_rust(root: Path) -> dict:
    """Observe exact installed binaries/target locally without network or writes."""
    paths = _rust_paths(root)
    result = {'state': 'unavailable', 'status': 'unavailable', 'root': str(paths['root']),
              'version': RUST_VERSION, 'toolchain': RUST_TOOLCHAIN,
              'requested': {'rust': RUST_VERSION, 'target': RUST_WASM_TARGET,
                            'wasm_bindgen': RUST_BINDGEN_VERSION}}
    try:
        binaries = {'rustc': paths['prefix'] / 'bin/rustc',
                    'cargo': paths['prefix'] / 'bin/cargo',
                    'rustup': paths['cargo'] / 'bin/rustup',
                    'wasm_bindgen': paths['bindgen'] / 'wasm-bindgen'}
        for name, path in binaries.items():
            if not path.is_file():
                raise RuntimeError(f'Required exact Rust runtime binary missing: {name}: {path}')
        versions = {name: _rust_command([path, '--version'], paths)
                    for name, path in binaries.items()}
        if not versions['rustc'].startswith('rustc 1.98.1 '):
            raise RuntimeError(f'Rust compiler version mismatch: {versions["rustc"]}')
        if not versions['cargo'].startswith('cargo 1.98.1 '):
            raise RuntimeError(f'Cargo version mismatch: {versions["cargo"]}')
        if versions['wasm_bindgen'] != 'wasm-bindgen 0.2.128':
            raise RuntimeError(f'wasm-bindgen version mismatch: {versions["wasm_bindgen"]}')
        installed_targets = _rust_command([binaries['rustup'], 'target', 'list', '--installed',
                                          '--toolchain', RUST_TOOLCHAIN], paths).splitlines()
        wasm_lib = Path(_rust_command([binaries['rustc'], '--print', 'target-libdir',
                                      '--target', RUST_WASM_TARGET], paths))
        standard_libraries = list(wasm_lib.glob('libstd-*.rlib'))
        if RUST_WASM_TARGET not in installed_targets or not standard_libraries:
            raise RuntimeError(f'Required exact wasm standard-library target missing: {wasm_lib}')
        result.update({'schema': 'commons.private_rust_runtime/v1', 'state': 'available',
                       'status': 'installed', 'prefix': str(paths['prefix']),
                       'binary_path': str(binaries['rustc']), 'version_output': versions['rustc'],
                       **{name: str(path) for name, path in binaries.items()}, 'versions': versions,
                       'shared_proxy_bin': str(paths['cargo'] / 'bin'),
                       'bin_dirs': [str(paths['cargo'] / 'bin'), str(paths['bindgen'])],
                       'activation': {'RUSTUP_HOME': str(paths['rustup']),
                                      'SWARM_CARGO_HOME': str(paths['cargo']),
                                      'WASM_BINDGEN_ROOT': str(paths['bindgen'])},
                       'sysroot': _rust_command([binaries['rustc'], '--print', 'sysroot'], paths),
                       'installed_targets': installed_targets, 'wasm_target_libdir': str(wasm_lib),
                       'wasm_standard_library': str(standard_libraries[0]),
                       'manifest_path': str(paths['manifest']),
                       'channel_manifest': {'url': RUST_MANIFEST_URL,
                                            'sha256': RUST_MANIFEST_SHA256,
                                            'release_date': '2026-09-03'},
                       'artifacts': [{**item, 'archive': str(paths['downloads'] / item['url'].rsplit('/', 1)[-1])}
                                     for item in RUST_ARTIFACTS]})
    except Exception as error:
        result.update({'message': str(error), 'error': type(error).__name__})
    return result


def install_rust(root: Path) -> dict:
    """Install exact official bytes, or reuse the existing complete runtime."""
    paths = _rust_paths(root)
    existing = status_rust(root)
    if existing['state'] == 'available':
        return {**existing, 'reused': True}
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise RuntimeError('Pinned Fluxer Rust runtime requires Linux x86_64; no version/platform fallback')
    with _rust_install_lock(paths):
        existing = status_rust(root)
        if existing['state'] == 'available':
            return {**existing, 'reused': True}
        _rust_download(RUST_MANIFEST_URL, RUST_MANIFEST_SHA256,
                       paths['root'] / 'channel-rust-1.98.1.toml')
        archives = {item['component'] + '/' + item['target']:
                    _rust_download(item['url'], item['sha256'],
                                   paths['downloads'] / item['url'].rsplit('/', 1)[-1])
                    for item in RUST_ARTIFACTS}
        # Use the official component installers before registering the ordinary
        # named rustup toolchain. Its installer reuses these exact verified archives.
        paths['bootstrap'].mkdir(parents=True, exist_ok=True)
        for item in RUST_ARTIFACTS[:4]:
            component, target = item['component'], item['target']
            present = (paths['bootstrap'] / 'bin' / component).is_file() if component != 'rust-std' else bool(
                list((paths['bootstrap'] / 'lib/rustlib' / target / 'lib').glob('libstd-*.rlib')))
            if present:
                if component != 'rust-std':
                    native = _rust_command([paths['bootstrap'] / 'bin' / component, '--version'], paths)
                    if not native.startswith(component + ' 1.98.1 '):
                        raise RuntimeError(f'Existing private Rust bootstrap version mismatch: {native}')
                continue
            unpacked = _rust_unpack(archives[component + '/' + target], paths)
            _rust_command(['bash', unpacked / 'install.sh', '--prefix=' + str(paths['bootstrap']),
                           '--disable-ldconfig'], paths, installing=True, timeout=300)
        manager = paths['cargo'] / 'bin/rustup'
        if not manager.is_file():
            installer = archives['rustup-init/x86_64-unknown-linux-gnu']
            installer.chmod(0o755)
            _rust_command([installer, '-y', '--no-modify-path', '--default-toolchain', 'none',
                           '--profile', 'minimal'], paths, installing=True, timeout=300)
        cache = paths['rustup'] / 'downloads'
        cache.mkdir(parents=True, exist_ok=True)
        for item in RUST_ARTIFACTS[:4]:
            archive = archives[item['component'] + '/' + item['target']]
            cached = cache / item['sha256']
            if cached.exists():
                if _rust_sha256(cached) != item['sha256']:
                    raise RuntimeError(f'Rustup cached official artifact SHA256 mismatch; retained {cached}')
            else:
                try:
                    cached.hardlink_to(archive)
                except OSError:
                    shutil.copyfile(archive, cached)
        _rust_command([manager, 'toolchain', 'install', RUST_VERSION, '--profile', 'minimal',
                       '--target', RUST_WASM_TARGET, '--no-self-update'], paths,
                      installing=True, timeout=900)
        _rust_command([manager, 'default', RUST_VERSION], paths, installing=True)
        bindgen = paths['bindgen'] / 'wasm-bindgen'
        if not bindgen.is_file():
            unpacked = _rust_unpack(archives['wasm-bindgen/x86_64-unknown-linux-musl'], paths)
            paths['bindgen'].mkdir(parents=True, exist_ok=True)
            for filename in ('wasm-bindgen', 'wasm-bindgen-test-runner', 'wasm2es6js'):
                source = unpacked / filename
                if source.is_file():
                    destination = paths['bindgen'] / filename
                    if destination.exists():
                        raise RuntimeError(f'Existing incomplete wasm-bindgen installation retained: {destination}')
                    shutil.copy2(source, destination)
        result = status_rust(root)
        if result['state'] != 'available':
            raise RuntimeError(f'Exact Rust installation incomplete: {result["message"]}')
        result.update({'reused': False, 'operation_id': 'swarm-cloud-fluxer-rust-1.98.1',
                       'observed_at': dt.datetime.now(dt.timezone.utc).isoformat()})
        paths['manifest'].write_text(json.dumps(result, indent=2) + '\n')
        return result


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def version(binary: Path, arguments: list[str]) -> str:
    environment = dict(os.environ, GOTOOLCHAIN='local')
    result = subprocess.run([str(binary), *arguments], capture_output=True, text=True,
                            env=environment, timeout=30)
    if result.returncode:
        detail = (result.stderr.strip() or result.stdout.strip())[-3000:]
        raise RuntimeError(f'{binary}: exited {result.returncode}: {detail}')
    return result.stdout.strip()


def compiler_versions(root: Path) -> dict[str, str]:
    observations = {name: version(root / 'bin' / name, ['--version'])
                    for name in ('clang', 'clang++', 'llvm-ar')}
    if any('20.1.2' not in value.split() for value in observations.values()):
        raise RuntimeError('LLVM compiler/archive tool no longer matches pinned 20.1.2')
    return observations


def selected_node24(root: Path, item: dict | None = None) -> dict | None:
    """Reuse an exact native runtime; otherwise let install fetch the official pin."""
    pin = PINS['node24']
    candidates = []
    if item and item.get('binary_path'):
        candidates.append(Path(item['binary_path']))
    candidates.append(root / pin['directory'] / pin['binary'])
    if os.environ.get('SWARM_NODE24_BIN'):
        candidates.append(Path(os.environ['SWARM_NODE24_BIN']) / 'node')
    inherited = shutil.which('node')
    if inherited:
        candidates.append(Path(inherited))
    for candidate in dict.fromkeys(candidates):
        try:
            binary = candidate.resolve()
            actual = version(binary, pin['version_args'])
            if actual != pin['version']:
                continue
            return {**pin, 'state': 'available', 'root': str(binary.parent.parent),
                    'binary_path': str(binary), 'version_output': actual, 'reused': True,
                    'runtime_source': 'private_install' if binary.is_relative_to(root)
                                      else 'inherited_runtime'}
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            continue
    return None


def install_component(name: str, root: Path) -> dict:
    if name == 'rust':
        return install_rust(root)
    if name == 'node24':
        existing = selected_node24(root)
        if existing:
            return existing
    pin = PINS[name]
    destination = root / pin['directory']
    binary = destination / pin['binary']
    if binary.is_file():
        actual = version(binary, pin['version_args'])
        if pin['version'] not in actual.split():
            raise RuntimeError(f'{name}: existing runtime has unexpected version: {actual}')
        extra = {'compiler_versions': compiler_versions(destination)} if name == 'llvm' else {}
        return {**pin, **extra, 'state': 'available', 'root': str(destination),
                'binary_path': str(binary), 'version_output': actual, 'reused': True}
    if destination.exists():
        raise RuntimeError(f'{name}: existing incomplete directory retained: {destination}')
    downloads = root / 'language-downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / pin['archive']
    http_status = None
    if not archive.is_file():
        context = ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE')
                                             or os.environ.get('REQUESTS_CA_BUNDLE'))
        descriptor, temporary_name = tempfile.mkstemp(prefix=pin['archive'] + '.', dir=downloads)
        with os.fdopen(descriptor, 'wb') as output:
            with urllib.request.urlopen(pin['url'], context=context, timeout=90) as response:
                http_status = response.status
                for block in iter(lambda: response.read(1024 * 1024), b''):
                    output.write(block)
        temporary = Path(temporary_name)
        if digest(temporary) != pin['sha256']:
            raise RuntimeError(f'{name}: official artifact digest mismatch; retained {temporary}')
        temporary.rename(archive)
    if digest(archive) != pin['sha256']:
        raise RuntimeError(f'{name}: existing archive digest mismatch; retained {archive}')
    staging = Path(tempfile.mkdtemp(prefix=f'.{name}-extract-', dir=root))
    if name == 'llvm':
        # Keep the official runtime/tools/resources; omit static development
        # archives and documentation. Stream once rather than seeking through
        # a two-gigabyte xz archive for every selected member.
        with tarfile.open(archive, mode='r|*') as source:
            for member in source:
                relative = '/'.join(Path(member.name).parts[1:])
                if (relative == 'bin' or relative.startswith('bin/')
                        or relative == 'lib' or relative.startswith('lib/clang/')
                        or (relative.startswith('lib/') and '.so' in relative)):
                    source.extract(member, staging, filter='data')
    else:
        with tarfile.open(archive) as source:
            source.extractall(staging, filter='data')
    if name == 'go':
        extracted = staging
    elif name == 'pnpm':
        extracted = staging
        (extracted / 'bin').mkdir()
        (extracted / 'bin' / 'pnpm').write_text('#!/bin/sh\nexec node "$(dirname "$0")/../package/bin/pnpm.cjs" "$@"\n')
        (extracted / 'bin' / 'pnpm').chmod(0o755)
    else:
        extracted = staging / pin['directory']
    candidate = extracted / pin['binary']
    actual = version(candidate, pin['version_args'])
    if pin['version'] not in actual.split():
        raise RuntimeError(f'{name}: extracted runtime version mismatch: {actual}')
    extra = {'compiler_versions': compiler_versions(extracted)} if name == 'llvm' else {}
    extracted.rename(destination)
    return {**pin, **extra, 'state': 'available', 'root': str(destination),
            'binary_path': str(binary), 'version_output': version(binary, pin['version_args']),
            'archive_path': str(archive), 'http_status': http_status, 'reused': False}


def write_activation(root: Path, components: dict) -> Path:
    values = {}
    if components.get('node24', {}).get('state') == 'available':
        values['SWARM_NODE24_BIN'] = str(Path(components['node24']['binary_path']).parent)
    if components.get('go', {}).get('state') == 'available':
        values['GOROOT'] = str(root / PINS['go']['directory'] / 'go')
    if components.get('node18', {}).get('state') == 'available':
        values['SWARM_NODE18_ROOT'] = str(root / PINS['node18']['directory'])
    if components.get('llvm', {}).get('state') == 'available':
        values['SWARM_LLVM_ROOT'] = str(root / PINS['llvm']['directory'])
        values['CC'] = str(Path(values['SWARM_LLVM_ROOT']) / 'bin' / 'clang')
        values['CXX'] = str(Path(values['SWARM_LLVM_ROOT']) / 'bin' / 'clang++')
        values['AR'] = str(Path(values['SWARM_LLVM_ROOT']) / 'bin' / 'llvm-ar')
    if components.get('pnpm', {}).get('state') == 'available':
        values['SWARM_PNPM_ROOT'] = str(root / PINS['pnpm']['directory'])
    rust = components.get('rust', {})
    if rust.get('state') == 'available':
        for name in ('RUSTUP_HOME', 'SWARM_CARGO_HOME', 'WASM_BINDGEN_ROOT'):
            value = rust.get('activation', {}).get(name)
            if value:
                values[name] = value
    lines = ['# Shared installed binaries; worker caches remain separate.',
             '# Node 24 remains the default. Revert workers prepend $SWARM_NODE18_ROOT/bin.']
    lines.extend(f'export {name}={shlex.quote(str(value))}' for name, value in values.items())
    paths = [values['SWARM_NODE24_BIN']] if 'SWARM_NODE24_BIN' in values else []
    if 'GOROOT' in values:
        paths.append(str(Path(values['GOROOT']) / 'bin'))
    if 'SWARM_LLVM_ROOT' in values:
        paths.append(str(Path(values['SWARM_LLVM_ROOT']) / 'bin'))
    if 'SWARM_PNPM_ROOT' in values:
        paths.append(str(Path(values['SWARM_PNPM_ROOT']) / 'bin'))
    if 'SWARM_CARGO_HOME' in values:
        paths.append(str(Path(values['SWARM_CARGO_HOME']) / 'bin'))
    if 'WASM_BINDGEN_ROOT' in values:
        paths.append(values['WASM_BINDGEN_ROOT'])
    if paths:
        lines.append('export PATH=' + shlex.quote(':'.join(paths)) + ':"$PATH"')
    activation = root / 'languages.sh'
    activation.write_text('\n'.join(lines) + '\n')
    return activation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('install', 'status', 'activate'))
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--component', action='append', choices=tuple(PINS))
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'languages-manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {'components': {}}
    components = manifest['components']
    if args.command == 'install':
        selected = list(args.component or PINS)
        # pnpm's native entrypoint requires the supplied Node 24 runtime.
        # Install it first on a fresh base image, then retain parallel downloads.
        if 'node24' in selected:
            selected.remove('node24')
            try:
                components['node24'] = install_component('node24', root)
                node_bin = str(Path(components['node24']['binary_path']).parent)
                os.environ['SWARM_NODE24_BIN'] = node_bin
                os.environ['PATH'] = node_bin + os.pathsep + os.environ.get('PATH', '')
            except Exception as error:
                components['node24'] = {'state': 'unavailable', 'error': type(error).__name__,
                                        'message': str(error), **PINS['node24']}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {name: pool.submit(install_component, name, root) for name in selected}
            for name, future in futures.items():
                try:
                    components[name] = future.result()
                except Exception as error:
                    components[name] = {'state': 'unavailable', 'error': type(error).__name__,
                                        'message': str(error), **PINS[name]}
        manifest['observed_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    if args.command in ('status', 'activate'):
        for name in args.component or list(PINS):
            if name == 'rust':
                components[name] = status_rust(root)
                continue
            if name == 'node24':
                components[name] = selected_node24(root, components.get(name)) or {
                    **PINS[name], 'state': 'unavailable',
                    'message': 'Pinned Node v24.19.0 is absent; run the language installer.'}
                if components[name]['state'] == 'available':
                    node_bin = str(Path(components[name]['binary_path']).parent)
                    os.environ['SWARM_NODE24_BIN'] = node_bin
                    os.environ['PATH'] = node_bin + os.pathsep + os.environ.get('PATH', '')
                continue
            item = components.setdefault(name, dict(PINS[name]))
            try:
                binary = root / PINS[name]['directory'] / PINS[name]['binary']
                item['version_output'] = version(binary, PINS[name]['version_args'])
                if PINS[name]['version'] not in item['version_output'].split():
                    raise RuntimeError(f'{name}: runtime no longer matches pinned version')
                if name == 'llvm':
                    item['compiler_versions'] = compiler_versions(root / PINS[name]['directory'])
                item.update({'state': 'available', 'root': str(root / PINS[name]['directory']),
                             'binary_path': str(binary)})
                item.pop('message', None)
                item.pop('error', None)
            except Exception as error:
                item.update({'state': 'unavailable', 'error': type(error).__name__,
                             'message': str(error)})
        manifest['observed_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    activation = write_activation(root, components)
    print(json.dumps({'manifest': str(manifest_path), 'activation': str(activation),
                      'components': components}, indent=2))
    return int(any(item.get('state') != 'available' for item in components.values()))


if __name__ == '__main__':
    raise SystemExit(main())
