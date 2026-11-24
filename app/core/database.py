"""Read-only SQLite connections to existing runtime databases."""

import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path


@contextmanager
def read_sqlite(path: Path, *, timeout: float = 5.0) -> Generator[sqlite3.Connection]:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=timeout)) as connection:
        yield connection
