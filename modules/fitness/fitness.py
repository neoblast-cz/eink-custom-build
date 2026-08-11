import json
import logging
import math
import time
import base64
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image, ImageDraw
from modules.base import BaseModule
from modules import theme

logger = logging.getLogger(__name__)

TOKEN_PATH = Path(__file__).parent.parent.parent / "fitbit_token.json"
FITBIT_API = "https://api.fitbit.com"


class FitnessModule(BaseModule):
    NAME = "fitness"
    DISPLAY_NAME = "Fitness"
    DESCRIPTION = "Fitbit cardio load, steps, calories, and sleep"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        token = self._refresh_if_needed(settings)
        if not token:
            return self._draw_not_authorized(width, height)

        summary = self._fetch_daily_summary(token)
        sleep = self._fetch_sleep(token)
        weekly_steps, today_steps = self._fetch_weekly_steps(token)

        steps = summary.get("steps", 0)
        steps_goal = summary.get("steps_goal") or int(settings.get("step_goal", 10000))
        weekly_steps_goal = steps_goal * 7
        distance = summary.get("distance", 0.0)
        api_distance_goal = summary.get("distance_goal")
        # Fitbit has been observed returning garbage/mis-scaled distance goals
        # (e.g. 8036720 instead of ~8) for some accounts — ignore anything implausible.
        if api_distance_goal and 0 < api_distance_goal <= 200:
            distance_goal = api_distance_goal
        else:
            distance_goal = float(settings.get("distance_goal_km", 8))
        calories = summary.get("calories", 0)
        calories_goal = summary.get("calories_goal") or int(settings.get("calorie_goal", 2500))

        sleep_minutes = sleep.get("minutes_asleep", 0)
        sleep_goal_minutes = sleep.get("goal_minutes") or int(
            float(settings.get("sleep_goal_hours", 8)) * 60
        )

        # How far into the week we are, as a fraction — e.g. 48h into a week
        # is 2/7, so a linear day-by-day pace should be at 2x the daily goal.
        now = datetime.now()
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        pace_pct = min((now - week_start).total_seconds() / (7 * 86400), 1.0)

        return self._draw(
            width, height, steps, steps_goal, distance, distance_goal,
            calories, calories_goal, sleep_minutes, sleep_goal_minutes,
            weekly_steps, weekly_steps_goal, today_steps, pace_pct,
        )

    def default_settings(self) -> dict:
        return {
            "step_goal": "10000",
            "distance_goal_km": "8",
            "calorie_goal": "2500",
            "sleep_goal_hours": "8",
        }

    # ── Token management ───────────────────────────────────────────

    def _load_token(self) -> dict | None:
        if not TOKEN_PATH.exists():
            return None
        try:
            return json.loads(TOKEN_PATH.read_text())
        except Exception:
            return None

    def _save_token(self, token_data: dict):
        TOKEN_PATH.write_text(json.dumps(token_data, indent=2))

    def _refresh_if_needed(self, settings: dict) -> str | None:
        token_data = self._load_token()
        if not token_data:
            return None

        access_token = token_data.get("access_token", "")
        expires_at = token_data.get("expires_at", 0)

        if time.time() < expires_at - 300:
            return access_token

        refresh_token = token_data.get("refresh_token", "")
        if not refresh_token:
            return None

        client_id = settings.get("_fitbit_client_id", "")
        client_secret = settings.get("_fitbit_client_secret", "")
        if not client_id or not client_secret:
            logger.warning("Fitbit credentials not injected, cannot refresh token")
            return access_token if time.time() < expires_at else None

        try:
            auth_header = base64.b64encode(
                f"{client_id}:{client_secret}".encode()
            ).decode()
            data = urllib.parse.urlencode({
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }).encode()
            req = urllib.request.Request(
                f"{FITBIT_API}/oauth2/token",
                data=data,
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                new_token = json.loads(resp.read())

            new_token["expires_at"] = time.time() + new_token.get("expires_in", 28800)
            self._save_token(new_token)
            logger.info("Fitbit token refreshed successfully")
            return new_token["access_token"]
        except Exception as e:
            logger.error(f"Fitbit token refresh failed: {e}")
            return access_token if time.time() < expires_at else None

    # ── API helpers ────────────────────────────────────────────────

    def _api_get(self, url: str, access_token: str) -> dict:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {access_token}",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def _fetch_daily_summary(self, token: str) -> dict:
        """Fetch today's activity summary: steps, distance, calories burned, and Fitbit's own goals."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            data = self._api_get(f"{FITBIT_API}/1/user/-/activities/date/{today}.json", token)
            summary = data.get("summary", {})
            goals = data.get("goals", {})
            total_distance = next(
                (d.get("distance", 0.0) for d in summary.get("distances", [])
                 if d.get("activity") == "total"),
                0.0,
            )
            return {
                "steps": summary.get("steps", 0),
                "distance": total_distance,
                "calories": summary.get("caloriesOut", 0),
                "steps_goal": goals.get("steps"),
                "distance_goal": goals.get("distance"),
                "calories_goal": goals.get("caloriesOut"),
            }
        except Exception as e:
            logger.error(f"Fitbit daily summary fetch failed: {e}")
            return {}

    def _fetch_sleep(self, token: str) -> dict:
        """Fetch last night's sleep total and the user's configured sleep goal."""
        minutes_asleep = 0
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            data = self._api_get(f"{FITBIT_API}/1.2/user/-/sleep/date/{today}.json", token)
            minutes_asleep = data.get("summary", {}).get("totalMinutesAsleep", 0)
        except Exception as e:
            logger.error(f"Fitbit sleep fetch failed: {e}")

        goal_minutes = None
        try:
            goal_data = self._api_get(f"{FITBIT_API}/1.2/user/-/sleep/goal.json", token)
            goal_minutes = goal_data.get("goal", {}).get("minDuration")
        except Exception as e:
            logger.error(f"Fitbit sleep goal fetch failed: {e}")

        return {"minutes_asleep": minutes_asleep, "goal_minutes": goal_minutes}

    def _fetch_weekly_steps(self, token: str) -> tuple:
        """Sum steps from the start of the current calendar week (Monday) through
        today. Returns (week_total, today_value)."""
        try:
            today_dt = datetime.now()
            start_dt = today_dt - timedelta(days=today_dt.weekday())  # Monday
            end = today_dt.strftime("%Y-%m-%d")
            start = start_dt.strftime("%Y-%m-%d")
            data = self._api_get(
                f"{FITBIT_API}/1/user/-/activities/steps/date/{start}/{end}.json",
                token,
            )
            entries = data.get("activities-steps", [])
            total = sum(int(e.get("value", 0)) for e in entries)
            today_val = 0
            if entries and entries[-1].get("dateTime") == end:
                today_val = int(entries[-1].get("value", 0))
            return total, today_val
        except Exception as e:
            logger.error(f"Fitbit weekly steps fetch failed: {e}")
            return 0, 0

    # ── Drawing ────────────────────────────────────────────────────

    def _draw_not_authorized(self, width: int, height: int) -> Image.Image:
        img = Image.new("L", (width, height), theme.SURFACE)
        draw = ImageDraw.Draw(img)
        theme.draw_empty_state(draw, width, height, "Fitness", "Authorize Fitbit in module settings")
        return img

    def _draw(self, width, height, steps, steps_goal, distance, distance_goal,
              calories, calories_goal, sleep_minutes, sleep_goal_minutes,
              weekly_steps, weekly_steps_goal, today_steps, pace_pct):
        img = Image.new("L", (width, height), theme.SURFACE)
        draw = ImageDraw.Draw(img)
        fonts = theme.load_fonts()
        margin = 14

        # Title bar
        draw.text((margin, 8), "Fitness", fill=theme.ON_SURFACE, font=fonts["headline"])
        now = datetime.now()
        date_str = now.strftime("%a, %b %d")
        dw = fonts["body"].getlength(date_str)
        draw.text((width - margin - dw, 13), date_str, fill=theme.ON_SURFACE_VARIANT, font=fonts["body"])
        title_y = 36
        theme.draw_divider(draw, margin, title_y, width - margin)

        content_top = title_y + 16
        content_h = height - content_top - margin

        left_w = int(width * 0.42)
        right_x = margin + left_w + 24
        right_w = width - right_x - margin

        self._draw_steps_ring(
            draw, margin, content_top, left_w, content_h,
            weekly_steps, weekly_steps_goal, today_steps, pace_pct, fonts,
        )

        row_gap = 10
        row_h = (content_h - row_gap * 3) // 4
        items = [
            ("Steps", steps, steps_goal, "int", "footsteps"),
            ("Distance", distance, distance_goal, "km", "pin"),
            ("Calories", calories, calories_goal, "int", "flame"),
            ("Sleep", sleep_minutes, sleep_goal_minutes, "time", "moon"),
        ]
        for i, (label, value, goal, fmt, glyph) in enumerate(items):
            ry = content_top + i * (row_h + row_gap)
            self._draw_goal_pill(draw, right_x, ry, right_w, row_h, label, value, goal, fonts, fmt, glyph)

        return img

    def _draw_steps_ring(self, draw, x, y, w, h, weekly_steps, goal, today_steps, pace_pct, fonts):
        cx = x + w // 2
        cy = y + h // 2
        radius = min(w, h) // 2 - 10
        thickness = max(34, radius // 2)

        pct = min(weekly_steps / goal, 1.0) if goal else 0.0
        start_angle = 90  # 6 o'clock; fill sweeps clockwise from here

        bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.arc(bbox, 0, 360, fill=theme.SURFACE_CONTAINER_HIGHEST, width=thickness)
        if pct > 0:
            # M3 circular progress indicator: a small angular gap separates the
            # active arc from the remaining track, with rounded stroke caps on
            # the active arc's ends. This ring is unusually thick, so a cap
            # radius of a full half-thickness reads as a bulging blob and can
            # swallow a small gap outright — use a softer partial rounding and
            # size the gap to stay visible past the cap's angular footprint.
            cap_r = thickness * 0.3
            end_angle = start_angle + pct * 360
            gap_deg = min(20, pct * 360 * 0.4) if pct < 0.98 else 0
            active_end_angle = end_angle - gap_deg

            draw.arc(bbox, start_angle, active_end_angle, fill=theme.ON_SURFACE, width=thickness)
            if gap_deg > 0:
                # Erase a sliver back to the plain background so the track
                # visibly resumes after the gap.
                draw.arc(bbox, active_end_angle, end_angle, fill=theme.SURFACE, width=thickness)
            self._draw_round_cap(draw, cx, cy, radius, cap_r * 2, start_angle, theme.ON_SURFACE)
            self._draw_round_cap(draw, cx, cy, radius, cap_r * 2, active_end_angle, theme.ON_SURFACE)

        # Pace marker: a dashed radial tick showing where a linear day-by-day
        # pace toward the weekly goal would put you right now.
        self._draw_pace_marker(draw, cx, cy, radius, thickness, start_angle, pace_pct)

        pct_str = f"{int(pct * 100)}%"
        pw = fonts["display"].getlength(pct_str)
        draw.text((cx - pw // 2, cy - 26), pct_str, fill=theme.ON_SURFACE, font=fonts["display"])

        sub = "Weekly Steps"
        sw = fonts["body"].getlength(sub)
        draw.text((cx - sw // 2, cy + 22), sub, fill=theme.ON_SURFACE_VARIANT, font=fonts["body"])

        detail = f"{int(weekly_steps):,} of {int(goal):,}"
        dw = fonts["label"].getlength(detail)
        draw.text((cx - dw // 2, cy + 42), detail, fill=theme.DISABLED, font=fonts["label"])

        # "+N today" badge, upper-right of the ring — mirrors the Google Health style
        if today_steps > 0:
            badge_str = f"+{int(today_steps):,}"
            theme.draw_chip(
                draw, (cx + int(radius * 0.62), cy - int(radius * 0.8)), badge_str, fonts["body"],
                align="center", valign="center", fill=30, text_fill=theme.SURFACE,
            )

            caption = "today"
            cw = fonts["label"].getlength(caption)
            draw.text((cx + int(radius * 0.62) - cw // 2, cy - int(radius * 0.8) + 14),
                       caption, fill=theme.DISABLED, font=fonts["label"])

    def _draw_round_cap(self, draw, cx, cy, radius, thickness, angle_deg, fill):
        """A filled circle sitting exactly on the arc's centerline, matching
        its thickness — Pillow's arc has flat (butt) ends, so this simulates
        M3's rounded stroke cap at a given angle."""
        angle_rad = math.radians(angle_deg)
        px = cx + radius * math.cos(angle_rad)
        py = cy + radius * math.sin(angle_rad)
        r = thickness / 2
        draw.ellipse([px - r, py - r, px + r, py + r], fill=fill)

    def _draw_pace_marker(self, draw, cx, cy, radius, thickness, start_angle, pace_pct):
        """Dashed radial tick at the angle you'd be at with linear daily pacing
        toward the weekly goal — e.g. 48h into the week at an 8k/day pace sits
        at the 16k mark."""
        angle_rad = math.radians(start_angle + pace_pct * 360)
        cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
        inner_r = radius - thickness / 2
        outer_r = radius + thickness / 2

        segments = 5
        for i in range(segments):
            if i % 2 == 1:
                continue  # skip every other segment for the dashed look
            r0 = inner_r + (outer_r - inner_r) * i / segments
            r1 = inner_r + (outer_r - inner_r) * (i + 1) / segments
            p0 = (cx + r0 * cos_a, cy + r0 * sin_a)
            p1 = (cx + r1 * cos_a, cy + r1 * sin_a)
            draw.line([p0, p1], fill=theme.SURFACE, width=5)
            draw.line([p0, p1], fill=theme.ON_SURFACE, width=2)

    def _draw_goal_pill(self, draw, x, y, w, h, label, value, goal, fonts, fmt="int", glyph=None):
        pad_x = 14
        pad_y = 10

        theme.draw_card(draw, (x, y, x + w, y + h), fill=theme.SURFACE_CONTAINER, outline=theme.OUTLINE)

        label_x = x + pad_x
        if glyph:
            icon_size = 16
            theme.draw_icon(draw, glyph, (label_x, y + pad_y), size=icon_size,
                             tone=theme.ON_SURFACE_VARIANT, bg=theme.SURFACE_CONTAINER)
            label_x += icon_size + theme.SPACE_XS
        draw.text((label_x, y + pad_y), label, fill=theme.ON_SURFACE_VARIANT, font=fonts["body"])

        val_str = self._format_goal_value(value, fmt)
        vw = fonts["title"].getlength(val_str)
        draw.text((x + w - pad_x - vw, y + pad_y - 4), val_str, fill=theme.ON_SURFACE, font=fonts["title"])

        bar_x = x + pad_x
        bar_w = w - pad_x * 2
        bar_h = 12
        bar_y = y + h - pad_y - bar_h - 14

        self._draw_linear_progress(draw, (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h),
                                    value / goal if goal else 0.0)

        goal_str = f"Goal {self._format_goal_value(goal, fmt)}"
        gw = fonts["label"].getlength(goal_str)
        draw.text((x + w - pad_x - gw, bar_y + bar_h + 4), goal_str, fill=theme.DISABLED, font=fonts["label"])

    def _draw_linear_progress(self, draw, box, pct):
        """M3 linear progress indicator: track, an active indicator with a
        gap before it, rounded ends, and a stop indicator dot marking the
        100% goal endpoint."""
        x0, y0, x1, y1 = box
        bar_w, bar_h = x1 - x0, y1 - y0
        pct = max(0.0, min(pct, 1.0))
        radius = theme.clamp_radius(6, bar_w, bar_h)

        theme.draw_card(draw, box, radius=radius, fill=theme.SURFACE_CONTAINER_HIGH)

        gap = 5 if pct < 0.98 else 0
        fill_w = bar_w * pct
        active_w = 0
        if fill_w > 0:
            active_w = max(fill_w - gap, 0)
            if active_w > 0:
                active_w = min(max(active_w, bar_h), bar_w)
                theme.draw_card(draw, (x0, y0, x0 + active_w, y1), radius=radius, fill=theme.ON_SURFACE)

        # Stop indicator: a small dot at the goal (100%) end of the track.
        dot_r = 3
        dot_cx = x1 - dot_r - 1
        dot_cy = (y0 + y1) / 2
        dot_fill = theme.SURFACE if dot_cx <= x0 + active_w else theme.ON_SURFACE
        draw.ellipse([dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r], fill=dot_fill)

    def _format_goal_value(self, value, fmt: str) -> str:
        if fmt == "time":
            hrs = int(value // 60)
            mins = int(value % 60)
            return f"{hrs}h {mins}m"
        if fmt == "km":
            return f"{value:.2f} km"
        return f"{int(value):,}"
