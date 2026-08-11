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
        weekly_azm = self._fetch_weekly_azm(token)

        steps = summary.get("steps", 0)
        steps_goal = summary.get("steps_goal") or int(settings.get("step_goal", 10000))
        calories = summary.get("calories", 0)
        calories_goal = summary.get("calories_goal") or int(settings.get("calorie_goal", 2500))

        sleep_minutes = sleep.get("minutes_asleep", 0)
        sleep_goal_minutes = sleep.get("goal_minutes") or int(
            float(settings.get("sleep_goal_hours", 8)) * 60
        )

        cardio_goal = int(settings.get("weekly_cardio_goal", 150))

        return self._draw(
            width, height, steps, steps_goal, calories, calories_goal,
            sleep_minutes, sleep_goal_minutes, weekly_azm, cardio_goal,
        )

    def default_settings(self) -> dict:
        return {
            "step_goal": "10000",
            "calorie_goal": "2500",
            "sleep_goal_hours": "8",
            "weekly_cardio_goal": "150",
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
        """Fetch today's activity summary: steps, calories burned, and Fitbit's own goals."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            data = self._api_get(f"{FITBIT_API}/1/user/-/activities/date/{today}.json", token)
            summary = data.get("summary", {})
            goals = data.get("goals", {})
            return {
                "steps": summary.get("steps", 0),
                "calories": summary.get("caloriesOut", 0),
                "steps_goal": goals.get("steps"),
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

    def _fetch_weekly_azm(self, token: str) -> int:
        """Sum Active Zone Minutes over the trailing 7 days — Fitbit's cardio-load equivalent."""
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
            data = self._api_get(
                f"{FITBIT_API}/1/user/-/activities/active-zone-minutes/date/{start}/{end}.json",
                token,
            )
            entries = data.get("activities-active-zone-minutes", [])
            return sum(e.get("value", {}).get("activeZoneMinutes", 0) for e in entries)
        except Exception as e:
            logger.error(f"Fitbit active zone minutes fetch failed: {e}")
            return 0

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

    def _draw(self, width, height, steps, steps_goal, calories, calories_goal,
              sleep_minutes, sleep_goal_minutes, weekly_azm, cardio_goal):
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

        self._draw_cardio_ring(
            draw, margin, content_top, left_w, content_h,
            weekly_azm, cardio_goal, fonts,
        )

        row_gap = 14
        row_h = (content_h - row_gap * 2) // 3
        items = [
            ("Steps", steps, steps_goal, False),
            ("Calories", calories, calories_goal, False),
            ("Sleep", sleep_minutes, sleep_goal_minutes, True),
        ]
        for i, (label, value, goal, is_time) in enumerate(items):
            ry = content_top + i * (row_h + row_gap)
            self._draw_goal_pill(draw, right_x, ry, right_w, row_h, label, value, goal, fonts, is_time)

        return img

    def _draw_cardio_ring(self, draw, x, y, w, h, weekly_azm, goal, fonts):
        cx = x + w // 2
        cy = y + h // 2
        radius = min(w, h) // 2 - 10
        thickness = max(14, radius // 6)

        pct = min(weekly_azm / goal, 1.0) if goal else 0.0

        bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.arc(bbox, 0, 360, fill=210, width=thickness)
        if pct > 0:
            end_angle = -90 + pct * 360
            draw.arc(bbox, -90, end_angle, fill=30, width=thickness)

        pct_str = f"{int(pct * 100)}%"
        pw = fonts["xxl"].getlength(pct_str)
        draw.text((cx - pw // 2, cy - 26), pct_str, fill=0, font=fonts["xxl"])

        sub = "Weekly Cardio"
        sw = fonts["sm"].getlength(sub)
        draw.text((cx - sw // 2, cy + 22), sub, fill=90, font=fonts["sm"])

        detail = f"{int(weekly_azm)} of {int(goal)} min"
        dw = fonts["xs"].getlength(detail)
        draw.text((cx - dw // 2, cy + 42), detail, fill=140, font=fonts["xs"])

    def _draw_goal_pill(self, draw, x, y, w, h, label, value, goal, fonts, is_time=False):
        pad_x = 14
        pad_y = 10

        draw.rounded_rectangle([x, y, x + w, y + h], radius=10, outline=180, width=1)

        draw.text((x + pad_x, y + pad_y), label, fill=70, font=fonts["sm"])

        if is_time:
            hrs = int(value // 60)
            mins = int(value % 60)
            val_str = f"{hrs}h {mins}m"
        else:
            val_str = f"{int(value):,}"
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

        if is_time:
            goal_str = f"Goal {int(goal // 60)}h {int(goal % 60)}m"
        else:
            goal_str = f"Goal {int(goal):,}"
        gw = fonts["xs"].getlength(goal_str)
        draw.text((x + w - pad_x - gw, bar_y + bar_h + 4), goal_str, fill=130, font=fonts["xs"])
