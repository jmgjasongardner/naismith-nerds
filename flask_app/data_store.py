"""
Holds the dataset the web app serves, and swaps it atomically.

A rebuild happens on a background thread while requests are still being served,
so readers must never see a half-built dataset. They don't: the rebuild
produces a brand new object and `swap()` rebinds a single reference under a
lock. In-flight requests finish against the old object and are garbage
collected normally.

`version` increments on every swap. Anything caching derived state keys on it.
"""

import threading
from contextlib import contextmanager
from typing import Optional

import duckdb

from collective_bball.paths import db_path


class DataStore:
    def __init__(self, data):
        self._data = data
        self._version = 1
        self._lock = threading.Lock()
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._conn_lock = threading.Lock()

    @property
    def data(self):
        """Current dataset. Read without a lock: rebinding a reference is
        atomic under the GIL, and each rebuild yields a fresh object."""
        return self._data

    @property
    def version(self) -> int:
        return self._version

    def swap(self, new_data) -> int:
        """Replace the dataset and bump the version. Returns the new version."""
        with self._lock:
            self._data = new_data
            self._version += 1
            return self._version

    @contextmanager
    def db(self):
        """Yield the process-wide DuckDB connection, serialized.

        DuckDB permits only one read-write handle to a file at a time, and the
        scheduled rebuild writes while pages are being served, so every caller
        shares one connection rather than opening its own. The connection is
        opened lazily and deliberately never closed.
        """
        with self._conn_lock:
            if self._conn is None:
                self._conn = duckdb.connect(str(db_path()))
            yield self._conn
