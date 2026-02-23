import logging
import urllib.request
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

logger = logging.getLogger(__name__)

HABITICA_API = "https://habitica.com/api/v3"


class HabitsModule(BaseModule):
    NAME = "habits"
    DISPLAY_NAME = "Habits"
    DESCRIPTION = "Track daily habits from Habitica"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        data = self._fetch_from_habitica(settings)
        tz = ZoneInfo(settings.get("_timezone", "Europe/Brussels"))
        today = datetime.now(tz).date()
        max_display = int(settings.get("max_display", 8))
        return self._draw(width, height, data, today, max_display)

    def default_settings(self) -> dict:
        return {"habitica_user_id": "", "habitica_api_token": "", "max_display": 8}

    def _fetch_from_habitica(self, settings: dict) -> dict:
        """Fetch dailies from Habitica API and convert to internal format."""
        user_id = settings.get("habitica_user_id", "")
        api_token = settings.get("habitica_api_token", "")

        if not user_id or not api_token:
            return {"habits": [], "log": {}}

        try:
            url = f"{HABITICA_API}/tasks/user?type=dailys"
            req = urllib.request.Request(url, headers={
                "x-api-user": user_id,
                "x-api-key": api_token,
                "x-client": f"{user_id}-EinkPi",
                "Content-Type": "application/json",
            })

            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())

            if not result.get("success"):
                logger.error(f"Habitica API error: {result}")
                return {"habits": [], "log": {}}

            dailies = result["data"]

            # Build habits list and log from history
            habits = []
            log = {}  # {date_str: {habit_name: bool}}

            for daily in dailies:
                name = daily["text"]
                # Store created date to cap percentage calculations
                created_at = daily.get("createdAt", "")
                created_date = None
                if created_at:
                    try:
                        created_date = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        ).strftime("%Y-%m-%d")
                    except (ValueError, TypeError):
                        pass
                streak = daily.get("streak", 0)
                habits.append({"name": name, "created": created_date, "streak": streak})

                # Process history entries
                for entry in daily.get("history", []):
                    dt = datetime.fromtimestamp(entry["date"] / 1000, tz=timezone.utc)
                    date_str = dt.strftime("%Y-%m-%d")
                    completed = entry.get("completed", False)

                    if date_str not in log:
                        log[date_str] = {}

                    # Multiple entries per day possible — last one wins
                    log[date_str][name] = completed

                # Today's status comes from the task's `completed` field
                # (history may not have today's entry yet)
                today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if today_str not in log:
                    log[today_str] = {}
                log[today_str][name] = daily.get("completed", False)

            return {"habits": habits, "log": log}

        except Exception as e:
            logger.error(f"Habitica fetch failed: {e}")
            return {"habits": [], "log": {}}

    def _calc_percentage(self, log: dict, habit_name: str, today, days: int,
                         created_date: str | None = None) -> int | None:
        """Calculate completion percentage, excluding today (starts from yesterday).
        Only counts days that have actual log data for this habit — days with
        no Habitica history entry are skipped (API doesn't return full history)."""
        done = 0
        total = 0
        for i in range(1, days + 1):  # start from 1 to skip today
            date_str = (today - timedelta(days=i)).isoformat()
            # Skip days before the habit was created
            if created_date and date_str < created_date:
                continue
            entry = log.get(date_str, {})
            if habit_name in entry:
                total += 1
                if entry[habit_name]:
                    done += 1
            # Days with no log entry are skipped — Habitica API
            # doesn't return complete history for all days
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
        days_shown = 15

        if not habits:
            draw.text((margin, margin), "Habits", fill=0, font=fonts["lg"])
            draw.text((margin, margin + 35), "No habits found.", fill=80, font=fonts["md"])
            draw.text((margin, margin + 58), "Enter your Habitica credentials in the", fill=120, font=fonts["sm"])
            draw.text((margin, margin + 78), "module settings page.", fill=120, font=fonts["sm"])
            return img

        # Layout: left section (name + circles + per-habit %) | right section (overall big %)
        overall_panel_w = 120
        left_w = width - overall_panel_w

        name_w = 140
        circles_w = days_shown * 22 + 10
        pct_col_w = 42
        content_w = name_w + circles_w + pct_col_w * 4
        x_start = max(margin, (left_w - content_w) // 2)

        col_name = x_start
        col_circles = col_name + name_w
        col_7d = col_circles + circles_w
        col_30d = col_7d + pct_col_w

        y = margin

        # Header
        draw.text((col_name, y), "Habits", fill=0, font=fonts["lg"])

        # Day labels above circles (today is bold/darker)
        for i in range(days_shown):
            day = today - timedelta(days=days_shown - 1 - i)
            day_label = str(day.day)
            cx = col_circles + i * 22 + 11
            lw = fonts["xs"].getlength(day_label)
            is_today = (i == days_shown - 1)
            draw.text((cx - lw // 2, y + 4), day_label,
                      fill=0 if is_today else 160, font=fonts["xs"])

        # Percentage headers (7d, 30d, 60d, streak)
        col_60d = col_30d + pct_col_w
        col_streak = col_60d + pct_col_w
        for label, col_x in [("7d", col_7d), ("30d", col_30d), ("60d", col_60d)]:
            lw = fonts["sm"].getlength(label)
            draw.text((col_x + (pct_col_w - lw) // 2, y + 2), label, fill=100, font=fonts["sm"])
        # Streak header with flame-like symbol
        streak_label = "streak"
        slw = fonts["xs"].getlength(streak_label)
        draw.text((col_streak + (pct_col_w - slw) // 2, y + 4), streak_label, fill=100, font=fonts["xs"])

        y += 32

        # Separator
        draw.line([(x_start, y), (col_streak + pct_col_w, y)], fill=180, width=1)
        y += 8

        # Habit rows
        row_h = (height - y - margin - 10) // max(len(habits), 1)
        row_h = min(row_h, 48)
        circle_r = 8

        overall_7d = []
        overall_30d = []
        overall_60d = []

        # Draw today highlight column (light gray background behind today's circles)
        today_col_idx = days_shown - 1  # today is the last column
        today_cx = col_circles + today_col_idx * 22 + 11
        draw.rectangle(
            [today_cx - circle_r - 3, y - 2, today_cx + circle_r + 3, y + row_h * len(habits) + 2],
            fill=235,
        )

        for habit_info in habits:
            habit_name = habit_info["name"]
            created_date = habit_info.get("created")

            # Name (truncate if needed)
            display_name = habit_name
            if fonts["md"].getlength(display_name) > name_w - 10:
                while fonts["md"].getlength(display_name + "..") > name_w - 10 and len(display_name) > 1:
                    display_name = display_name[:-1]
                display_name += ".."
            draw.text((col_name, y + (row_h - 18) // 2), display_name, fill=0, font=fonts["md"])

            # Circles for last N days
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

            # Per-habit percentages (7d, 30d, 60d) — excludes today
            for days, col_x, overall_list in [
                (7, col_7d, overall_7d),
                (30, col_30d, overall_30d),
                (60, col_60d, overall_60d),
            ]:
                pct = self._calc_percentage(log, habit_name, today, days, created_date)
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

            # Current streak from Habitica API
            streak = habit_info.get("streak", 0)
            streak_str = str(streak)
            sw = fonts["sm"].getlength(streak_str)
            streak_fill = 0 if streak >= 30 else 80 if streak >= 7 else 160
            draw.text((col_streak + (pct_col_w - sw) // 2, y + (row_h - 14) // 2),
                       streak_str, fill=streak_fill, font=fonts["sm"])

            y += row_h

        # Separator below habits
        draw.line([(x_start, y + 4), (col_streak + pct_col_w, y + 4)], fill=180, width=1)

        # ---- Right panel: Overall percentages in big font ----
        panel_x = left_w
        panel_y = margin + 10
        panel_center = panel_x + overall_panel_w // 2

        # "Overall" label
        label = "Overall"
        lw = fonts["md"].getlength(label)
        draw.text((panel_center - lw // 2, panel_y), label, fill=80, font=fonts["md"])
        panel_y += 35

        for values, label in [(overall_7d, "7d"), (overall_30d, "30d"), (overall_60d, "60d")]:
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
            panel_y += 38

            # Small label below
            lw = fonts["sm"].getlength(label)
            draw.text((panel_center - lw // 2, panel_y), label, fill=120, font=fonts["sm"])
            panel_y += 28

        return img
