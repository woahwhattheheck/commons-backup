# SPDX-License-Identifier: Apache-2.0
"""Release packaging invariants for the integrated wrapper entrypoints."""
import io
import json
import tarfile

import build_integrated


WRAPPERS = ('integrated_main.py', 'integrated_parent.py')


def test_every_declared_runtime_file_has_an_archive_mapping():
    mapping = build_integrated.source_files()
    assert set(build_integrated.RUNTIME) <= set(mapping)


def test_integrated_wrappers_ship_from_their_hardened_source_bytes():
    mapping = build_integrated.source_files()
    archive_bytes, manifest_bytes, _ = build_integrated.render()
    manifest = json.loads(manifest_bytes)

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        for name in WRAPPERS:
            assert mapping[name] == name
            packaged = archive.extractfile(name)
            assert packaged is not None
            assert packaged.read() == (build_integrated.ROOT / name).read_bytes()
            assert manifest['runtime'][name]['source_path'] == name
