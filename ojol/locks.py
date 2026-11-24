"""Exclusive file-lock primitives for per-account and control-server processes."""

import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive_lock(directory: Path) -> Generator[None]:
    """Acquire a non-blocking exclusive lock on ``directory / 'run.lock'``."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "run.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Automation sudah berjalan. Gunakan status/stop; tidak membuka controller kedua."
            ) from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def running(directory: Path) -> bool:
    """Return True if another process currently holds the directory lock."""
    try:
        with exclusive_lock(directory):
            return False
    except RuntimeError:
        return True
