import threading
import logging

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Runs a refresh callback on a fixed interval.
    Interval is re-read each cycle so config changes take effect immediately.
    """

    def __init__(self, refresh_callback, get_interval_fn):
        self._callback = refresh_callback
        self._get_interval = get_interval_fn
        self._thread = None
        self._stop_event = threading.Event()
        self._force_event = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started")

    def force_refresh(self):
        """Trigger an immediate refresh (from web UI 'Refresh Now' button)."""
        self._force_event.set()

    def stop(self):
        self._stop_event.set()

    def _loop(self):
        self._run_refresh()

        while not self._stop_event.is_set():
            interval_seconds = self._get_interval() * 60
            self._force_event.wait(timeout=interval_seconds)
            if self._stop_event.is_set():
                break
            self._force_event.clear()
            self._run_refresh()

    def _run_refresh(self):
        try:
            self._callback()
        except Exception:
            logger.exception("Refresh cycle failed")
