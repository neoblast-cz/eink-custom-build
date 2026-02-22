import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

logger = logging.getLogger(__name__)

SHEETS_TOKEN_PATH = Path(__file__).parent.parent.parent / "google_sheets_token.json"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class HabitsModule(BaseModule):
    NAME = "habits"
    DISPLAY_NAME = "Habits"
    DESCRIPTION = "Track daily habits via Google Sheets"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        data = self._fetch_from_sheets(settings)
        tz = ZoneInfo(settings.get("_timezone", "Europe/Brussels"))
        today = datetime.now(tz).date()
        max_display = int(settings.get("max_display", 8))
        return self._draw(width, height, data, today, max_display)

    def default_settings(self) -> dict:
        return {"spreadsheet_id": "", "max_display": 8}

    def _get_sheets_service(self, settings: dict):
        """Build an authenticated Google Sheets API service."""
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError:
            logger.error("Install google libs: pip install google-auth-oauthlib google-api-python-client")
            return None

        if not SHEETS_TOKEN_PATH.exists():
            logger.warning("Google Sheets not authorized. Visit the Habits settings page to authorize.")
            return None

        try:
            creds = Credentials.from_authorized_user_file(str(SHEETS_TOKEN_PATH), SHEETS_SCOPES)

            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                SHEETS_TOKEN_PATH.write_text(creds.to_json())

            return build("sheets", "v4", credentials=creds)
        except Exception as e:
            logger.error(f"Google Sheets auth failed: {e}")
            return None

    def _fetch_from_sheets(self, settings: dict) -> dict:
        """Fetch habits data from Google Sheets and convert to internal format."""
        spreadsheet_id = settings.get("spreadsheet_id", "")
        if not spreadsheet_id:
            return {"habits": [], "log": {}}

        service = self._get_sheets_service(settings)
        if not service:
            return {"habits": [], "log": {}}

        try:
            # Read all data from the first sheet
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range="A1:Z1000",
            ).execute()

            rows = result.get("values", [])
            if len(rows) < 1:
                return {"habits": [], "log": {}}

            # Row 0 = headers: ["Date", "Exercise", "Read 30 min", ...]
            headers = rows[0]
            habit_names = headers[1:]  # Skip "Date" column

            habits = [{"name": name} for name in habit_names]
            log = {}

            for row in rows[1:]:
                if not row or not row[0]:
                    continue
                date_str = row[0].strip()
                day_log = {}
                for i, habit_name in enumerate(habit_names):
                    cell = row[i + 1].strip().upper() if i + 1 < len(row) else ""
                    day_log[habit_name] = cell in ("TRUE", "1", "YES")
                log[date_str] = day_log

            return {"habits": habits, "log": log}

        except Exception as e:
            logger.error(f"Google Sheets fetch failed: {e}")
            return {"habits": [], "log": {}}

    def _calc_percentage(self, log: dict, habit_name: str, today, days: int) -> int | None:
        done = 0
        total = 0
        for i in range(days):
            date_str = (today - timedelta(days=i)).isoformat()
            entry = log.get(date_str, {})
            if habit_name in entry:
                total += 1
                if entry[habit_name]:
                    done += 1
            else:
                total += 1  # count missing as not done
        if total == 0:
            return None
        return round(done / total * 100)

    def _load_fonts(self):
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        fonts = {}
        for size_name, size in [("xl", 36), ("lg", 24), ("md", 16), ("sm", 13), ("xs", 11)]:
            loaded = False
            for path in font_paths:
                try:
                    fonts[size_name] = ImageFont.truetype(path, size)
                    loaded = True
                    break
                except OSError:
                    continue
            if not loaded:
                fonts[size_name] = ImageFont.load_default()
        return fonts

    def _draw(self, width: int, height: int, data: dict, today, max_display: int) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()

        habits = data.get("habits", [])[:max_display]
        log = data.get("log", {})
        margin = 20
        days_shown = 10

        if not habits:
            draw.text((margin, margin), "Habits", fill=0, font=fonts["lg"])
            if not SHEETS_TOKEN_PATH.exists():
                draw.text((margin, margin + 35), "Not authorized", fill=80, font=fonts["md"])
                draw.text((margin, margin + 58), "Open Habits settings in the web UI to connect", fill=120, font=fonts["sm"])
                draw.text((margin, margin + 78), "your Google Sheet.", fill=120, font=fonts["sm"])
            else:
                draw.text((margin, margin + 35), "No habits found in the spreadsheet.", fill=100, font=fonts["md"])
            return img

        # Layout: left section (name + circles + per-habit %) | right section (overall big %)
        overall_panel_w = 120  # right panel for overall stats
        left_w = width - overall_panel_w

        name_w = 150
        circles_w = days_shown * 22 + 10
        pct_col_w = 50  # per-habit percentage columns (7d, 30d)
        content_w = name_w + circles_w + pct_col_w * 2
        x_start = max(margin, (left_w - content_w) // 2)

        col_name = x_start
        col_circles = col_name + name_w
        col_7d = col_circles + circles_w
        col_30d = col_7d + pct_col_w

        y = margin

        # Header
        draw.text((col_name, y), "Habits", fill=0, font=fonts["lg"])

        # Day labels above circles
        for i in range(days_shown):
            day = today - timedelta(days=days_shown - 1 - i)
            day_label = str(day.day)
            cx = col_circles + i * 22 + 11
            lw = fonts["xs"].getlength(day_label)
            draw.text((cx - lw // 2, y + 4), day_label, fill=160, font=fonts["xs"])

        # Percentage headers (7d, 30d)
        for label, col_x in [("7d", col_7d), ("30d", col_30d)]:
            lw = fonts["sm"].getlength(label)
            draw.text((col_x + (pct_col_w - lw) // 2, y + 2), label, fill=100, font=fonts["sm"])

        y += 32

        # Separator
        draw.line([(x_start, y), (col_30d + pct_col_w, y)], fill=180, width=1)
        y += 8

        # Habit rows
        row_h = (height - y - margin - 10) // max(len(habits), 1)
        row_h = min(row_h, 48)
        circle_r = 8

        overall_7d = []
        overall_30d = []

        for habit_info in habits:
            habit_name = habit_info["name"]

            # Name (truncate if needed)
            display_name = habit_name
            if fonts["md"].getlength(display_name) > name_w - 10:
                while fonts["md"].getlength(display_name + "..") > name_w - 10 and len(display_name) > 1:
                    display_name = display_name[:-1]
                display_name += ".."
            draw.text((col_name, y + (row_h - 18) // 2), display_name, fill=0, font=fonts["md"])

            # Circles for last 10 days
            for i in range(days_shown):
                day = today - timedelta(days=days_shown - 1 - i)
                date_str = day.isoformat()
                entry = log.get(date_str, {})
                done = entry.get(habit_name, False)

                cx = col_circles + i * 22 + 11
                cy = y + row_h // 2

                if done:
                    draw.ellipse([cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
                                  fill=0)
                else:
                    draw.ellipse([cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
                                  outline=180, width=1)

            # Per-habit percentages (7d, 30d)
            for days, col_x, overall_list in [
                (7, col_7d, overall_7d),
                (30, col_30d, overall_30d),
            ]:
                pct = self._calc_percentage(log, habit_name, today, days)
                if pct is not None:
                    overall_list.append(pct)
                    pct_str = f"{pct}%"
                    fill = max(0, 160 - pct)
                else:
                    pct_str = "--"
                    fill = 180
                pw = fonts["sm"].getlength(pct_str)
                draw.text((col_x + (pct_col_w - pw) // 2, y + (row_h - 14) // 2),
                           pct_str, fill=fill, font=fonts["sm"])

            y += row_h

        # Separator below habits
        draw.line([(x_start, y + 4), (col_30d + pct_col_w, y + 4)], fill=180, width=1)

        # ---- Right panel: Overall percentages in big font ----
        panel_x = left_w
        panel_y = margin + 10
        panel_center = panel_x + overall_panel_w // 2

        # "Overall" label
        label = "Overall"
        lw = fonts["md"].getlength(label)
        draw.text((panel_center - lw // 2, panel_y), label, fill=80, font=fonts["md"])
        panel_y += 35

        for values, label in [(overall_7d, "7d"), (overall_30d, "30d")]:
            if values:
                avg = round(sum(values) / len(values))
                pct_str = f"{avg}%"
                fill = max(0, 140 - avg)
            else:
                pct_str = "--"
                fill = 180

            # Big percentage
            pw = fonts["xl"].getlength(pct_str)
            draw.text((panel_center - pw // 2, panel_y), pct_str, fill=fill, font=fonts["xl"])
            panel_y += 42

            # Small label below
            lw = fonts["sm"].getlength(label)
            draw.text((panel_center - lw // 2, panel_y), label, fill=120, font=fonts["sm"])
            panel_y += 35

        return img
