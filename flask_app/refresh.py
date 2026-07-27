"""
Keeps the served dataset in sync with the OneDrive workbook.

A background thread polls OneDrive on an interval, hashes the workbook, and
rebuilds only when the bytes actually changed. Polling beats a wall-clock cron
here because the Fly machine suspends when idle: an interval check resumes
correctly, whereas "run at 06:00" quietly does not fire on a suspended machine.

The workbook is ~90 KB, so a poll costs almost nothing; the expensive rebuild
runs only when Jason has actually entered games.

Rebuilds happen off the request path. Requests keep being served from the old
dataset until the new one is fully built and saved, then a single atomic swap
switches over.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from collective_bball import artifacts

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30 * 60

# After a failure, back off rather than retrying every interval. Mostly this
# stops an expired token from writing a log line every 30 minutes forever.
FAILURE_BACKOFF_SECONDS = 4 * 60 * 60


class RefreshService:
    def __init__(self, store, interval_seconds: int = DEFAULT_INTERVAL_SECONDS):
        self._store = store
        self._interval = interval_seconds
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.status = {
            "last_checked_at": None,
            "last_rebuilt_at": None,
            "last_error": None,
            "consecutive_failures": 0,
            "rebuild_count": 0,
        }

    # -- core ------------------------------------------------------------

    def run_once(self, force: bool = False, allow_stale: bool = False) -> dict:
        """Check OneDrive and rebuild if the workbook changed.

        Serialized: a manual trigger arriving mid-rebuild waits rather than
        starting a second concurrent build.
        """
        with self._lock:
            from collective_bball.utils.util_code import get_data_source

            self.status["last_checked_at"] = _now()

            try:
                source = get_data_source(allow_stale=allow_stale)
                fingerprint = artifacts.source_fingerprint(source)

                current = getattr(self._store.data, "source_fingerprint", None)
                if not force and fingerprint and fingerprint == current:
                    self.status["last_error"] = None
                    self.status["consecutive_failures"] = 0
                    return {"changed": False, "reason": "workbook unchanged"}

                logger.info("Workbook changed; rebuilding dataset")
                data = artifacts.build(source)
                artifacts.save(data, fingerprint=fingerprint)
                version = self._store.swap(artifacts.load())

                self.status.update(
                    {
                        "last_rebuilt_at": _now(),
                        "last_error": None,
                        "consecutive_failures": 0,
                        "rebuild_count": self.status["rebuild_count"] + 1,
                    }
                )
                logger.info("Dataset swapped in at version %d", version)
                return {
                    "changed": True,
                    "version": version,
                    "games": data.games.height,
                    "ingest_report": data.ingest_report,
                }

            except Exception as exc:
                self.status["last_error"] = f"{type(exc).__name__}: {exc}"
                self.status["consecutive_failures"] += 1
                logger.exception("Refresh failed")
                return {"changed": False, "error": self.status["last_error"]}

    # -- scheduling ------------------------------------------------------

    def _loop(self) -> None:
        # Don't poll the instant we boot; the dataset was just loaded.
        while not self._stop.wait(self._interval):
            result = self.run_once()
            if result.get("error"):
                logger.warning(
                    "Backing off refresh for %d minutes after failure",
                    FAILURE_BACKOFF_SECONDS // 60,
                )
                if self._stop.wait(FAILURE_BACKOFF_SECONDS):
                    return

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="onedrive-refresh", daemon=True
        )
        self._thread.start()
        logger.info(
            "Refresh service started; polling OneDrive every %d minutes",
            self._interval // 60,
        )

    def stop(self) -> None:
        self._stop.set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
