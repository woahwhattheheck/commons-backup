from __future__ import annotations

import base64
import hashlib
import json
import os
import ssl
import stat
import tempfile
import threading
from contextlib import contextmanager
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Tuple, Union


class StoreConflict(RuntimeError):
    pass


class StoreUncertain(RuntimeError):
    pass


class FileLeaseStore:
    """Reference atomic store used for local/operator proofs.

    `O_CREAT|O_EXCL` models GitHub create-if-absent. Delete is generation-bound.
    It is intentionally suitable only for one shared filesystem namespace.
    """

    def __init__(self, root: Union[str, os.PathLike]):
        self.root = Path(root)
        self.active = self.root / "active"
        self.outcomes = self.root / "outcomes"
        self.active.mkdir(parents=True, exist_ok=True)
        self.outcomes.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _generation(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _read(self, path: Path):
        try:
            flags = os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0))
            fd = os.open(path, flags)
        except FileNotFoundError:
            return None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise StoreConflict("lease path is not regular file")
            data = b""
            while True:
                block = os.read(fd, 65536)
                if not block:
                    break
                data += block
                if len(data) > 512 * 1024:
                    raise StoreConflict("lease file oversized")
            return data, self._generation(data)
        finally:
            os.close(fd)

    def get_active(self, org_fingerprint: str):
        return self._read(self.active / f"{org_fingerprint}.json")

    def get_outcome(self, org_fingerprint: str, lease_id: str):
        return self._read(self.outcomes / org_fingerprint / f"{lease_id}.json")

    def _create(self, path: Path, content: bytes) -> str:
        """Publish only complete bytes, with link(2) as the create-if-absent point."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".lease-stage-", dir=path.parent)
        tmp = Path(tmp_name)
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(content)
            total = 0
            while total < len(view):
                total += os.write(fd, view[total:])
            os.fsync(fd)
            os.close(fd)
            fd = -1
            try:
                os.link(tmp, path)
            except FileExistsError as exc:
                raise StoreConflict("already exists") from exc
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
        return self._generation(content)

    @contextmanager
    def _org_lock(self, org_fingerprint: str):
        """Serialize local-reference acquire/release for one organization."""
        lock_path = self.active / f".{org_fingerprint}.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                import fcntl
            except ImportError as exc:
                raise StoreConflict("local reference store requires advisory flock support") from exc
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def create_active(self, org_fingerprint: str, content: bytes) -> str:
        with self._org_lock(org_fingerprint):
            return self._create(self.active / f"{org_fingerprint}.json", content)

    def create_outcome(self, org_fingerprint: str, lease_id: str, content: bytes) -> str:
        return self._create(self.outcomes / org_fingerprint / f"{lease_id}.json", content)

    def delete_active(self, org_fingerprint: str, expected_generation: str) -> None:
        path = self.active / f"{org_fingerprint}.json"
        with self._org_lock(org_fingerprint):
            current = self._read(path)
            if current is None:
                raise StoreConflict("active lease missing")
            _, generation = current
            if generation != expected_generation:
                raise StoreConflict("active lease generation changed")
            os.unlink(path)


class GitHubContentsLeaseStore:
    """GitHub Contents API adapter on a dedicated coordination branch.

    Atomicity comes from create-without-sha for acquire/outcome and delete-with-exact
    blob sha for release. A stale deleter cannot remove a successor generation because
    GitHub rejects a SHA mismatch.
    """

    def __init__(
        self,
        *,
        repository: str,
        branch: str,
        token: str,
        api_base: str = "https://api.github.com",
        opener: Optional[Callable[[urllib.request.Request], Tuple[int, bytes]]] = None,
    ):
        if "/" not in repository or repository.count("/") != 1:
            raise ValueError("repository must be owner/name")
        if not branch or len(branch) > 200:
            raise ValueError("invalid coordination branch")
        if not token:
            raise ValueError("GitHub token is required")
        self.repository = repository
        self.branch = branch
        self.token = token
        self.api_base = api_base.rstrip("/")
        self._opener = opener or self._default_open

    def _url(self, rel: str) -> str:
        return f"{self.api_base}/repos/{self.repository}/contents/{urllib.parse.quote(rel, safe='/')}"

    def _default_open(self, req: urllib.request.Request) -> tuple[int, bytes]:
        try:
            with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise StoreUncertain("GitHub request outcome uncertain") from exc

    def _request(self, method: str, rel: str, payload: Optional[dict] = None, query: Optional[dict] = None) -> Tuple[int, dict]:
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        url = self._url(rel)
        if query:
            url += "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        status, raw = self._opener(req)
        if not raw:
            return status, {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise StoreUncertain("non-JSON GitHub response") from exc
        return status, body

    def _get(self, rel: str):
        status, body = self._request("GET", rel, query={"ref": self.branch})
        if status == 404:
            return None
        if status != 200:
            raise StoreUncertain(f"GitHub GET failed status={status}")
        if body.get("type") != "file" or not isinstance(body.get("sha"), str):
            raise StoreConflict("GitHub lease path is not a regular file")
        try:
            content = base64.b64decode(body["content"], validate=False)
        except Exception as exc:
            raise StoreConflict("invalid GitHub file content") from exc
        return content, body["sha"]

    def get_active(self, org_fingerprint: str):
        return self._get(f"active/{org_fingerprint}.json")

    def get_outcome(self, org_fingerprint: str, lease_id: str):
        return self._get(f"outcomes/{org_fingerprint}/{lease_id}.json")

    def _create(self, rel: str, content: bytes, message: str) -> str:
        payload = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.branch,
        }
        status, body = self._request("PUT", rel, payload)
        if status in (200, 201):
            sha = body.get("content", {}).get("sha")
            if not isinstance(sha, str):
                raise StoreUncertain("GitHub create returned no blob sha")
            return sha
        if status in (409, 422):
            raise StoreConflict("GitHub create-if-absent conflict")
        raise StoreUncertain(f"GitHub create outcome uncertain status={status}")

    def create_active(self, org_fingerprint: str, content: bytes) -> str:
        return self._create(f"active/{org_fingerprint}.json", content, "coord: acquire organization outbound lease")

    def create_outcome(self, org_fingerprint: str, lease_id: str, content: bytes) -> str:
        return self._create(f"outcomes/{org_fingerprint}/{lease_id}.json", content, "coord: record organization outbound outcome")

    def delete_active(self, org_fingerprint: str, expected_generation: str) -> None:
        rel = f"active/{org_fingerprint}.json"
        payload = {
            "message": "coord: release unsent organization outbound lease",
            "sha": expected_generation,
            "branch": self.branch,
        }
        status, _ = self._request("DELETE", rel, payload)
        if status in (200, 204):
            return
        if status in (409, 422):
            raise StoreConflict("GitHub conditional release generation mismatch")
        raise StoreUncertain(f"GitHub release outcome uncertain status={status}")
