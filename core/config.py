import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class Config:
    def __init__(self):
        self._data = {}
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                self._data = json.load(f)

    def save(self):
        with open(CONFIG_PATH, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, *keys, default=None):
        """Nested key access: config.get('modules', 'calendar', 'ics_url')"""
        d = self._data
        for k in keys:
            if not isinstance(d, dict) or k not in d:
                return default
            d = d[k]
        return d

    def set(self, value, *keys):
        """Nested key set: config.set('https://...', 'modules', 'calendar', 'ics_url')"""
        d = self._data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    @property
    def display_width(self):
        return self.get("display", "width", default=800)

    @property
    def display_height(self):
        return self.get("display", "height", default=480)

    @property
    def refresh_minutes(self):
        return self.get("display", "refresh_interval_minutes", default=30)

    @property
    def timezone(self):
        return self.get("display", "timezone", default="Europe/Brussels")

    @property
    def google_client_id(self):
        return self.get("google", "client_id", default="")

    @property
    def google_client_secret(self):
        return self.get("google", "client_secret", default="")

    @property
    def active_module(self):
        return self.get("active_module", default="calendar")

    @property
    def rotation(self) -> list:
        """List of {"module": "name", "duration_minutes": N} entries."""
        return self.get("rotation", default=[])

    @property
    def rotation_enabled(self) -> bool:
        return len(self.rotation) > 1

    def module_settings(self, name: str) -> dict:
        return self.get("modules", name, default={})
