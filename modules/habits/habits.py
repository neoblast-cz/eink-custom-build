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

            # Fetch user stats (level, XP)
            user_stats = {}
            try:
                # Fetching the full user object (not userFields=stats) matters here:
                # toNextLevel is a server-computed virtual that Habitica only
                # populates on the full document, not on a field-projected query.
                user_url = f"{HABITICA_API}/user"
                user_req = urllib.request.Request(user_url, headers={
                    "x-api-user": user_id,
                    "x-api-key": api_token,
                    "x-client": f"{user_id}-EinkPi",
                    "Content-Type": "application/json",
                })
                with urllib.request.urlopen(user_req, timeout=15) as resp:
                    user_result = json.loads(resp.read())
                if user_result.get("success"):
                    stats = user_result["data"].get("stats", {})
                    user_stats = {
                        "lvl": stats.get("lvl", 0),
                        "exp": int(stats.get("exp", 0)),
                        "toNextLevel": stats.get("toNextLevel", 0),
                    }
            except Exception as e:
                logger.warning(f"Failed to fetch Habitica user stats: {e}")

            return {"habits": habits, "log": log, "user_stats": user_stats}

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

    def _draw_trend_bar(self, draw, col_x, y, col_w, row_h, pct_7d, pct_30d, pct_60d):
        """A single vertical capsule per habit, layering 60d/30d/7d completion as
        nested fills from the bottom — recent performance visually overlays the
        longer-term baseline instead of three separate numbers."""
        bar_w = 22
        pad = 5
        track_top = y + pad
        track_bottom = y + row_h - pad
        track_h = track_bottom - track_top
        bar_x = col_x + (col_w - bar_w) // 2

        if track_h < 10:
            return

        track_r = max(2, min(bar_w // 2, track_h // 2))
        draw.rounded_rectangle(
            [bar_x, track_top, bar_x + bar_w, track_bottom],
            radius=track_r, fill=235, outline=195, width=1,
        )

        # Faint 50% reference tick
        mid_y = track_bottom - int(track_h * 0.5)
        draw.line([(bar_x + 3, mid_y), (bar_x + bar_w - 3, mid_y)], fill=210, width=1)

        # Layer from lightest/longest-window to darkest/most-recent so each
        # shorter window's rounded cap reads as a "liquid level" sitting on top.
        layers = [(pct_60d, 205), (pct_30d, 115), (pct_7d, 15)]
        any_data = False
        for pct, shade in layers:
            if pct is None:
                continue
            any_data = True
            fill_h = int(track_h * pct / 100)
            if fill_h <= 0:
                continue
            fill_top = track_bottom - fill_h
            r = max(2, min(bar_w // 2, fill_h // 2))
            draw.rounded_rectangle([bar_x, fill_top, bar_x + bar_w, track_bottom], radius=r, fill=shade)

        if not any_data:
            draw.line(
                [(bar_x + 5, (track_top + track_bottom) // 2), (bar_x + bar_w - 5, (track_top + track_bottom) // 2)],
                fill=200, width=2,
            )

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
        user_stats = data.get("user_stats", {})
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
        bar_col_w = 60
        pct_col_w = 42
        content_w = name_w + circles_w + bar_col_w + pct_col_w
        x_start = max(margin, (left_w - content_w) // 2)

        col_name = x_start
        col_circles = col_name + name_w
        col_bar = col_circles + circles_w
        col_streak = col_bar + bar_col_w

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

        # Trend bar header — legend for the layered 7d/30d/60d fill
        trend_label = "7·30·60d"
        tlw = fonts["xs"].getlength(trend_label)
        draw.text((col_bar + (bar_col_w - tlw) // 2, y + 4), trend_label, fill=100, font=fonts["xs"])
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

            # Layered trend bar (7d/30d/60d) replaces the old numeric columns
            pct_7d = self._calc_percentage(log, habit_name, today, 7, created_date)
            pct_30d = self._calc_percentage(log, habit_name, today, 30, created_date)
            pct_60d = self._calc_percentage(log, habit_name, today, 60, created_date)
            self._draw_trend_bar(draw, col_bar, y, bar_col_w, row_h, pct_7d, pct_30d, pct_60d)

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

        # ---- Right panel: Level and XP ----
        panel_x = left_w
        panel_center = panel_x + overall_panel_w // 2

        if user_stats:
            lvl = user_stats.get("lvl", 0)
            exp = user_stats.get("exp", 0)
            to_next = user_stats.get("toNextLevel", 0)

            panel_y = margin + 10

            # Level
            lvl_str = f"Lv {lvl}"
            lw = fonts["lg"].getlength(lvl_str)
            draw.text((panel_center - lw // 2, panel_y), lvl_str, fill=0, font=fonts["lg"])
            panel_y += 30

            # XP progress bar
            bar_x = panel_x + 12
            bar_w = overall_panel_w - 24
            bar_h = 8
            progress = exp / to_next if to_next > 0 else 0
            draw.rectangle([bar_x, panel_y, bar_x + bar_w, panel_y + bar_h],
                          fill=230, outline=180)
            if progress > 0:
                draw.rectangle([bar_x, panel_y, bar_x + int(bar_w * progress), panel_y + bar_h],
                              fill=80)
            panel_y += bar_h + 4

            # XP label
            xp_str = f"{exp}/{to_next} XP"
            xw = fonts["xs"].getlength(xp_str)
            draw.text((panel_center - xw // 2, panel_y), xp_str, fill=120, font=fonts["xs"])

        return img
