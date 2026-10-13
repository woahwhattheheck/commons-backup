from __future__ import annotations

"""Canonical core entrypoint for the commercial laundry operations desk.

There is exactly one product implementation class.  The internal engine is
already hardened when loaded directly; this module gives it the stable public
core import surface and adds the supported non-initializing read-only open path
used by the CLI.  It does not create a second subclass or authority layer.
"""

import importlib.machinery as _machinery
import importlib.util as _importlib_util
import sys as _sys
from pathlib import Path as _LoaderPath

_ENGINE_NAME = "_commercial_laundry_engine"
_ENGINE_PATH = _LoaderPath(__file__).with_name("_laundry_desk_engine.py.disabled")
_loader = _machinery.SourceFileLoader(_ENGINE_NAME, str(_ENGINE_PATH))
_spec = _importlib_util.spec_from_loader(_ENGINE_NAME, _loader)
if _spec is None:
    raise ImportError("unable to load commercial-laundry engine")
_engine = _importlib_util.module_from_spec(_spec)
_sys.modules[_ENGINE_NAME] = _engine
try:
    _loader.exec_module(_engine)
finally:
    _sys.modules.pop(_ENGINE_NAME, None)

for _name, _value in vars(_engine).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


def _make_read_only_surface():
    original_connect = LaundryDesk._connect
    path_type = Path
    sqlite_module = sqlite3
    closing_type = closing
    expected_schema_version = str(SCHEMA_VERSION)

    def read_only_connect(self):
        if not getattr(self, "_commons_read_only", False):
            return original_connect(self)
        database_path = path_type(self.database).resolve()
        uri = database_path.as_uri() + "?mode=ro"
        conn = sqlite_module.connect(uri, uri=True, timeout=8.0, isolation_level=None)
        conn.row_factory = sqlite_module.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 8000")
        conn.execute("PRAGMA query_only = ON")
        return conn

    @classmethod
    def open_read_only(cls, database: str | Path):
        database_path = path_type(database)
        if not database_path.is_file():
            raise FileNotFoundError(f"laundry database does not exist: {database_path}")

        # Skip the writable initializer: it creates parent directories and
        # initializes schema by design, which a read-only inspection must not do.
        instance = cls.__new__(cls)
        instance.database = str(database_path)
        instance._commons_read_only = True
        try:
            with closing_type(instance._connect()) as conn:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()
        except sqlite_module.Error as exc:
            raise LaundryDeskError("existing laundry database schema is unavailable") from exc
        if row is None or row[0] != expected_schema_version:
            observed = None if row is None else row[0]
            raise LaundryDeskError(f"unsupported schema version {observed}")
        return instance

    return open_read_only, read_only_connect


LaundryDesk.open_read_only, LaundryDesk._connect = _make_read_only_surface()

# No raw implementation module/class handle is introduced beyond the one class
# object exported above. The class's functions legitimately retain their engine
# globals, while the read-only methods retain only closure-captured dependencies.
del _engine, _loader, _spec, _name, _value, _make_read_only_surface
