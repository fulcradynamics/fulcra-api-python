"""A credentials file that several processes can share safely."""

import contextlib
import os
import pathlib
import sys
import tempfile
import time
from typing import Generator, Optional

from .credentials import FulcraCredentials
from .oidc import FulcraAuthUnavailable

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# How long to wait for another process to finish refreshing before giving up:
# longer than a refresh can take with its retries and timeouts.
LOCK_TIMEOUT = 120.0


class CredentialsLockTimeout(FulcraAuthUnavailable):
    """Another process held the credentials lock for too long."""


class CredentialsFile:
    """
    Credentials stored as JSON at `path`, shared by every process that uses
    it (each `fulcra` CLI command, the stdio MCP server, ...).

    `FulcraAPI` refreshes under `lock()` and re-reads the file first, so when
    several processes find the access token expired at once only one of them
    spends the refresh token. With refresh token rotation, Auth0 treats a
    refresh token used twice as stolen and revokes the user's session.
    """

    def __init__(self, path: os.PathLike | str):
        self.path = pathlib.Path(path)

    def load(self) -> Optional[FulcraCredentials]:
        """The stored credentials, or None if there's no file."""
        try:
            data = self.path.read_text()
        except FileNotFoundError:
            return None
        return FulcraCredentials.from_json(data)

    def save(self, creds: FulcraCredentials):
        """
        Replace the stored credentials atomically, readable only by the
        current user, so a reader never sees a partly written file.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(creds.to_json())
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise

    @contextlib.contextmanager
    def lock(self) -> Generator[None, None, None]:
        """Hold an exclusive lock on the credentials, across processes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(self.path.name + ".lock")
        with open(lock_path, "a+") as f:
            _acquire(f.fileno())
            try:
                yield
            finally:
                _release(f.fileno())


def _acquire(fd: int):
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            if sys.platform == "win32":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() > deadline:
                raise CredentialsLockTimeout(
                    "timed out waiting for another process to refresh the Fulcra credentials"
                )
            time.sleep(0.1)


def _release(fd: int):
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
