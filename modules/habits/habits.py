import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).parent.parent.parent / "habits.json"


class HabitsModule(BaseModule):
    NAME = "habits"
    DISPLAY_NAME = "Habits"
    DESCRIPTION = "Track daily habits with streaks and success percentages"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        data = self._load_data()
        tz = ZoneInfo(settings.get("_timezone", "Europe/Brussels"))
        today = datetime.now(tz).date()
        max_display = int(settings.get("max_display", 8))
        return self._draw(width, height, data, today, max_display)

    def default_settings(self) -> dict:
        return {"max_display": 8}

    @staticmethod
    def _load_data() -> dict:
        if DATA_PATH.exists():
            try:
                return json.loads(DATA_PATH.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"habits": [], "log": {}}

    @staticmethod
    def save_data(data: dict):
        DATA_PATH.write_text(json.dumps(data, indent=2))

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
        for size_name, size in [("lg", 24), ("md", 16), ("sm", 13), ("xs", 11)]:
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
            draw.text((margin, margin + 35), "No habits configured yet.", fill=100, font=fonts["md"])
            draw.text((margin, margin + 58), "Add habits in the module settings.", fill=140, font=fonts["sm"])
            return img

        # Layout columns
        name_w = 120       # habit name column
        circles_w = days_shown * 22 + 10  # circles area
        pct_w = 55         # each percentage column
        total_w = name_w + circles_w + pct_w * 3
        x_start = max(margin, (width - total_w) // 2)

        col_name = x_start
        col_circles = col_name + name_w
        col_7d = col_circles + circles_w
        col_30d = col_7d + pct_w
        col_365d = col_30d + pct_w

        y = margin

        # Header
        draw.text((col_name, y), "Habits", fill=0, font=fonts["lg"])

        # Day labels above circles (last 10 days)
        for i in range(days_shown):
            day = today - timedelta(days=days_shown - 1 - i)
            day_label = str(day.day)
            cx = col_circles + i * 22 + 11
            lw = fonts["xs"].getlength(day_label)
            draw.text((cx - lw // 2, y + 4), day_label, fill=160, font=fonts["xs"])

        # Percentage headers
        for label, col_x in [("7d", col_7d), ("30d", col_30d), ("365d", col_365d)]:
            lw = fonts["sm"].getlength(label)
            draw.text((col_x + (pct_w - lw) // 2, y + 2), label, fill=100, font=fonts["sm"])

        y += 32

        # Separator
        draw.line([(x_start, y), (col_365d + pct_w, y)], fill=180, width=1)
        y += 8

        # Habit rows
        row_h = (height - y - margin - 35) // max(len(habits), 1)
        row_h = min(row_h, 48)
        circle_r = 8

        overall_7d = []
        overall_30d = []
        overall_365d = []

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

            # Percentages
            for days, col_x, overall_list in [
                (7, col_7d, overall_7d),
                (30, col_30d, overall_30d),
                (365, col_365d, overall_365d),
            ]:
                pct = self._calc_percentage(log, habit_name, today, days)
                if pct is not None:
                    overall_list.append(pct)
                    pct_str = f"{pct}%"
                    # Color: darker = better
                    fill = max(0, 160 - pct)
                else:
                    pct_str = "--"
                    fill = 180
                pw = fonts["sm"].getlength(pct_str)
                draw.text((col_x + (pct_w - pw) // 2, y + (row_h - 14) // 2),
                           pct_str, fill=fill, font=fonts["sm"])

            y += row_h

        # Overall separator
        y += 4
        draw.line([(x_start, y), (col_365d + pct_w, y)], fill=180, width=1)
        y += 8

        # Overall row
        draw.text((col_name, y), "Overall", fill=0, font=fonts["md"])

        for values, col_x in [
            (overall_7d, col_7d),
            (overall_30d, col_30d),
            (overall_365d, col_365d),
        ]:
            if values:
                avg = round(sum(values) / len(values))
                pct_str = f"{avg}%"
                fill = max(0, 160 - avg)
            else:
                pct_str = "--"
                fill = 180
            pw = fonts["md"].getlength(pct_str)
            draw.text((col_x + (pct_w - pw) // 2, y), pct_str, fill=fill, font=fonts["md"])

        return img
