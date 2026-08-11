import json
import logging
import time
import base64
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

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

        return self._draw(
            width, height, steps, steps_goal, distance, distance_goal,
            calories, calories_goal, sleep_minutes, sleep_goal_minutes,
            weekly_steps, weekly_steps_goal, today_steps,
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

    # ── Font loading ───────────────────────────────────────────────

    def _load_fonts(self):
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]
        fonts = {}
        for size_name, size in [("xxl", 42), ("xl", 32), ("lg", 24), ("md", 16),
                                 ("sm", 13), ("xs", 10)]:
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

    # ── Drawing ────────────────────────────────────────────────────

    def _draw_not_authorized(self, width: int, height: int) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()
        cx, cy = width // 2, height // 2
        msg = "Fitness"
        mw = fonts["lg"].getlength(msg)
        draw.text((cx - mw // 2, cy - 30), msg, fill=0, font=fonts["lg"])
        hint = "Authorize Fitbit in module settings"
        hw = fonts["sm"].getlength(hint)
        draw.text((cx - hw // 2, cy + 10), hint, fill=120, font=fonts["sm"])
        return img

    def _draw(self, width, height, steps, steps_goal, distance, distance_goal,
              calories, calories_goal, sleep_minutes, sleep_goal_minutes,
              weekly_steps, weekly_steps_goal, today_steps):
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()
        margin = 14

        # Title bar
        draw.text((margin, 8), "Fitness", fill=0, font=fonts["lg"])
        now = datetime.now()
        date_str = now.strftime("%a, %b %d")
        dw = fonts["sm"].getlength(date_str)
        draw.text((width - margin - dw, 13), date_str, fill=100, font=fonts["sm"])
        title_y = 36
        draw.line([(margin, title_y), (width - margin, title_y)], fill=180, width=1)

        content_top = title_y + 16
        content_h = height - content_top - margin

        left_w = int(width * 0.42)
        right_x = margin + left_w + 24
        right_w = width - right_x - margin

        self._draw_steps_ring(
            draw, margin, content_top, left_w, content_h,
            weekly_steps, weekly_steps_goal, today_steps, fonts,
        )

        row_gap = 10
        row_h = (content_h - row_gap * 3) // 4
        items = [
            ("Steps", steps, steps_goal, "int"),
            ("Distance", distance, distance_goal, "km"),
            ("Calories", calories, calories_goal, "int"),
            ("Sleep", sleep_minutes, sleep_goal_minutes, "time"),
        ]
        for i, (label, value, goal, fmt) in enumerate(items):
            ry = content_top + i * (row_h + row_gap)
            self._draw_goal_pill(draw, right_x, ry, right_w, row_h, label, value, goal, fonts, fmt)

        return img

    def _draw_steps_ring(self, draw, x, y, w, h, weekly_steps, goal, today_steps, fonts):
        cx = x + w // 2
        cy = y + h // 2
        radius = min(w, h) // 2 - 10
        thickness = max(34, radius // 2)

        pct = min(weekly_steps / goal, 1.0) if goal else 0.0

        bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.arc(bbox, 0, 360, fill=210, width=thickness)
        if pct > 0:
            # Fill starts at 6 o'clock (PIL angle 90) and sweeps clockwise.
            start_angle = 90
            end_angle = start_angle + pct * 360
            draw.arc(bbox, start_angle, end_angle, fill=30, width=thickness)

        pct_str = f"{int(pct * 100)}%"
        pw = fonts["xxl"].getlength(pct_str)
        draw.text((cx - pw // 2, cy - 26), pct_str, fill=0, font=fonts["xxl"])

        sub = "Weekly Steps"
        sw = fonts["sm"].getlength(sub)
        draw.text((cx - sw // 2, cy + 22), sub, fill=90, font=fonts["sm"])

        detail = f"{int(weekly_steps):,} of {int(goal):,}"
        dw = fonts["xs"].getlength(detail)
        draw.text((cx - dw // 2, cy + 42), detail, fill=140, font=fonts["xs"])

        # "+N today" badge, upper-right of the ring — mirrors the Google Health style
        if today_steps > 0:
            badge_str = f"+{int(today_steps):,}"
            bw = fonts["sm"].getlength(badge_str)
            bcx = cx + int(radius * 0.62)
            bcy = cy - int(radius * 0.8)
            pad = 6
            box = [bcx - bw // 2 - pad, bcy - 10, bcx + bw // 2 + pad, bcy + 10]
            draw.rounded_rectangle(box, radius=10, fill=30)
            draw.text((bcx - bw // 2, bcy - 7), badge_str, fill=255, font=fonts["sm"])

    def _draw_goal_pill(self, draw, x, y, w, h, label, value, goal, fonts, fmt="int"):
        pad_x = 14
        pad_y = 10

        draw.rounded_rectangle([x, y, x + w, y + h], radius=10, outline=180, width=1)

        draw.text((x + pad_x, y + pad_y), label, fill=70, font=fonts["sm"])

        val_str = self._format_goal_value(value, fmt)
        vw = fonts["lg"].getlength(val_str)
        draw.text((x + w - pad_x - vw, y + pad_y - 4), val_str, fill=0, font=fonts["lg"])

        bar_x = x + pad_x
        bar_w = w - pad_x * 2
        bar_h = 12
        bar_y = y + h - pad_y - bar_h - 14

        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=6, fill=225)
        pct = min(value / goal, 1.0) if goal else 0.0
        fill_w = int(bar_w * pct)
        if fill_w > 0:
            fill_w = max(fill_w, bar_h)
            draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=6, fill=40)

        goal_str = f"Goal {self._format_goal_value(goal, fmt)}"
        gw = fonts["xs"].getlength(goal_str)
        draw.text((x + w - pad_x - gw, bar_y + bar_h + 4), goal_str, fill=130, font=fonts["xs"])

    def _format_goal_value(self, value, fmt: str) -> str:
        if fmt == "time":
            hrs = int(value // 60)
            mins = int(value % 60)
            return f"{hrs}h {mins}m"
        if fmt == "km":
            return f"{value:.2f} km"
        return f"{int(value):,}"
