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
    DESCRIPTION = "Fitbit steps, distance, calories, and weight"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        token = self._refresh_if_needed(settings)
        if not token:
            return self._draw_not_authorized(width, height)

        steps = self._fetch_time_series("steps", token)
        distance = self._fetch_time_series("distance", token)
        calories = self._fetch_time_series("calories", token)
        weight = self._fetch_weight(token)
        step_goal = int(settings.get("step_goal", 10000))
        weight_unit = settings.get("weight_unit", "kg")

        return self._draw(width, height, steps, distance, calories, weight,
                          step_goal, weight_unit)

    def default_settings(self) -> dict:
        return {"weight_unit": "kg", "step_goal": "10000"}

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

    def _fetch_time_series(self, resource: str, token: str) -> list:
        """Fetch 15-day time series for steps, distance, or calories."""
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
            data = self._api_get(
                f"{FITBIT_API}/1/user/-/activities/{resource}/date/{start}/{end}.json",
                token,
            )
            key = f"activities-{resource}"
            entries = data.get(key, [])
            return [
                {"date": e.get("dateTime", ""), "value": float(e.get("value", 0))}
                for e in entries
            ]
        except Exception as e:
            logger.error(f"Fitbit {resource} fetch failed: {e}")
            return []

    def _fetch_weight(self, token: str) -> list:
        """Fetch weight log entries for the last 2 years (in 30-day chunks)."""
        try:
            all_entries = []
            end = datetime.now()
            empty_streak = 0
            for i in range(24):  # up to 24 months back
                period_end = end - timedelta(days=30 * i)
                period_start = period_end - timedelta(days=30)
                url = (
                    f"{FITBIT_API}/1/user/-/body/log/weight/date/"
                    f"{period_start.strftime('%Y-%m-%d')}/{period_end.strftime('%Y-%m-%d')}.json"
                )
                try:
                    data = self._api_get(url, token)
                    entries = data.get("weight", [])
                    if entries:
                        all_entries.extend(entries)
                        empty_streak = 0
                    else:
                        empty_streak += 1
                        if empty_streak >= 3:
                            break  # 3 consecutive empty months = no older data
                except Exception:
                    break
            # Deduplicate by date and sort
            seen = {}
            for e in all_entries:
                d = e.get("date", "")
                if d not in seen:
                    seen[d] = e.get("weight", 0)
            sorted_dates = sorted(seen.keys())
            return [{"date": d, "value": seen[d]} for d in sorted_dates]
        except Exception as e:
            logger.error(f"Fitbit weight fetch failed: {e}")
            return []

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

    def _draw(self, width, height, steps, distance, calories, weight,
              step_goal, weight_unit):
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()
        margin = 10

        # Title bar
        draw.text((margin, 6), "Fitness", fill=0, font=fonts["lg"])
        now = datetime.now()
        date_str = now.strftime("%a, %b %d")
        dw = fonts["sm"].getlength(date_str)
        draw.text((width - margin - dw, 10), date_str, fill=100, font=fonts["sm"])
        title_y = 32
        draw.line([(margin, title_y), (width - margin, title_y)], fill=180, width=1)

        # 2x2 grid
        mid_x = width // 2
        mid_y = title_y + (height - title_y) // 2
        top_y = title_y + 4

        # Grid lines
        draw.line([(mid_x, top_y), (mid_x, height - 4)], fill=180, width=1)
        draw.line([(margin, mid_y), (width - margin, mid_y)], fill=180, width=1)

        cell_w = mid_x - margin
        cell_h = mid_y - top_y

        # Top-left: Steps (bar chart with goal line)
        self._draw_bar_chart(
            draw, margin, top_y, cell_w, cell_h, steps,
            "Steps", fonts, goal=step_goal, fmt_int=True,
        )
        # Top-right: Distance (bar chart, km)
        self._draw_bar_chart(
            draw, mid_x + 1, top_y, cell_w, cell_h, distance,
            "Distance (km)", fonts, fmt_float=True,
        )
        # Bottom-left: Calories (bar chart)
        self._draw_bar_chart(
            draw, margin, mid_y + 1, cell_w, cell_h, calories,
            "Calories", fonts, fmt_int=True,
        )
        # Bottom-right: Weight (line chart)
        self._draw_weight_chart(
            draw, mid_x + 1, mid_y + 1, cell_w, cell_h,
            weight, weight_unit, fonts,
        )

        return img

    def _draw_bar_chart(self, draw, x, y, w, h, data, title, fonts,
                        goal=None, fmt_int=False, fmt_float=False):
        pad = 8

        # Title on the left, today's value on the right
        draw.text((x + pad, y + 4), title, fill=60, font=fonts["sm"])

        today_val = data[-1]["value"] if data else 0
        if fmt_int:
            val_str = f"{int(today_val):,}"
        elif fmt_float:
            val_str = f"{today_val:.2f}"
        else:
            val_str = f"{today_val}"
        vw = fonts["xl"].getlength(val_str)
        draw.text((x + w - pad - vw, y + 2), val_str, fill=0, font=fonts["xl"])

        if not data:
            cx = x + w // 2
            msg = "No data"
            mw = fonts["sm"].getlength(msg)
            draw.text((cx - mw // 2, y + h // 2), msg, fill=140, font=fonts["sm"])
            return

        # Chart area — reduced y-axis label space for 15 bars
        chart_left = x + pad + 24
        chart_right = x + w - pad
        chart_top = y + 38
        chart_bottom = y + h - 16
        chart_w = chart_right - chart_left
        chart_h = chart_bottom - chart_top

        if chart_h < 20 or chart_w < 40:
            return

        values = [d["value"] for d in data]
        max_val = max(values) if values else 1
        if goal and goal > max_val:
            max_val = goal * 1.1
        if max_val == 0:
            max_val = 1

        # Y-axis labels (compact)
        if fmt_float:
            draw.text((x + 2, chart_top - 2), f"{max_val:.1f}", fill=150, font=fonts["xs"])
        else:
            if max_val >= 1000:
                top_label = f"{int(max_val) // 1000}k"
            else:
                top_label = f"{int(max_val)}"
            draw.text((x + 2, chart_top - 2), top_label, fill=150, font=fonts["xs"])
        draw.text((x + 2, chart_bottom - 8), "0", fill=150, font=fonts["xs"])

        # Axes
        draw.line([(chart_left, chart_top), (chart_left, chart_bottom)], fill=180, width=1)
        draw.line([(chart_left, chart_bottom), (chart_right, chart_bottom)], fill=180, width=1)

        # Goal line (dashed)
        if goal and goal > 0:
            goal_y = chart_bottom - int((goal / max_val) * chart_h)
            goal_y = max(chart_top, min(chart_bottom, goal_y))
            dash_len = 6
            gap_len = 4
            lx = chart_left
            while lx < chart_right:
                end = min(lx + dash_len, chart_right)
                draw.line([(lx, goal_y), (end, goal_y)], fill=100, width=1)
                lx = end + gap_len
            gl = f"goal: {goal:,}"
            glw = fonts["xs"].getlength(gl)
            draw.text((chart_right - glw, goal_y - 11), gl, fill=100, font=fonts["xs"])

        # Bars — tight spacing for 15 bars
        n = len(values)
        gap = 2
        bar_w = max((chart_w - gap * (n + 1)) // n, 3)
        total_used = bar_w * n + gap * (n + 1)
        offset = chart_left + (chart_w - total_used) + gap  # right-align bars

        for i, val in enumerate(values):
            bx = offset + i * (bar_w + gap)
            bar_h_px = int((val / max_val) * chart_h) if max_val > 0 else 0
            bar_h_px = max(bar_h_px, 1)

            fill = 40 if i == n - 1 else 120
            draw.rectangle(
                [bx, chart_bottom - bar_h_px, bx + bar_w, chart_bottom],
                fill=fill,
            )

        # Day labels — only show every few days to avoid overlap
        label_every = max(1, n // 5)  # ~5 labels across 15 bars
        for i in range(n):
            if i % label_every != 0 and i != n - 1:
                continue
            date_str = data[i].get("date", "")
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    day_label = dt.strftime("%d")
                except ValueError:
                    day_label = ""
                bx = offset + i * (bar_w + gap)
                dlw = fonts["xs"].getlength(day_label)
                draw.text(
                    (bx + bar_w // 2 - dlw // 2, chart_bottom + 2),
                    day_label, fill=140, font=fonts["xs"],
                )

    def _convert_weight(self, value, unit):
        """Convert weight from metric (kg, API default) to display unit."""
        if unit == "lbs":
            return value * 2.20462
        return value

    def _draw_weight_chart(self, draw, x, y, w, h, data, unit, fonts):
        pad = 8

        # Title left, value right
        draw.text((x + pad, y + 4), "Weight", fill=60, font=fonts["sm"])

        if not data:
            cx = x + w // 2
            msg = "No weight data"
            mw = fonts["sm"].getlength(msg)
            draw.text((cx - mw // 2, y + h // 2), msg, fill=140, font=fonts["sm"])
            return

        latest = self._convert_weight(data[-1]["value"], unit)
        unit_str = "lbs" if unit == "lbs" else "kg"
        val_str = f"{latest:.1f} {unit_str}"
        vw = fonts["xl"].getlength(val_str)
        draw.text((x + w - pad - vw, y + 2), val_str, fill=0, font=fonts["xl"])

        if len(data) < 2:
            return

        # Chart area
        chart_left = x + pad + 24
        chart_right = x + w - pad
        chart_top = y + 38
        chart_bottom = y + h - 16
        chart_w = chart_right - chart_left
        chart_h = chart_bottom - chart_top

        if chart_h < 20 or chart_w < 40:
            return

        weights = [self._convert_weight(d["value"], unit) for d in data]

        min_w = min(weights)
        max_w = max(weights)
        range_w = max_w - min_w if max_w != min_w else 1.0
        min_w -= range_w * 0.15
        max_w += range_w * 0.15
        range_w = max_w - min_w

        # Y-axis labels
        draw.text((x + 2, chart_top - 2), f"{max_w:.0f}", fill=150, font=fonts["xs"])
        draw.text((x + 2, chart_bottom - 8), f"{min_w:.0f}", fill=150, font=fonts["xs"])

        # Axes
        draw.line([(chart_left, chart_top), (chart_left, chart_bottom)], fill=180, width=1)
        draw.line([(chart_left, chart_bottom), (chart_right, chart_bottom)], fill=180, width=1)

        # Plot line
        n = len(weights)
        coords = []
        for i, wt in enumerate(weights):
            px = chart_left + (i * chart_w // (n - 1) if n > 1 else chart_w // 2)
            py = chart_bottom - int((wt - min_w) / range_w * chart_h)
            coords.append((px, py))

        for i in range(len(coords) - 1):
            draw.line([coords[i], coords[i + 1]], fill=60, width=2)

        # Dot on latest point
        last = coords[-1]
        draw.ellipse([last[0] - 4, last[1] - 4, last[0] + 4, last[1] + 4], fill=0)

        # X-axis hint
        hint = f"Last {len(data)} entries"
        hw = fonts["xs"].getlength(hint)
        draw.text(((chart_left + chart_right) // 2 - hw // 2, chart_bottom + 3),
                  hint, fill=160, font=fonts["xs"])
