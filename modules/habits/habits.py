import logging
import urllib.request
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw
from modules.base import BaseModule
from modules import theme

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

        theme.draw_card(draw, (bar_x, track_top, bar_x + bar_w, track_bottom),
                         radius=theme.clamp_radius(bar_w, bar_w, track_h),
                         fill=theme.SURFACE_CONTAINER_HIGHEST, outline=theme.OUTLINE)

        # Faint 50% reference tick
        mid_y = track_bottom - int(track_h * 0.5)
        draw.line([(bar_x + 3, mid_y), (bar_x + bar_w - 3, mid_y)], fill=theme.OUTLINE, width=1)

        # Layer from lightest/longest-window to darkest/most-recent so each
        # shorter window's rounded cap reads as a "liquid level" sitting on top.
        layers = [(pct_60d, theme.DISABLED), (pct_30d, theme.ON_SURFACE_VARIANT), (pct_7d, theme.ON_SURFACE)]
        any_data = False
        for pct, shade in layers:
            if pct is None:
                continue
            any_data = True
            fill_h = int(track_h * pct / 100)
            if fill_h <= 0:
                continue
            fill_top = track_bottom - fill_h
            r = theme.clamp_radius(bar_w, bar_w, fill_h)
            draw.rounded_rectangle([bar_x, fill_top, bar_x + bar_w, track_bottom], radius=r, fill=shade)

        if not any_data:
            draw.line(
                [(bar_x + 5, (track_top + track_bottom) // 2), (bar_x + bar_w - 5, (track_top + track_bottom) // 2)],
                fill=theme.OUTLINE, width=2,
            )

    def _draw(self, width: int, height: int, data: dict, today, max_display: int) -> Image.Image:
        img = Image.new("L", (width, height), theme.SURFACE)
        draw = ImageDraw.Draw(img)
        fonts = theme.load_fonts()

        habits = data.get("habits", [])[:max_display]
        log = data.get("log", {})
        user_stats = data.get("user_stats", {})
        margin = 20
        days_shown = 15

        if not habits:
            theme.draw_empty_state(
                draw, width, height, "Habits",
                "Enter your Habitica credentials in the module settings page.",
                fonts=fonts,
            )
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

        # Card behind the whole habit-list panel
        theme.draw_card(
            draw, (x_start - 10, margin - 10, col_streak + pct_col_w + 10, height - margin + 4),
            fill=theme.SURFACE, outline=theme.OUTLINE,
        )

        # Header
        draw.text((col_name, y), "Habits", fill=theme.ON_SURFACE, font=fonts["headline"])

        # Day labels above circles (today is bold/darker)
        for i in range(days_shown):
            day = today - timedelta(days=days_shown - 1 - i)
            day_label = str(day.day)
            cx = col_circles + i * 22 + 11
            lw = fonts["label"].getlength(day_label)
            is_today = (i == days_shown - 1)
            draw.text((cx - lw // 2, y + 4), day_label,
                      fill=theme.ON_SURFACE if is_today else theme.DISABLED, font=fonts["label"])

        # Trend bar header — legend for the layered 7d/30d/60d fill
        trend_label = "7·30·60d"
        tlw = fonts["label_sm"].getlength(trend_label)
        draw.text((col_bar + (bar_col_w - tlw) // 2, y + 5), trend_label, fill=theme.ON_SURFACE_VARIANT, font=fonts["label_sm"])
        # Streak header
        streak_label = "streak"
        slw = fonts["label_sm"].getlength(streak_label)
        draw.text((col_streak + (pct_col_w - slw) // 2, y + 5), streak_label, fill=theme.ON_SURFACE_VARIANT, font=fonts["label_sm"])

        y += 32

        # Separator
        theme.draw_divider(draw, x_start, y, col_streak + pct_col_w)
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
            fill=theme.SELECTED,
        )

        for habit_info in habits:
            habit_name = habit_info["name"]
            created_date = habit_info.get("created")

            # Name (truncate if needed)
            display_name = theme.truncate_to_width(habit_name, fonts["body_lg"], name_w - 10, ellipsis="..")
            draw.text((col_name, y + (row_h - 18) // 2), display_name, fill=theme.ON_SURFACE, font=fonts["body_lg"])

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
                                  fill=theme.ON_SURFACE)
                else:
                    draw.ellipse([cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
                                  outline=theme.OUTLINE, width=1)

            # Layered trend bar (7d/30d/60d) replaces the old numeric columns
            pct_7d = self._calc_percentage(log, habit_name, today, 7, created_date)
            pct_30d = self._calc_percentage(log, habit_name, today, 30, created_date)
            pct_60d = self._calc_percentage(log, habit_name, today, 60, created_date)
            self._draw_trend_bar(draw, col_bar, y, bar_col_w, row_h, pct_7d, pct_30d, pct_60d)

            # Current streak, with a flame icon once it's actually a streak
            streak = habit_info.get("streak", 0)
            streak_str = str(streak)
            streak_fill = theme.ON_SURFACE if streak >= 30 else theme.ON_SURFACE_VARIANT if streak >= 7 else theme.DISABLED
            sw = fonts["body"].getlength(streak_str)
            icon_w = 12 if streak > 0 else 0
            total_w = icon_w + (3 if streak > 0 else 0) + sw
            sx = col_streak + (pct_col_w - total_w) // 2
            if streak > 0:
                theme.draw_icon(draw, "flame", (sx, y + (row_h - icon_w) // 2), size=icon_w,
                                 tone=streak_fill, bg=theme.SURFACE)
                sx += icon_w + 3
            draw.text((sx, y + (row_h - 14) // 2), streak_str, fill=streak_fill, font=fonts["body"])

            y += row_h

        # Separator below habits
        theme.draw_divider(draw, x_start, y + 4, col_streak + pct_col_w)

        # ---- Right panel: Level and XP ----
        panel_x = left_w
        panel_center = panel_x + overall_panel_w // 2

        theme.draw_card(
            draw, (panel_x, margin - 10, width - margin + 10, height - margin + 4),
            fill=theme.SURFACE, outline=theme.OUTLINE,
        )

        if user_stats:
            lvl = user_stats.get("lvl", 0)
            exp = user_stats.get("exp", 0)
            to_next = user_stats.get("toNextLevel", 0)
            progress = exp / to_next if to_next > 0 else 0

            panel_y = margin + 10

            # Level
            lvl_str = f"Lv {lvl}"
            lw = fonts["headline"].getlength(lvl_str)
            draw.text((panel_center - lw // 2, panel_y), lvl_str, fill=theme.ON_SURFACE, font=fonts["headline"])
            panel_y += 40

            # XP label, pinned to the bottom of the card
            xp_str = f"{exp}/{to_next} XP"
            xw = fonts["label"].getlength(xp_str)
            xp_y = height - margin - 6
            draw.text((panel_center - xw // 2, xp_y), xp_str, fill=theme.DISABLED, font=fonts["label"])

            # XP grid fills the rest of the panel — each dot is a chunk of XP
            # toward the next level; filled dots swap from a plain circle to
            # a bolder rounded square, so progress reads by shape as well as
            # tone (in the spirit of M3's shape system).
            grid_top = panel_y
            grid_bottom = xp_y - 10
            self._draw_xp_grid(draw, panel_x + 12, grid_top, width - margin - 2 - (panel_x + 12), grid_bottom - grid_top, progress)

        return img

    def _draw_xp_grid(self, draw, x, y, w, h, fraction):
        """A grid of small shapes standing in for XP progress toward the next
        level. Unfilled = a plain light dot; filled = a bolder dark rounded
        square, so the boundary reads by shape, not just shade. Fills from
        the bottom up, like a rising gauge."""
        cell = 18
        cols = max(1, int(w // cell))
        rows = max(1, int(h // cell))
        total = cols * rows
        if total <= 0 or cols <= 0:
            return

        filled_count = round(total * max(0.0, min(fraction, 1.0)))
        grid_w = cols * cell
        offset_x = x + (w - grid_w) / 2

        idx = 0
        for r in range(rows - 1, -1, -1):
            for c in range(cols):
                dot_cx = offset_x + c * cell + cell / 2
                dot_cy = y + r * cell + cell / 2
                if idx < filled_count:
                    s = 6
                    theme.draw_card(draw, (dot_cx - s, dot_cy - s, dot_cx + s, dot_cy + s),
                                     radius=3, fill=theme.ON_SURFACE)
                else:
                    rdot = 3
                    draw.ellipse([dot_cx - rdot, dot_cy - rdot, dot_cx + rdot, dot_cy + rdot],
                                 fill=theme.SURFACE_CONTAINER_HIGH, outline=theme.OUTLINE)
                idx += 1
