"""Verify and read the exact T07 receipts without running another game."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA256 = 'b4514c75131ccc2929114004fc90b3519ea343ef5cabe39aedee8a85ebe5e369'
PARTS = (
    ('raw-reports.xz.part1', 'd9125e2574ee65edf2672cf47c029f8a3f01af67c8507bd0d1dfef55e9ccbf71'),
    ('raw-reports.xz.part2', '90641759f0f055178b7d32fa78b76492a86c5756d7fe404a61015353eff28294'),
    ('raw-reports.xz.part3', 'ed71d0398f7a22d14e1a337903ffa47872a1dbcee6bdae0872cb1c95f28a81bc'),
)
GAME_REPORTS = ('controls-development.json', 'barnyard-development.json',
                'barnyard-held.json', 'nearclone-development.json', 'nearclone-development-v2.json')


def archive_bytes(root: Path = HERE) -> bytes:
    chunks = []
    for name, expected in PARTS:
        raw = (root / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f'Report part differs: {name}')
        chunks.append(raw)
    archive = b''.join(chunks)
    if hashlib.sha256(archive).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Combined report archive differs')
    return archive


def load_reports(root: Path = HERE) -> dict[str, bytes]:
    """Return original member bytes, including the preserved failed wrapper."""
    with tarfile.open(fileobj=io.BytesIO(archive_bytes(root)), mode='r:xz') as tar:
        members = tar.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)) or not all(member.isfile() for member in members):
            raise ValueError('Expected unique regular report members')
        if sum(member.size for member in members) != 913043:
            raise ValueError('Unexpected uncompressed report size')
        return {member.name: tar.extractfile(member).read() for member in members}


def summary(members: dict[str, bytes]) -> dict:
    games = {}
    for name in GAME_REPORTS:
        report = json.loads(members[name])
        for row in report['games']:
            key = row['full_trace']
            if key in games and games[key] != row:
                raise ValueError(f'Conflicting copies of reused game: {key}')
            games[key] = row
    counts = Counter(row['status'] for row in games.values())
    if any(row['steps'] != 719 for row in games.values() if row['status'] == 'complete'):
        raise ValueError('A completed game did not reach 719 decisions')
    return {'unique_attempts': len(games), 'status_counts': dict(counts),
            'reused_rows_not_counted_again': sum(len(json.loads(members[n])['games']) for n in GAME_REPORTS) - len(games),
            'primary_development': json.loads(members['barnyard-development.json'])['summary'],
            'primary_held': json.loads(members['barnyard-held.json'])['summary'],
            'nearclone_repaired': json.loads(members['nearclone-development-v2.json'])['summary'],
            'failed_attempts': [row['failure'] for row in games.values() if row['status'] != 'complete'],
            'limits': 'Full report/freezes/replay analyses are published; full transition-trace bytes remain in the producing cloud evidence archive.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parts-dir', type=Path, default=HERE)
    parser.add_argument('--write-archive', type=Path)
    args = parser.parse_args()
    members = load_reports(args.parts_dir)
    result = summary(members)
    if args.write_archive:
        with args.write_archive.open('xb') as stream:
            stream.write(archive_bytes(args.parts_dir))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
