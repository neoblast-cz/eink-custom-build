import threading
import logging

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Handles two modes:
    - Single module: refreshes at a fixed interval
    - Rotation: cycles through modules, each with its own display duration
    """

    def __init__(self, render_module_fn, config):
        self._render_module = render_module_fn
        self._config = config
        self._thread = None
        self._stop_event = threading.Event()
        self._force_event = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started")

    def force_refresh(self):
        self._force_event.set()

    def stop(self):
        self._stop_event.set()

    def _loop(self):
        while not self._stop_event.is_set():
            self._config.load()  # pick up any config changes

            if self._config.rotation_enabled:
                self._run_rotation_cycle()
            else:
                self._render_module(self._config.active_module)
                interval = self._config.refresh_minutes * 60
                if self._force_event.wait(timeout=interval):
                    self._force_event.clear()

    def _run_rotation_cycle(self):
        """Run through each module in the rotation list once."""
        for entry in self._config.rotation:
            if self._stop_event.is_set():
                break

            module_name = entry.get("module", "")
            duration_min = int(entry.get("duration_minutes", 5))

            self._render_module(module_name)

            # Wait for this module's duration, or until force-refresh
            if self._force_event.wait(timeout=duration_min * 60):
                self._force_event.clear()
                break  # restart the cycle on force refresh
