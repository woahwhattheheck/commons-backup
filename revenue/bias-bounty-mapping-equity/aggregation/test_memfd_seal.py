from __future__ import annotations

import fcntl
import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path

import aggregate as a


class SealedGenerationRegressionTests(unittest.TestCase):
    def test_proc_fd_write_reopen_cannot_mutate_retained_generation(self) -> None:
        """Kill the #14579 predecessor: proc-fd reopen must not restore writes."""
        uri = a.source_registry("northern-ca")["sample"]
        original = b"generation-A"
        with tempfile.TemporaryDirectory() as td:
            fd, path, generation = a._stream_response_to_retained_fd(
                "sample", uri, io.BytesIO(original), Path(td)
            )
            try:
                required = (
                    fcntl.F_SEAL_WRITE
                    | fcntl.F_SEAL_GROW
                    | fcntl.F_SEAL_SHRINK
                    | fcntl.F_SEAL_SEAL
                )
                observed = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
                self.assertEqual(required, observed & required)
                self.assertEqual(hashlib.sha256(original).hexdigest(), generation["sha256"])
                self.assertEqual(len(original), generation["bytes"])

                # `/proc/self/fd/<n>` is a reopenable magic pathname. A read-only
                # retained fd alone is insufficient: old #14579 allowed this fresh
                # writable open to mutate the anonymous tempfile inode. The memfd
                # may still be opened O_WRONLY, but kernel seals must reject every
                # content/size mutation with EPERM.
                attacker = os.open(path, os.O_WRONLY | getattr(os, "O_CLOEXEC", 0))
                try:
                    with self.assertRaises(PermissionError):
                        os.pwrite(attacker, b"B", 0)
                    with self.assertRaises(PermissionError):
                        os.ftruncate(attacker, 1)
                finally:
                    os.close(attacker)

                with open(path, "rb") as retained:
                    self.assertEqual(original, retained.read())
            finally:
                os.close(fd)

    def test_empty_source_still_fails_closed(self) -> None:
        uri = a.source_registry("northern-ca")["sample"]
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(a.AggregationError, "empty source object"):
                a._stream_response_to_retained_fd("sample", uri, io.BytesIO(b""), Path(td))


if __name__ == "__main__":
    unittest.main()
