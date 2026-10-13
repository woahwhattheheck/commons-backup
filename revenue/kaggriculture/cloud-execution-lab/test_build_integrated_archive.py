# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for standalone TITAN release closure."""
import ast
import io
import json
from pathlib import Path
import tarfile

import build_integrated


def test_enabled_town_procurement_is_in_standalone_archive():
    config = json.loads((build_integrated.ROOT / "TITAN-CONFIG.json").read_text())
    assert config["town_procurement"] is True

    data, _manifest, receipt = build_integrated.render()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        names = set(archive.getnames())

    assert "main.py" in names
    assert "town_procurement.py" in names
    assert receipt["runtime_files"] == len(build_integrated.source_files())


def _absolute_import_roots(source):
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _local_root_exists(source_path, name):
    """Whether an absolute import root resolves to repository-local source."""
    source = (build_integrated.ROOT / source_path).resolve()
    for base in (source.parent, build_integrated.ROOT):
        target = base / name
        if target.with_suffix(".py").is_file() or (target / "__init__.py").is_file():
            return True
    return False


def _archive_provides_root(mapping, name):
    """Whether the standalone archive contains a module/package for one root."""
    if f"{name}.py" in mapping or f"{name}/__init__.py" in mapping:
        return True
    prefix = f"{name}/"
    return any(path.startswith(prefix) and path.endswith(".py") for path in mapping)


def _missing_local_root_imports(mapping):
    missing = {}
    for member, source_path in mapping.items():
        if "/" in member or not member.endswith(".py"):
            continue
        source = (build_integrated.ROOT / source_path).read_text()
        omitted = sorted(
            name for name in _absolute_import_roots(source)
            if _local_root_exists(source_path, name)
            and not _archive_provides_root(mapping, name)
        )
        if omitted:
            missing[member] = omitted
    return missing


def test_packaged_root_modules_are_closed_over_local_imports():
    """A packaged root module cannot depend on an omitted local import root."""
    missing = _missing_local_root_imports(build_integrated.source_files())
    assert not missing, f"standalone local-import closure holes: {missing}"


def test_relocated_root_source_imports_are_part_of_closure():
    """Mapped sibling-tree sources must not hide their local root dependencies."""
    mapping = dict(build_integrated.source_files())
    pressure_source = mapping["pressure_priority.py"]
    assert pressure_source == "../cloud-opponent-league/lark-responsive/pressure_priority.py"
    assert mapping.pop("sell_priority.py") == "../cloud-opponent-league/lark-responsive/sell_priority.py"

    missing = _missing_local_root_imports(mapping)
    assert missing.get("pressure_priority.py") == ["sell_priority"]
