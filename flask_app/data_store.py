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
        """Open a DuckDB connection for the duration of one operation.

        Serialized, because DuckDB permits a single read-write handle per file
        and the scheduled rebuild writes while pages are being served.

        Deliberately opened and closed per use rather than held for the
        lifetime of the process. A long-lived handle keeps the file locked, so
        a rebuild from the CLI — `python -m collective_bball.main` — fails with
        "Could not set lock on file" for as long as any server is running.
        Holding it saved a millisecond and cost the ability to rebuild.
        """
        with self._conn_lock:
            conn = duckdb.connect(str(db_path()))
            try:
                yield conn
            finally:
                conn.close()
