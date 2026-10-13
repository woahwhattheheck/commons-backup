from __future__ import annotations

import os
import stat
from typing import Any

try:
    import pwd
except ImportError:  # pragma: no cover - production CURRENT fails closed
    pwd = None

from .authority import AuthorityError


_COMPONENTS = (".config", "commons", "service-deal-economics")
_FILENAMES = ("authority-key.json", "current-authority.json", "authority-floor.json")


def fixed_host_root() -> str:
    """Return the verifier-owned POSIX trust root without pathlib dispatch."""
    if os.name != "posix" or pwd is None:
        raise AuthorityError("fixed-host authority requires POSIX account semantics")
    try:
        home = pwd.getpwuid(os.getuid()).pw_dir
    except (KeyError, OSError) as exc:
        raise AuthorityError("cannot resolve fixed OS-account home") from exc
    if type(home) is not str or not home.startswith("/") or "\x00" in home:
        raise AuthorityError("fixed OS-account home must be absolute POSIX text")
    base = home.rstrip("/") or "/"
    if base == "/":
        return "/" + "/".join(_COMPONENTS)
    return base + "/" + "/".join(_COMPONENTS)


def fixed_host_paths() -> tuple[str, str, str]:
    root = fixed_host_root()
    return tuple(root + "/" + name for name in _FILENAMES)  # type: ignore[return-value]


def no_symlink_components(path: Any) -> None:
    """Reject symlink components using only POSIX text + captured OS calls.

    Production CURRENT receives strings from ``fixed_host_paths``. ``os.fspath``
    is retained only so historical/hermetic tests that inject pathlib objects
    continue to exercise the same file validation helper.
    """
    try:
        text = os.fspath(path)
    except TypeError as exc:
        raise AuthorityError("host trust path must be filesystem text") from exc
    if type(text) is not str or not text.startswith("/") or "\x00" in text:
        raise AuthorityError("host trust path must be absolute POSIX text")
    current = ""
    for part in text.split("/"):
        if not part:
            continue
        current += "/" + part
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode):
            raise AuthorityError("host trust path contains a symlink")
