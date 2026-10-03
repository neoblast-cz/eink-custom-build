# EinkPi — Claude Code Guide

Custom e-ink display app for Raspberry Pi Zero 2 W + Waveshare 7.5" B&W (800×480, SPI).

## Project Structure

```
app.py                  # Entry point: MODULE_REGISTRY, wires all components
core/
  config.py             # Config read/write (config.json); nested get/set helpers
  display.py            # Waveshare EPD wrapper; falls back to preview.png on Windows
  renderer.py           # Calls module.render(), sends to display, handles errors
  scheduler.py          # Fixed-interval or rotation scheduling; force_refresh()
modules/
  base.py               # BaseModule ABC — all modules inherit this
  photos/               # Rotate uploaded images
  calendar_mod/         # ICS URL calendar
  tasks/                # Habitica to-dos
  habits/               # Habitica dailies + stats
  fitness/              # Fitbit activity data
web/
  routes.py             # All Flask routes (single file)
  analytics_data.py     # Local-only Health Analytics dashboard data (see below)
  finance_data.py       # Local-only Finance dashboard data (see below)
  templates/
    base.html / index.html / settings.html / photos_manage.html
    analytics.html / finance.html
    modules/            # One config form per module
static/
  style.css             # Dark theme
  preview.png           # Last rendered frame (auto-generated)
uploads/                # User photo uploads (gitignored)
```

## Adding a New Module

1. Create `modules/<name>/<name>.py` extending `BaseModule`
   - Set `NAME`, `DISPLAY_NAME`, `DESCRIPTION` class attrs
   - Implement `render(width, height, settings) -> PIL.Image`
   - Optionally implement `default_settings() -> dict`
2. Create `web/templates/modules/<name>.html` (config form)
3. Add one import + one dict entry in `app.py` MODULE_REGISTRY

## Key Conventions

- **Rendering**: Pillow only — no headless browser. Modules return grayscale `PIL.Image` (`"L"` mode). The driver converts to B&W `"1"` internally.
- **Display size**: 800×480. Always render exactly this size.
- **Config**: `config.json` (gitignored). Access via `config.module_settings("name")`. Template: `config.example.json`.
- **Fonts**: Load with fallback — try system paths for Pi (DejaVu) and Windows (Segoe UI), then `ImageFont.load_default()`.
- **Secrets**: `config.json`, `google_token.json`, `google_sheets_token.json`, `fitbit_token.json` are all gitignored.
- **Windows dev**: No real EPD — display driver saves `static/preview.png` instead.

## Running Locally (Windows)

```bash
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python app.py          # Web UI at http://localhost:8080
```

## Active Modules

| Name | Description |
|------|-------------|
| `photos` | Rotates uploaded photos one per refresh |
| `calendar` | Renders ICS calendar (no Google OAuth needed) |
| `tasks` | Habitica to-dos |
| `habits` | Habitica dailies, streaks, completion %, level/XP |
| `fitness` | Fitbit activity/steps/HR |

## Local-Only Dashboards (not part of the e-ink pipeline)

Two extra web pages exist purely for local use — they never render to the e-ink display and are inert on the Pi (their data sources are local-machine-only), so nothing about them needs to be part of a deploy:

- **`/analytics`** (`web/analytics_data.py`) — reads a gitignored `Google Health/` export folder placed next to the app. Shows weight/steps/sleep trends and food-logging patterns.
- **`/finance`** (`web/finance_data.py`) — reads a portfolio Google Sheet live via OAuth (`google_sheets_token.json`, gitignored). Credentials live under the `"google"` config key (Permissions page) alongside a `"finance"` config key holding the target `spreadsheet_id`. Unlike Fitbit's OAuth (forced into a manual copy-paste flow because the Pi serves plain HTTP), this redirects automatically since Google explicitly permits HTTP `localhost` redirect URIs and the feature only ever runs locally.

## Deployment (Pi)

```bash
bash install.sh   # sets up venv, systemd service, SPI
```

Service: `einkpi.service`. Web UI: port 8080. Waveshare drivers cloned by install script (gitignored).

## Special Renderer Wiring

Some modules receive extra settings injected by `renderer.py` before `render()` is called:

- All modules: `settings["_timezone"]`
- `tasks`: `settings["_habitica_settings"]` (shared Habitica credentials)
- `fitness`: `settings["_fitbit_client_id"]`, `settings["_fitbit_client_secret"]`
