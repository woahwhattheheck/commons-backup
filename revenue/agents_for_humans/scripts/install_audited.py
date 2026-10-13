"""Install only after the completed source and dependency audits agree."""
import json
import importlib.metadata
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
audit = json.loads((ROOT / 'dependency-audit.json').read_text(encoding='utf-8'))
source = json.loads((ROOT / 'sdk-source-audit.json').read_text(encoding='utf-8'))
lock = ROOT / 'requirements-win-py312.lock'
if audit['root'] != 'strands-agents==1.0.1' or source['tag'] != 'v1.0.1':
    raise SystemExit('Dependency audit is incomplete or references an unapproved SDK version')
if source['truncated'] or not source['checked_before_distribution_download'] or not source['no_llamacpp_module']:
    raise SystemExit('Source inventory audit is incomplete')
for name in audit['packages']:
    if any(banned in name for banned in ('llama', 'ollama', 'ctransformers', 'gpt4all')):
        raise SystemExit('Prohibited dependency in audit')
lines = [f"{name} @ {item['url']} --hash=sha256:{item['sha256']}" for name, item in sorted(audit['packages'].items())]
expected = '# Windows CPython 3.12; generated from PyPI metadata before artifact downloads.\n' + '\n'.join(lines) + '\n'
if lock.exists() and lock.read_text(encoding='utf-8') != expected:
    raise SystemExit('Dependency lock differs from the completed audit')
lock.write_text(expected, encoding='utf-8')
missing = []
for (name, item), line in zip(sorted(audit['packages'].items()), lines):
    try:
        present = importlib.metadata.version(name) == item['version']
    except importlib.metadata.PackageNotFoundError:
        present = False
    if not present:
        missing.append(line)
pending = ROOT / '.install-required.lock'
try:
    pending.write_text('\n'.join(missing) + '\n', encoding='utf-8')
    if missing:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-cache-dir',
                        '--require-hashes', '--only-binary=:all:', '-r', str(pending)], check=True)
finally:
    pending.unlink(missing_ok=True)
