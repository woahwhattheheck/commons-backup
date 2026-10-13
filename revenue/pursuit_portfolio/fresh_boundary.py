"""Public current entrypoints closed over a clean isolated interpreter."""
from __future__ import annotations

import base64
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping

from .core import PortfolioError
from .host_kernel import HostAuthorizedPortfolio
from .fresh_exec import WORKER_LIMIT, make_worker_call
from .fresh_protocol import canonical_json, decode_response, rebuild_compile


def build_entrypoints(
    *,
    _canonical=canonical_json,
    _decode=decode_response,
    _rebuild=rebuild_compile,
    _b64encode=base64.b64encode,
    _error=PortfolioError,
    _limit=WORKER_LIMIT,
    _make_call=make_worker_call,
    _realpath=os.path.realpath,
    _isabs=os.path.isabs,
    _stat=os.stat,
    _isreg=stat.S_ISREG,
    _Path=Path,
    _executable=sys.executable,
) -> tuple[Any, Any]:
    executable = _realpath(_executable)
    if not _isabs(executable):
        raise _error("fresh worker executable must be absolute")
    try:
        info = _stat(executable, follow_symlinks=True)
    except OSError as exc:
        raise _error("fresh worker executable unavailable") from exc
    if not _isreg(info.st_mode):
        raise _error("fresh worker executable must be a regular file")
    repo_root = str(_Path(__file__).resolve().parents[2])
    bootstrap = (
        "import sys; "
        f"sys.path.insert(0, {repo_root!r}); "
        "from revenue.pursuit_portfolio.fresh_worker import main; "
        "raise SystemExit(main())"
    )
    worker_call = _make_call(executable, bootstrap)

    def compile_current(
        source: Mapping[str, Any], authority: Mapping[str, Any]
    ) -> HostAuthorizedPortfolio:
        request = _canonical(
            {"action": "compile", "authority": dict(authority), "source": dict(source)}
        )
        return _rebuild(_decode(worker_call(request)))

    def verify_current(
        result_raw: bytes,
        markdown_raw: bytes,
        receipt_raw: bytes,
        authority_raw: bytes,
        current_receipt_raw: bytes,
        host_seal_raw: bytes,
    ) -> dict[str, Any]:
        fields = {
            "authority": authority_raw,
            "current_receipt": current_receipt_raw,
            "host_seal": host_seal_raw,
            "markdown": markdown_raw,
            "receipt": receipt_raw,
            "result": result_raw,
        }
        for name, raw in fields.items():
            if type(raw) is not bytes or len(raw) > _limit:
                raise _error(f"{name}: bounded bytes required")
        request = _canonical(
            {
                "action": "verify",
                "artifacts": {
                    name: _b64encode(raw).decode("ascii")
                    for name, raw in fields.items()
                },
            }
        )
        response = _decode(worker_call(request))
        if set(response) != {"ok", "verified"} or type(response["verified"]) is not dict:
            raise _error("fresh worker verify response has wrong shape")
        return dict(response["verified"])

    return compile_current, verify_current
